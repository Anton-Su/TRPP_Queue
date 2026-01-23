# TRPP_Queue (Русский)

## Описание

Этот проект предназначен для получения, обработки и хранения расписаний занятий учебных групп. Он загружает данные с удалённого источника, парсит их и сохраняет в базу данных. Зарегистрированный пользователь может записаться на конкретное занятие из доступных предстоящих дат, и в нужный момент он (в группе и в личных сообщениях) получит уведомление, когда его очередь подойдёт. После этого пользователь может подтвердить, что он "закончил", и очередь перейдёт к следующему записавшемуся из той же группы. Вы также можете добавлять свои независимые группы и занятия.

## Зависимости

Для этого проекта, построенного на Python 3.11, требуются следующие внешние библиотеки:

- `python-dotenv` — загрузка переменных окружения из файла .env
- `aiogram` — библиотека для работы с Telegram-ботами
- `APScheduler` — планировщик задач для периодического обновления расписания
- `setuptools` — утилиты для установки и управления пакетами (не обязательно)
- `icalendar` — работа с данными в формате iCal
- `dotenv` — работа с переменными окружения
- `beautifulsoup4` — парсинг HTML
- `aiosqlite` — асинхронная работа с SQLite
- `aiohttp` — асинхронные HTTP-запросы
- `re` — работа с регулярными выражениями
- `pydantic` — валидация данных и управление настройками

В дополнение используются стандартные библиотеки Python:

- `sqlite3` — работа с базой данных SQLite
- `os` — работа с переменными окружения и путями
- `datetime` — работа с датами и временем
- `asyncio` — асинхронное программирование
- `logging` — логирование
- `json` — работа с JSON
- `argparse` — парсинг аргументов командной строки

## Установка и настройка

1. Установите Python 3.11 и убедитесь, что Python добавлен в PATH. Проверить это можно через Панель управления -> Система -> Дополнительные параметры системы -> Переменные окружения -> PATH.

2. Клонируйте репозиторий на локальную машину:

   ```bash
   git clone https://github.com/Anton-Su/TRPP_Queue.git
   cd TRPP_Queue
   ```

3. Создайте виртуальное окружение и активируйте его:

   ```bash
   python -m venv venv
   ```
   Активируйте виртуальное окружение.

   На Windows:

   ```bash
   venv\Scripts\activate
   ```

   На Linux или macOS:

   ```bash
   source venv/bin/activate
   ```
4. Установите необходимые зависимости:

   ```bash
   pip install -r requirements.txt
   ```

5. Обратите внимание на файл `queue.db`. Он содержит данные, актуальные до зимы 2026 года. Если вы запускаете проект позже этого срока, рекомендуется на шаге 7 не использовать готовый `queue.db` (или удалить его) — при необходимости будет автоматически создан новый файл SQLite. После первоначального запуска может пройти до часа (время, необходимое для сбора данных с mirea.ru при первой настройке), прежде чем бот начнёт полноценно работать (шаг 9). Но обычно бот начинает работу минут через пять.

