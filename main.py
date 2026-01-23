import argparse
import asyncio
import logging
import re
import aiosqlite

from datetime import datetime
from os import getenv
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    BotCommand,
    ChatMemberUpdated,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import ValidationError
from validation import (
    form_correct_links,
    get_link_with_current_hash,
    form_correct_links_step_two,
)
from schedule import refresh_schedule, get_schedule, sync
from createdb import create


load_dotenv()  # получаю значение токена и имени базы данных из .env файла

depth_search = 20000  # глубина поиска для валидации
limit_group_by_one = 1  # Лимит одновременного создания групп на одного пользователя
TOKEN = getenv("BOT_TOKEN")
DATABASE_NAME = getenv("DATABASE_NAME")
dp = Dispatcher()
scheduler = AsyncIOScheduler()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)  # логирование
logger = logging.getLogger(__name__)
bot = Bot(token=TOKEN)
kbRegister = ReplyKeyboardMarkup(  # Создаем кнопку, которую видит только зарегистрированный пользователь
    keyboard=[
        [KeyboardButton(text="Создать"), KeyboardButton(text="Выйти")],
        [KeyboardButton(text="Забронировать"), KeyboardButton(text="Cтатистика")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)
kbNotRegister = ReplyKeyboardMarkup(  # Создаем кнопку, которую видит только незарегистрированный пользователь
    keyboard=[[KeyboardButton(text="Помощь"), KeyboardButton(text="Регистрация")]],
    resize_keyboard=True,
    one_time_keyboard=False,
)
kbPass = ReplyKeyboardMarkup(  # Создаем кнопку, на которую должен нажать человек, когда он закончил
    keyboard=[[KeyboardButton(text="Сдал")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)
kbCreateGroup = ReplyKeyboardMarkup(  # Создаем кнопку, которая для
    keyboard=[[KeyboardButton(text="Помощь"), KeyboardButton(text="Создать")]],
    resize_keyboard=True,
    one_time_keyboard=False,
)
MARKDOWN_V2_SPECIAL_CHARS = r"_*[\]()~`>#+-=|{}.!"


def add_job_if_not_exists(job_tag, job_func, run_date):
    if not any(job.id == job_tag for job in scheduler.get_jobs()):
        scheduler.add_job(
            job_func,
            "date",
            run_date=run_date,
            kwargs={
                "year": run_date.year,
                "month": run_date.month,
                "date": run_date.day,
                "hour": run_date.hour,
                "minute": run_date.minute,
            },
            id=job_tag,
        )


def escape_md(text: str) -> str:
    """
    Экранирует специальные символы MarkdownV2 в строке text, потому что кто-то решил удалить соответствующую фф-ю из aiogram
    """
    escaped_text = re.sub(rf"([{re.escape(MARKDOWN_V2_SPECIAL_CHARS)}])", r"\\\1", text)
    return escaped_text


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


@dp.message(Command("register"))  # Обработчик команды /register
@dp.message(
    lambda message: message.text == "Регистрация"
)  # Обрабатываем и "Регистрация"
async def register(message: types.Message, state: FSMContext):
    """
    Обрабатывает команду /register.
    - Проверяет, зарегистрирован ли пользователь в базе данных.
    - Если нет, запрашивает у пользователя название группы и переводит FSM в состояние RegisterState.group.
    """
    if message.chat.type != "private":
        return
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE ID = ?", (user_id,))
            group_name = await cursor.fetchone()
            if not group_name:
                await message.answer("Введите вашу группу:")
                await state.set_state(RegisterState.group)
            else:
                await message.answer(
                    "Вы уже зарегистрированы!", reply_markup=kbRegister
                )
                return await state.clear()


@dp.message(RegisterState.group)  # Обработка ввода группы
async def process_group(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод группы пользователя и проверяет ее наличие в базе данных.
    - Получает введенную пользователем группу.
    - Проверяет, существует ли группа в базе данных.
    - Если группа существует, запрашивает ввод имени пользователя.
    - Если группа не существует, отправляет ошибку и очищает состояние.
    """
    await state.update_data(group=message.text.upper())
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT 1 FROM Session WHERE GroupName = ?", (message.text.upper(),)
            )
            group_exist = await cursor.fetchone()
    if not group_exist:
        await message.answer(
            f"⚠ Ошибка: группы «{message.text}» не существует, проверьте корректность шифра (дефисы тоже считаются). Также можно создать пользовательскую группу с помощью /add_group название (но расписание пар не будет автоматически синхронизироваться). ",
            reply_markup=kbNotRegister,
        )
        return await state.clear()
    await message.answer("Введите ваше имя:")
    await state.set_state(RegisterState.name)


@dp.message(RegisterState.name)  # Обработка ввода имени
async def process_name(message: types.Message, state: FSMContext):
    """Обрабатывает ввод имени пользователя и переходит к вводу фамилии."""
    await state.update_data(name=message.text.capitalize())
    await message.answer("Введите вашу фамилию:")
    await state.set_state(RegisterState.surname)


@dp.message(RegisterState.surname)  # Обработка ввода фамилии
async def process_surname(message: types.Message, state: FSMContext):
    """Обрабатывает ввод фамилии пользователя и переходит к вводу отчества."""
    await state.update_data(surname=message.text.capitalize())
    await message.answer("Введите ваше отчество (если нет, напишите '-'): ")
    await state.set_state(RegisterState.middle_name)


@dp.message(RegisterState.middle_name)  # Обработка ввода отчества и сохранение в БД
async def process_middle_name(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод отчества пользователя, сохраняет данные в базе и завершает регистрацию.
    - После успешного ввода отчества сохраняет все данные пользователя в таблице `Users`.
    - Если группа еще не существует в таблице `All_groups`, добавляет группу и подгружает расписание.
    - Завершает регистрацию, отправляя сообщение пользователю и очищая состояние.
    """
    user_data = await state.get_data()
    middle_name = message.text.capitalize() if message.text != "-" else ""
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """INSERT INTO Users (ID, GroupName, NAME, SURNAME, MIDDLE_NAME) VALUES (?, ?, ?, ?, ?)""",
                (
                    message.from_user.id,
                    user_data["group"],
                    user_data["name"],
                    user_data["surname"],
                    middle_name,
                ),
            )
            await conn.commit()
            await cursor.execute(
                "SELECT 1 FROM All_groups WHERE GroupName = ?", (user_data["group"],)
            )
            if not await cursor.fetchone():
                await cursor.execute(
                    """INSERT INTO All_groups (GroupName) VALUES (?)""",
                    (user_data["group"],),
                )
                await conn.commit()
                await cursor.execute(
                    "SELECT Url FROM Session WHERE GroupName = ?", (user_data["group"],)
                )
                url_data = await cursor.fetchone()
                url_data = str(url_data[0])
                if url_data == "None":
                    await state.clear()
                    return await message.answer(
                        "✅ Регистрация в специальной группе завершена",
                        reply_markup=kbRegister,
                    )
                current_hash = await get_link_with_current_hash()
                if not current_hash:
                    await message.answer(
                        "✅ Регистрация завершена, группа создана, но сайт миреа точка ру не отвечает, расписание не подгружено "
                        "(maybe, bot hosts not in Russia?). В случае необходимости можно вручную использовать /sync",
                        reply_markup=kbRegister,
                    )
                    return await state.clear()
                url = current_hash + url_data
                await get_schedule(url, user_data["group"])
                await generate_scheduler_to_current_day()
    await message.answer(
        "✅ Регистрация завершена! Попробуйте функционал!", reply_markup=kbRegister
    )
    return await state.clear()


class AddState(StatesGroup):
    """
    Класс состояний для регистрации добавления пары в FSM (Finite State Machine).
    Содержит следующие состояния:
    - groupName: Номер группы
    - start: Дата начала пары.
    - end: Дата конца пары.
    - title: Название пары
    - location: Где находится пара
    """
    group_name = State()
    start_time = State()
    end_time = State()
    title = State()
    location = State()


@dp.message(Command("add_pair"))
@dp.message(lambda message: message.text == "Создать")
async def new_register(message: types.Message, state: FSMContext):
    """
    Обрабатывает добавлением юзером своей, неофициальной пары.
    - Если юзер зарегистрирован, пропускает дальше
    """
    if message.chat.type != "private":
        return
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE ID = ?", (user_id,))
            group = await cursor.fetchone()
    if group:
        await state.update_data(group_name=group[0])
        await message.answer(
            "Введите дату начала пары в формате: ДД.ММ ЧЧ:ММ (например, 02.09 12:30)"
        )
        await state.set_state(AddState.start_time)
    else:
        await message.answer(
            "Вы не зарегистрированы. Сначала выполните регистрацию.",
            reply_markup=kbNotRegister,
        )
        return await state.clear()


@dp.message(AddState.start_time)
async def process_start(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод начала добавленного занятия.
    - Если оно верно введено, то будет переход на ввод конца занятия
    """
    try:
        user_input = message.text.strip()
        parsed = datetime.strptime(user_input, "%d.%m %H:%M")
        start_date = datetime(
            year=datetime.now().year,
            month=parsed.month,
            day=parsed.day,
            hour=parsed.hour,
            minute=parsed.minute,
        )
        await state.update_data(start_time=start_date)
        await message.answer(
            "Введите время окончания пары в формате: ЧЧ:ММ (Например, 14:40)"
        )
        await state.set_state(AddState.end_time)
    except ValueError:
        await message.answer("Неверный формат даты. Попробуйте снова: ДД.ММ ЧЧ:ММ", reply_markup=kbCreateGroup)
        return await state.clear()


@dp.message(AddState.end_time)
async def process_end(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод конца добавленного занятия.
    - Если оно верно введено и не раньше начала, то будет переход на название занятия
    """
    try:
        user_input = message.text.strip()
        end_minute_and_hours = datetime.strptime(user_input, "%H:%M").time()
        data = await state.get_data()
        start_time = data["start_time"]
        # Формируем полноценную дату окончания с той же датой, что и у начала пары
        end_time = datetime(
            year=start_time.year,
            month=start_time.month,
            day=start_time.day,
            hour=end_minute_and_hours.hour,
            minute=end_minute_and_hours.minute,
        )
        if end_time <= start_time:
            await message.answer(
                "Дата окончания пары должна быть позже начала.", reply_markup=kbCreateGroup
            )
            return await state.clear()
        await state.update_data(end_time=end_time)
        await message.answer("Введите название пары (до 14 символов)")
        await state.set_state(AddState.title)
    except ValueError:
        await message.answer("Неверный формат времени. Верный формат времени: ЧЧ:ММ")
        return await state.clear()


@dp.message(AddState.title)
async def process_title(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод названия добавленного занятия.
    """
    await state.update_data(title=message.text.capitalize()[:14].replace("_", "-"))
    await message.answer("Введите место проведения пары")
    await state.set_state(AddState.location)


@dp.message(AddState.location)
async def process_location(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод локации добавленного занятия (обрезает до 14 символов).
    - Если в группе пользователя нет пересечений занятий, добавляет новое занятие в базу данных
    - Добавляет временные слоты (если раньше слотов с таким id не было)
    """
    await state.update_data(location=message.text.strip().capitalize()[:14].replace("_", "-"))
    data = await state.get_data()
    group_name, title = data["group_name"], data["title"]
    location, start_time, end_time = data["location"], data["start_time"], data["end_time"]
    if start_time < datetime.now():
        await message.answer(
            "Для создания пары нельзя выбрать прошедшее время.",
            reply_markup=kbCreateGroup,
        )
        return await state.clear()
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            duration_start_minutes = start_time.hour * 60 + start_time.minute
            duration_end_minutes = end_time.hour * 60 + end_time.minute
            # Проверяем ВСЕ возможные пересечения по времени
            await cursor.execute(
                """SELECT 1 FROM Timetable 
                WHERE GroupName = ? 
                AND (
                    (Start_Year = ? AND Start_Month = ? AND Start_Day = ?)
                    OR
                    (End_Year = ? AND End_Month = ? AND End_Day = ?)
                    OR
                    (Start_Year <= ? AND Start_Month <= ? AND Start_Day <= ? 
                     AND End_Year >= ? AND End_Month >= ? AND End_Day >= ?)
                )
                AND NOT (
                    (? >= (End_Hour * 60 + End_Minute))
                    OR
                    (? <= (Start_Hour * 60 + Start_Minute))
                )
                """,
                (
                    group_name,
                    start_time.year, start_time.month, start_time.day,
                    end_time.year, end_time.month, end_time.day,
                    start_time.year, start_time.month, start_time.day,
                    end_time.year, end_time.month, end_time.day,
                    duration_start_minutes,
                    duration_end_minutes,
                ),
            )
            conflict_pair = await cursor.fetchone()
            if conflict_pair:
                await message.answer(
                    f"Не забивай на свои же пары, студент группы «{group_name}»!",
                    reply_markup=kbCreateGroup,
                )
                return await state.clear()
            await cursor.execute(
                """INSERT INTO Timetable (GroupName, TeacherFIO, Task, Start_Year, Start_Month, Start_Day, 
            Start_Hour, Start_Minute, End_Year, End_Month, End_Day, End_Hour, End_Minute, location) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    group_name,
                    "Someone",
                    title,
                    start_time.year,
                    start_time.month,
                    start_time.day,
                    start_time.hour,
                    start_time.minute,
                    end_time.year,
                    end_time.month,
                    end_time.day,
                    end_time.hour,
                    end_time.minute,
                    location,
                ),
            )
            await conn.commit()
    start_tag = f"start_{start_time.year}_{start_time.month:02d}_{start_time.day:02d}_{start_time.hour:02d}_{start_time.minute:02d}"
    end_tag = f"end_{end_time.year}_{end_time.month:02d}_{end_time.day:02d}_{end_time.hour:02d}_{end_time.minute:02d}"
    # Проверка: есть ли уже такие слоты в планировщике
    add_job_if_not_exists(start_tag, dindin, start_time)
    add_job_if_not_exists(end_tag, dandalan, end_time)
    await message.answer("Пара успешно добавлена!", reply_markup=kbRegister)
    return await state.clear()


async def lighttriggerlistupdate(id_zanyatia: int):
    """Определяет, как реагировать: в личке (урез.версия), или в группе."""
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT Id FROM Ochered WHERE Numseance = ? limit 1", (id_zanyatia,)
            )
            _next_user = await cursor.fetchone()
            if _next_user[0]:
                await bot.send_message(
                    _next_user[0], "Привет, твоя очередь", reply_markup=kbPass
                )


async def triggerlistupdate(chat_id: int, message_id: int, personality_id: int):
    """
    Фф-я, созданная для обработки очереди. Вызывается
    После каждого нажатия кнопки или иного события, затрагивающего очередь.
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT Id, GroupName, Task FROM Timetable WHERE message_id = ?",
                (message_id,),
            )
            _class = await cursor.fetchone()
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Сдать",
                            callback_data=f"query_handler_pass_{_class[0]}",
                        ),
                        InlineKeyboardButton(
                            text="За(от)писаться",
                            callback_data=f"query_handler_reg_{_class[0]}",
                        ),
                        InlineKeyboardButton(
                            text="Поменяться",
                            callback_data=f"query_ustuply_pass_{_class[0]}",
                        ),
                    ]
                ]
            )
            await cursor.execute(
                "SELECT NAME, Surname, Middle_name, Id FROM Users WHERE GroupName = ?",
                (_class[1],),
            )
            _people = await cursor.fetchall()
            await cursor.execute(
                "SELECT Poryadok, Id FROM Ochered WHERE Numseance = ? ORDER BY Poryadok",
                (_class[0],),
            )
            _schedule = await cursor.fetchall()
            people_dict = {person[3]: person for person in _people}
            __people = []
            for _, person_id in _schedule:
                if person_id in people_dict:
                    __people.append(people_dict[person_id])
            queue_lines = []
            for i in __people:
                text = escape_md(f"{i[0]} {i[1]} {i[2]}")
                name_with_id = f"[{text}](tg://user?id={i[3]})"
                queue_lines.append(name_with_id)
            queue_text = "\n".join(queue_lines)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=keyboard,
                parse_mode="MarkdownV2",
                text=f"Началось занятие «{escape_md(_class[2])}»\\!\n\nОчередь:\n{queue_text}",
            )
            if __people and (personality_id == 1 or __people[0][3] == personality_id):
                await bot.send_message(
                    __people[0][3], "Привет, твоя очередь", reply_markup=kbPass
                )


async def dindin(year: int, month: int, date: int, hour: int, minute: int):
    """
    Фф-я для обработки начала занятия.
    - Вызывается по расписанию в указанное время. Устраивает спам-рассылку с очередью.
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT Id, GroupName, Task FROM Timetable WHERE Start_Year = ? AND Start_Month = ? AND Start_Day = ? AND Start_Hour = ? AND Start_Minute = ?",
                (year, month, date, hour, minute),
            )
            _class = await cursor.fetchall()
            await conn.commit()
    for i in _class:
        async with aiosqlite.connect(DATABASE_NAME) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT group_id, thread_id FROM All_groups Where GroupName = ?",
                    (i[1],),
                )
                chat_id_thread = (await cursor.fetchall())[0]
                if chat_id_thread[0] is not None:
                    msg = await bot.send_message(
                        chat_id=chat_id_thread[0],
                        message_thread_id=chat_id_thread[1],
                        text="Генерация очереди пары...",
                    )
                    try:
                        await bot.pin_chat_message(chat_id_thread[0], msg.message_id)
                    except TelegramAPIError:
                        await bot.send_message(
                            chat_id=chat_id_thread[0],
                            text="Бот не смог закрепить сообщение, сделайте его админом",
                            reply_to_message_id=msg.message_id,
                            allow_sending_without_reply=True,
                        )
                    await cursor.execute(
                        "UPDATE Timetable SET message_id = ? WHERE Id = ?",
                        (msg.message_id, i[0]),
                    )
                    await conn.commit()
                    await triggerlistupdate(chat_id_thread[0], msg.message_id, 1)
                else:
                    await lighttriggerlistupdate(i[0])


@dp.callback_query(F.data.startswith("query_ustuply_pass_"))
async def query_ustuply_pass(call: CallbackQuery):
    """
    Фф-я для уступки места юзеру.
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            # Проверка регистрации пользователя
            await cursor.execute(
                "SELECT * FROM Users WHERE Id = ?", (call.from_user.id,)
            )
            if await cursor.fetchone() is None:
                return await call.answer("Вы не зарегистрированы!", show_alert=True)
            numseance = call.data.split("_")[-1]
            await cursor.execute(
                "SELECT Poryadok FROM Ochered WHERE Id = ? AND Numseance = ?",
                (call.from_user.id, numseance),
            )
            row = await cursor.fetchone()
            if row is None:
                return await call.answer(
                    "Вы не регистрировались на данную пару!", show_alert=True
                )
            current_poryadok = row[0]
            await cursor.execute(
                """
                SELECT Id, Poryadok FROM Ochered WHERE Numseance = ? AND Poryadok > ?
                ORDER BY Poryadok LIMIT 1""",
                (numseance, current_poryadok),
            )
            next_user = await cursor.fetchone()
            if next_user:
                next_user_id, next_poryadok = next_user
                # Меняем местами Poryadok
                await cursor.execute(
                    """
                    UPDATE Ochered SET Poryadok = -1 WHERE Id = ? AND Numseance = ?""",
                    (call.from_user.id, numseance),
                )
                await cursor.execute(
                    """
                    UPDATE Ochered SET Poryadok = ? WHERE Id = ? AND Numseance = ?""",
                    (current_poryadok, next_user_id, numseance),
                )
                await cursor.execute(
                    """
                    UPDATE Ochered SET Poryadok = ? WHERE Id = ? AND Numseance = ?""",
                    (next_poryadok, call.from_user.id, numseance),
                )
                await conn.commit()
                await call.answer("Вы поменялись.")
                await bot.send_message(
                    chat_id=call.from_user.id,
                    text="Вы поменялись",
                    reply_markup=kbRegister,
                )
                return await triggerlistupdate(
                    call.message.chat.id, call.message.message_id, next_user_id
                )
            return await call.answer("За вами никого нет.", show_alert=True)

@dp.callback_query(F.data.startswith("query_handler_pass_"))
async def query_handler_pass(call: CallbackQuery):
    """
    Фф-я для сдачи записи пользователя.
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            # Проверка регистрации пользователя
            await cursor.execute(
                "SELECT * FROM Users WHERE Id = ?", (call.from_user.id,)
            )
            if await cursor.fetchone() is None:
                return await call.answer("Вы не зарегистрированы!", show_alert=True)
            _class_id = call.data.split("_")[-1]
            await cursor.execute(
                "SELECT * FROM Ochered WHERE Numseance = ? order by Poryadok limit 1",
                (_class_id,),
            )
            result = await cursor.fetchone()
            if result is None:
                return await call.answer("Очередь пустая!", show_alert=True)
            if result[1] != call.from_user.id:
                return await call.answer(
                    "Вы не первый на данную пару!", show_alert=True
                )
            # Получение данных о занятии
            await cursor.execute(
                "SELECT Start_Year, Start_Month, Start_Day, Start_Hour, Start_Minute, Location, GroupName FROM Timetable WHERE Id = ?",
                (_class_id,),
            )
            _class_data = (await cursor.fetchall())[0]
            await handle_subject_uni(
                call.from_user.id,
                _class_data[6],
                _class_data[0],
                _class_data[1],
                _class_data[2],
                _class_data[3],
                _class_data[4],
                _class_data[5],
            )
            await triggerlistupdate(call.message.chat.id, call.message.message_id, 1)
    await bot.send_message(
        chat_id=call.from_user.id, text="Надеюсь, реально сдал", reply_markup=kbRegister
    )
    return await call.answer("Надеюсь, реально сдал", show_alert=True)


@dp.callback_query(F.data.startswith("query_handler_reg_"))
async def query_handler_reg(call: CallbackQuery):
    """
    ФФ-я для записи/отмены записи пользователя, используя инлайн клавиатуру.
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            # Проверка регистрации пользователя
            await cursor.execute(
                "SELECT * FROM Users WHERE Id = ?", (call.from_user.id,)
            )
            if await cursor.fetchone() is None:
                return await call.answer("Вы не зарегистрированы!", show_alert=True)
            _class_id = call.data.split("_")[-1]
            await cursor.execute(
                "SELECT * FROM Ochered WHERE Numseance = ? order by Poryadok limit 1",
                (_class_id,),
            )
            result = await cursor.fetchone()
            if result and result[1] == call.from_user.id:
                return await call.answer("Используйте «Сдать»!", show_alert=True)
            # Получение данных о занятии
            await cursor.execute(
                "SELECT Start_Year, Start_Month, Start_Day, Start_Hour, Start_Minute, Location, GroupName FROM Timetable "
                "WHERE Id = ?",
                (_class_id,),
            )
            _class_data = (await cursor.fetchall())[0]
            result = await handle_subject_uni(
                call.from_user.id,
                _class_data[6],
                _class_data[0],
                _class_data[1],
                _class_data[2],
                _class_data[3],
                _class_data[4],
                _class_data[5],
            )
            await triggerlistupdate(
                call.message.chat.id, call.message.message_id, call.from_user.id
            )
    return await call.answer(result)


@dp.message(lambda message: message.text == "Сдал")  # Обработка псевдонима
@dp.message(Command("pass"))
async def handle_pass(message: Message):
    """Обрабатывает процесс сдачи пользователя в личных сообщениях (не через группу)"""
    user_id = message.from_user.id
    current_time = datetime.now()
    current_year = current_time.year
    current_month = current_time.month
    current_day = current_time.day
    current_hour = current_time.hour
    current_minute = current_time.minute
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,))
            group_name = (await cursor.fetchone())[0]
            await cursor.execute(
                """
                SELECT Id, Task, TeacherFIO, Location
                FROM Timetable
                WHERE 
                     (Start_Year < ? OR 
                     (Start_Year = ? AND Start_Month < ?) OR
                     (Start_Year = ? AND Start_Month = ? AND Start_Day < ?) OR
                     (Start_Year = ? AND Start_Month = ? AND Start_Day = ? AND Start_Hour < ?) OR
                     (Start_Year = ? AND Start_Month = ? AND Start_Day = ? AND Start_Hour = ? AND Start_Minute <= ?))
                AND 
                     (End_Year > ? OR
                     (End_Year = ? AND End_Month > ?) OR
                     (End_Year = ? AND End_Month = ? AND End_Day > ?) OR
                     (End_Year = ? AND End_Month = ? AND End_Day = ? AND End_Hour > ?) OR
                     (End_Year = ? AND End_Month = ? AND End_Day = ? AND End_Hour = ? AND End_Minute >= ?))
                AND GroupName = ?
                """,
                (
                    current_year,
                    current_year, current_month,
                    current_year, current_month, current_day,
                    current_year, current_month, current_day, current_hour,
                    current_year, current_month, current_day, current_hour, current_minute,
                    current_year,
                    current_year, current_month,
                    current_year, current_month, current_day,
                    current_year, current_month, current_day, current_hour,
                    current_year, current_month, current_day, current_hour, current_minute,
                    group_name,
                ),
            )
            class_id = (await cursor.fetchone())[0]
            await cursor.execute(
                "SELECT Id FROM Ochered WHERE Numseance = ? ORDER BY Poryadok LIMIT 1",
                (class_id,),
            )
            first = await cursor.fetchone()
            if first and first[0] == user_id:
                await cursor.execute(
                    "DELETE FROM Ochered WHERE Numseance = ? AND Id = ?",
                    (class_id, user_id),
                )
                await conn.commit()
                await message.answer("Надеюсь, реально сдал!", reply_markup=kbRegister)
                await cursor.execute(
                    "SELECT message_id FROM Timetable Where Id = ?", (class_id,)
                )
                message_id = (await cursor.fetchall())[0]
                if message_id[0] is None:
                    return await lighttriggerlistupdate(class_id)
                await cursor.execute(
                    "SELECT group_id FROM All_groups Where GroupName = ?", (group_name,)
                )
                chat_id_thread = (await cursor.fetchall())[0]
                return await triggerlistupdate(chat_id_thread[0], message_id[0], 1)
    if first:
        return await message.answer("Ещё не время!")
    return await message.answer("Мы не нашли вас в очереди!")


