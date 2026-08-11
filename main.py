import os
import json
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.stories import (
    GetPeerStoriesRequest,
    GetPinnedStoriesRequest
)


# =========================================================
# إعدادات Telegram
# =========================================================

API_ID = int(os.getenv("API_ID", "32492582"))
API_HASH = os.getenv("API_HASH")

SESSION = os.getenv("SESSION")

if not API_HASH:
    raise RuntimeError("❌ API_HASH غير موجود في Railway Variables")

if not SESSION:
    raise RuntimeError("❌ SESSION غير موجود في Railway Variables")

# تنظيف الـ Session من المسافات والأسطر الزائدة
SESSION = "".join(SESSION.split())

# إزالة علامات الاقتباس إذا تم نسخها بالخطأ
if len(SESSION) >= 2:
    if (
        (SESSION[0] == '"' and SESSION[-1] == '"')
        or
        (SESSION[0] == "'" and SESSION[-1] == "'")
    ):
        SESSION = SESSION[1:-1]

if not SESSION:
    raise RuntimeError("❌ SESSION فارغة")


client = TelegramClient(
    StringSession(SESSION),
    API_ID,
    API_HASH
)


# =========================================================
# الملفات والذاكرة
# =========================================================

BANNED_FILE = "banned.json"

auto_save_users = set()
media_cache = {}
message_info_cache = {}
visited_users_cache = set()
pending_stories = {}

DOWNLOAD_DIR = "downloads"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# قفل لمنع تعارض عمليات حفظ banned.json
banned_save_lock = asyncio.Lock()


# =========================================================
# المحظورين
# =========================================================

def load_banned_users():
    if not os.path.exists(BANNED_FILE):
        return set()

    try:
        with open(BANNED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))

    except Exception as e:
        print(f"خطأ في قراءة ملف المحظورين: {e}")
        return set()


def save_banned_users():
    try:
        # كتابة مؤقتة ثم استبدال الملف
        temp_file = BANNED_FILE + ".tmp"

        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(
                list(banned_users),
                f,
                ensure_ascii=False
            )

        os.replace(temp_file, BANNED_FILE)

    except Exception as e:
        print(f"خطأ في حفظ ملف المحظورين: {e}")


async def async_save_banned_users():
    """
    حفظ banned.json بالخلفية حتى لا يتأخر أمر /ban أو /unban.
    """
    async with banned_save_lock:
        try:
            await asyncio.to_thread(
                save_banned_users
            )
        except Exception as e:
            print(
                f"خطأ في الحفظ بالخلفية: {e}"
            )


banned_users = load_banned_users()


# =========================================================
# تنظيف الكاش
# =========================================================

def clean_caches():

    if len(media_cache) > 100:

        keys = list(media_cache.keys())

        for key in keys[:50]:
            del media_cache[key]

    if len(message_info_cache) > 100:

        keys = list(message_info_cache.keys())

        for key in keys[:50]:
            del message_info_cache[key]


# =========================================================
# /help
# =========================================================

@client.on(
    events.NewMessage(
        outgoing=True,
        pattern=r"^/help$"
    )
)
async def help_command_handler(event):

    if not event.is_private:
        return

    try:
        await event.delete()
    except Exception:
        pass

    help_text = (
        "🤖 **قائمة أوامر اليوزر بوت:**\n\n"

        "🔍 `/done [المعرف/الآيدي]`\n"
        "لفحص القصص النشطة والهايلايت.\n\n"

        "🚫 `/ban`\n"
        "بالرد على رسالة شخص لحظره.\n\n"

        "✅ `/unban`\n"
        "بالرد على شخص لإلغاء الحظر.\n\n"

        "📋 `/banned`\n"
        "عرض قائمة المحظورين.\n\n"

        "📥 `/save`\n"
        "بالرد على شخص لتفعيل/إلغاء الحفظ التلقائي.\n\n"

        "7️⃣ بالرد على ميديا\n"
        "تحميلها داخل المحادثة.\n\n"

        "8️⃣ بالرد على ميديا\n"
        "إرسالها إلى الرسائل المحفوظة.\n"
    )

    await client.send_message(
        event.chat_id,
        help_text
    )


# =========================================================
# /banned
# =========================================================