6. Создайте бота в Telegram через [BotFather](https://t.me/botfather) и получите токен бота. Следуйте подсказкам BotFather для создания нового бота и получения токена.

   - Отправьте команду `/newbot` BotFather.
   - Следуйте подсказкам, задайте имя и username бота.
   - После создания вы получите токен вида `123456789:ABCdefGhIJKlmnoPQRstuVWXyz`.
   Вставьте этот токен в переменную `BOT_TOKEN`.

7. Создайте файл `.env` в корне проекта и добавьте в него переменные окружения:

   ```plaintext
   BOT_TOKEN=your_bot_token
   DATABASE_NAME=your_database_name
   ```

8. Запустите скрипт:

   ```bash
   python main.py
   ```

Дополнительно вы также можете указать два необязательных параметра (`depth-search`, `limit-group-by-one`). По умолчанию они равны 20000 и 1.

Примеры использования:

```bash
python main.py --depth-search 50000
```

```bash
python main.py --limit-group-by-one 3 --depth-search 30000
```

9. Бот начнёт работу, и вы сможете взаимодействовать с ним через Telegram. Рекомендуется отключить VPN, так как расписание подгружается только в России.

10. Найдите бота по username в приложении Telegram и добавьте в группу.


---

# TRPP_Queue (English)

## Description

This project is designed to retrieve, process, and store class schedules for study groups. It downloads data from a remote source, parses it, and saves it to a database. Subsequently, a registered user can sign up for a specific class from the available upcoming dates, and at the appropriate time, they will be notified when their turn in the queue arrives. After that, they can confirm that they have "completed" their session, and the turn will pass to the next person who signed up from the same group. You can add yours independent groups and session.

## Dependencies

For this project, which is built using Python 3.11, the following external libraries are required:

- `python-dotenv` — for loading environment variables from a .env file
- `aiogram` — a library for working with Telegram bots
- `APScheduler` — a task scheduler for periodically updating the schedule
- `setuptools` — utilities for installing and managing packages (not need)
- `icalendar` — for handling data in iCal format
- `dotenv` — for working with environment variables
- `beautifulsoup4` — for parsing HTML documents
- `aiosqlite` — for working with SQLite databases asynchronously
- `aiohttp` — for making asynchronous HTTP requests
- `re` - for working with regular expressions
- `pydantic` - for data validation and settings management

Additionally, the following built-in libraries are used:

- `sqlite3` — for working with SQLite databases
- `os` — for handling environment variables
- `datetime` — for working with dates and times
- `asyncio` — for working with asynchronous code
- `logging` — for logging
- `json` — for working with JSON data
- `argparse` — for parsing command-line arguments

## Installation and Setup

1. Install [Python 3.11](https://docs.python.org/3/whatsnew/3.11.html) and ensure that Python is added to your PATH. You can check this by navigating to System (Control Panel) -> Advanced system settings -> Environment Variables -> System Variables -> PATH -> Edit.

2. Clone the repository to your local machine:

   ```bash
   git clone https://github.com/Anton-Su/TRPP_Queue.git
   cd TRPP_Queue
    ```

3. Create a virtual environment and activate it:

   ```bash
   python -m venv venv
   ```
   Activate the virtual environment.

   On Windows:

   ```bash
   venv\Scripts\activate
   ```

   On Linux or macOS:

   ```bash
   source venv/bin/activate
   ```
4. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

5. Look at the queue.db file. It contains data that are relevant until winter 2026. So if you are from the future, I recommend you in step 7 not to chose queue.db (or just delete it) - instead you will auto create an SQLite database file. After 1 hour (time that require to collect data in mirea.ru in the first setup) or something, the bot starts working (step 9). But usually, the bot starts working in 5 minutes.

6. Create a bot on Telegram by talking to the [BotFather](https://t.me/botfather) and get your bot token. Follow the instructions provided by BotFather to create a new bot and obtain the token.

   - To create a new bot, send the command `/newbot` to BotFather.
   - Follow the prompts to set a name and username for your bot.
   - After creating the bot, you will receive a token that looks like this: `123456789:ABCdefGhIJKlmnoPQRstuVWXyz`.
   Enter this token in BOT_TOKEN.

7. Create a `.env` file in the root directory of the project and add the following environment variables:

   ```plaintext
   BOT_TOKEN=your_bot_token
   DATABASE_NAME=your_database_name
   ```

8. Run the script:

   ```bash
   python main.py
   ```
Actually, you can additionally fill in two parameters (depth-search, limit-group-by-one). Default 20000 and 1
Примеры использования:
  ```bash
  python main.py --depth-search 50000\
  ```
```bash
  python main.py --limit-group-by-one 3 --depth-search 30000
   ```

9. The bot will start running, and you can interact with it through Telegram. I highly recommend you to turn of VPN. The schedule is only loaded in Russia.

10. Add you telegram bot in the group where you want to use it. You can do this by searching for your bot's username in the Telegram app and adding it to the group.

Just to make sure - Kiezuna (Horikodji) kanon
