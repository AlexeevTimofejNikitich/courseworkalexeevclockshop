# Используйте официальный образ Python как базовый образ
FROM python:3.9-slim

# Установите рабочую директорию
WORKDIR /app

# Скопируйте зависимости
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Скопируйте весь код приложения
COPY . .

# Откройте порт, на котором работает Flask
EXPOSE 5000

# Укажите команду для запуска вашего приложения
CMD ["python", "app.py"]