async def dandalan(year: int, month: int, date: int, hour: int, minute: int):
    """
    Функция для обработки окончания занятия.
    Вызывается в конце занятия.
    Удаляет все упоминания о занятии.
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT GroupName, Id, message_id FROM Timetable WHERE End_Year = ? AND End_Month = ? AND End_Day = ?"
                "AND End_Hour = ? AND End_Minute = ?",
                (year, month, date, hour, minute),
            )
            _class = await cursor.fetchall()
            for group_name, _, message_id in _class:
                await cursor.execute(
                    "SELECT id FROM Ochered WHERE Numseance = ?", (_,)
                )
                last_peoples = await cursor.fetchall()
                if last_peoples is not None:
                    await cursor.execute(
                        "SELECT Start_Year, Start_Month, Start_Day, Start_Hour, Start_Minute, Task from Timetable WHERE Id = ?",
                        (_,),
                    )
                    info = await cursor.fetchone()
                    for last_people in last_peoples:
                        await bot.send_message(
                            last_people[0],
                            f"Пара «{info[5]}» ({str(info[1]).rjust(2, '0')}.{str(info[2]).rjust(2, '0')}.{info[0]} {str(info[3]).rjust(2, '0')}:{str(info[4]).rjust(2, '0')}) закончилась... вы не успели (грустная эмодзи, тут даже фрирен не поможет)",
                            reply_markup=kbRegister,
                        )
                await cursor.execute("DELETE FROM Ochered WHERE Numseance = ?", (_,))
                await cursor.execute(
                    "SELECT group_id FROM All_groups WHERE GroupName = ?", (group_name,)
                )
                chat_id = await cursor.fetchone()
                if chat_id and message_id:
                    try:
                        await bot.delete_message(chat_id[0], message_id)
                    except TelegramBadRequest:
                        print(
                            f"{chat_id[0]} - {message_id} (не удалось удалить)"
                        )  # игнорируем ошибку
            await cursor.execute(
                "DELETE FROM Timetable WHERE End_Year = ? AND End_Month = ? AND End_Day = ? AND End_Hour = ? AND End_Minute = ?",
                (year, month, date, hour, minute),
            )
            await conn.commit()


async def delete_old_sessions():
    """
    Удаляет просроченные записи из базы данных (время сеансов раньше текущего момента).
    Эта функция выполняет проверку всех записей в таблице `Timetable` и удаляет те, которые уже прошли по сравнению с текущим временем.
    Просроченные записи удаляются из таблиц `Timetable` и `Ochered`.
    - Вызывает функцию dindin, если занятие ещё не окончено (создаёт таблицу)
    """
    async with aiosqlite.connect(getenv("DATABASE_NAME")) as conn:
        async with conn.cursor() as cursor:
            current_date = datetime.now()
            hour, minute, day, month, year = (
                current_date.hour,
                current_date.minute,
                current_date.day,
                current_date.month,
                current_date.year,
            )
            # Получаем пары, которые уже минимум начались
            await cursor.execute(
                """SELECT DISTINCT Start_Year, Start_Month, Start_Day, Start_Hour, Start_Minute, End_Year, End_Month, End_Day, End_Hour, End_Minute FROM Timetable 
                WHERE 
                (Start_Year < ?) OR 
                    (Start_Year = ? AND Start_Month < ?) OR 
                    (Start_Year = ? AND Start_Month = ? AND Start_Day < ?) OR 
                    (Start_Year = ? AND Start_Month = ? AND Start_Day = ? AND Start_Hour < ?) OR 
                    (Start_Year = ? AND Start_Month = ? AND Start_Day = ? AND Start_Hour = ? AND Start_Minute <= ?)
                """,
                (
                    year,
                    year, month,
                    year, month, day,
                    year, month, day, hour,
                    year, month, day, hour, minute
                ),
            )
            result = await cursor.fetchall()
            for start_year, start_month, start_day, start_hour, start_minute, end_year, end_month, end_day, end_hour, end_minute in result:
                end_datetime = datetime(
                    end_year, end_month, end_day, end_hour, end_minute
                )
                # пара уже прошла вся
                if current_date >= end_datetime:
                    await dandalan(end_year, end_month, end_day, end_hour, end_minute)
                else:
                    await dindin(start_year, start_month, start_day, start_hour, start_minute)



def generate_calendar(raspisanie):  # Функция для генерации клавиатуры-календаря
    """
    Генерирует Inline-клавиатуру с датами на основе переданного расписания.
    Возвращает Inline-клавиатуру с кнопками дат и кнопкой закрытия.
    """
    days_of_week = {
        "Monday": "Понедельник",
        "Tuesday": "Вторник",
        "Wednesday": "Среда",
        "Thursday": "Четверг",
        "Friday": "Пятница",
        "Saturday": "Суббота",
        "Sunday": "Воскресенье",
    }
    keyboard = []
    for year, month, day in raspisanie:
        date = datetime(year, month, day)
        date_name = days_of_week[date.strftime("%A")]  # Получаем русское название
        button = InlineKeyboardButton(
            text=f"{date.strftime('%d.%m.%Y')} ({date_name})",
            callback_data=f"date_{date.strftime('%Y-%m-%d')}",
        )
        keyboard.append([button])
    keyboard.append(
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="remove_keyboard")]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def generate_scheduler_to_current_day():  # установка будильников на текущий день
    """
    Устанавливает запланированные задачи на текущий день, используя расписание из базы данных.
    - Подключается к базе данных и получает время запланированных событий.
    - Проверяет, существуют ли уже задачи с таким временем.
    - Если задачи нет, создаёт две задачи:
    1. `dindin` запускается в указанное время.
    2. `dandalan` запускается обычно через 90 (+10) минут после первой (если данные получены из сайта mirea.ru).
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            current_date = datetime.now()
            await cursor.execute(
                "SELECT DISTINCT Start_Hour, Start_Minute FROM Timetable "
                "WHERE Start_Year = ? AND Start_Month = ? AND Start_Day = ?",
                (current_date.year, current_date.month, current_date.day),
            )
            start_hour_minute = await cursor.fetchall()
            await cursor.execute(
                "SELECT DISTINCT End_Hour, End_Minute FROM Timetable WHERE Start_Year = ? AND Start_Month = ? AND Start_Day = ?",
                (current_date.year, current_date.month, current_date.day),
            )
            end_hour_minute = await cursor.fetchall()

    for start_hour, start_minute in start_hour_minute:
        start_date = datetime(
            current_date.year,
            current_date.month,
            current_date.day,
            start_hour,
            start_minute,
        )
        add_job_if_not_exists(
            f"start_{start_date.year}_{start_date.month:02d}_{start_date.day:02d}_{start_date.hour:02d}_{start_date.minute:02d}",
            dindin,
            start_date,
        )
    for end_hour, end_minute in end_hour_minute:
        end_date = datetime(
            current_date.year,
            current_date.month,
            current_date.day,
            end_hour,
            end_minute,
        )
        add_job_if_not_exists(
            f"end_{end_date.year}{end_date.month:02d}_{end_date.day:02d}_{end_date.hour:02d}_{end_date.minute:02d}",
            dandalan,
            end_date,
        )


