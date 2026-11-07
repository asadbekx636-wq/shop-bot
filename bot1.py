import asyncio
import logging
import os
import sqlite3
import time
import urllib.request
from threading import Thread

from flask import Flask
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                      ReplyKeyboardMarkup, Update)
from telegram.ext import (ApplicationBuilder, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler, filters)

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("shop-bot")

# --- SOZLAMALAR (Render > Environment bo'limida kiritiladi, kodga yozilmaydi) ---
TOKEN = os.environ.get("9245489726:AAG7lnCh-IU3uTgofPDpKCTOfgoC9SBT2nc", "").strip()          # BotFather bergan token
try:
    ADMIN_ID = int(os.environ.get("7161851696", "0") or 0)  # sizning Telegram ID raqamingiz
except ValueError:
    ADMIN_ID = 0
CONTACT_PHONE = os.environ.get("CONTACT_PHONE", "9986194040")
DB_PATH = os.environ.get("DB_PATH", "shop.db")

# Bosqichlar (States)
BROADCAST = 1
SEARCH = 2

# Tugma nomlari (klaviatura va tekshiruvda bir xil ishlatiladi)
BTN_PROFILE = "👤 Profilim"
BTN_SEARCH = "🔍 Qidiruv"
BTN_SHOP = "🛍 Do'kon"
BTN_CART = "🛒 Savatcham"
BTN_NOTIF = "🔔 Bildirishnomalar"
BTN_SETTINGS = "⚙️ Sozlamalar"
BTN_HELP = "ℹ️ Yordam / Bot haqida"
BTN_CONTACT = "📞 Bog'lanish"
BTN_ADMIN = "🛠 Admin Panel"
BTN_STATS = "👥 Statistika"
BTN_BROADCAST = "📢 Xabar yuborish"
BTN_PRODUCTS = "📦 Mahsulotlar ro'yxati"
BTN_BACK = "🔙 Asosiy menyu"
MENU_BUTTONS = {BTN_PROFILE, BTN_SEARCH, BTN_SHOP, BTN_CART, BTN_NOTIF, BTN_SETTINGS,
                BTN_HELP, BTN_CONTACT, BTN_ADMIN, BTN_STATS, BTN_BROADCAST, BTN_PRODUCTS, BTN_BACK}


# --- RENDER PORT TALABINI BAJARISH UCHUN FLASK SERVER ---
app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is running 24/7!"


@app.route("/health")
def health():
    return "ok"


def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def self_ping():
    """Render bepul tarifida server uxlab qolmasligi uchun har 10 daqiqada o'z manzilini ochadi."""
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        return
    while True:
        time.sleep(600)
        try:
            urllib.request.urlopen(url, timeout=20).read()
        except Exception as e:
            log.warning("O'zini tekshirishda xatolik: %s", e)


def keep_alive():
    Thread(target=run_web, daemon=True).start()
    Thread(target=self_ping, daemon=True).start()


