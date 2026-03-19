FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir "python-telegram-bot[webhooks]==21.6" httpx==0.27.2 python-dotenv==1.0.1 pyyaml==6.0.2
COPY . .
CMD ["python", "bot.py"]
