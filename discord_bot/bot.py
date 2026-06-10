import os
import discord
from discord.ext import tasks, commands
from dotenv import load_dotenv
import threading
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer

# Загружаем переменные окружения из файла .env
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID_STR = os.getenv('DISCORD_CHANNEL_ID')

# Проверка конфигурации
if not TOKEN:
    print("Внимание! Пожалуйста, укажите реальный DISCORD_TOKEN в файле .env")
if not CHANNEL_ID_STR:
    print("Внимание! Пожалуйста, укажите реальный DISCORD_CHANNEL_ID в файле .env")

# Преобразуем ID канала в число
try:
    CHANNEL_ID = int(CHANNEL_ID_STR) if CHANNEL_ID_STR else 0
except ValueError:
    print("Ошибка! DISCORD_CHANNEL_ID должен быть числом.")
    CHANNEL_ID = 0

intents = discord.Intents.default()
# intents.message_content = True  # Отключаем, чтобы не требовалось включать Privileged Intents в панели Discord

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Бот {bot.user} успешно запустился и готов к работе!')
    # Запускаем фоновую задачу отправки сообщений
    if CHANNEL_ID > 0:
        send_hello.start()
    else:
        print("Задача отправки сообщений не запущена, так как указан некорректный ID канала.")

@tasks.loop(seconds=5.0)
async def send_hello():
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        try:
            await channel.send("привет")
            print("Отправлено сообщение 'привет'")
        except Exception as e:
            print(f"Ошибка при отправке сообщения: {e}")
    else:
        print(f"Канал с ID {CHANNEL_ID} не найден. Проверьте правильность ID и добавлен ли бот на этот сервер.")

# Перед запуском задачи дождемся готовности бота
@send_hello.before_loop
async def before_send_hello():
    await bot.wait_until_ready()

# Простейший веб-сервер для прохождения проверки портов Render и UptimeRobot
def run_web_server():
    class HealthCheckHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Bot is alive!")

        def log_message(self, format, *args):
            # Отключаем логирование запросов, чтобы не засорять консоль
            return

    port = int(os.getenv("PORT", 8080))
    try:
        server = TCPServer(("0.0.0.0", port), HealthCheckHandler)
        print(f"Веб-сервер запущен на порту {port} для Render.")
        server.serve_forever()
    except Exception as e:
        print(f"Не удалось запустить веб-сервер: {e}")

if __name__ == "__main__":
    # Запускаем веб-сервер в отдельном потоке
    threading.Thread(target=run_web_server, daemon=True).start()

    if TOKEN:
        try:
            bot.run(TOKEN)
        except Exception as e:
            print(f"Не удалось запустить бота: {e}")
    else:
        print("Запуск бота невозможен без корректного токена.")