@client.on(
    events.NewMessage(
        outgoing=True,
        pattern=r"^/banned$"
    )
)
async def list_banned_handler(event):

    if not event.is_private:
        return

    try:
        await event.delete()
    except Exception:
        pass

    if not banned_users:

        await client.send_message(
            event.chat_id,
            "📭 قائمة المحظورين فارغة حالياً."
        )

        return

    status_msg = await event.respond(
        "🔍 جاري جلب معلومات المحظورين..."
    )

    banned_details = []

    for uid in banned_users:

        username_str = "لا يوجد معرف"

        try:

            entity = await client.get_entity(uid)

            if getattr(entity, "username", None):

                username_str = f"@{entity.username}"

            elif getattr(entity, "first_name", None):

                username_str = entity.first_name

        except Exception:
            pass

        banned_details.append(
            f"• الآيدي: `{uid}` | المعرف: {username_str}"
        )

    banned_list_str = "\n".join(banned_details)

    await status_msg.edit(
        f"🚫 **قائمة المحظورين حالياً:**\n\n"
        f"{banned_list_str}"
    )


# =========================================================
# /ban — سريع
# =========================================================

@client.on(
    events.NewMessage(
        outgoing=True,
        pattern=r"^/ban$"
    )
)
async def ban_user_handler(event):

    if not event.is_private:
        return

    # نحصل على الرسالة أولاً
    reply_msg = await event.get_reply_message()

    # حذف الأمر
    try:
        await event.delete()
    except Exception:
        pass

    if not reply_msg:
        return

    sender_id = reply_msg.sender_id

    if not sender_id:
        return

    # إضافة فورية للذاكرة
    banned_users.add(sender_id)

    # الحفظ بالخلفية
    asyncio.create_task(
        async_save_banned_users()
    )


# =========================================================
# /unban — سريع
# =========================================================

@client.on(
    events.NewMessage(
        outgoing=True,
        pattern=r"^/unban$"
    )
)
async def unban_user_handler(event):

    if not event.is_private:
        return

    # الحصول على الرسالة قبل حذف الأمر
    reply_msg = await event.get_reply_message()

    try:
        await event.delete()
    except Exception:
        pass

    if not reply_msg:
        return

    sender_id = reply_msg.sender_id

    if not sender_id:
        return

    # إزالة فورية من الذاكرة
    banned_users.discard(sender_id)

    # الحفظ بالخلفية
    asyncio.create_task(
        async_save_banned_users()
    )


# =========================================================
# /save
# =========================================================

@client.on(
    events.NewMessage(
        outgoing=True,
        pattern=r"^/save$"
    )
)
async def auto_save_handler(event):

    if not event.is_private:
        return

    try:
        await event.delete()
    except Exception:
        pass

    reply_msg = await event.get_reply_message()

    if not reply_msg:
        return

    sender_id = reply_msg.sender_id

    if sender_id in auto_save_users:

        auto_save_users.remove(sender_id)

        await client.send_message(
            event.chat_id,
            f"🔴 تم إلغاء الحفظ التلقائي للمستخدم `{sender_id}`."
        )

    else:

        auto_save_users.add(sender_id)

        await client.send_message(
            event.chat_id,
            f"🟢 تم تفعيل الحفظ التلقائي للمستخدم `{sender_id}`."
        )


# =========================================================
# جلب القصص النشطة
# =========================================================

async def get_active_stories(user):

    stories = []

    try:

        result = await client(
            GetPeerStoriesRequest(
                peer=user
            )
        )

        if result and hasattr(result, "stories"):

            peer_stories = result.stories

            if peer_stories and hasattr(
                peer_stories,
                "stories"
            ):

                stories.extend(
                    peer_stories.stories
                )

    except Exception as e:

        print(
            f"خطأ في جلب القصص النشطة: {e}"
        )

    return stories


# =========================================================
# جلب الهايلايت
# =========================================================

async def get_highlight_stories(user):

    stories = []

    try:

        result = await client(
            GetPinnedStoriesRequest(
                peer=user,
                offset_id=0,
                limit=100
            )
        )

        if result and hasattr(
            result,
            "stories"
        ):

            for story in result.stories:

                if story not in stories:
                    stories.append(story)

    except Exception as e:

        print(
            f"خطأ في جلب الهايلايت: {e}"
        )

    return stories


