import asyncio
from datetime import datetime
from os import getenv
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from validation import form_correctslinks
from update import get_schedule
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from update import generate_schedule
import sqlite3

load_dotenv() # получаю значение токена из специального файла
TOKEN = getenv("BOT_TOKEN")
dp = Dispatcher()
scheduler = AsyncIOScheduler()
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


def dindin():
    # заглушка для реализации
    pass

# Определяем состояния для FSM
class RegisterState(StatesGroup):
    group = State()
    name = State()
    surname = State()
    middle_name = State()


# Обработчик команды /register
@dp.message(Command("register"))
async def register(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    cursor.execute("SELECT Name FROM Users WHERE ID = ?", (user_id,))
    Name = cursor.fetchone()
    if not Name:
        await message.answer("Введите вашу группу:")
        await state.set_state(RegisterState.group)
    else:
        await message.answer(f"Вы уже зарегистрированы, {Name[0]}.")
    conn.close()


@dp.message(RegisterState.group) # Обработка ввода группы
async def process_group(message: types.Message, state: FSMContext):
    await state.update_data(group=message.text.upper())
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (message.text.upper(),))
    url = cursor.fetchone()
    conn.close()
    if not url:
        await message.answer("⚠ Ошибка: Такой группы не существует. Попробуйте еще раз.")
        await state.clear()
        return
    await message.answer("Введите ваше имя:")
    await state.set_state(RegisterState.name)



@dp.message(RegisterState.name) # Обработка ввода имени
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.capitalize())
    await message.answer("Введите вашу фамилию:")
    await state.set_state(RegisterState.surname)



@dp.message(RegisterState.surname) # Обработка ввода фамилии
async def process_surname(message: types.Message, state: FSMContext):
    await state.update_data(surname=message.text.capitalize())
    await message.answer("Введите ваше отчество (если нет, напишите '-'): ")
    await state.set_state(RegisterState.middle_name)


@dp.message(RegisterState.middle_name) # Обработка ввода отчества и сохранение в БД
async def process_middle_name(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    middle_name = message.text.capitalize() if message.text != "-" else None
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Users (ID, GroupName, NAME, SURNAME, MIDDLE_NAME) 
        VALUES (?, ?, ?, ?, ?)""",
                   (message.from_user.id, user_data['group'], user_data['name'], user_data['surname'], middle_name)
                   )
    conn.commit()
    cursor.execute("SELECT 1 FROM Timetable WHERE GroupName = ?", (user_data['group'],))
    exists = cursor.fetchone()
    if not exists: # подгрузить расписание
        get_schedule(user_data['group'])

    conn.close()

    await message.answer("✅ Регистрация завершена!")
    await state.clear()


@dp.message() # Функция для обработки любого текстового сообщения
async def echo_message(message: Message):
    scheduler.add_job(dindin, 'cron', hour=20, minute=2)
    await message.answer(f"Вы написали: {message.text}")


async def main() -> None: # Run the bot
    scheduler.add_job(form_correctslinks, 'cron', hour=15, minute=15)
    #scheduler.add_job(get_schedule, 'cron', hour=0, minute=30)
    # scheduler.add_job(get_schedule, 'cron', day=15, hour=0, minute=30) клин данных условно раз в месяц
    scheduler.add_job(form_correctslinks, 'cron', month=1, day=10, hour=0, minute=30)
    scheduler.add_job(form_correctslinks, 'cron', month=9, day=10, hour=0, minute=30)
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
