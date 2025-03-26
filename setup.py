from setuptools import setup, find_packages

setup(
    name="TRPP_Queue",
    version="0.1",
    packages=find_packages(),
    install_requires=[
    'dotenv>=0.9.9',
    'python-dotenv>=1.0.1',
    'aiogram>=3.18.0',
    'APScheduler>=3.11.0',
    'requests>=2.32.3',
    'icalendar>=6.1.2',
    ],
    entry_points={
        'console_scripts': [
            'kiezunago=main:main',  # точку входа для бота
        ],
    },
)