@dp.my_chat_member()
async def on_bot_added_or_delete_to_group(event: ChatMemberUpdated):
    """Автоматически привязывают юзера к группе
    - Вызывается при добавлении бота в группу
    - Вызывается при удалении бота из группы
    """
    if event.chat.type == "private":
        return
    bot_id = (await bot.me()).id
    if event.new_chat_member.user.id != bot_id:
        return None
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            chat_id = event.chat.id
            user_id = event.from_user.id
            if event.new_chat_member.status in ("member", "administrator"):
                try:
                    await cursor.execute(
                        "SELECT GroupName FROM Users WHERE Id = ?", (user_id,)
                    )
                    user_group = (await cursor.fetchone())[0]
                    await cursor.execute(
                        "SELECT group_id FROM All_groups WHERE GroupName = ?",
                        (user_group,),
                    )
                    existing_chat_id = (await cursor.fetchone())[0]
                    await bot.get_chat(existing_chat_id)
                    if existing_chat_id != chat_id:
                        await bot.send_message(
                            chat_id, f"«{user_group}» уже привязан к другой группе."
                        )
                        return await bot.leave_chat(chat_id)
                    return None
                except TypeError:
                    await bot.send_message(
                        chat_id,
                        f"Прикалываешься, {event.from_user.full_name}? Ты не зарегистрирован в системе.",
                    )
                    return await bot.leave_chat(chat_id)
                except ValidationError:
                    await cursor.execute(
                        "UPDATE All_groups SET group_id = ?, thread_id = NULL WHERE GroupName = ?",
                        (chat_id, user_group),
                    )
                    await conn.commit()
                    return await bot.send_message(
                        chat_id, f"Теперь бот привязан к группе «{user_group}»."
                    )
            elif event.new_chat_member.status in ("kicked", "left"):
                await cursor.execute(
                    "UPDATE All_groups SET group_id = NULL, thread_id = NULL WHERE group_id = ?",
                    (chat_id,),
                )
                await conn.commit()
    return None


