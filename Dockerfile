FROM python:3.11-alpine
ENV TZ=Europe/Moscow
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
# ✅ Создаём непривилегированного пользователя
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
# ✅ Меняем владельца рабочей директории
RUN chown -R appuser:appgroup /app
# ✅ Запускаем контейнер от имени безопасного пользователя
USER appuser
CMD ["python", "main.py"]