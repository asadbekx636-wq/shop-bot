import asyncio
import os
import logging
from collections import defaultdict, deque

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
import google.generativeai as genai

# Konsolda xatoliklar va jarayonni kuzatib borish uchun sozlama
logging.basicConfig(level=logging.INFO)

# 1. .env faylidan maxfiy kalitlarni o'qib olamiz
load_dotenv()
BOT_TOKEN = os.getenv("8863172445:AAHK4J68HyVhqCBdxc811yzEcjWM_5atdaw")
GEMINI_API_KEY = os.getenv("")

# Kalitlar to'ldirilganligini tekshiramiz
if not BOT_TOKEN or not GEMINI_API_KEY:
    raise ValueError("BOT_TOKEN yoki GEMINI_API_KEY .env faylida topilmadi!")

# 2. Gemini API ni sozlaymiz
genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = (
    "Sen o'zbek tilida gaplashadigan tushuntiruvchi o'quv yordamchisan. "
    "Avval qisqa tushuntir, keyin hayotiy misol keltir, oxirida qadamma-qadam izohla. "
    "Masalalarni bosqichma-bosqich yech. O'quvchini kamsitma. Bilmagan narsangni o'ylab topma."
)

# Gemini modelini yaratamiz
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=SYSTEM_INSTRUCTION
)

# 3. Har bir foydalanuvchining muloqot tarixini xotirada saqlash (Oxirgi 10 ta xabar)
user_history = defaultdict(lambda: deque(maxlen=10))

# 4. Telegram bot va dispetcherni ishga tushiramiz
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# 5. /start buyrug'i bosilganda ishlaydigan funksiya
@dp.message(CommandStart())
async def send_welcome(message: types.Message):
    welcome_text = (
        "Assalomu alaykum! Men sizning o'zbek tilidagi tushuntiruvchi o'quv yordamchingizman. 🎓\n\n"
        "Istalgan fan yoki dasturlash bo'yicha savolingizni yozing, "
        "men uni sodda va tushunarli qilib tushuntirib beraman!"
    )
    # Yangi suhbat boshlanganda eski tarix tozalanadi
    user_history[message.from_user.id].clear()
    await message.answer(welcome_text)


# 6. Telegram'ning 4096 belgi chegarasidan uzun javoblarni bo'lib yuboruvchi yordamchi funksiya
async def send_long_message(message: types.Message, text: str):
    MAX_LENGTH = 4096
    for i in range(0, len(text), MAX_LENGTH):
        await message.answer(text[i:i + MAX_LENGTH])


# 7. Kelgan barcha matnli xabarlarni qayta ishlovchi qism
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text

    # Xotiradagi oldingi xabarlar va yangi savolni Gemini'ga uzatish uchun tayyorlaymiz
    contents = list(user_history[user_id])
    contents.append({"role": "user", "parts": [user_text]})

    # Bot "o'ylayotgani" (typing) holatini ko'rsatib turamiz
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        # Gemini API dan javob olish
        response = await asyncio.to_thread(
            model.generate_content,
            contents
        )
        
        reply_text = response.text

        # Muloqot tarixini yangilab qo'yamiz
        user_history[user_id].append({"role": "user", "parts": [user_text]})
        user_history[user_id].append({"role": "model", "parts": [reply_text]})

        # Javobni foydalanuvchiga yuboramiz
        await send_long_message(message, reply_text)

    except Exception as e:
        logging.error(f"Gemini API xatoligi: {e}")
        await message.answer("Hozir javob bera olmadim, keyinroq urinib ko'ring.")


# 8. Botni ishga tushirish jarayoni
async def main():
    logging.info("Bot ishga tushmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
