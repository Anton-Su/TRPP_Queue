from datetime import datetime
from os import getenv
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from validation import form_correctslinks, get_link_with_current_hash
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from schedule import refresh_schedule, get_schedule
from deletion import delete_old_sessions
import sqlite3
import logging
import asyncio


load_dotenv() # получаю значение токена из специального файла
TOKEN = getenv("BOT_TOKEN")
DATABASE_NAME = getenv("DATABASE_NAME")
dp = Dispatcher()
scheduler = AsyncIOScheduler()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s") # устанавливаю логгирование
logger = logging.getLogger(__name__)
bot = Bot(token=TOKEN)
kbregister = ReplyKeyboardMarkup( # Создаем кнопку, которую видит только зарегистрированный пользователь
    keyboard=[
        [KeyboardButton(text="Помощь"), KeyboardButton(text="Выйти")],
        [KeyboardButton(text="Забронировать"), KeyboardButton(text="Cтатистика")]
    ], resize_keyboard=True, one_time_keyboard=False)
kbnotregister = ReplyKeyboardMarkup( # Создаем кнопку, которую видит только незарегистрированный пользователь
    keyboard=[
        [KeyboardButton(text="Помощь"), KeyboardButton(text="Регистрация")]
    ], resize_keyboard=True, one_time_keyboard=False)


class RegisterState(StatesGroup):
    """
    Класс состояний для регистрации пользователя в FSM (Finite State Machine).
    Содержит следующие состояния:
    - group: Ввод группы пользователя.
    - name: Ввод имени пользователя.
    - surname: Ввод фамилии пользователя.
    - middle_name: Ввод отчества пользователя.
    """
    group = State()
    name = State()
    surname = State()
    middle_name = State()


async def dindin():
    """
    Заглушка для обработки начала занятия.
    - Вызывается по расписанию в указанное время.
    """
    print("Пары в период такой-то начались")
    pass


async def dandalan():
    """
    Заглушка для обработки конца занятия.
    - Вызывается по расписанию через 90 (+10) минут после начала занятия.
    """
    print("Пары в период такой-то закончились")
    pass


