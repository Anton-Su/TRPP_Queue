# TRPP_Queue

## Description

This project is designed to retrieve, process, and store class schedules for study groups. It downloads data from a remote source, parses it, and saves it to a database. Subsequently, a registered user can sign up for a specific class from the available upcoming dates, and at the appropriate time, they will be notified when their turn in the queue arrives. After that, they can confirm that they have "completed" their session, and the turn will pass to the next person who signed up from the same group.

## Dependencies

For this project, which is built using Python 3.11, the following external libraries are required:

- `python-dotenv` — for loading environment variables from a .env file  
- `aiogram` — a library for working with Telegram bots  
- `APScheduler` — a task scheduler for periodically updating the schedule  
- `setuptools` — utilities for installing and managing packages
- `icalendar` — for handling data in iCal format  
- `dotenv` — for working with environment variables
- `beautifulsoup4` — for parsing HTML and XML documents
- `aiosqlite` — for working with SQLite databases asynchronously
- `aiohttp` — for making asynchronous HTTP requests
- `re` - for working with regular expressions

Additionally, the following built-in libraries are used:

- `sqlite3` — for working with SQLite databases
- `os` — for handling environment variables  
- `datetime` — for working with dates and times  
- `asyncio` — for working with asynchronous code  
- `logging` — for logging
- `json` — for working with JSON data

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

5. Look at the queue.db file. It contains data that are relevant until summer 2025. So if you are from the future, I recommend you in step 7 not to chose queue.db (or just delete it) - instead you will auto create an SQLite database file. After 1 hour (time that require to collect data in mirea.ru in the first setup) or something, the bot starts working (step 9).

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

9. The bot will start running, and you can interact with it through Telegram. I highly recommend you to turn of VPN, if VPN country not in Commonwealth of Independent states.

10. Add you telegram bot in the group where you want to use it. You can do this by searching for your bot's username in the Telegram app and adding it to the group.

Just to make sure - Kiezuna (Horikodji) kanon
