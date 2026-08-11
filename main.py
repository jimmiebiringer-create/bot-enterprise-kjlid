import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from telethon import TelegramClient, events
from telethon.tl.functions.stories import GetPeerStoriesRequest, GetPinnedStoriesRequest

API_ID = 32492582
API_HASH ="d7737a28a39c86f3bb82777d0a1aea6e"

client = TelegramClient('my_account', API_ID, API_HASH)

BANNED_FILE = "banned.json"
auto_save_users = set()
media_cache = {}
message_info_cache = {}
visited_users_cache = set()
pending_stories = {}

DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def load_banned_users():
    if os.path.exists(BANNED_FILE):
        try:
            with open(BANNED_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_banned_users():
    try:
        with open(BANNED_FILE, "w", encoding="utf-8") as f:
            json.dump(list(banned_users), f)
    except Exception as e:
        print(f"خطأ في حفظ ملف المحظورين: {e}")

banned_users = load_banned_users()

def clean_caches():
    if len(media_cache) > 100:
        sorted_keys = sorted(media_cache.keys())
        for key in sorted_keys[:50]:
            del media_cache[key]
    if len(message_info_cache) > 100:
        sorted_keys = sorted(message_info_cache.keys())
        for key in sorted_keys[:50]:
            del message_info_cache[key]

@client.on(events.NewMessage(outgoing=True, pattern=r'^/help$'))
async def help_command_handler(event):
    if not event.is_private:
        return
    try:
        await event.delete()
    except Exception:
        pass
    
    help_text = (
        "🤖 **قائمة أوامر اليوزر بوت:**\n\n"
        "🔍 `/done [المعرف/الآيدي]` - لفحص وتحميل قصص الحساب.\n"
        "🚫 `/ban` - (بالرد على رسالة شخص) لحظره ومنع رسائله بصمت.\n"
        "✅ `/unban` - (بالرد على شخص) لإلغاء حظره بصمت.\n"
        "📋 `/banned` - لعرض قائمة المحظورين (الآيدي والمعرف).\n"
        "📥 `/save` - (بالرد على شخص) لتفعيل/إلغاء الحفظ التلقائي لوسائطه.\n"
        "7️⃣ أو 8️⃣ - (بالرد على أي ميديا) لتحميلها مباشرة (هنا أو في المحفوظات).\n"
        "❓ `/help` - لعرض هذه القائمة."
    )
    await client.send_message(event.chat_id, help_text)

@client.on(events.NewMessage(outgoing=True, pattern=r'^/banned$'))
async def list_banned_handler(event):
    if not event.is_private:
        return
    
    try:
        await event.delete()
    except Exception:
        pass
    
    if not banned_users:
        await client.send_message(event.chat_id, "📭 قائمة المحظورين فارغة حالياً.")
        return

    status_msg = await event.respond("🔍 جاري جلب معلومات المحظورين...")

    banned_details = []
    for uid in banned_users:
        username_str = "لا يوجد معرف"
        try:
            entity = await client.get_entity(uid)
            if entity and hasattr(entity, 'username') and entity.username:
                username_str = f"@{entity.username}"
            elif entity and hasattr(entity, 'first_name') and entity.first_name:
                username_str = entity.first_name
        except Exception:
            pass
        banned_details.append(f"• الآيدي: `{uid}` | المعرف: {username_str}")

    banned_list_str = "\n".join(banned_details)
    await status_msg.edit(f"🚫 **قائمة المحظورين حالياً:**\n\n{banned_list_str}")

@client.on(events.NewMessage(outgoing=True, pattern=r'^/ban$'))
async def ban_user_handler(event):
    if not event.is_private:
        return
    client.loop.create_task(event.delete())
    reply_msg = await event.get_reply_message()
    if reply_msg:
        banned_users.add(reply_msg.sender_id)
        save_banned_users()

@client.on(events.NewMessage(outgoing=True, pattern=r'^/unban$'))
async def unban_user_handler(event):
    if not event.is_private:
        return
    client.loop.create_task(event.delete())
    reply_msg = await event.get_reply_message()
    if reply_msg:
        if reply_msg.sender_id in banned_users:
            banned_users.remove(reply_msg.sender_id)
            save_banned_users()

@client.on(events.NewMessage(outgoing=True, pattern=r'^/save$'))
async def auto_save_handler(event):
    if not event.is_private:
        return
    client.loop.create_task(event.delete())
    reply_msg = await event.get_reply_message()
    if reply_msg:
        sender_id = reply_msg.sender_id
        if sender_id in auto_save_users:
            auto_save_users.remove(sender_id)
            await client.send_message(event.chat_id, f"🔴 تم إلغاء الحفظ التلقائي للمستخدم (`{sender_id}`).")
        else:
            auto_save_users.add(sender_id)
            await client.send_message(event.chat_id, f"🟢 تم تفعيل الحفظ التلقائي للمستخدم (`{sender_id}`).")

@client.on(events.NewMessage(outgoing=True, pattern=r'^/done\s+(.+)'))
async def check_stories_handler(event):
    target = event.pattern_match.group(1).strip()
    
    try:
        await event.delete()
    except Exception:
        pass

    status_msg = await event.respond(f"🔍 جاري فحص القصص للحساب: `{target}`...")

    try:
        if target.isdigit():
            user = await client.get_entity(int(target))
        else:
            user = await client.get_entity(target)

        active_stories = []
        highlighted_stories = []

        try:
            peer_stories = await client(GetPeerStoriesRequest(peer=user))
            if peer_stories and hasattr(peer_stories, 'stories'):
                if hasattr(peer_stories.stories, 'stories'):
                    active_stories.extend(peer_stories.stories.stories)
        except Exception as e:
            print(f"خطأ في جلب القصص النشطة: {e}")

        try:
            pinned_res = await client(GetPinnedStoriesRequest(peer=user, offset_id=0, limit=100))
            if pinned_res and hasattr(pinned_res, 'stories'):
                for s in pinned_res.stories:
                    if s not in active_stories and s not in highlighted_stories:
                        highlighted_stories.append(s)
        except Exception as e:
            print(f"خطأ في جلب القصص البارزة: {e}")

        total_active = len(active_stories)
        total_highlighted = len(highlighted_stories)
        total_all = total_active + total_highlighted

        if total_all > 0:
            pending_stories[event.chat_id] = {
                "step": "select_type",
                "active": active_stories,
                "highlighted": highlighted_stories,
                "target": target
            }

            text_report = (
                f"✅ تم فحص الحساب `{target}` بنجاح:\n"
                f"🟢 **قصص نشطة حالية:** {total_active}\n"
                f"⭐ **قصص بارزة/أرشيف:** {total_highlighted}\n"
                f"📊 **المجموع الكلي:** {total_all}\n\n"
                f"ما الذي ترغب في تحميله؟\n"
                f"1️⃣ **القصص النشطة فقط**\n"
                f"2️⃣ **القصص البارزة/الأرشيف فقط**\n"
                f"3️⃣ **الاثنين معاً**\n"
                f"(قم بالرد على هذه الرسالة برقم الخيار المطلوب)."
            )
            await status_msg.edit(text_report)
        else:
            await status_msg.edit(f"❌ لا توجد أي قصص نشطة أو بارزة ظاهرة للحساب `{target}`.")

    except Exception as e:
        await status_msg.edit(f"⚠️ حدث خطأ أثناء فحص الحساب: {e}")

@client.on(events.NewMessage(outgoing=True))
async def handle_user_replies(event):
    if not event.is_private and not event.is_group:
        return
    
    reply_msg = await event.get_reply_message()
    if not reply_msg:
        return

    chat_id = event.chat_id
    if chat_id in pending_stories:
        text = event.raw_text.strip().lower()
        data = pending_stories[chat_id]
        current_step = data.get("step")

        if current_step == "select_type":
            if text in ['1', 'نشطة', 'القصص النشطة']:
                selected_types = [("🟢 [قصة نشطة]", data["active"])]
                selected_types = [x for x in selected_types if len(x[1]) > 0]
            elif text in ['2', 'بارزة', 'أرشيف', 'القصص البارزة', 'الأرشيف']:
                selected_types = [("⭐ [قصة بارزة/أرشيف]", data["highlighted"])]
                selected_types = [x for x in selected_types if len(x[1]) > 0]
            elif text in ['3', 'الاثنين', 'الاثنين معاً', 'الكل']:
                selected_types = []
                if len(data["active"]) > 0:
                    selected_types.append(("🟢 [قصة نشطة]", data["active"]))
                if len(data["highlighted"]) > 0:
                    selected_types.append(("⭐ [قصة بارزة/أرشيف]", data["highlighted"]))
            else:
                return

            if not selected_types:
                await event.respond("❌ النوع الذي اخترته لا يحتوي على أي قصص. تم إلغاء العملية.")
                del pending_stories[chat_id]
                try:
                    await client.delete_messages(chat_id, [event.id, reply_msg.id])
                except Exception:
                    pass
                return

            data["selected_types"] = selected_types
            data["step"] = "select_destination"

            try:
                await client.delete_messages(chat_id, [event.id, reply_msg.id])
            except Exception:
                pass

            await client.send_message(
                chat_id,
                f"📂 ممتاز! أين تريد تنزيل القصص المختارة؟\n\n"
                f"1️⃣ أرسل **مفصول** أو **محفوظة** (للرسائل المحفوظة)\n"
                f"2️⃣ أرسل **هنا** (في هذه المحادثة أو القروب)\n"
                f"3️⃣ أرسل **لا** للإلغاء\n"
                f"(قم بالرد على هذه الرسالة بالخيار المطلوب)."
            )
            return

        elif current_step == "select_destination":
            if text in ['محفوظة', 'المحفوظة', '1', 'مفصول']:
                destination = 'me'
                dest_name = "الرسائل المحفوظة"
            elif text in ['هنا', '2']:
                destination = event.chat_id
                dest_name = "هذه المحادثة/القروب"
            elif text in ['لا', 'no', '3']:
                del pending_stories[chat_id]
                try:
                    await client.delete_messages(chat_id, [event.id, reply_msg.id])
                except Exception:
                    pass
                return
            else:
                return

            try:
                await client.delete_messages(chat_id, [event.id, reply_msg.id])
            except Exception:
                pass

            selected_types = data["selected_types"]
            target_name = data["target"]

            total_count = sum(len(s_list) for _, s_list in selected_types)
            current_index = 0
            success_count = 0

            counter_msg = await client.send_message(chat_id, f"📥 جاري بدء التنزيل السريع...\n⏳ تم تحميل (0 / {total_count})")

            for label, s_list in selected_types:
                for story in s_list:
                    current_index += 1
                    try:
                        if hasattr(story, 'media') and story.media:
                            
                            last_pct = [-1]
                            async def fast_progress(current, total):
                                if total > 0:
                                    pct = int((current / total) * 100)
                                    if pct >= last_pct[0] + 25 or pct == 100:
                                        last_pct[0] = pct
                                        try:
                                            await counter_msg.edit(
                                                f"📥 جاري التنزيل إلى {dest_name}...\n"
                                                f"⏳ القصة ({current_index} / {total_count})\n"
                                                f"📊 نسبة التحميل: `{pct}%`"
                                            )
                                        except Exception:
                                            pass

                            file_path = await client.download_media(
                                story.media, 
                                file=DOWNLOAD_DIR,
                                progress_callback=fast_progress
                            )

                            if file_path:
                                story_date = getattr(story, 'date', None)
                                if not story_date and hasattr(story, 'media') and hasattr(story.media, 'date'):
                                    story_date = story.media.date

                                if story_date:
                                    if story_date.tzinfo is None:
                                        story_date = story_date.replace(tzinfo=ZoneInfo("UTC"))
                                    baghdad_time = story_date.astimezone(ZoneInfo("Asia/Baghdad"))
                                    formatted_date = baghdad_time.strftime("%Y-%m-%d | %I:%M:%S %p")
                                else:
                                    baghdad_time = datetime.now(ZoneInfo("Asia/Baghdad"))
                                    formatted_date = baghdad_time.strftime("%Y-%m-%d | %I:%M:%S %p")

                                caption = f"{label} لـ: {target_name}\n⏱️ وقت النشر الأصلي: {formatted_date}"
                                
                                await client.send_file(destination, file_path, caption=caption)
                                success_count += 1
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                    except Exception as e:
                        print(f"خطأ أثناء تحميل قصة: {e}")

            try:
                await counter_msg.delete()
            except Exception:
                pass

            await client.send_message(chat_id, f"✅ تم الانتهاء بنجاح! تم تحميل وإرسال ({success_count} / {total_count}) قصة إلى {dest_name}.")
            del pending_stories[chat_id]

@client.on(events.NewMessage(incoming=True))
async def handle_incoming_messages(event):
    if not event.is_private:
        return
    
    sender_id = event.sender_id
    if sender_id in banned_users:
        client.loop.create_task(event.delete())
        return

    sender = await event.get_sender()
    username = f"@{sender.username}" if sender and sender.username else "لا يوجد معرف"
    current_time = datetime.now(ZoneInfo("Asia/Baghdad")).strftime("%Y-%m-%d | %I:%M:%S %p")

    if sender_id not in visited_users_cache:
        visited_users_cache.add(sender_id)
        try:
            visit_msg = (
                f"👀 **تم رصد تفاعل/دخول جديد للمحادثة:**\n\n"
                f"👤 **المعرف:** {username}\n"
                f"🆔 **الآيدي:** `{sender_id}`\n"
                f"⏱️ **الوقت:** {current_time}"
            )
            await client.send_message('me', visit_msg)
        except Exception as e:
            print(f"خطأ: {e}")

    message_info_cache[event.id] = {
        "sender_id": sender_id,
        "username": username,
        "text": event.message.text or ""
    }

    if event.media:
        media_cache[(sender_id, event.id)] = event.message
        clean_caches()
        if sender_id in auto_save_users:
            try:
                file_path = await client.download_media(event.message, file=DOWNLOAD_DIR)
                if file_path:
                    current_time = datetime.now(ZoneInfo("Asia/Baghdad")).strftime("%Y-%m-%d | %I:%M:%S %p")
                    await client.send_file('me', file_path, caption=f"📥 [حفظ تلقائي]\n👤 المعرف: {username}\n🆔 الآيدي: `{sender_id}`\n⏱️ الوقت: {current_time}")
                    if os.path.exists(file_path):
                        os.remove(file_path)
            except Exception as e:
                print(f"خطأ: {e}")

@client.on(events.MessageEdited(incoming=True))
async def handle_edited_messages(event):
    if not event.is_private:
        return
    msg_id = event.id
    new_text = event.message.text or "[ميديا أو محتوى فارغ]"
    current_time = datetime.now(ZoneInfo("Asia/Baghdad")).strftime("%Y-%m-%d | %I:%M:%S %p")
    if msg_id in message_info_cache:
        info = message_info_cache[msg_id]
        if info["text"] != new_text:
            try:
                log_msg = (
                    f"✏️ **تم رصد رسالة مُعدلة:**\n\n"
                    f"👤 **المعرف:** {info['username']}\n"
                    f"🆔 **الآيدي:** `{info['sender_id']}`\n"
                    f"⏱️ **الوقت:** {current_time}\n\n"
                    f"📌 **قبل التعديل:**\n{info['text']}\n\n"
                    f"📝 **بعد التعديل:**\n{new_text}"
                )
                await client.send_message('me', log_msg)
            except Exception as e:
                print(f"خطأ: {e}")
        message_info_cache[msg_id]["text"] = new_text

@client.on(events.MessageDeleted)
async def handle_deleted_messages(event):
    current_time = datetime.now(ZoneInfo("Asia/Baghdad")).strftime("%Y-%m-%d | %I:%M:%S %p")
    for msg_id in event.deleted_ids:
        if msg_id in message_info_cache:
            info = message_info_cache[msg_id]
            try:
                log_msg = (
                    f"🗑️ **تم حذف رسالة نصية:**\n\n"
                    f"👤 **المعرف:** {info['username']}\n"
                    f"🆔 **الآيدي:** `{info['sender_id']}`\n"
                    f"⏱️ **الوقت:** {current_time}\n\n"
                    f"💬 **النص المحذوف:**\n{info['text']}"
                )
                await client.send_message('me', log_msg)
            except Exception as e:
                print(f"خطأ: {e}")
            finally:
                del message_info_cache[msg_id]

        for cache_key, msg_obj in list(media_cache.items()):
            if cache_key[1] == msg_id:
                sender_id = cache_key[0]
                username = message_info_cache.get(msg_id, {}).get("username", "غير متوفر")
                try:
                    file_path = await client.download_media(msg_obj, file=DOWNLOAD_DIR)
                    if file_path:
                        caption = (
                            f"🗑️ **تم استخراج وسائط بعد حذفها!**\n\n"
                            f"👤 **المعرف:** {username}\n"
                            f"🆔 **الآيدي:** `{sender_id}`\n"
                            f"⏱️ **الوقت:** {current_time}"
                        )
                        await client.send_file('me', file_path, caption=caption)
                        if os.path.exists(file_path):
                            os.remove(file_path)
                except Exception as e:
                    print(f"خطأ: {e}")
                finally:
                    del media_cache[cache_key]
                break

@client.on(events.NewMessage(outgoing=True, pattern=r'^(7|8)$'))
async def handle_media_download_commands(event):
    if not event.is_private:
        return
    reply_msg = await event.get_reply_message()
    if not reply_msg:
        return
    sender_id = reply_msg.sender_id
    command = event.raw_text.strip()
    target_message = media_cache.get((sender_id, reply_msg.id)) or (reply_msg if reply_msg.media else None)
    if not target_message or not target_message.media:
        client.loop.create_task(event.delete())
        return
    client.loop.create_task(event.delete())
    try:
        file_path = await client.download_media(target_message, file=DOWNLOAD_DIR)
        if file_path:
            current_time = datetime.now(ZoneInfo("Asia/Baghdad")).strftime("%Y-%m-%d | %I:%M:%S %p")
            if command == '7':
                await client.send_file(event.chat_id, file_path, caption=f"⏱️ الوقت: {current_time}")
            elif command == '8':
                await client.send_file('me', file_path, caption=f"⏱️ الوقت: {current_time}")
            if os.path.exists(file_path):
                os.remove(file_path)
    except Exception as e:
        print(f"خطأ: {e}")

def main():
    print("جاري تشغيل اليوزر بوت...")
    client.start()
    client.run_until_disconnected()

if __name__ == '__main__':
    main()