async def generate_calendar(raspisanie): # Функция для генерации клавиатуры-календаря
    """
    Генерирует inline-клавиатуру с датами на основе переданного расписания.
    Возвращает Inline-клавиатуру с кнопками дат и кнопкой закрытия.
    """
    days_of_week = {
        "Monday": "Понедельник",
        "Tuesday": "Вторник",
        "Wednesday": "Среда",
        "Thursday": "Четверг",
        "Friday": "Пятница",
        "Saturday": "Суббота",
        "Sunday": "Воскресенье"
    }
    keyboard = []
    for raspisanieday in raspisanie:
        current_date = datetime.now()
        day = datetime(current_date.year, raspisanieday[0], raspisanieday[1])
        day_name = days_of_week[day.strftime("%A")]  # Получаем русское название
        button = InlineKeyboardButton(
            text=f"{day.strftime('%d.%m.%Y')} ({day_name})",
            callback_data=f"date_{day.strftime('%Y-%m-%d')}"
        )
        keyboard.append([button])
    keyboard.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="remove_keyboard")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def generatescheduler_to_currect_day(): # установка будильников на текущий день
    """
    Устанавливает будильники (запланированные задачи) на текущий день, используя расписание из базы данных.
    - Подключается к базе данных и получает время запланированных событий.
    - Проверяет, существуют ли уже задачи с таким временем.
    - Если задачи нет, создаёт две задачи:
    1. `dindin` запускается в указанное время.
    2. `dandalan` запускается через 90 минут после первой.
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    current_date = datetime.now()
    hour_minute = cursor.execute("SELECT DISTINCT Start_Hour, Start_Minute, End_Hour, End_Minute FROM Timetable WHERE Start_Month = ? AND Start_Day = ?",
                                 (current_date.month, current_date.day)).fetchall()  # Получаем все строки в виде списка кортежей
    if hour_minute:
        for start_hour, start_minute, end_hour, end_minute in hour_minute:
            existing_job = scheduler.get_job(f"{start_hour}_{start_minute}")
            if not existing_job: # если id такого не встречалось
                start_date = datetime(current_date.year, current_date.month, current_date.day, start_hour, start_minute)
                end_date = datetime(current_date.year, current_date.month, current_date.day, end_hour, end_minute)
                scheduler.add_job(dindin, 'date', run_date=start_date, id=f"{start_hour}_{start_minute}")
                scheduler.add_job(dandalan, 'date', run_date=end_date, id=f"{end_hour}_{end_minute}")


@dp.message(Command("stats")) # Команда посмотреть статистику
@dp.message(lambda message: message.text == "Cтатистика") # Обрабатываем и "Статистика"
async def command_start_handler(message: Message) -> None:
    """Обрабатывает команду /stats, отправляя пользователю его график записей."""
    user_id = message.from_user.id
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    results = []
    year = datetime.now().year
    # Запрос с динамическим расчетом актуальной позиции
    result = cursor.execute("""
        SELECT T.Task,  T.TeacherFIO, T.Start_Month, 
            T.Start_Day, T.Start_Hour, T.Start_Minute, 
            T.End_Hour,  T.End_Minute, T.Location,
            (
                SELECT COUNT(*) + 1
                FROM Ochered O2
                WHERE O2.Numseance = O.Numseance
                AND O2.Poryadok < O.Poryadok
            ) AS ActualPosition
        FROM Timetable T
        JOIN Ochered O ON T.Id = O.Numseance
        WHERE O.Id = ?
        ORDER BY T.Start_Month, T.Start_Day, T.Start_Hour, T.Start_Minute
    """, (user_id,)).fetchall()
    conn.close()
    for index, (subject, teacherfio, start_month, start_date, start_hour, start_minute,
                end_hour, end_minute, location, actual_position) in enumerate(result, start=1):
        # Форматирование даты и времени
        start_time = f"{str(start_date).rjust(2, '0')}.{str(start_month).rjust(2, '0')}.{year} " \
                     f"{str(start_hour).rjust(2, '0')}:{str(start_minute).rjust(2, '0')}"
        end_time = f"{str(end_hour).rjust(2, '0')}:{str(end_minute).rjust(2, '0')}"
        results.append(
            f"{index}. {actual_position} место в очереди, {start_time} - {end_time}*\n"
            f"«{subject}», проходит в «{location}», ведёт {teacherfio}"
        )
    if not result:
        return await message.answer("На данный момент вы не записаны ни на одно занятие")
    results.append("\n*Длительность занятия увеличена на 10 минут, чтобы учесть время перерыва")
    results.insert(0, f'Всего активных записей: {len(result)}')
    await message.answer("\n".join(results))


@dp.message(Command("exit"))  # Команда выйти из системы
@dp.message(lambda message: message.text == "Выйти")  # Обрабатываем и "Выйти"
async def command_start_handler(message: Message) -> None:
    """
    Обрабатывает выход пользователя из системы и удаляет его данные.
    - Удаляет пользователя из всех очередей (таблицы `Ochered`).
    - Удаляет пользователя из таблицы `Users`.
    - Если он был последним в группе, удаляет данные группы (`All_groups`, `Timetable`).
    """
    user_id = message.from_user.id
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    group = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,)).fetchone()[0]
    count = cursor.execute("SELECT COUNT(*) FROM Users WHERE GroupName = ?", (group,)).fetchone()[0]
    cursor.execute("DELETE FROM Ochered WHERE Id = ?", (user_id,))
    cursor.execute("DELETE FROM Users WHERE Id = ?", (user_id,))
    if count == 1: # Если он был последним участником группы, удаляем все данные группы
        cursor.execute("DELETE FROM All_groups WHERE GroupName = ?", (group,))
        cursor.execute("DELETE FROM Timetable WHERE GroupName = ?", (group,))
        await message.answer(f"Юзер, довожу до вашего сведения: с вашим уходом группа «{group}» распущена!")
    conn.commit()
    conn.close()
    await message.answer("😢😢😢Очень жаль с вами расставаться, Юзер, возвращайтесь поскорее!!!!!", reply_markup=kbnotregister)


@dp.message(Command("start")) # Начальная команда
async def command_start_handler(message: Message) -> None:
    """Обрабатывает команду /start, приветствует пользователя и предлагает зарегистрироваться."""
    await message.answer("Привет! Я бот, который регулирует процесс очереди, записываю, отписываю, слежу, и всё такое. Просто зарегистрируйся, и ты сможешь записываться на занятия, и больше не будешь полагаться на авось", reply_markup=kbnotregister)


@dp.message(Command("help")) # Функция для обработки команды /help
@dp.message(lambda message: message.text == "Помощь")  # Обрабатываем и "Помощь"
async def send_help(message: Message):
    """
    Обрабатывает команду /help, отправляет шуточное мотивационное сообщение.
    """
    #await message.answer("ААААА! Альтушкааааа в белых чулочкаааах", reply_markup=kbnotregister)
    await message.answer("Через 20 лет вы будете больше разочарованы теми вещами, которые вы не делали, чем теми, которые вы сделали. Так отчальте от тихой пристани. Почувствуйте попутный ветер в вашем парусе. Двигайтесь вперед, действуйте, открывайте!", reply_markup=kbnotregister)


@dp.callback_query(F.data.startswith("back_to_calendar_"))
async def back_to_calendar(callback: CallbackQuery):
    await show_calendar(user_id=callback.from_user.id, callback=callback)


async def show_calendar(user_id: int, message: types.Message = None, callback: CallbackQuery = None): #Универсальная функция для показа календаря (из команды и callback-запроса
    """
    Универсальная функция для отображения календаря пользователю.
    - Извлекает расписание (уникальные даты) из базы данных.
    - Генерирует интерактивную клавиатуру-календарь.
    - Отправляет или редактирует сообщение с календарем в зависимости от типа вызова (команда или callback-запрос).
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    group = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,)).fetchone()
    if not group:
        if message:
            return await message.answer("Вы не зарегистрированы!", reply_markup=kbnotregister)
        return await callback.answer("Вы не зарегистрированы!", reply_markup=kbnotregister)
    raspisanie = cursor.execute(
        "SELECT DISTINCT Start_Month, Start_Day FROM Timetable WHERE GroupName = ? ORDER BY Start_Month , Start_Day ",
        (group[0],)).fetchall()
    conn.close()
    keyboard = await generate_calendar(raspisanie)
    if message: # Определяем, как отправить сообщение
        await message.answer("Определитесь с датой:", reply_markup=keyboard)
    elif callback:
        await callback.message.edit_text("Определитесь с датой:", reply_markup=keyboard)