# =========================================================
# /done
# =========================================================

@client.on(
    events.NewMessage(
        outgoing=True,
        pattern=r"^/done\s+(.+)"
    )
)
async def check_stories_handler(event):

    target = event.pattern_match.group(1).strip()

    try:
        await event.delete()
    except Exception:
        pass

    status_msg = await event.respond(
        f"🔍 جاري فحص القصص للحساب:\n"
        f"`{target}` ..."
    )

    try:

        # جلب الحساب
        if target.isdigit():

            user = await client.get_entity(
                int(target)
            )

        else:

            user = await client.get_entity(
                target
            )

        # القصص النشطة
        active_stories = await get_active_stories(
            user
        )

        # الهايلايت
        highlighted_stories = await get_highlight_stories(
            user
        )

        # إزالة التكرار
        active_ids = {
            getattr(s, "id", None)
            for s in active_stories
        }

        highlighted_stories = [
            s
            for s in highlighted_stories
            if getattr(s, "id", None)
            not in active_ids
        ]

        total_active = len(active_stories)

        total_highlighted = len(
            highlighted_stories
        )

        total_all = (
            total_active +
            total_highlighted
        )

        # لا توجد قصص
        if total_all == 0:

            await status_msg.edit(
                f"❌ لا توجد قصص نشطة أو "
                f"هايلايت ظاهرة للحساب "
                f"`{target}`."
            )

            return

        # حفظ العملية
        pending_stories[event.chat_id] = {

            "step": "select_type",

            "active": active_stories,

            "highlighted": highlighted_stories,

            "target": target,

            "status_msg_id": status_msg.id
        }

        # النوعين موجودين
        if total_active > 0 and total_highlighted > 0:

            text_report = (
                f"✅ **تم فحص الحساب بنجاح**\n\n"

                f"👤 الحساب: `{target}`\n\n"

                f"🟢 القصص النشطة: "
                f"**{total_active}**\n"

                f"⭐ الهايلايت: "
                f"**{total_highlighted}**\n\n"

                f"📊 المجموع: "
                f"**{total_all}**\n\n"

                f"━━━━━━━━━━━━━━\n"

                f"📥 ماذا تريد تحميله؟\n\n"

                f"1️⃣ **القصص النشطة فقط**\n"

                f"2️⃣ **الهايلايت فقط**\n"

                f"3️⃣ **الاثنين معاً**\n\n"

                f"📌 قم بالرد على هذه الرسالة بالرقم."
            )

        # النشطة فقط
        elif total_active > 0:

            text_report = (
                f"✅ **تم فحص الحساب بنجاح**\n\n"

                f"👤 الحساب: `{target}`\n\n"

                f"🟢 القصص النشطة: "
                f"**{total_active}**\n\n"

                f"⭐ الهايلايت: **0**\n\n"

                f"📥 يوجد نوع واحد فقط:\n\n"

                f"1️⃣ **تحميل القصص النشطة**\n\n"

                f"📌 قم بالرد بـ `1`."
            )

        # الهايلايت فقط
        else:

            text_report = (
                f"✅ **تم فحص الحساب بنجاح**\n\n"

                f"👤 الحساب: `{target}`\n\n"

                f"🟢 القصص النشطة: **0**\n\n"

                f"⭐ الهايلايت: "
                f"**{total_highlighted}**\n\n"

                f"📥 يوجد نوع واحد فقط:\n\n"

                f"1️⃣ **تحميل الهايلايت**\n\n"

                f"📌 قم بالرد بـ `1`."
            )

        await status_msg.edit(
            text_report
        )

    except Exception as e:

        await status_msg.edit(
            f"⚠️ حدث خطأ أثناء فحص الحساب:\n\n"
            f"`{type(e).__name__}: {e}`"
        )


# =========================================================
# الردود الخاصة بالقصص
# =========================================================