@dp.message(Command("link"))
async def link(message: Message):
    """Привязывает бота к определённому топику
    - Если группа обычная (топиков нет), возвращает NULL
    """
    if message.chat.type == "private":
        return
    user_id = message.from_user.id
    thread_id = message.message_thread_id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            try:
                await cursor.execute(
                    "SELECT GroupName FROM Users WHERE Id = ?", (user_id,)
                )
                user_group = (await cursor.fetchone())[0]
                await cursor.execute(
                    "SELECT group_id FROM All_groups WHERE GroupName = ?", (user_group,)
                )
                chat_id = (await cursor.fetchone())[0]
                await bot.get_chat(chat_id)
                if message.chat.id == chat_id:
                    await cursor.execute(
                        "UPDATE All_groups SET group_id = ?, thread_id = ? WHERE GroupName = ?",
                        (chat_id, thread_id, user_group),
                    )
                    await conn.commit()
                    return await message.answer(
                        f"Теперь бот привязан к этому топику группы «{user_group}»."
                    )
            except TypeError:
                return await message.answer(
                    "Вы не зарегистрированы.", reply_markup=kbNotRegister
                )


@dp.message(Command("unlink"))
async def unlink(message: Message):
    """Удаляет бота из группы (команда админа)"""
    if message.chat.type == "private":
        return
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("creator", "administrator"):
        return await message.answer("Вы не админ!")
    chat_id = message.chat.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            try:
                await cursor.execute(
                    "SELECT Id FROM Users WHERE Id = ?", (message.from_user.id,)
                )
                if not await cursor.fetchone():
                    return await message.answer(
                        "Вы не зарегистрированы.", reply_markup=kbNotRegister
                    )
                await cursor.execute(
                    "SELECT GroupName FROM All_groups WHERE group_id = ?", (chat_id,)
                )
                group_name = (await cursor.fetchone())[0]
                await cursor.execute(
                    "UPDATE All_groups SET group_id = NULL, thread_id = NULL WHERE group_id = ?",
                    (chat_id,),
                )
                await conn.commit()
                await bot.send_message(chat_id, f"Бот отвязан от {group_name}.")
                return await bot.leave_chat(chat_id)
            except TypeError:
                return await message.answer("А чат вообще был к чему-то привязан?")


