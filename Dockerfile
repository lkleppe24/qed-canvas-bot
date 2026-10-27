FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py .
# Mount a volume at /app/data so the bot remembers what it announced across restarts
VOLUME ["/app/data"]
CMD ["python", "-u", "bot.py"]