@client.on(
    events.NewMessage(outgoing=True)
)
async def handle_user_replies(event):

    if not event.is_private and not event.is_group:
        return

    reply_msg = await event.get_reply_message()

    if not reply_msg:
        return

    chat_id = event.chat_id

    if chat_id not in pending_stories:
        return

    data = pending_stories[chat_id]

    text = event.raw_text.strip().lower()

    current_step = data.get("step")


    # =====================================================
    # اختيار نوع القصص
    # =====================================================

    if current_step == "select_type":

        # يجب أن يكون الرد على رسالة نتيجة الفحص
        if reply_msg.id != data.get("status_msg_id"):
            return

        active = data["active"]

        highlighted = data["highlighted"]

        selected_types = []


        # النوعان موجودان
        if active and highlighted:

            if text in [
                "1",
                "نشطة",
                "القصص النشطة"
            ]:

                selected_types = [
                    (
                        "🟢 [قصة نشطة]",
                        active
                    )
                ]

            elif text in [
                "2",
                "هايلايت",
                "بارزة",
                "أرشيف",
                "القصص البارزة",
                "الأرشيف"
            ]:

                selected_types = [
                    (
                        "⭐ [هايلايت]",
                        highlighted
                    )
                ]

            elif text in [
                "3",
                "الكل",
                "الاثنين",
                "الاثنين معا",
                "الاثنين معاً"
            ]:

                selected_types = [
                    (
                        "🟢 [قصة نشطة]",
                        active
                    ),
                    (
                        "⭐ [هايلايت]",
                        highlighted
                    )
                ]

            else:
                return


        # النشطة فقط
        elif active:

            if text not in [
                "1",
                "نشطة",
                "القصص النشطة"
            ]:
                return

            selected_types = [
                (
                    "🟢 [قصة نشطة]",
                    active
                )
            ]


        # الهايلايت فقط
        elif highlighted:

            if text not in [
                "1",
                "هايلايت",
                "بارزة",
                "أرشيف",
                "القصص البارزة",
                "الأرشيف"
            ]:
                return

            selected_types = [
                (
                    "⭐ [هايلايت]",
                    highlighted
                )
            ]


        if not selected_types:
            return


        data["selected_types"] = selected_types

        data["step"] = "select_destination"


        try:
            await event.delete()
        except Exception:
            pass


        destination_msg = await client.send_message(
            chat_id,

            "📂 **تم اختيار القصص بنجاح!**\n\n"

            "أين تريد إرسالها؟\n\n"

            "1️⃣ **المحفوظات**\n"
            "إرسالها إلى الرسائل المحفوظة.\n\n"

            "2️⃣ **هنا**\n"
            "إرسالها في هذه المحادثة.\n\n"

            "3️⃣ **إلغاء**\n\n"

            "📌 قم بالرد على هذه الرسالة بالرقم."
        )


        data["destination_msg_id"] = (
            destination_msg.id
        )

        return


    # =====================================================
    # اختيار مكان التنزيل
    # =====================================================

    if current_step == "select_destination":

        if reply_msg.id != data.get(
            "destination_msg_id"
        ):
            return


        if text in [
            "1",
            "محفوظة",
            "المحفوظة",
            "مفصول"
        ]:

            destination = "me"

            dest_name = "الرسائل المحفوظة"


        elif text in [
            "2",
            "هنا"
        ]:

            destination = event.chat_id

            dest_name = "هذه المحادثة"


        elif text in [
            "3",
            "لا",
            "الغاء",
            "إلغاء",
            "no"
        ]:

            del pending_stories[chat_id]

            try:
                await event.delete()
            except Exception:
                pass

            await client.send_message(
                chat_id,
                "❌ تم إلغاء عملية تحميل القصص."
            )

            return

        else:
            return


        try:
            await event.delete()
        except Exception:
            pass


        selected_types = data[
            "selected_types"
        ]

        target_name = data[
            "target"
        ]


        total_count = sum(
            len(stories)
            for _, stories in selected_types
        )

        current_index = 0

        success_count = 0


        counter_msg = await client.send_message(
            chat_id,

            f"📥 **جاري بدء التحميل...**\n\n"
            f"⏳ 0 / {total_count}\n"
            f"📂 الوجهة: {dest_name}"
        )


        # تحميل القصص
        for label, stories in selected_types:

            for story in stories:

                current_index += 1

                try:

                    if not getattr(
                        story,
                        "media",
                        None
                    ):
                        continue


                    last_pct = -1


                    async def progress_callback(
                        current,
                        total
                    ):

                        nonlocal last_pct

                        if total <= 0:
                            return

                        pct = int(
                            current / total * 100
                        )

                        if (
                            pct >= last_pct + 25
                            or pct == 100
                        ):

                            last_pct = pct

                            try:

                                await counter_msg.edit(
                                    f"📥 **جاري التحميل...**\n\n"

                                    f"📌 القصة: "
                                    f"{current_index} / {total_count}\n"
                f"📊 التقدم: "
                f"`{pct}%`\n"
                f"📂 الوجهة: "
                f"{dest_name}"
            )

        except Exception:
            pass


    # =====================================================
    # إنهاء التحميل
    # =====================================================

    try:
        await counter_msg.delete()
    except Exception:
        pass


    await client.send_message(
        chat_id,

        f"✅ **اكتمل التحميل!**\n\n"
        f"📥 تم تحميل: "
        f"**{success_count} / {total_count}**\n"
        f"📂 الوجهة: "
        f"**{dest_name}**"
    )


    pending_stories.pop(
        chat_id,
        None
    )