# --- MA'LUMOTLAR BAZASI BILAN ISHLASH ---
def db():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            description TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            user_id INTEGER,
            product_id INTEGER,
            quantity INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            language TEXT DEFAULT 'UZ'
        )
    """)

    # Dastlabki ma'lumotlar
    cursor.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO categories (name) VALUES ('📱 Telefonlar'), ('💻 Noutbuklar'), ('⌚️ Aksessuarlar'), ('👕 Kiyim-kechak')")

        products_list = [
            (1, 'iPhone 15 Pro', 12000000, 'Yangi holatda, 256GB, Titanium'),
            (1, 'Samsung Galaxy S24 Ultra', 11500000, 'Ajoyib kamera va tezkor protsessor'),
            (1, 'Redmi Note 13 Pro', 3200000, 'Hamyonbop va sifatli smartfon'),
            (2, 'MacBook Air M2', 14000000, 'Tezkor, yengil va batareyasi uzoq chidaydi'),
            (2, 'Asus ROG Strix G16', 18000000, 'Geymerlar uchun kuchli noutbuk'),
            (3, 'AirPods Pro 2', 2500500, 'Mukammal ovoz va shovqinni yo‘qotish funksiyasi'),
            (3, 'Smart Watch Ultra 8', 450000, 'Sport va kundalik uchun aqlli soat'),
            (4, 'Stilish Hudi (Hoodie)', 250000, 'Issiq va qulay paxtali mato'),
            (4, 'Krossovka Nike Air', 650000, 'Sport uchun qulay oyoq kiyim')
        ]
        cursor.executemany("INSERT INTO products (category_id, name, price, description) VALUES (?, ?, ?, ?)", products_list)

    conn.commit()
    conn.close()


# --- MENYULAR ---
def get_main_menu(user_id):
    keyboard = [
        [KeyboardButton(BTN_PROFILE), KeyboardButton(BTN_SEARCH)],
        [KeyboardButton(BTN_SHOP), KeyboardButton(BTN_CART)],
        [KeyboardButton(BTN_NOTIF), KeyboardButton(BTN_SETTINGS)],
        [KeyboardButton(BTN_HELP), KeyboardButton(BTN_CONTACT)],
    ]
    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton(BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_admin_menu():
    keyboard = [
        [KeyboardButton(BTN_STATS), KeyboardButton(BTN_BROADCAST)],
        [KeyboardButton(BTN_PRODUCTS), KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# --- /START VA /HELP ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = db()
    cursor = conn.cursor()

    # Foydalanuvchini bazaga qo'shish (Agar oldin bo'lmasa)
    cursor.execute("INSERT OR IGNORE INTO users (user_id, full_name, language) VALUES (?, ?, ?)",
                   (user.id, user.full_name, 'UZ'))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"Assalomu alaykum, {user.first_name}! Onlayn Do'konimizga xush kelibsiz. 🚀\n"
        "Kerakli bo'limni pastdagi tugmalar orqali tanlang:",
        reply_markup=get_main_menu(user.id)
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Bot haqida:\n\n"
        "Bu onlayn do'kon boti bo'lib, xaridlaringizni qulay amalga oshirish va qidirish imkonini beradi.\n"
        "Buyruqlar: /start, /help"
    )


# --- MATNLI XABARLARNI BOSHQARISH ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == BTN_PROFILE:
        conn = db()
        cursor = conn.cursor()
        cursor.execute("SELECT full_name, language FROM users WHERE user_id = ?", (user_id,))
        user_info = cursor.fetchone()
        conn.close()

        name = user_info[0] if user_info else update.effective_user.full_name
        lang = user_info[1] if user_info else 'UZ'

        await update.message.reply_text(
            f"👤 Sizning profilingiz:\n\n"
            f"• Ism: {name}\n"
            f"• Telegram ID: {user_id}\n"
            f"• Tanlangan til: {lang}"
        )

    elif text == BTN_SEARCH:
        await update.message.reply_text("🔍 Qidirmoqchi bo'lgan mahsulot nomini yozib yuboring (masalan: iPhone):")
        return SEARCH

    elif text == BTN_SHOP:
        conn = db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM categories")
        categories = cursor.fetchall()
        conn.close()

        keyboard = [[InlineKeyboardButton(cat[1], callback_data=f"cat_{cat[0]}")] for cat in categories]
        await update.message.reply_text("Mavjud kategoriyalardan birini tanlang:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == BTN_CART:
        conn = db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.name, p.price, c.quantity, p.id FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = ?
        """, (user_id,))
        items = cursor.fetchall()
        conn.close()

        if not items:
            await update.message.reply_text("Savatchangiz bo'sh. 📭")
        else:
            text_msg = "🛒 Sizning savatchangiz:\n\n"
            total = 0
            for item in items:
                subtotal = item[1] * item[2]
                total += subtotal
                text_msg += f"• {item[0]} - {item[2]} dona x {item[1]:,.0f} so'm = {subtotal:,.0f} so'm\n"
            text_msg += f"\nUmumiy summa: {total:,.0f} so'm"

            keyboard = [[InlineKeyboardButton("✅ Buyurtmani rasmiylashtirish", callback_data="checkout")]]
            await update.message.reply_text(text_msg, reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == BTN_NOTIF:
        await update.message.reply_text("🔔 Hozircha sizda yangi bildirishnomalar yo'q.")

    elif text == BTN_SETTINGS:
        keyboard = [
            [InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz")],
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")]
        ]
        await update.message.reply_text("⚙️ Bot tilini tanlang:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == BTN_HELP:
        await help_command(update, context)

    elif text == BTN_CONTACT:
        await update.message.reply_text(f"📞 Admin bilan bog'lanish uchun: Tel: {CONTACT_PHONE}")

    elif text == BTN_ADMIN and user_id == ADMIN_ID:
        await update.message.reply_text("Xush kelibsiz, Admin! Kerakli bo'limni tanlang:", reply_markup=get_admin_menu())

    elif text == BTN_STATS and user_id == ADMIN_ID:
        conn = db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM products")
        total_products = cursor.fetchone()[0]
        conn.close()

        await update.message.reply_text(
            f"📊 Bot statistikasi:\n\n"
            f"👥 Jami foydalanuvchilar: {total_users} ta\n"
            f"📦 Jami mahsulotlar: {total_products} ta"
        )

    elif text == BTN_PRODUCTS and user_id == ADMIN_ID:
        conn = db()
        cursor = conn.cursor()
        cursor.execute("SELECT name, price FROM products")
        prods = cursor.fetchall()
        conn.close()

        msg = "📦 Do'kondagi mahsulotlar:\n\n"
        for p in prods:
            msg += f"• {p[0]} — {p[1]:,.0f} so'm\n"
        await update.message.reply_text(msg)

    elif text == BTN_BROADCAST and user_id == ADMIN_ID:
        await update.message.reply_text(
            "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni (rasm, video yoki matn) yuboring.\n"
            "Bekor qilish uchun /cancel yozing yoki istalgan menyu tugmasini bosing.")
        return BROADCAST

    elif text == BTN_BACK:
        await update.message.reply_text("Asosiy menyuga qaytdingiz:", reply_markup=get_main_menu(user_id))

    else:
        await update.message.reply_text("Kechirasiz, bu buyruq tushunarsiz. Iltimos, tugmalardan foydalaning. 😊",
                                        reply_markup=get_main_menu(user_id))

    return ConversationHandler.END


# --- QIDIRUV JARAYONI ---
async def search_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text

    # Agar qidiruv paytida boshqa menyu tugmasi bosib yuborilsa
    if query_text in MENU_BUTTONS:
        return await handle_message(update, context)

    conn = db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM products WHERE name LIKE ?", (f"%{query_text}%",))
    products = cursor.fetchall()
    conn.close()

    if not products:
        await update.message.reply_text("❌ Bunday nomdagi mahsulot topilmadi.",
                                        reply_markup=get_main_menu(update.effective_user.id))
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(f"{p[1]} — {p[2]:,.0f} so'm", callback_data=f"prod_{p[0]}")] for p in products]
    await update.message.reply_text("🔍 Qidiruv natijalari:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END


# --- RASSILKA JARAYONI ---
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return ConversationHandler.END

    # Menyu tugmasi bosilsa, xabar hech kimga yuborilmaydi (tasodifan tarqatib yubormaslik uchun)
    if (update.message.text or "") in MENU_BUTTONS:
        return await handle_message(update, context)

    conn = db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    success = 0
    fail = 0

    status_msg = await update.message.reply_text("⏳ Xabar barcha foydalanuvchilarga tarqatilmoqda...")

    for row in users:
        u_id = row[0]
        try:
            await context.bot.copy_message(chat_id=u_id, from_chat_id=update.effective_chat.id,
                                           message_id=update.message.message_id)
            success += 1
        except Exception as e:
            log.warning("Rassilka %s ga yetmadi: %s", u_id, e)
            fail += 1
        await asyncio.sleep(0.05)  # Telegram tezlik chegarasidan oshmaslik uchun

    await status_msg.edit_text(
        f"✅ Rassilka yakunlandi!\n\n"
        f"• Muvaffaqiyatli yuborildi: {success} ta\n"
        f"• Xatolik (botni bloklaganlar): {fail} ta"
    )

    await update.message.reply_text("Admin panel:", reply_markup=get_admin_menu())
    return ConversationHandler.END


async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = get_admin_menu() if update.effective_user.id == ADMIN_ID else get_main_menu(update.effective_user.id)
    await update.message.reply_text("Bekor qilindi.", reply_markup=reply_markup)
    return ConversationHandler.END


# --- INLINE TUGMALAR ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    if data.startswith("cat_"):
        cat_id = data.split("_")[1]
        conn = db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, price FROM products WHERE category_id = ?", (cat_id,))
        products = cursor.fetchall()
        conn.close()

        if not products:
            await query.edit_message_text("Bu kategoriyada hozircha mahsulot yo'q.")
            return

        keyboard = [[InlineKeyboardButton(f"{p[1]} — {p[2]:,.0f} so'm", callback_data=f"prod_{p[0]}")] for p in products]
        keyboard.append([InlineKeyboardButton("🔙 Kategoriyalarga qaytish", callback_data="back_to_cats")])
        await query.edit_message_text("Mahsulotni tanlang:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "back_to_cats":
        conn = db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM categories")
        categories = cursor.fetchall()
        conn.close()

        keyboard = [[InlineKeyboardButton(cat[1], callback_data=f"cat_{cat[0]}")] for cat in categories]
        await query.edit_message_text("Mavjud kategoriyalardan birini tanlang:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("prod_"):
        prod_id = data.split("_")[1]
        conn = db()
        cursor = conn.cursor()
        cursor.execute("SELECT name, price, description FROM products WHERE id = ?", (prod_id,))
        prod = cursor.fetchone()
        conn.close()

        if not prod:
            await query.edit_message_text("Bu mahsulot topilmadi.")
            return

        text = f"📦 {prod[0]}\n\nNarxi: {prod[1]:,.0f} so'm\nTavsif: {prod[2]}"
        keyboard = [
            [InlineKeyboardButton("🛒 Savatchaga qo'shish", callback_data=f"add_{prod_id}")],
            [InlineKeyboardButton("🔙 Ortga", callback_data="back_to_cats")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("add_"):
        prod_id = data.split("_")[1]
        user_id = user.id

        conn = db()
        cursor = conn.cursor()
        cursor.execute("SELECT quantity FROM cart WHERE user_id = ? AND product_id = ?", (user_id, prod_id))
        item = cursor.fetchone()
        if item:
            cursor.execute("UPDATE cart SET quantity = quantity + 1 WHERE user_id = ? AND product_id = ?", (user_id, prod_id))
        else:
            cursor.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, 1)", (user_id, prod_id))
        conn.commit()
        conn.close()

        await query.message.reply_text("Mahsulot savatchaga qo'shildi! ✅")

    elif data == "checkout":
        user_id = user.id
        conn = db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.name, p.price, c.quantity FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = ?
        """, (user_id,))
        items = cursor.fetchall()

        if not items:
            await query.message.reply_text("Savatchangiz bo'sh!")
            conn.close()
            return

        order_text = "🚨 YANGI BUYURTMA!\n\n"
        order_text += f"👤 Mijoz: {user.full_name} (@{user.username if user.username else 'yo‘q'})\n"
        order_text += f"🆔 ID: {user.id}\n\n"

        total = 0
        for item in items:
            subtotal = item[1] * item[2]
            total += subtotal
            order_text += f"• {item[0]} — {item[2]} dona x {item[1]:,.0f} so'm = {subtotal:,.0f} so'm\n"

        order_text += f"\n💰 Umumiy summa: {total:,.0f} so'm\n"
        order_text += "⏰ Yetkazib berish vaqti: 1 soat ichida bog'laniladi."

        cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

        try:
            # Adminga xabar yuborish (oddiy matn ko'rinishida)
            await context.bot.send_message(chat_id=ADMIN_ID, text=order_text)
        except Exception as e:
            log.error("Admin uchun xabar yuborishda xatolik: %s", e)

        await query.message.reply_text(
            "✅ Buyurtmangiz qabul qilindi!\n\n"
            "⏰ Operatorimiz belgilangan vaqt ichida (1 soat ichida) siz bilan bog'lanadi. Rahmat! 🎉"
        )

    elif data.startswith("lang_"):
        lang = data.split("_")[1].upper()
        conn = db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user.id))
        conn.commit()
        conn.close()
        await query.message.reply_text(f"✅ Til muvaffaqiyatli o'zgartirildi: {lang}")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error("Xatolik yuz berdi:", exc_info=context.error)


# --- ASOSIY QISM ---
def main():
    if not TOKEN:
        raise SystemExit("BOT_TOKEN topilmadi. Render'da Environment bo'limiga BOT_TOKEN ni qo'shing.")
    if not ADMIN_ID:
        log.warning("ADMIN_ID sozlanmagan: admin panel va buyurtma xabarlari ishlamaydi.")

    init_db()
    keep_alive()

    app_bot = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        ],
        states={
            BROADCAST: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_message)],
            SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_products)]
        },
        fallbacks=[CommandHandler("start", start), CommandHandler("cancel", cancel_broadcast)],
        allow_reentry=True,
    )

    app_bot.add_handler(CommandHandler("help", help_command))
    app_bot.add_handler(conv_handler)
    app_bot.add_handler(CallbackQueryHandler(button_handler))
    app_bot.add_error_handler(on_error)

    log.info("Bot ishga tushdi, Telegram'dan xabarlar kutilmoqda...")
    # drop_pending_updates: qayta ishga tushganda eski, to'planib qolgan bosishlarga javob bermaydi
    app_bot.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
