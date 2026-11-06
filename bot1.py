import os
from flask import Flask
from threading import Thread
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters

# --- SOZLAMALAR VA ADMIN ID ---
ADMIN_ID = 7161851696  # <--- O'z Telegram ID raqamingizni shu yerga yozing! (Faqat raqam)

# Rassilka uchun bosqich (State)
BROADCAST = 1

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


# --- MA'LUMOTLAR BAZASI BILAN ISHLASH (Kengaytirilgan do'kon) ---
def init_db():
    conn = sqlite3.connect("shop.db")
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
            user_id INTEGER PRIMARY KEY
        )
    """)
    
    # Dastlabki kategoriyalar va mahsulotlar
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

init_db()


# --- ASOSIY MENYU ---
def get_main_menu(user_id):
    keyboard = [
        [KeyboardButton("🛍 Do'kon"), KeyboardButton("🛒 Savatcham")],
        [KeyboardButton("📋 Buyurtmalarim"), KeyboardButton("ℹ️ Biz haqimizda")],
        [KeyboardButton("📞 Admin bilan bog'lanish")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton("🛠 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_menu():
    keyboard = [
        [KeyboardButton("👥 Statistika"), KeyboardButton("📢 Xabar yuborish")],
        [KeyboardButton("🔙 Asosiy menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# --- /START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user.id,))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"Assalomu alaykum, {user.first_name}! Online Do'konimizga xush kelibsiz. 🚀\n"
        "Kerakli bo'limni pastdagi tugmalar orqali tanlang:",
        reply_markup=get_main_menu(user.id)
    )


# --- MATNLI XABARLARNI BOSHQARISH ---
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

    elif text == "📋 Buyurtmalarim":
        await update.message.reply_text("Sizda hozircha faol buyurtmalar yo'q. 😊")

    elif text == "ℹ️ Biz haqimizda":
        await update.message.reply_text(
            "Salom! Bu onlayn do'kon boti bo'lib, xaridlaringizni qulay amalga oshirish uchun yaratilgan. 🏢"
        )

    elif text == "📞 Admin bilan bog'lanish":
        await update.message.reply_text("Savollar bo'yicha adaminga murojaat qiling: Tel: 9986194040")

    elif text == "🛠 Admin Panel" and user_id == ADMIN_ID:
        await update.message.reply_text("Xush kelibsiz, Admin! Kerakli bo'limni tanlang:", reply_markup=get_admin_menu())

    elif text == "👥 Statistika" and user_id == ADMIN_ID:
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM products")
        total_products = cursor.fetchone()[0]
        conn.close()

        await update.message.reply_text(
            f"📊 **Bot statistikasi:**\n\n"
            f"👥 Jami foydalanuvchilar: {total_users} ta\n"
            f"📦 Jami mahsulotlar: {total_products} ta",
            parse_mode="Markdown"
        )

    elif text == "📢 Xabar yuborish" and user_id == ADMIN_ID:
        await update.message.reply_text("Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni (rasm, video yoki matn) yuboring:")
        return BROADCAST

    elif text == "🔙 Asosiy menyu":
        await update.message.reply_text("Asosiy menyuga qaytdingiz:", reply_markup=get_main_menu(user_id))

    else:
        await update.message.reply_text(f"Kechirasiz, bu buyruq tushunarsiz. Iltimos, tugmalardan foydalaning. 😊", reply_markup=get_main_menu(user_id))

    return ConversationHandler.END


# --- RASSILKA JARAYONI (Rasm, video va matnlar uchun) ---
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return ConversationHandler.END

    conn = sqlite3.connect("shop.db")
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
            # Admin yuborgan matn, rasm yoki videoni barchaga nusxalaymiz
            await update.message.copy_to(chat_id=u_id)
            success += 1
        except Exception:
            fail += 1

    await status_msg.edit_text(
        f"✅ **Rassilka yakunlandi!**\n\n"
        f"• Muvaffaqiyatli yuborildi: {success} ta\n"
        f"• Xatolik (botni bloklaganlar): {fail} ta",
        parse_mode="Markdown"
    )

    await update.message.reply_text("Admin panel:", reply_markup=get_admin_menu())
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi.", reply_markup=get_admin_menu())
    return ConversationHandler.END


# --- INLINE TUGMALAR VA BUYURTMA QILISH ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

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
        keyboard.append([InlineKeyboardButton("🔙 Kategoriyalarga qaytish", callback_data="back_to_cats")])
        await query.edit_message_text("Mahsulotni tanlang:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "back_to_cats":
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM categories")
        categories = cursor.fetchall()
        conn.close()

        keyboard = [[InlineKeyboardButton(cat[1], callback_data=f"cat_{cat[0]}")] for cat in categories]
        await query.edit_message_text("Mavjud kategoriyalardan birini tanlang:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("prod_"):
        prod_id = data.split("_")[1]
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name, price, description FROM products WHERE id = ?", (prod_id,))
        prod = cursor.fetchone()
        conn.close()

        text = f"📦 **{prod[0]}**\n\nNarxi: {prod[1]:,.0f} so'm\nTavsif: {prod[2]}"
        keyboard = [
            [InlineKeyboardButton("🛒 Savatchaga qo'shish", callback_data=f"add_{prod_id}")],
            [InlineKeyboardButton("🔙 Ortga", callback_data=f"back_to_cat")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("add_"):
        prod_id = data.split("_")[1]
        user_id = user.id

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
        user_id = user.id
        conn = sqlite3.connect("shop.db")
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

        order_text = f"🚨 **YANGI BUYURTMA!**\n\n"
        order_text += f"👤 Mijoz: {user.full_name} (@{user.username if user.username else 'yo‘q'})\n"
        order_text += f"🆔 ID: `{user.id}`\n\n"
        
        total = 0
        for item in items:
            subtotal = item[1] * item[2]
            total += subtotal
            order_text += f"• {item[0]} — {item[2]} dona x {item[1]:,.0f} so'm = {subtotal:,.0f} so'm\n"
        
        order_text += f"\n💰 **Umumiy summa:** {total:,.0f} so'm\n"
        order_text += f"⏰ **Yetkazib berish vaqti:** 1 soat ichida bog'laniladi."

        cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=order_text, parse_mode="Markdown")
        except Exception as e:
            print(f"Admin uchun xabar yuborishda xatolik: {e}")

        await query.message.reply_text(
            "✅ **Buyurtmangiz qabul qilindi!**\n\n"
            "⏰ Operatorimiz belgilangan vaqt ichida (1 soat ichida) siz bilan bog'lanadi. Rahmat! 🎉",
            parse_mode="Markdown"
        )


# --- ASOSIY QISM ---
if __name__ == '__main__':
    keep_alive()

    TOKEN = "8569615512:AAEz4pDDF5rFL3bpw3IfuOCTDNY49jjItEI"

    app_bot = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
        states={
            # filters.ALL yordamida rasm, video va har qanday xabarni qabul qilish ta'minlandi
            BROADCAST: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_message)]
        },
        fallbacks=[CommandHandler("cancel", cancel_broadcast)]
    )

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CallbackQueryHandler(button_handler))
    app_bot.add_handler(conv_handler)

    print("Online Do'kon boti muvaffaqiyatli ishga tushdi...")
    app_bot.run_polling()
