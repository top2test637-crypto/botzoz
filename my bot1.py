import asyncio
import logging
import sqlite3
import os
import threading
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

# ================== الإعدادات ==================
TOKEN = "8738398462:AAEyrNr6xBoFrEymxVW12Sqd-66XdHCYR98"  # توكن البوت
ADMIN_ID = 8544414786     # الآيدي الخاص بك

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ================== قاعدة البيانات ==================
class Database:
    def __init__(self, db_name="bot_data.db"):
        self.db_name = db_name
        self.lock = threading.Lock()
        self.init_db()

    def execute(self, query, params=(), fetch_one=False, fetch_all=False, commit=True):
        with self.lock:
            conn = sqlite3.connect(self.db_name, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            try:
                cur.execute(query, params)
                if commit: conn.commit()
                if fetch_one: return dict(cur.fetchone()) if cur.fetchone() else None
                if fetch_all: return [dict(row) for row in cur.fetchall()]
                return cur.lastrowid
            except Exception as e:
                logging.error(f"DB Error: {e}")
                return None
            finally:
                conn.close()

    def init_db(self):
        self.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        self.execute('''CREATE TABLE IF NOT EXISTS channels (chat_id TEXT PRIMARY KEY, name TEXT, url TEXT)''')
        self.execute('''CREATE TABLE IF NOT EXISTS message_map (admin_msg_id INTEGER PRIMARY KEY, user_id INTEGER)''')

db = Database()

# ================== حالات الأدمن (FSM) ==================
class AdminStates(StatesGroup):
    wait_broadcast = State()
    wait_add_channel = State()
    wait_del_channel = State()

# ================== نظام الاشتراك الإجباري ==================
async def check_force_sub(user_id: int):
    if user_id == ADMIN_ID:
        return True, []
    
    channels = db.execute("SELECT * FROM channels", fetch_all=True)
    missing_channels = []
    
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch['chat_id'], user_id=user_id)
            if member.status in ['left', 'kicked']:
                missing_channels.append(ch)
        except Exception as e:
            # إذا لم يكن البوت مشرفاً في القناة أو الآيدي غير صحيح
            logging.warning(f"Force sub check error for channel {ch['chat_id']}: {e}")
            missing_channels.append(ch)
            
    return len(missing_channels) == 0, missing_channels

# ================== أوامر المستخدم العادي ==================
@router.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    name = message.from_user.full_name
    
    # حفظ المستخدم في قاعدة البيانات
    db.execute("INSERT OR IGNORE INTO users (id, name) VALUES (?, ?)", (user_id, name))
    
    if user_id == ADMIN_ID:
        await message.answer("👑 أهلاً بك يا زوز في لوحة القيادة!\nأرسل `/admin` لفتح خيارات التحكم.")
        return

    # فحص الاشتراك الإجباري
    is_subbed, missing = await check_force_sub(user_id)
    if not is_subbed:
        builder = InlineKeyboardBuilder()
        for ch in missing:
            builder.button(text=f"📢 اشترك في: {ch['name']}", url=ch['url'])
        builder.button(text="✅ تأكيد الاشتراك", callback_data="check_sub")
        builder.adjust(1)
        await message.answer("⚠️ **عذراً!**\nلا يمكنك استخدام البوت إلا بعد الاشتراك في قنواتنا أولاً 👇", 
                             reply_markup=builder.as_markup(), parse_mode="Markdown")
        return

    await message.answer("👋 السلام عليكم ورحمة الله وبركاته\nأهلاً بك في بوت التواصل مع زوز.\nأرسل رسالتك، صورتك، أو ملفك وسأرد عليك قريباً ⏳")

@router.callback_query(F.data == "check_sub")
async def verify_sub_callback(call: CallbackQuery):
    is_subbed, missing = await check_force_sub(call.from_user.id)
    if is_subbed:
        await call.message.edit_text("✅ شكراً لاشتراكك! يمكنك الآن إرسال رسائلك بحرية.")
    else:
        await call.answer("❌ لم تقم بالاشتراك في جميع القنوات بعد!", show_alert=True)

