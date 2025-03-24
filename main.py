import asyncio
from datetime import datetime
from os import getenv
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from validation import form_correctslinks
from update import get_schedule


load_dotenv() # получаю значение токена из специального файла
TOKEN = getenv("BOT_TOKEN")
dp = Dispatcher()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s") # устанавливаю логгирование
logger = logging.getLogger(__name__)
bot = Bot(token=TOKEN)



kb = ReplyKeyboardMarkup( # Создаем кнопки
    keyboard=[
        [KeyboardButton(text="Помощь"), KeyboardButton(text="О нас")],
        [KeyboardButton(text="Контакты")]
    ],
    resize_keyboard=True
)


@dp.message(Command("start")) # Command handler
async def command_start_handler(message: Message) -> None:
    await message.answer("Привет! Я бот, который регулирует процесс очереди", reply_markup=kb)


@dp.message(Command("help")) # Функция для обработки команды /help
@dp.message(lambda message: message.text == "Помощь")  # Обрабатываем и "Помощь"
async def send_help(message: Message):
    await message.answer("ААААА!")



@dp.message() # Функция для обработки любого текстового сообщения
async def echo_message(message: Message):
    await message.answer(f"Вы написали: {message.text}")


async def main() -> None: # Run the bot
    scheduler = AsyncIOScheduler()
    scheduler.add_job(form_correctslinks, 'cron', hour=15, minute=15)
    scheduler.add_job(get_schedule, 'cron', hour=0, minute=30)
    # scheduler.add_job(get_schedule, 'cron', day=15, hour=0, minute=30) клин данных условно раз в месяц
    scheduler.add_job(form_correctslinks, 'cron', month=1, day=10, hour=0, minute=30)
    scheduler.add_job(form_correctslinks, 'cron', month=9, day=10, hour=0, minute=30)
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