@dp.message(Command("stats"))  # Команда посмотреть статистику
@dp.message(lambda message: message.text == "Cтатистика")  # Обрабатываем и "Статистика"
async def statistic(message: Message) -> None:
    """Обрабатывает команду /stats, отправляя пользователю его график записей."""
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                    SELECT T.Task, T.TeacherFIO, T.Start_Year, T.Start_Month, 
                        T.Start_Day, T.Start_Hour, T.Start_Minute, 
                        T.End_Hour, T.End_Minute, T.Location,
                        (
                            SELECT COUNT(*) + 1
                            FROM Ochered O2
                            WHERE O2.Numseance = O.Numseance
                            AND O2.Poryadok < O.Poryadok
                        ) AS ActualPosition
                    FROM Timetable T
                    JOIN Ochered O ON T.Id = O.Numseance
                    WHERE O.Id = ?
                    ORDER BY T.Start_Year, T.Start_Month, T.Start_Day, T.Start_Hour, T.Start_Minute
                """,
                (user_id,),
            )
            result = await cursor.fetchall()
            await cursor.execute(
                "SELECT GroupName FROM GroupCreaters WHERE Id = ?", (user_id,)
            )
            group_creates = await cursor.fetchall()
    if group_creates:
        text = ", ".join(f"«{row[0]}»" for row in group_creates)
        await message.answer("👑 👑 👑 Создатель групп: " + text)
    if not result:
        await message.answer(
            "На данный момент вы не записаны ни на одно занятие. Записаться - /record. Создать свою - /add_pair"
        )
        return
    results = []
    count = False
    for index, (
        subject,
        teacher_fio,
        start_year,
        start_month,
        start_date,
        start_hour,
        start_minute,
        end_hour,
        end_minute,
        location,
        actual_position,
    ) in enumerate(result, start=1):
        # Форматирование даты и времени
        start_time = f"{str(start_hour).rjust(2, '0')}:{str(start_minute).rjust(2, '0')}"
        end_time = f"{str(end_hour).rjust(2, '0')}:{str(end_minute).rjust(2, '0')}"
        duration = f"{str(start_date).rjust(2, '0')}.{str(start_month).rjust(2, '0')}.{start_year}\n{start_time} - {end_time}"
        if teacher_fio != "Someone":
            results.append(
                f"{index}) «{subject}», проходит в «{location}», ведёт {teacher_fio} {duration}\n"
                f"{actual_position} место в очереди.\n"
            )
            count = True
        else:
            results.append(
                f"{index}) «{subject}», проходит в «{location}» {duration}\n"
                f"{actual_position} место в очереди.\n"
            )
    if count:
        results.append(
            "\n*Длительность занятия увеличена на 10 минут, чтобы учесть время перерыва."
        )
    results.insert(0, f"Всего активных записей: {len(result)}")
    await message.answer("\n".join(results))


"""friren actually is useful
friren important
friren helpful
friren nice
friren amazing
friren incredible
friren stunning
friren breathtaking
friren extraordinary
friren impressive
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣯⣫⣡⡿⡵⣫⣾⣿⡿⣋⣥⣶⣷⣾⣿⣿⣵⣦⣌⠻⣿⣿⣿⣿⣷⣻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢷⠝⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠯⢱⣫⢗⡞⢕⣿⣿⢿⣾⣿⣿⣿⣿⢿⣿⣿⣿⣿⣿⣿⣜⣿⡽⣿⣿⣷⣿⣿⣿⣿⣿⣷⣹⣿⣟⢿⣿⣿⣿⣯⣇⡸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⢠⣏⡟⢟⡾⣾⣿⢳⣿⡿⣷⣿⡿⡫⣾⣿⢿⣿⣿⣿⣿⣿⢻⣿⢿⣿⣿⣧⢿⣿⣿⣿⣿⣯⣿⣿⢸⣿⣿⣿⣇⡘⡽⣌⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⡿⠀⣿⡰⡞⣿⢳⣿⣷⣿⢟⣿⣿⢏⣬⣾⡇⢿⡏⢿⣿⣿⣿⣿⡏⣿⡌⣿⣿⣿⡟⣿⣿⣿⣿⣿⣿⣿⡇⢻⣿⣿⣿⡁⢷⢿⡌⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⢃⠀⢣⣽⣱⡿⣿⡏⣿⣏⣾⡟⣵⣿⣿⣿⣿⡜⣯⢊⢿⣿⣿⣿⣷⣿⡇⣮⢿⣿⣿⣹⣿⣿⣿⣿⣿⣿⣷⢸⣿⣿⣿⣧⣿⡘⣿⢹⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⠼⢠⡽⣿⣿⠇⣿⢸⣟⣾⢯⣾⣿⣿⣿⣿⣿⣷⡜⣯⣎⢻⣿⣿⣿⣿⡇⣿⡎⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡎⣿⢻⣿⣿⣸⡇⢿⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣧⢞⡻⣕⢸⢧⣿⣿⢸⣿⣿⣿⢄⢶⣯⣽⢿⣿⣿⣿⣿⣿⣌⢮⢒⠛⣛⡿⣿⢁⢿⣿⡼⣿⣿⣿⣷⣿⣿⣿⣿⣿⣧⢿⠘⣿⣿⣧⡇⠞⣸⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣾⣾⠆⣤⠘⣷⢹⣿⢹⡇⣏⣿⣷⣾⣯⣼⣿⣿⣿⣿⣟⣑⣓⡙⢣⡉⠆⡟⣼⣦⣻⣧⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠸⡆⣿⣿⣿⢗⡖⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⢧⢫⣰⣿⢋⡇⣮⠘⠻⢞⢿⣷⣾⣻⣿⣿⣿⣿⣿⣿⣿⡿⢆⣙⡼⢀⠻⣛⡷⣻⣽⢻⣿⣿⣿⣿⣿⣿⣿⡏⢸⣿⣿⣽⣿⡘⡇⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⡟⣮⢿⡿⣿⣏⣧⠸⠀⢰⣀⢉⠒⠝⢣⣿⣿⣿⣿⣿⣿⣿⣡⣿⡑⠡⠤⠈⠊⠻⢷⠉⣾⡟⣽⣿⣿⣿⣿⢿⡇⡚⣩⣭⡭⠽⠷⠤⣭⡭⠭⣭⣭⡭⠭⢭⣝⢻
⣿⣿⣿⣿⣿⣿⣿⡇⣿⡇⢣⡏⣿⣝⡀⡇⣷⡹⣌⠳⠤⠌⢻⣿⣿⣿⣿⣿⣿⠟⠁⣀⠉⣉⠉⠉⡤⢠⡤⡀⣐⣿⣿⣻⣿⡿⣼⠃⣻⣭⣿⣶⣶⢳⣗⣶⣿⣿⣶⡶⣖⡴⣫⣴⣿
⣿⣿⣿⣿⣿⣿⣿⣧⢻⡇⢦⢏⢘⡟⣆⢻⢸⣿⣮⣯⣭⣿⣿⣿⣿⣿⣿⠟⡡⣢⣾⡻⣷⣽⣛⣛⡤⣃⣼⣳⣿⡿⣳⡟⣸⣧⣇⢺⣿⣿⣿⡿⣫⣿⠾⡟⣻⣭⡵⣺⣵⣾⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣄⢷⢸⣣⣣⡻⡿⣆⠃⠛⢿⣿⣿⣟⣽⣛⣿⣯⣴⣿⣿⣿⣿⣿⣿⣶⣶⠞⢈⡿⢡⣿⢿⣿⣟⢰⣟⡌⠀⣺⣿⠛⢉⣪⣥⣶⠿⢛⣭⣾⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡍⣷⠈⢤⠻⡙⣧⣳⣄⣭⣿⣸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣟⣥⢎⡾⣵⣿⣵⣿⠯⣲⡟⠍⢠⣶⣿⡭⠶⢟⣋⣭⣶⣿⣈⣝⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣮⣇⠸⣦⠡⠈⠋⢿⣿⣿⣷⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠫⢋⠜⣿⣿⡟⡡⠚⠋⠐⠖⢀⡭⡥⣰⢸⣿⣿⣿⣿⣿⣧⡜⡝⢿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣟⡞⣴⡿⣱⢸⣆⢀⢹⣿⣿⣿⡿⠿⢿⣿⣿⣿⣿⣿⣿⣿⣵⡏⢊⣿⠟⣫⡔⢀⢀⣮⠎⢰⢟⢹⡇⡏⠏⣿⣿⡏⣿⣆⢻⡽⢘⣎⢻⡿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⡺⣽⡿⡇⠊⣿⢏⣷⡝⢽⢿⣿⣯⣯⣿⣿⣿⣿⣿⣿⣿⣿⣿⡰⣚⣵⠿⢋⣴⣏⣜⣎⠆⢯⢧⣿⢸⣷⠂⢻⣿⣿⠘⣿⣕⠻⢯⠻⣆⠙⢿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣫⡾⢷⣿⣾⣿⣿⢏⣾⣿⢳⣷⡜⢽⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠿⢃⢉⣠⣾⣿⠏⢬⢮⠈⢶⡏⣸⣿⣼⣿⣜⡈⣿⣿⣧⢻⣿⣦⠮⡟⣗⡯⣎⠻⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣻⠷⢋⢴⣿⢿⣿⡿⢣⣾⣿⢧⣹⣟⣽⣷⣅⠙⢿⣿⡿⠿⠛⣛⣭⠴⣺⠵⢿⣻⣭⢄⡠⡳⡃⣬⡎⡇⣿⣿⢿⣿⣿⣻⡘⣿⣿⡌⣿⣿⣧⣓⡝⣿⠎⢳⡜⢿
⣿⣿⣿⡿⣿⢽⣾⢵⣰⣫⡿⣵⣿⠟⣡⣿⣿⣳⣷⢯⣾⡏⣸⣟⡖⡂⠠⣤⣤⣤⣤⣶⣶⡾⠿⣻⡻⠁⢈⢊⣜⣼⡟⡄⣧⢿⣿⢸⡞⣿⣷⢷⣜⣿⣿⡘⣿⣿⣧⡈⠺⣧⡈⢿⣾
⣿⢟⠙⣈⣵⢟⣽⣿⣽⣫⣾⡿⡹⣵⣷⡿⣵⡟⣴⣿⠯⢖⣻⣼⡇⠙⣶⠶⠶⠶⡶⠶⣶⣿⡟⣫⢀⣴⣢⡟⣼⣿⣷⡇⢸⡾⣿⡇⡱⠘⣿⣎⣿⣮⢿⣷⡨⡿⣿⣷⣶⡔⢕⠸⣿
⣾⢦⣾⣿⣷⣽⢟⢞⣷⡿⡫⢔⣾⣿⢋⣞⣿⣿⠋⡅⠤⠾⠿⠶⠒⡇⣿⣿⣿⣿⣿⣿⡿⣫⢞⣵⡿⣷⠟⢴⣿⣿⣰⡾⢺⣇⠹⣇⠘⣅⢮⢿⡘⣿⣷⡻⣷⠑⣝⢿⣿⣿⡧⣳⣟
⣷⢿⡿⣻⡿⣫⣾⡿⣏⣺⣪⣿⠟⣡⣿⢏⣶⢿⣴⣾⢍⡩⢟⣟⣳⣀⠿⣿⣿⣿⡿⡯⡟⡵⢟⢛⣾⡯⣼⠊⢹⣿⠔⣰⡄⢿⡴⡽⡔⣤⠪⣓⠓⢝⣿⣿⣾⢷⣈⣷⡟⢿⣿⣿⣾
⣿⣿⣿⣻⡴⣟⣽⣿⡿⣵⢿⢕⣾⣽⣿⣟⣯⣽⣿⣷⣯⣾⡿⢡⣶⣽⣛⣿⡿⢯⣾⢋⣿⣟⣛⣿⣟⣵⣿⢰⢸⣿⣸⣿⣿⡜⣿⡴⣬⡌⠳⠬⡻⢷⡪⣿⣿⣿⣷⡷⣝⣿⣽⣿⣿
"""


@dp.message(Command("exit"))  # Команда выйти из системы
@dp.message(lambda message: message.text == "Выйти")  # Обрабатываем и "Выйти"
async def decide_to_exit(message: Message) -> None:
    """
    Обрабатывает выход пользователя из системы и удаляет его данные.
    - Удаляет пользователя из всех очередей (таблицы `Ochered`).
    - Удаляет пользователя из таблицы `Users`.
    - Если он был последним в группе, удаляет данные группы (`All_groups`, `Timetable`).
    """
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,))
            group = (await cursor.fetchone())[0]
            await cursor.execute(
                "SELECT COUNT(*) FROM Users WHERE GroupName = ?", (group,)
            )
            count = (await cursor.fetchone())[0]
            await cursor.execute("DELETE FROM Ochered WHERE Id = ?", (user_id,))
            await cursor.execute("DELETE FROM Users WHERE Id = ?", (user_id,))
            if count == 1:
                await cursor.execute(
                    "SELECT group_id FROM All_groups WHERE GroupName = ?", (group,)
                )
                group_id = (await cursor.fetchone())[0]
                if group_id:
                    await bot.leave_chat(group_id)
                await cursor.execute(
                    "DELETE FROM All_groups WHERE GroupName = ?", (group,)
                )
                await cursor.execute(
                    "DELETE FROM Timetable WHERE GroupName = ?", (group,)
                )
                await message.answer(
                    f"{message.from_user.full_name}, с вашим уходом группа «{group}» временно расформирована! Для окончательного удаления группы «{group}» из бота (если вы её создатель), используйте /delete_group {group}."
                )
            await conn.commit()
    await message.answer(
        f"😢😢😢Очень жаль с вами расставаться, {message.from_user.full_name}, возвращайтесь поскорее!!!!!",
        reply_markup=kbNotRegister,
    )


@dp.message(Command("start"))  # Начальная команда
async def command_start_handler(message: Message) -> None:
    """Обрабатывает команду /start, приветствует пользователя и предлагает зарегистрироваться."""
    await message.answer(
        "Привет! Я бот, который регулирует процесс очереди, записываю, отписываю, закрепляю, слежу, и всё такое. Просто зарегистрируйся, добавь бота в группу вашей группы и следуй командам, "
        "и ты сможешь записываться на занятия, и больше не будешь полагаться на авось. Используй /help для отслеживания твоего состояния.",
        reply_markup=kbNotRegister,
    )


@dp.message(Command("help"))  # Функция для обработки команды /help
@dp.message(lambda message: message.text == "Помощь")  # Обрабатываем и "Помощь"
async def send_help(message: Message):
    """Обрабатывает команду /help, проверяя статус собеседника. Если всё в порядке, выдаёт шуточное сообщение."""
    # await message.answer("ААААА! Альтушкааааа в белых чулочкаааах", reply_markup=kbNotRegister)
    # await message.answer("Не делай добра, не получишь и зла!", reply_markup=kbNotRegister)
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE ID = ?", (user_id,))
            groupname = await cursor.fetchone()
    if not groupname:
        return await message.answer(
            "Похоже, вы не зарегистрированы! Пропишите команду /register, затем создайте тематическую группу в телеграмме и добавьте в неё бота. Дело касается не всей группы? Воспользуйтесь /add_group с аргументом название и создайте собственную группу!",
            reply_markup=kbNotRegister,
        )
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT GroupName, group_id FROM All_groups WHERE GroupName = ?",
                (groupname[0],),
            )
            group_id = await cursor.fetchone()
    if not group_id[1]:
        return await message.answer(
            f"Похоже, сообщество для группы «{group_id[0]}» ещё не создано в телеграмме! Это сулит ограничением возможностей до минимума. Создайте беседу и добавьте в неё бота через «добавить в группу» в настройках ботика!",
            reply_markup=kbRegister,
        )
    member = await bot.get_chat_member(group_id[1], user_id)
    if member.status in ["member", "administrator", "creator", "restricted", "kicked"]:
        return await message.answer(
            "Всё оки! Держи советик - через 20 лет вы будете больше разочарованы теми вещами, которые вы не делали, чем теми, которые вы сделали. "
            "Так отчальте от тихой пристани. Почувствуйте попутный ветер в вашем парусе. Двигайтесь вперед, действуйте, открывайте!",
            reply_markup=kbRegister,
        )
    chat = await bot.get_chat(group_id[1])
    if chat.username is not None:
        return await message.reply(
            f"Вижу, группка для {group_id[0]} есть, но тебя в ней ней - держи её username: @{chat.username}"
        )
    return await message.reply(
        f"Вижу, группка для {group_id[0]} есть, но тебя в ней ней. Сорян, но группка это... немного частная, туда только по блату"
    )


@dp.callback_query(F.data.startswith("back_to_calendar_"))
async def back_to_calendar(callback: CallbackQuery):
    """Обрабатывает кнопку назад в inline клавиатуре."""
    await show_calendar(user_id=callback.from_user.id, callback=callback)


async def show_calendar(
    user_id: int, message: types.Message = None, callback: CallbackQuery = None
):  # Универсальная функция для показа календаря (из команды и callback-запроса
    """
    Универсальная функция для отображения календаря пользователю.
    - Извлекает расписание (уникальные даты) из базы данных.
    - Генерирует интерактивную клавиатуру-календарь.
    - Отправляет или редактирует сообщение с календарем в зависимости от типа вызова (команда или callback-запрос).
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,))
            group = await cursor.fetchone()
            if not group:
                if message:
                    return await message.answer(
                        "Вы не зарегистрированы!", reply_markup=kbNotRegister
                    )
                return await callback.answer("Вы не зарегистрированы!", show_alert=True)
            await cursor.execute(
                "SELECT DISTINCT Start_Year, Start_Month, Start_Day FROM Timetable "
                "WHERE GroupName = ? ORDER BY Start_Year, Start_Month, Start_Day",
                (group[0],),
            )
            raspisanie = await cursor.fetchall()
    keyboard = generate_calendar(raspisanie)
    if message:
        await message.answer("Определитесь с датой:", reply_markup=keyboard)
    elif callback:
        await callback.message.edit_text("Определитесь с датой:", reply_markup=keyboard)