@dp.message(Command("record")) # команда записи/отмены записи
@dp.message(lambda message: message.text == "Забронировать") # обрабатываем и "Забронировать"
async def command_start_handler(message: types.Message) -> None:
    """Обрабатывает команду /record, вызывая функцию для отображения календаря."""
    await show_calendar(user_id=message.from_user.id, message=message)


@dp.callback_query(F.data.startswith("remove_keyboard"))
async def remove_keyboard(callback: CallbackQuery):
    """Удаляет inline-клавиатуру после нажатия на кнопку "удалить"."""
    await callback.message.delete()


@dp.callback_query(F.data.startswith("date_")) # Обработчик выбора даты
async def show_schedule(callback: CallbackQuery):
    """
    Обрабатывает выбор даты пользователем и отображает расписание на этот день.
    - Извлекает выбранную дату из callback-запроса.
    - Получает расписание занятий для данной группы на выбранную дату.
    - Генерирует кнопки с предметами, их временем и местом проведения.
    - Позволяет пользователю выбрать предмет или вернуться к календарю.
    """
    selected_date = callback.data.split("_")[1]  # Дата в формате YYYY-MM-DD
    user_id = callback.from_user.id
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    groupname = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,)).fetchone()[0] # Получаем группу пользователя
    subjects = cursor.execute("""SELECT Task, Start_Month, Start_Day, Start_Hour, 
    Start_Minute, Location FROM Timetable WHERE GroupName = ? AND Start_Month = ? AND Start_Day = ?""",
                              (groupname, selected_date.split("-")[1], selected_date.split("-")[2])).fetchall() # Получаем расписание на выбранную дату
    conn.close()
    keyboard = []
    for subject in subjects:
        task, month, day, hour, minute, location = subject
        # Формируем текст кнопки с названием предмета, временем и местом
        text = f"{location} {str(hour).rjust(2, '0')}:{str(minute).rjust(2, '0')} - {task}"
        button = InlineKeyboardButton(
            text=text[0:60],  # Реальные данные предмета
            callback_data=f"subject_{month}_{day}_{hour}_{minute}_{location}_{groupname}"  # Передаем в callback_data параметры
        )
        keyboard.append([button])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_calendar_{selected_date}")])
    keyboard.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="remove_keyboard")])
    await callback.message.edit_text("Выберите предмет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@dp.callback_query(F.data.startswith("subject_"))  # Обработчик выбора предмета
async def handle_subject(callback: CallbackQuery):
    """
    Обрабатывает выбор предмета пользователем.
    - Извлекает информацию о выбранном предмете из callback-запроса.
    - Определяет, записан ли пользователь на этот предмет.
    - Если записан, удаляет его из очереди.
    - Если не записан, добавляет его в очередь с новым порядковым номером.
    """
    _, month, day, hour, minute, location, groupname = callback.data.split("_")
    user_id = callback.from_user.id
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    numseance = cursor.execute("SELECT Id FROM Timetable WHERE GroupName = ? AND Start_Month = ? "
                               "AND Start_Day = ? AND Start_Hour = ? AND Start_Minute = ? AND Location = ?",
                               (groupname, month, day, hour, minute, location)).fetchone()[0]
    result = cursor.execute("""SELECT MAX(Poryadok) FROM Ochered WHERE numseance = ?""", (numseance,)).fetchone()
    if result[0] is not None:
        new_poryadok = result[0] + 1 # Если записи найдены, result[0] будет наибольшим Poryadok
    else:
        new_poryadok = 1
    if cursor.execute("SELECT 1 FROM Ochered WHERE Numseance = ? AND Id = ?", (numseance, user_id)).fetchone():
        cursor.execute("DELETE FROM Ochered WHERE Numseance = ? AND Id = ?", (numseance, user_id))
        conn.commit()
        conn.close()
        return await callback.answer("Запись отменена!")
    cursor.execute("""INSERT INTO Ochered (Numseance, Id, Poryadok) VALUES (?, ?, ?)""", (numseance, user_id, new_poryadok))
    conn.commit()
    await callback.answer(f"Успешно! Ваш номер в очереди: {cursor.execute("SELECT COUNT(*) FROM Ochered WHERE Numseance = ?", (numseance,)).fetchone()[0]}")
    conn.close()


@dp.message(Command("register")) # Обработчик команды /register
@dp.message(lambda message: message.text == "Регистрация")  # Обрабатываем и "Регистрация"
async def register(message: types.Message, state: FSMContext):
    """
    Обрабатывает команду /register.
    - Проверяет, зарегистрирован ли пользователь в базе данных.
    - Если нет, запрашивает у пользователя название группы и переводит FSM в состояние RegisterState.group.
    """
    user_id = message.from_user.id
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    groupname = cursor.execute("SELECT GroupName FROM Users WHERE ID = ?", (user_id,)).fetchone()
    if not groupname:
        await message.answer("Введите вашу группу:")
        await state.set_state(RegisterState.group)
    else:
        await message.answer("Вы уже зарегистрированы!", reply_markup=kbregister)
    conn.close()


@dp.message(RegisterState.group) # Обработка ввода группы
async def process_group(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод группы пользователя и проверяет ее наличие в базе данных.
    - Получает введенную пользователем группу.
    - Проверяет, существует ли группа в базе данных.
    - Если группа существует, запрашивает ввод имени пользователя.
    - Если группа не существует, отправляет ошибку и очищает состояние.
    """
    await state.update_data(group=message.text.upper())
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    group_number = cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (message.text.upper(),)).fetchone()
    conn.close()
    if not group_number:
        await message.answer("⚠ Ошибка: Такой группы не существует. Попробуйте еще раз.", reply_markup=kbnotregister)
        await state.clear()
        return
    await message.answer("Введите ваше имя:")
    await state.set_state(RegisterState.name)


@dp.message(RegisterState.name) # Обработка ввода имени
async def process_name(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод имени пользователя и переходит к вводу фамилии.
    """
    await state.update_data(name=message.text.capitalize())
    await message.answer("Введите вашу фамилию:")
    await state.set_state(RegisterState.surname)


@dp.message(RegisterState.surname) # Обработка ввода фамилии
async def process_surname(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод фамилии пользователя и переходит к вводу отчества.
    """
    await state.update_data(surname=message.text.capitalize())
    await message.answer("Введите ваше отчество (если нет, напишите '-'): ")
    await state.set_state(RegisterState.middle_name)


@dp.message(RegisterState.middle_name) # Обработка ввода отчества и сохранение в БД
async def process_middle_name(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод отчества пользователя, сохраняет данные в базе и завершает регистрацию.
    - После успешного ввода отчества сохраняет все данные пользователя в таблице `Users`.
    - Если группа еще не существует в таблице `All_groups`, добавляет группу и подгружает расписание.
    - Завершает регистрацию, отправляя сообщение пользователю и очищая состояние.
    """
    user_data = await state.get_data()
    middle_name = message.text.capitalize() if message.text != "-" else None
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO Users (ID, GroupName, NAME, SURNAME, MIDDLE_NAME) VALUES (?, ?, ?, ?, ?)""",
                   (message.from_user.id, user_data['group'], user_data['name'], user_data['surname'], middle_name))
    conn.commit()
    if not cursor.execute("SELECT 1 FROM All_groups WHERE GroupName = ?", (user_data['group'],)).fetchone(): # подгрузить расписание группы
        cursor.execute("""INSERT INTO All_groups (GroupName) VALUES (?)""", (user_data['group'],))
        conn.commit()
        cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (user_data['group'],))
        url = await get_link_with_current_hash() + cursor.fetchone()[0]
        await get_schedule(url, user_data['group'])
        await generatescheduler_to_currect_day()
    conn.close()
    await message.answer("✅ Регистрация завершена!", reply_markup=kbregister)
    await state.clear()


async def main_async() -> None: # Run the bot
    """
    Основная асинхронная функция для запуска бота и настройки задач.
    - Выполняет начальные действия, такие как удаление старых сессий, обновление расписания и генерация будильников для текущего дня.
    - Добавляет задачи в планировщик для регулярного обновления расписания и выполнения других задач в заданное время.
    - Запускает основной цикл бота, который обрабатывает сообщения от пользователей.
    Моментальные задачи:
    - `delete_old_sessions`: удаляет старые сессии.
    - `refresh_schedule`: обновляет расписание.
    - `generatescheduler_to_currect_day`: генерирует будильники на текущий день.
    - Регулярные задачи:
    - Обновление расписания каждое воскресенье в 00:30.
    - Генерация правильных ссылок 1 сентября в 00:30 и 2 февраля в 00:30. Вторая делается из расчёта на то, что 4 курс второго семестра не имеет расписания.
    - Генерация расписания пар на текущий день каждый день в 07:30.
    """
    #await form_correctslinks(await get_link_with_current_hash())
    await delete_old_sessions()
    await refresh_schedule()
    await generatescheduler_to_currect_day() # начальные три действия
    scheduler.add_job(refresh_schedule, trigger='cron', hour=0, minute=30)
    scheduler.add_job(form_correctslinks, 'cron', month=9, day=1, hour=0, minute=30, args=[await get_link_with_current_hash()])
    scheduler.add_job(generatescheduler_to_currect_day, trigger='cron', hour=7, minute=30)
    scheduler.add_job(form_correctslinks, 'cron', month=2, day=1, hour=0, minute=30, args=[await get_link_with_current_hash()])
    scheduler.start()
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(main_async())


if __name__ == '__main__':
    main()
