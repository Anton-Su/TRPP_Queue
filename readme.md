# TRPP_Queue

## Description

This project is designed to retrieve, process, and store class schedules for study groups. It downloads data from a remote source, parses it, and saves it to a database. Subsequently, a registered user can sign up for a specific class from the available upcoming dates, and at the appropriate time, they will be notified when their turn in the queue arrives. After that, they can confirm that they have "completed" their session, and the turn will pass to the next person who signed up from the same group.

## Dependencies

For this project, which is built using Python 3.11, the following external libraries are required:

- `python-dotenv` — for loading environment variables from a .env file  
- `aiogram` — a library for working with Telegram bots  
- `APScheduler` — a task scheduler for periodically updating the schedule  
- `setuptools` — utilities for installing and managing packages  
- `requests` — for making HTTP requests  
- `icalendar` — for handling data in iCal format  
- `dotenv` — for working with environment variables
- `beautifulsoup4` — for parsing HTML and XML documents

Additionally, the following built-in libraries are used:

- `sqlite3` — the built-in library for working with SQLite databases  
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

5. Create a `.env` file in the root directory of the project and add the following environment variables:

   ```plaintext
   BOT_TOKEN=your_bot_token
   DATABASE_NAME=your_database_name
   ```

6. Run the script:

   ```bash
   python main.py
   ```

Just to make sure - Kiezuna (Horikodji) kanon