# =========================================================
# الرسائل الواردة
# =========================================================

@client.on(
    events.NewMessage(
        incoming=True
    )
)
async def handle_incoming_messages(event):

    if not event.is_private:
        return

    sender_id = event.sender_id

    # المحظور
    if sender_id in banned_users:

        try:
            await event.delete()
        except Exception:
            pass

        return

    sender = await event.get_sender()

    username = (
        f"@{sender.username}"
        if sender and sender.username
        else "لا يوجد معرف"
    )

    current_time = datetime.now(
        ZoneInfo("Asia/Baghdad")
    ).strftime(
        "%Y-%m-%d | %I:%M:%S %p"
    )

    # أول تفاعل
    if sender_id not in visited_users_cache:

        visited_users_cache.add(
            sender_id
        )

        try:

            visit_msg = (
                f"👀 **تم رصد تفاعل جديد:**\n\n"
                f"👤 **المعرف:** {username}\n"
                f"🆔 **الآيدي:** `{sender_id}`\n"
                f"⏱️ **الوقت:** {current_time}"
            )

            await client.send_message(
                "me",
                visit_msg
            )

        except Exception as e:

            print(
                f"خطأ: {e}"
            )

    message_info_cache[event.id] = {

        "sender_id": sender_id,

        "username": username,

        "text": event.message.text or ""
    }

    # الميديا
    if event.media:

        media_cache[
            (sender_id, event.id)
        ] = event.message

        clean_caches()

        # الحفظ التلقائي
        if sender_id in auto_save_users:

            try:

                file_path = await client.download_media(
                    event.message,
                    file=DOWNLOAD_DIR
                )

                if file_path:

                    await client.send_file(

                        "me",

                        file_path,

                        caption=(
                            f"📥 **[حفظ تلقائي]**\n\n"
                            f"👤 المعرف: {username}\n"
                            f"🆔 الآيدي: `{sender_id}`\n"
                            f"⏱️ الوقت: {current_time}"
                        )
                    )

                    if os.path.exists(
                        file_path
                    ):

                        os.remove(
                            file_path
                        )

            except Exception as e:

                print(
                    f"خطأ في الحفظ التلقائي: {e}"
                )


# =========================================================
# تعديل الرسائل
# =========================================================

@client.on(
    events.MessageEdited(
        incoming=True
    )
)
async def handle_edited_messages(event):

    if not event.is_private:
        return

    msg_id = event.id

    new_text = (
        event.message.text
        or "[ميديا أو محتوى فارغ]"
    )

    current_time = datetime.now(
        ZoneInfo("Asia/Baghdad")
    ).strftime(
        "%Y-%m-%d | %I:%M:%S %p"
    )

    if msg_id not in message_info_cache:
        return

    info = message_info_cache[
        msg_id
    ]

    if info["text"] != new_text:

        try:

            log_msg = (
                f"✏️ **تم رصد رسالة معدلة:**\n\n"
                f"👤 **المعرف:** "
                f"{info['username']}\n"
                f"🆔 **الآيدي:** "
                f"`{info['sender_id']}`\n"
                f"⏱️ **الوقت:** "
                f"{current_time}\n\n"
                f"📌 **قبل التعديل:**\n"
                f"{info['text']}\n\n"
                f"📝 **بعد التعديل:**\n"
                f"{new_text}"
            )

            await client.send_message(
                "me",
                log_msg
            )

        except Exception as e:

            print(
                f"خطأ: {e}"
            )

    message_info_cache[
        msg_id
    ]["text"] = new_text


