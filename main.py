import asyncio
from os import getenv
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
import logging


load_dotenv() # получаю значение токена из специального файла
TOKEN = getenv("BOT_TOKEN")
dp = Dispatcher()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s") # устанавливаю логгирование
logger = logging.getLogger(__name__)


kb = ReplyKeyboardMarkup( # Создаем кнопки
    keyboard=[
        [KeyboardButton(text="Помощь"), KeyboardButton(text="О нас")],
        [KeyboardButton(text="Контакты")]
    ],
    resize_keyboard=True
)


@dp.message(Command("start")) # Command handler
async def command_start_handler(message: Message) -> None:
    await message.answer("Привет! Я бот, который регулирует процесс очереди, а также предоставляет возможность оставлять рецензии", reply_markup=kb)


@dp.message(Command("help")) # Функция для обработки команды /help
@dp.message(lambda message: message.text == "Помощь")  # Обрабатываем и "Помощь"
async def send_help(message: Message):
    await message.answer("ААААА!")



@dp.message() # Функция для обработки любого текстового сообщения
async def echo_message(message: Message):
    await message.answer(f"Вы написали: {message.text}")


async def main() -> None: # Run the bot
    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())