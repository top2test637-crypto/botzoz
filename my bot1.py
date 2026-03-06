import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message

# --- الإعدادات ---
TOKEN = "8738398462:AAEyrNr6xBoFrEymxVW12Sqd-66XdHCYR98"  # ضع توكن البوت هنا
ADMIN_ID = 8544414786     # ضع الآيدي الخاص بك هنا

bot = Bot(token=TOKEN)
dp = Dispatcher()

# قاموس لتخزين علاقة الرسائل (لضمان وصول الرد للشخص الصحيح)
# في البوتات الكبيرة يفضل استخدام قاعدة بيانات مثل SQLite
message_map = {}

@dp.message(Command("start"))
async def start_handler(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("مرحبا بك ! ايها الملك زوز هذا بوتك الخاص بالتواصل .")
    else:
        await message.answer(".السلام عليكم ورحمه الله وبركاته "
        "اهلا بك ف بوت تواصل زوز ارسل رسالتك وسارد عليها قريبا ")

@dp.message()
async def contact_logic(message: Message):
    # 1. إذا كانت الرسالة قادمة من مستخدم عادي (ليست من الأدمن)
    if message.from_user.id != ADMIN_ID:
        # إرسال الرسالة للأدمن مع تفاصيل المستخدم
        sent_msg = await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"👤 **رسالة من:** {message.from_user.full_name}\n"
                 f"🆔 **ID:** `{message.from_user.id}`\n\n"
                 f"💬 **المحتوى:**\n{message.text}",
            parse_mode="Markdown"
        )
        # تخزين معرف الرسالة لربط الرد لاحقاً
        message_map[sent_msg.message_id] = message.from_user.id
        await message.reply("✅ تم إرسال رسالتك بنجاح.")

    # 2. إذا كانت الرسالة من الأدمن (يريد الرد على مستخدم)
    else:
        if message.reply_to_message:
            reply_id = message.reply_to_message.message_id
            if reply_id in message_map:
                user_id = message_map[reply_id]
                try:
                    await bot.send_message(chat_id=user_id, text=f"🔔 **رد من الدعم:**\n\n{message.text}", parse_mode="Markdown")
                    await message.reply("🚀 تم إرسال ردك للمستخدم.")
                except Exception as e:
                    await message.reply(f"❌ حدث خطأ أثناء الإرسال: {e}")
            else:
                await message.reply("⚠️ لا يمكنني العثور على صاحب هذه الرسالة في ذاكرة الجلسة الحالية.")
        else:
            await message.reply("💡 للرد على مستخدم، قم بعمل (Reply/رد) على رسالته التي وصلت إليك.")

async def main():
    logging.basicConfig(level=logging.INFO)
    print("البوت يعمل الآن...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("تم إيقاف البوت.")