# ================== لوحة تحكم الأدمن ==================
@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 الإحصائيات", callback_data="admin_stats")
    builder.button(text="📢 إذاعة للكل", callback_data="admin_broadcast")
    builder.button(text="➕ إضافة قناة", callback_data="admin_add_ch")
    builder.button(text="➖ حذف قناة", callback_data="admin_del_ch")
    builder.button(text="📦 باك أب البيانات", callback_data="admin_backup")
    builder.adjust(2, 2, 1)
    
    await message.answer("⚙️ **لوحة التحكم الخاصة بالمدير:**\nاختر الإجراء المطلوب 👇", reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(F.data.startswith("admin_"))
async def admin_callbacks(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    action = call.data.split("_", 1)[1]
    
    if action == "stats":
        users_count = db.execute("SELECT COUNT(*) as c FROM users", fetch_one=True)['c']
        channels_count = db.execute("SELECT COUNT(*) as c FROM channels", fetch_one=True)['c']
        await call.message.edit_text(f"📊 **إحصائيات البوت:**\n\n👥 عدد المستخدمين: `{users_count}`\n📢 عدد قنوات الاشتراك: `{channels_count}`", parse_mode="Markdown")
        
    elif action == "broadcast":
        await state.set_state(AdminStates.wait_broadcast)
        await call.message.answer("📢 **قسم الإذاعة:**\nأرسل الرسالة التي تريد إرسالها لجميع المستخدمين (نص، صورة، فيديو).")
        
    elif action == "add_ch":
        await state.set_state(AdminStates.wait_add_channel)
        await call.message.answer("➕ **إضافة قناة:**\nأرسل بيانات القناة بهذا الترتيب (في رسالة واحدة):\n`آيدي_القناة اسم_القناة الرابط`\n\n📌 **مثال:**\n`-1001234567890 قناة_زوز https://t.me/zoz_channel`", parse_mode="Markdown")
        
    elif action == "del_ch":
        channels = db.execute("SELECT * FROM channels", fetch_all=True)
        if not channels:
            return await call.answer("❌ لا توجد قنوات مضافة حالياً.", show_alert=True)
        
        builder = InlineKeyboardBuilder()
        for ch in channels:
            builder.button(text=f"❌ حذف: {ch['name']}", callback_data=f"delch_{ch['chat_id']}")
        builder.adjust(1)
        await call.message.edit_text("🗑️ **اختر القناة التي تريد حذفها:**", reply_markup=builder.as_markup(), parse_mode="Markdown")
        
    elif action == "backup":
        if os.path.exists("bot_data.db"):
            await bot.send_document(ADMIN_ID, FSInputFile("bot_data.db"), caption="📦 **النسخة الاحتياطية اليدوية لقاعدة البيانات.**", parse_mode="Markdown")
        await call.answer()

@router.callback_query(F.data.startswith("delch_"))
async def delete_channel_cb(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    ch_id = call.data.split("_")[1]
    db.execute("DELETE FROM channels WHERE chat_id=?", (ch_id,))
    await call.message.edit_text("✅ **تم حذف القناة بنجاح من الاشتراك الإجباري.**", parse_mode="Markdown")

# ================== استلام إدخالات الأدمن ==================
@router.message(StateFilter(AdminStates.wait_add_channel))
async def process_add_channel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            return await message.answer("❌ **صيغة خاطئة!** يرجى الإرسال كالتالي:\n`آيدي اسم رابط`", parse_mode="Markdown")
        
        ch_id, ch_name, ch_url = parts[0], parts[1], parts[2]
        db.execute("INSERT OR REPLACE INTO channels (chat_id, name, url) VALUES (?, ?, ?)", (ch_id, ch_name, ch_url))
        await message.answer(f"✅ **تم إضافة القناة بنجاح:**\n[{ch_name}]({ch_url})", parse_mode="Markdown")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ حدث خطأ: {e}")

@router.message(StateFilter(AdminStates.wait_broadcast))
async def process_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    users = db.execute("SELECT id FROM users", fetch_all=True)
    await message.answer(f"⏳ جاري الإرسال إلى `{len(users)}` مستخدم...", parse_mode="Markdown")
    
    success, fail = 0, 0
    for u in users:
        try:
            await message.copy_to(chat_id=u['id'])
            success += 1
            await asyncio.sleep(0.05) # تجنب حظر تليجرام
        except:
            fail += 1
            
    await message.answer(f"✅ **تمت الإذاعة بنجاح!**\n🟢 نجح: {success}\n🔴 فشل: {fail}", parse_mode="Markdown")
    await state.clear()

# ================== منطق المراسلة (التواصل) ==================
@router.message(StateFilter(None))
async def contact_logic(message: Message):
    user_id = message.from_user.id

    # --- 1. رسالة من مستخدم عادي إلى الأدمن ---
    if user_id != ADMIN_ID:
        is_subbed, _ = await check_force_sub(user_id)
        if not is_subbed:
            return await start_handler(message) # توجيهه للاشتراك

        # إرسال رسالة تعريفية للأدمن
        info_msg = await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"👤 **رسالة جديدة من:** {message.from_user.full_name}\n"
                 f"🆔 **ID:** `{message.from_user.id}`\n"
                 f"🔗 **يوزر:** @{message.from_user.username or 'لا يوجد'}",
            parse_mode="Markdown"
        )
        
        # نسخ الرسالة الأصلية للأدمن (لكي تدعم الصور والملفات والصوتيات)
        copied_msg = await message.copy_to(chat_id=ADMIN_ID)
        
        # حفظ رقم الرسالة المنسوخة لربطها بالرد
        db.execute("INSERT OR REPLACE INTO message_map (admin_msg_id, user_id) VALUES (?, ?)", 
                   (copied_msg.message_id, user_id))
        
        await message.reply("✅ تم استلام رسالتك وتوجيهها للمسؤول بنجاح.")

    # --- 2. رسالة من الأدمن إلى المستخدم (رد) ---
    else:
        if message.reply_to_message:
            reply_id = message.reply_to_message.message_id
            target = db.execute("SELECT user_id FROM message_map WHERE admin_msg_id=?", (reply_id,), fetch_one=True)
            
            if target:
                try:
                    await message.copy_to(chat_id=target['user_id'])
                    await message.reply("🚀 **تم إرسال ردك للمستخدم بنجاح.**", parse_mode="Markdown")
                except TelegramForbiddenError:
                    await message.reply("❌ **المستخدم قام بحظر البوت!**", parse_mode="Markdown")
                except Exception as e:
                    await message.reply(f"❌ **حدث خطأ:** {e}", parse_mode="Markdown")
            else:
                await message.reply("⚠️ لا يمكنني العثور على صاحب هذه الرسالة في قاعدة البيانات.\nتأكد من أنك ترد على الرسالة الأصلية (التي تحتوي على المحتوى وليس رسالة الـ ID).")

# ================== النسخ الاحتياطي التلقائي ==================
async def daily_backup():
    while True:
        await asyncio.sleep(86400) # كل 24 ساعة (86400 ثانية)
        if os.path.exists("bot_data.db"):
            try:
                await bot.send_document(chat_id=ADMIN_ID, document=FSInputFile("bot_data.db"), 
                                        caption="📦 **النسخة الاحتياطية اليومية التلقائية.**", parse_mode="Markdown")
                logging.info("تم إرسال النسخة الاحتياطية بنجاح.")
            except Exception as e:
                logging.error(f"فشل إرسال الباك أب: {e}")

# ================== نقطة البداية ==================
async def main():
    logging.basicConfig(level=logging.INFO)
    print("🚀 جاري إقلاع البوت وتجهيز قاعدة البيانات...")
    
    # تشغيل مهمة الباك أب في الخلفية
    asyncio.create_task(daily_backup())
    
    # مسح التحديثات القديمة حتى لا يرد عليها البوت فجأة
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 تم إيقاف البوت.")
