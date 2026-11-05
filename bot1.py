import os
from flask import Flask
from threading import Thread
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# --- SOZLAMALAR VA ADMIN ID ---
ADMIN_ID = 7161851696  # <--- O'z Telegram ID raqamingizni shu yerga yozing!

# --- RENDER PORT TALABINI BAJARISH UCHUN FLASK SERVER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()


# --- MA'LUMOTLAR BAZASI BILAN ISHLASH ---
def init_db():
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    # Kategoriyalar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)
    # Mahsulotlar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            description TEXT
        )
    """)
    # Savatcha jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            user_id INTEGER,
            product_id INTEGER,
            quantity INTEGER
        )
    """)
    # Dastlabki ma'lumotlar (agar bo'sh bo'lsa)
    cursor.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO categories (name) VALUES ('Telefonlar'), ('Noutbuklar')")
        cursor.execute(
            "INSERT INTO products (category_id, name, price, description) VALUES (1, 'iPhone 15 Pro', 12000000, 'Yangi holatda, 256GB')"
        )
        cursor.execute(
            "INSERT INTO products (category_id, name, price, description) VALUES (2, 'MacBook Air M2', 14000000, 'Tezkor va yengil')"
        )
    conn.commit()
    conn.close()

init_db()


# --- ASOSIY MENYU (Tugmalar) ---
def get_main_menu(user_id):
    keyboard = [
        [KeyboardButton("🛍 Do'kon"), KeyboardButton("🛒 Savatcham")],
        [KeyboardButton("📋 Buyurtmalarim"), KeyboardButton("ℹ️ Biz haqimizda")],
        [KeyboardButton("📞 Admin bilan bog'lanish")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton("🛠 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# --- 1. /START BUYRUG'I ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Assalomu alaykum, {user.first_name}! Online Do'konimizga xush kelibsiz. 🚀\n"
        "Kerakli bo'limni pastdagi tugmalar orqali tanlang:",
        reply_markup=get_main_menu(user.id)
    )


# --- 2. MATNli XABARLAR VA BO'LIMLAR (SHARTLAR) ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "🛍 Do'kon":
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM categories")
        categories = cursor.fetchall()
        conn.close()

        keyboard = [[InlineKeyboardButton(cat[1], callback_data=f"cat_{cat[0]}")] for cat in categories]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Mavjud kategoriyalardan birini tanlang:", reply_markup=reply_markup)

    elif text == "🛒 Savatcham":
        conn = sqlite3.connect("shop.db")
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
            text_msg = "🛒 **Sizning savatchangiz:**\n\n"
            total = 0
            for item in items:
                subtotal = item[1] * item[2]
                total += subtotal
                text_msg += f"• {item[0]} - {item[2]} dona x {item[1]:,.0f} so'm = {subtotal:,.0f} so'm\n"
            text_msg += f"\n**Umumiy summa:** {total:,.0f} so'm"

            keyboard = [[InlineKeyboardButton("✅ Buyurtmani rasmiylashtirish", callback_data="checkout")]]
            await update.message.reply_text(
                text_msg, 
                reply_markup=InlineKeyboardMarkup(keyboard), 
                parse_mode="Markdown"
            )

    elif text == "ℹ️ Biz haqimizda":
        await update.message.reply_text(
            "Bizning online do'kon eng sifatli texnika va gadjetlarni eng qulay narxlarda taqdim etadi! 🏢"
        )

    elif text == "📞 Admin bilan bog'lanish":
        await update.message.reply_text("Savollar bo'yicha adaminga murojaat qiling: @admin_username")

    elif text == "🛠 Admin Panel" and user_id == ADMIN_ID:
        await update.message.reply_text("Xush kelibsiz, Admin! Bu yerda do'konni boshqarishingiz mumkin.")

    else:
        await update.message.reply_text(f"Siz yozdingiz: '{text}'. Iltimos, menyudagi tugmalardan foydalaning! 😊")


# --- 3. TUGMALAR (INLINE) BILAN ISHLASH ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("cat_"):
        cat_id = data.split("_")[1]
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, price FROM products WHERE category_id = ?", (cat_id,))
        products = cursor.fetchall()
        conn.close()

        if not products:
            await query.edit_message_text("Bu kategoriyada hozircha mahsulot yo'q.")
            return

        keyboard = [[InlineKeyboardButton(f"{p[1]} — {p[2]:,.0f} so'm", callback_data=f"prod_{p[0]}")] for p in products]
        await query.edit_message_text("Mahsulotni tanlang:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("prod_"):
        prod_id = data.split("_")[1]
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name, price, description FROM products WHERE id = ?", (prod_id,))
        prod = cursor.fetchone()
        conn.close()

        text = f"📦 **{prod[0]}**\n\nNarxi: {prod[1]:,.0f} so'm\nTavsif: {prod[2]}"
        keyboard = [[InlineKeyboardButton("🛒 Savatchaga qo'shish", callback_data=f"add_{prod_id}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("add_"):
        prod_id = data.split("_")[1]
        user_id = query.from_user.id

        conn = sqlite3.connect("shop.db")
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
        await query.message.reply_text("Buyurtmangiz qabul qilindi! Operator tez orada siz bilan bog'lanadi. Rahmat! 🎉")


# --- ASOSIY QISM ---
if __name__ == '__main__':
    # Flask veb-serverni fonda ishga tushiramiz (Render port talabini qondirish uchun)
    keep_alive()

    # Tokeningiz
    TOKEN = "8569615512:AAEz4pDDF5rFL3bpw3IfuOCTDNY49jjItEI"

    app_bot = ApplicationBuilder().token(TOKEN).build()

    # Handlers (Ulovchilar)
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CallbackQueryHandler(button_handler))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Online Do'kon boti muvaffaqiyatli ishga tushdi...")
    app_bot.run_polling()