@dp.message(Command("record"))  # команда записи/отмены записи
@dp.message(
    lambda message: message.text == "Забронировать"
)  # обрабатываем и "Забронировать"
async def decide_to_record(message: types.Message) -> None:
    """Обрабатывает команду /record, вызывая функцию для отображения календаря."""
    await show_calendar(user_id=message.from_user.id, message=message)


@dp.callback_query(F.data.startswith("remove_keyboard"))
async def remove_keyboard(callback: CallbackQuery):
    """Удаляет inline-клавиатуру после нажатия на кнопку "удалить"."""
    await callback.message.delete()


@dp.callback_query(F.data.startswith("date_"))  # Обработчик выбора даты
async def show_schedule(callback: CallbackQuery):
    """
    Обрабатывает выбор даты пользователем и отображает расписание на этот день.
    - Извлекает выбранную дату из callback-запроса.
    - Получает расписание занятий для данной группы на выбранную дату.
    - Генерирует кнопки с предметами, их временем и местом проведения.
    - Позволяет пользователю выбрать предмет или вернуться к календарю.
    """
    selected_date = callback.data.split("_")[1]
    user_id = callback.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,))
            group_name = (await cursor.fetchone())[0]
            await cursor.execute(
                """
                SELECT Task, Start_Year, Start_Month, Start_Day, Start_Hour, Start_Minute, Location 
                FROM Timetable 
                WHERE GroupName = ? AND Start_Year = ? AND Start_Month = ? AND Start_Day = ?
                """,
                (group_name, selected_date.split("-")[0], selected_date.split("-")[1], selected_date.split("-")[2]),
            )
            subjects = await cursor.fetchall()
    keyboard = []
    for subject in subjects:
        task, year, month, day, hour, minute, location = subject
        text = (
            f"{hour:02d}:{minute:02d} «{task}»"
        )
        button = InlineKeyboardButton(
            text=text,
            callback_data=f"subject_{year}_{month}_{day}_{hour}_{minute}_{location}_{group_name}",
        )
        keyboard.append([button])
    keyboard.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад", callback_data=f"back_to_calendar_{selected_date}"
            )
        ]
    )
    keyboard.append(
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="remove_keyboard")]
    )
    await callback.message.edit_text(
        "Выберите пару:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )


async def handle_subject_uni(
    user_id: int,
    group_name: str,
    year: str,
    month: str,
    day: str,
    hour: str,
    minute: str,
    location: str,
):
    """
    Обрабатывает выбор предмета пользователем.
    - Извлекает информацию о выбранном предмете из callback-запроса.
    - Определяет, записан ли пользователь на этот предмет.
    - Если записан, удаляет его из очереди.
    - Если не записан, добавляет его в очередь с новым порядковым номером.
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT Id FROM Timetable WHERE GroupName = ? AND Start_Year = ? AND Start_Month = ? "
                "AND Start_Day = ? AND Start_Hour = ? AND Start_Minute = ? AND Location = ?",
                (group_name, year, month, day, hour, minute, location),
            )
            numseance = (await cursor.fetchone())[0]

            await cursor.execute(
                "SELECT 1 FROM Ochered WHERE Numseance = ? AND Id = ?",
                (numseance, user_id),
            )
            cancel = await cursor.fetchone()
            if cancel:
                await cursor.execute(
                    "DELETE FROM Ochered WHERE Numseance = ? AND Id = ?",
                    (numseance, user_id),
                )
                await conn.commit()
                return "Запись отменена!"
            await cursor.execute(
                "SELECT MAX(Poryadok) FROM Ochered WHERE numseance = ?", (numseance,)
            )
            result = await cursor.fetchone()
            new_poryadok = (result[0] + 1) if result[0] is not None else 1
            await cursor.execute(
                "INSERT INTO Ochered (Numseance, Id, Poryadok) VALUES (?, ?, ?)",
                (numseance, user_id, new_poryadok),
            )
            await conn.commit()
            await cursor.execute(
                "SELECT COUNT(*) FROM Ochered WHERE Numseance = ?", (numseance,)
            )
            queue_position = (await cursor.fetchone())[0]
            current_time = datetime.now()
            if queue_position == 1 and current_time >= datetime(
                int(year), int(month), int(day), int(hour), int(minute)
            ):
                await lighttriggerlistupdate(numseance)
            return f"Успешно! Ваш номер в очереди: {queue_position}"


@dp.callback_query(F.data.startswith("subject_"))  # Обработчик выбора предмета
async def handle_subject(callback: CallbackQuery):
    """call-back запрос для обработки выбора предмета."""
    _, year, month, day, hour, minute, location, group_name = callback.data.split("_")
    user_id = callback.from_user.id
    message = await handle_subject_uni(
        user_id, group_name, year, month, day, hour, minute, location
    )
    return await callback.answer(message)


@dp.message(Command("sync"))
@dp.message(lambda message: message.text == "Обновить")
async def update(message: types.Message) -> None:
    """Обрабатывает команду /sync, обновляя расписание группы юзера по запросу."""
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE ID = ?", (user_id,))
            group_name = await cursor.fetchone()
    if group_name:
        await sync(group_name[0])
        await message.answer("Запрос выполнен!", reply_markup=kbRegister)
    else:
        await message.answer(
            "Вы не зарегистрированы. Сначала выполните регистрацию.",
            reply_markup=kbNotRegister,
        )


@dp.message(Command("add_group"))
async def add_group(message: types.Message) -> Message:
    """Обрабатывает команду /add_group название, добавляя группу юзера по запросу."""
    # по-хорошему, тут надо бы проверить, что команду не злоупотребляют (один юзер создаёт максимум одну группу), но это долго (типа привязка к id юзера), изменение процесса регистрации
    # из этого вытекает создание команды удаления группы юзером, который её создал, либо всеобщим админом (очередная перемена окружения), но это тоже долго
    # или типа создать новую таблицу GroupCreators с полями GroupName и CreatorID, и проверять её при создании группы
    # и в Session сделать поле CreatorID, типа внешний ключ на GroupCreators, ха-ха-ха, кто это вообще читать будет?
    # да и вообще, кто будет создавать группы, если можно просто зарегистрироваться в уже существующей?
    # ладно, потом доделаю, когда будет время и желание
    user_id = message.from_user.id
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) != 2:
        return await message.answer(
            "Вы не указали название группы. Используйте /add_group название-группы",
            reply_markup=kbNotRegister,
        )
    group_name = parts[1].upper().replace("_", "-")
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT COUNT(*) FROM GroupCreaters WHERE Id = ?", (user_id,)
                )
                count = (await cursor.fetchone())[0]
                if count >= limit_group_by_one:
                    return await message.answer(
                        f"Превышен лимит созданных групп ({limit_group_by_one}). Удалите лишние группы через /delete_group название_группы!",
                        reply_markup=kbNotRegister,
                    )
                await cursor.execute(
                    "INSERT INTO Session (GroupName, Url) VALUES (?, ?)",
                    (group_name, None),
                )
                await cursor.execute(
                    "INSERT INTO GroupCreaters (id, groupname) VALUES (?, ?)",
                    (user_id, group_name),
                )
                await conn.commit()
        except aiosqlite.IntegrityError:
            return await message.answer(
                "Группа с таким названием уже существует", reply_markup=kbNotRegister
            )
    return await message.answer(
        f"Группа «{group_name}» создана! Для удаления используйте /delete_group {group_name}",
        reply_markup=kbNotRegister,
    )


@dp.message(Command("delete_group"))
async def delete_group(message: types.Message) -> Message:
    """Обрабатывает команду /delete_group название, удаляя группу юзера по запросу."""
    user_id = message.from_user.id
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) != 2:
        return await message.answer(
            "Вы не указали название группы. Используйте /delete_group название-группы",
            reply_markup=kbNotRegister,
        )
    group_name = parts[1].upper()
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT 1 FROM GroupCreaters WHERE Id = ? AND GroupName = ?",
                (user_id, group_name),
            )
            count = await cursor.fetchone()
            if count:
                await cursor.execute(
                    "DELETE FROM GroupCreaters WHERE Id = ? AND GroupName = ?",
                    (user_id, group_name),
                )
                await cursor.execute(
                    "DELETE FROM Session WHERE GroupName = ?", (group_name,)
                )
                await cursor.execute(
                    "DELETE FROM Users WHERE GroupName = ?", (group_name,)
                )
                await conn.commit()
                return await message.answer(
                    f"Группа «{group_name}» удалена!", reply_markup=kbNotRegister
                )
        return await message.answer("Отказано", reply_markup=kbNotRegister)


async def main_async() -> None:  # Run the bot
    """
    Основная асинхронная функция для запуска бота и настройки задач.
    - Закрепляет основные команды взаимодействия юзера с ботом
    - Выполняет начальные действия, такие как удаление старых сессий, обновление расписания и генерация будильников для текущего дня.
    - Добавляет задачи в планировщик для регулярного обновления расписания и выполнения других задач в заданное время.
    - Запускает основной цикл бота, который обрабатывает сообщения от пользователей.
    Моментальные задачи:
    - `create`: создаёт таблицы в базе данных (и саму базу), если они не существуют.
    - `delete_old_sessions`: удаляет старые сессии.
    - `refresh_schedule`: обновляет расписание.
    - `generate_scheduler_to_current_day`: генерирует расписание на текущий день.
    - Регулярные задачи:
    - Обновление расписания каждое воскресенье в 00:30.
    - Генерация правильных ссылок 1 сентября в 00:30 и 2 февраля в 00:30. Вторая делается из расчёта на то, что 4 курс второго семестра не имеет расписания.
    - Генерация расписания пар на текущий день каждый день в 07:30.
    Если база данных не создана, вызывается функция `form_correct_links_step_two` с параметрами depth_search и `scheduler`.
    """
    await bot.set_my_commands(
        [
            BotCommand(command="/add_pair", description="Добавить уникальное занятие"),
            BotCommand(command="/link", description="Привязать бота к топику"),
            BotCommand(command="/unlink", description="Отвязать бота от чата"),
            BotCommand(command="/pass", description="Подтвердить посещение"),
            BotCommand(command="/help", description="Проверить свой статус"),
            BotCommand(command="/register", description="Зарегистрироваться в системе"),
            BotCommand(command="/stats", description="Статистика"),
            BotCommand(command="/exit", description="Выход из системы"),
            BotCommand(command="/record", description="Забронировать / отменить бронь"),
            BotCommand(command="/sync", description="Синхронизировать расписание"),
            BotCommand(
                command="/add_group",
                description="Добавить группу. Через пробел указать название",
            ),
        ]
    )
    bd = create()
    await refresh_schedule()
    await delete_old_sessions()
    #await form_correct_links(depth_search, scheduler, bot) # для моментального перезапуска всего
    if bd:
        await form_correct_links_step_two(depth_search, scheduler)
    await generate_scheduler_to_current_day()  # начальные три действия
    scheduler.add_job(refresh_schedule, trigger="cron", hour=0, minute=30)
    scheduler.add_job(
        form_correct_links,
        "cron",
        month=9,
        day=1,
        hour=0,
        minute=30,
        kwargs={"stop": depth_search, "scheduler": scheduler, "bot": bot},
    )
    scheduler.add_job(
        generate_scheduler_to_current_day, trigger="cron", hour=7, minute=30
    )
    scheduler.add_job(
        form_correct_links,
        "cron",
        month=2,
        day=1,
        hour=0,
        minute=30,
        kwargs={"stop": depth_search, "scheduler": scheduler, "bot": bot},
    )
    scheduler.start()
    await dp.start_polling(bot)


def main() -> None:
    # Запуск бота + парсинг аргументов командной строки
    parser = argparse.ArgumentParser(description='Бот для управления расписанием учебных групп')
    parser.add_argument(
        '--depth-search',
        type=int,
        default=20000,
        help='Глубина поиска для валидации (по умолчанию: 20000)'
    )
    parser.add_argument(
        '--limit-group-by-one',
        type=int,
        default=1,
        help='Лимит одновременного создания групп на одного пользователя (по умолчанию: 1)'
    )
    args = parser.parse_args()
    global depth_search, limit_group_by_one
    depth_search = args.depth_search
    limit_group_by_one = args.limit_group_by_one
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
