import requests
from icalendar import Calendar
from datetime import datetime, timedelta
import asyncio
from os import getenv
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from validation import form_correctslinks
# from update import get_schedule
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

def dindin():
    # заглушка для реализации обработки начала занятия
    # возможно, вызывать вторую такую функция для обработки конца занятия (удаление строк с данными), если занятие состоялось (очередь сформирвоалось), настроить это здесь
    #scheduler.add_job(dindin, 'cron', month=start_date.month, day=start_date.day, hour=start_date.hour, minute=start_date.minute) многоразово
    #scheduler.add_job(dindin, 'date', run_date=start_date)  одноразово
    pass


kb = ReplyKeyboardMarkup( # Создаем кнопки
    keyboard=[
        [KeyboardButton(text="Помощь"), KeyboardButton(text="О нас")],
        [KeyboardButton(text="Контакты")]
    ],
    resize_keyboard=True
)


async def refresh_schedule():
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    groups = cursor.execute("SELECT GroupName FROM All_groups").fetchall()  # Получаем все строки в виде списка кортежей
    for group in groups:
        group_name = group[0]
        url = cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (group_name,)).fetchone()[0]
        await get_schedule(url, group_name)
    conn.close()



async def get_schedule(url, groupName):
    response = requests.get(url, timeout=5)
    if response.status_code == 200:
        data = response.json()
        schedule_info = data["pageProps"]["scheduleLoadInfo"]
        if schedule_info:
            schedule_info = schedule_info[0]
            groups = schedule_info["title"]
            schedule = schedule_info["iCalContent"]
            realschedule = Calendar.from_ical(schedule)
            for component in realschedule.walk():
                if component.name == "VEVENT":
                    dtstart = component.get('dtstart').dt
                    dtend = component.get('dtend').dt
                    summary = component.get('summary').replace('ПР ', "", 1)
                    description = str(component.get('description'))
                    location = component.get('location')
                    if description:
                        test = description.split('\n')
                        if len(test) == 2:
                            teacher_fio = test[0].replace('Преподаватель: ', '')
                            # Передаём даты в виде объектов datetime
                            await generate_schedule(dtstart.replace(tzinfo=None), dtend.replace(tzinfo=None), summary,
                                                    teacher_fio, location, groupName)
    else:
        print(f"⚠ Ошибка {response.status_code} для {url}")


async def generate_schedule(start_date, end_date, description, teacher, location, groupName):
    # Определяем конец семестра
    current_date = datetime.now()
    if current_date.month > 1:  # Если после января, конец семестра - май
        end_of_semester = datetime(current_date.year, 5, 31)
    else:
        end_of_semester = datetime(current_date.year, 9, 30)
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    # Генерируем расписание
    while start_date <= end_of_semester:
        if current_date <= start_date:
            exists = cursor.execute("""
                            SELECT 1 FROM TIMETABLE 
                            WHERE GroupName = ? AND TeacherFIO = ? AND TASK = ? 
                            AND MONTH = ? AND DAY = ? AND HOUR = ? AND MINUTE = ? AND LOCATION = ?
                        """, (
            groupName, teacher, description, start_date.month, start_date.day, start_date.hour, start_date.minute,
            location)).fetchone()
            if not exists:
                cursor.execute("""
                INSERT INTO TIMETABLE (GroupName, TeacherFIO, TASK, MONTH, DAY, HOUR, MINUTE, LOCATION) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (groupName, teacher, description, start_date.month, start_date.day, start_date.hour, start_date.minute, location)
                )
                conn.commit()
                scheduler.add_job(dindin, 'date', run_date=start_date)
            break
        # Добавляем 2 недели
        start_date += timedelta(weeks=2)
        end_date += timedelta(weeks=2)
    conn.commit()


@dp.message(Command("stop")) # Command handler
async def command_start_handler(message: Message) -> None:
    user_id = message.from_user.id
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    Group = cursor.execute("SELECT GroupName FROM Users WHERE ID = ?", (user_id,)).fetchone()[0]
    Count = len(cursor.execute("SELECT ID FROM Users WHERE GroupName = ?", (Group,)).fetchall())
    cursor.execute("DELETE FROM Users WHERE ID = ?", (user_id,))
    if Count == 1:
        cursor.execute("DELETE FROM All_groups WHERE GroupName = ?", (Group,))
        cursor.execute("DELETE FROM Timetable WHERE GroupName = ?", (Group,))
        await message.answer("Группа распущена")
    conn.commit()
    conn.close()
    await message.answer("Очень жаль с вами расставаться, юзер")


@dp.message(Command("start")) # Command handler
async def command_start_handler(message: Message) -> None:
    await message.answer("Привет! Я бот, который регулирует процесс очереди", reply_markup=kb)


@dp.message(Command("help")) # Функция для обработки команды /help
@dp.message(lambda message: message.text == "Помощь")  # Обрабатываем и "Помощь"
async def send_help(message: Message):
    await message.answer("ААААА! Альтушкааааа")



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
    Name = cursor.execute("SELECT Name FROM Users WHERE ID = ?", (user_id,)).fetchone()
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
    url = cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (message.text.upper(),)).fetchone()
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
    exists = cursor.execute("SELECT 1 FROM All_groups WHERE GroupName = ?", (user_data['group'],)).fetchone()
    if not exists: # подгрузить расписание
        cursor.execute("""INSERT INTO All_groups (GroupName) VALUES (?)""", (user_data['group'],))
        conn.commit()
        cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (user_data['group'],))
        url = cursor.fetchone()[0]
        await get_schedule(url, user_data['group'])
    conn.close()
    await message.answer("✅ Регистрация завершена!")
    await state.clear()


@dp.message() # Функция для обработки любого текстового сообщения
async def echo_message(message: Message):
    await message.answer(f"Вы написали: {message.text}")


async def main() -> None: # Run the bot
    scheduler.add_job(form_correctslinks, 'cron', hour=15, minute=15)
    scheduler.add_job(refresh_schedule, day_of_week='sun', trigger='cron', hour=0, minute=30)
    scheduler.add_job(form_correctslinks, 'cron', month=1, day=10, hour=0, minute=30)
    scheduler.add_job(form_correctslinks, 'cron', month=9, day=10, hour=0, minute=30)
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
