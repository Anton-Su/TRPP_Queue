FROM python:3.11-alpine
ENV TZ=Europe/Moscow
WORKDIR /app
COPY . /app
RUN pip install -r requirements.txt
CMD ["python", "main.py"]