# =========================================================
# الرسائل المحذوفة
# =========================================================

@client.on(
    events.MessageDeleted
)
async def handle_deleted_messages(event):

    current_time = datetime.now(
        ZoneInfo("Asia/Baghdad")
    ).strftime(
        "%Y-%m-%d | %I:%M:%S %p"
    )

    for msg_id in event.deleted_ids:

        info = message_info_cache.get(
            msg_id
        )

        # الرسائل النصية
        if info:

            try:

                log_msg = (
                    f"🗑️ **تم حذف رسالة:**\n\n"
                    f"👤 **المعرف:** "
                    f"{info['username']}\n"
                    f"🆔 **الآيدي:** "
                    f"`{info['sender_id']}`\n"
                    f"⏱️ **الوقت:** "
                    f"{current_time}\n\n"
                    f"💬 **النص:**\n"
                    f"{info['text']}"
                )

                await client.send_message(
                    "me",
                    log_msg
                )

            except Exception as e:

                print(
                    f"خطأ: {e}"
                )

        # الميديا المحذوفة
        for cache_key, msg_obj in list(
            media_cache.items()
        ):

            if cache_key[1] != msg_id:
                continue

            sender_id = cache_key[0]

            username = (
                info["username"]
                if info
                else "غير متوفر"
            )

            try:

                file_path = await client.download_media(
                    msg_obj,
                    file=DOWNLOAD_DIR
                )

                if file_path:

                    caption = (
                        f"🗑️ **تم رصد ميديا محذوفة**\n\n"
                        f"👤 **المعرف:** "
                        f"{username}\n"
                        f"🆔 **الآيدي:** "
                        f"`{sender_id}`\n"
                        f"⏱️ **الوقت:** "
                        f"{current_time}"
                    )

                    await client.send_file(
                        "me",
                        file_path,
                        caption=caption
                    )

                    if os.path.exists(
                        file_path
                    ):

                        os.remove(
                            file_path
                        )

            except Exception as e:

                print(
                    f"خطأ في الميديا المحذوفة: {e}"
                )

            finally:

                del media_cache[
                    cache_key
                ]

            break

        if msg_id in message_info_cache:

            del message_info_cache[
                msg_id
            ]


# =========================================================
# 7 / 8 لتحميل الميديا
# =========================================================

@client.on(
    events.NewMessage(
        outgoing=True,
        pattern=r"^(7|8)$"
    )
)
async def handle_media_download_commands(event):

    if not event.is_private:
        return

    reply_msg = await event.get_reply_message()

    if not reply_msg:
        return

    sender_id = reply_msg.sender_id

    command = event.raw_text.strip()

    target_message = (
        media_cache.get(
            (sender_id, reply_msg.id)
        )
        or (
            reply_msg
            if reply_msg.media
            else None
        )
    )

    if not target_message:

        try:
            await event.delete()
        except Exception:
            pass

        return

    try:
        await event.delete()
    except Exception:
        pass

    try:

        file_path = await client.download_media(
            target_message,
            file=DOWNLOAD_DIR
        )

        if not file_path:
            return

        current_time = datetime.now(
            ZoneInfo("Asia/Baghdad")
        ).strftime(
            "%Y-%m-%d | %I:%M:%S %p"
        )

        if command == "7":

            await client.send_file(
                event.chat_id,
                file_path,
                caption=f"⏱️ الوقت: {current_time}"
            )

        elif command == "8":

            await client.send_file(
                "me",
                file_path,
                caption=f"⏱️ الوقت: {current_time}"
            )

        if os.path.exists(
            file_path
        ):

            os.remove(
                file_path
            )

    except Exception as e:

        print(
            f"خطأ في تحميل الميديا: {e}"
        )


# =========================================================
# التشغيل
# =========================================================

def main():

    print(
        "🚀 جاري تشغيل اليوزر بوت..."
    )

    client.start()

    print(
        "✅ تم الاتصال بحساب Telegram بنجاح."
    )

    client.run_until_disconnected()


if __name__ == "__main__":
    main()
             
