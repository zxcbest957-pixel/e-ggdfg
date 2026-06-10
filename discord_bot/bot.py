import os
import discord
from discord.ext import tasks, commands
from dotenv import load_dotenv
import threading
import sqlite3
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer

# Загружаем переменные окружения из файла .env
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID_STR = os.getenv('DISCORD_CHANNEL_ID')

# Преобразуем ID канала в число
try:
    CHANNEL_ID = int(CHANNEL_ID_STR) if CHANNEL_ID_STR else 0
except ValueError:
    CHANNEL_ID = 0

# Инициализация базы данных SQLite
DB_PATH = "clan.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            roblox_name TEXT,
            wins INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

intents = discord.Intents.default()
intents.message_content = True  # Разрешаем чтение сообщений для работы текстовых команд !top, !register и др.

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Бот {bot.user} успешно запустился и готов к работе!')
    # Запускаем фоновую задачу отправки сообщений (каждые 5 сек)
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

@send_hello.before_loop
async def before_send_hello():
    await bot.wait_until_ready()

# --- КОМАНДЫ ЛИДЕРБОРДА ---

# 1. Регистрация ника Roblox
@bot.command(name="register", aliases=["регистрация"])
async def register(ctx, roblox_name: str):
    user_id = str(ctx.author.id)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Проверяем, есть ли уже пользователь в базе
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row:
        cursor.execute("UPDATE users SET roblox_name = ? WHERE user_id = ?", (roblox_name, user_id))
        await ctx.send(f"✅ Никнейм Roblox успешно изменен на **{roblox_name}** для {ctx.author.mention}!")
    else:
        cursor.execute("INSERT INTO users (user_id, roblox_name, wins) VALUES (?, ?, 0)", (user_id, roblox_name))
        await ctx.send(f"🎉 {ctx.author.mention} успешно зарегистрирован с ником Roblox: **{roblox_name}**!")
        
    conn.commit()
    conn.close()

# 2. Добавление побед (Доступно модераторам с правами "Управление сообщениями")
@bot.command(name="addwins", aliases=["добавитьпобеды"])
@commands.has_permissions(manage_messages=True)
async def addwins(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ Количество побед должно быть больше нуля!")
        return
        
    user_id = str(member.id)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT wins FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row:
        new_wins = row[0] + amount
        cursor.execute("UPDATE users SET wins = ? WHERE user_id = ?", (new_wins, user_id))
    else:
        new_wins = amount
        # Регистрируем без ника, если еще не был зарегистрирован
        cursor.execute("INSERT INTO users (user_id, roblox_name, wins) VALUES (?, ?, ?)", (user_id, "Не указан", amount))
        
    conn.commit()
    conn.close()
    await ctx.send(f"🏆 Добавлено **{amount}** побед пользователю {member.mention}! Всего побед: **{new_wins}**.")

@addwins.error
async def addwins_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ У вас нет прав модератора (требуется право `Управление сообщениями`) для начисления побед!")
    else:
        await ctx.send("❌ Ошибка использования команды. Пример: `!addwins @Ник 5` или `!addwins @Ник 10`.")

# 3. Вывод Топ-10 клана
@bot.command(name="top", aliases=["топ", "лидеры"])
async def top(ctx):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, roblox_name, wins FROM users ORDER BY wins DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await ctx.send("📭 Лидерборд пока пуст! Зарегистрируйтесь с помощью `!register <ник>`.")
        return
        
    embed = discord.Embed(
        title="🏆 Лидерборд клана MyPvp (Bedwars) 🏆",
        description="Топ игроков по количеству побед:",
        color=discord.Color.gold()
    )
    
    leaderboard_text = ""
    medals = ["🥇", "🥈", "🥉"]
    
    for i, row in enumerate(rows):
        user_id, roblox_name, wins = row
        member = ctx.guild.get_member(int(user_id))
        discord_name = member.display_name if member else f"ID: {user_id}"
        
        # Красивое оформление призовых мест медальками
        place_emoji = medals[i] if i < 3 else f"**#{i+1}**"
        leaderboard_text += f"{place_emoji} {discord_name} (Roblox: *{roblox_name}*) — **{wins}** побед\n"
        
    embed.description = leaderboard_text
    embed.set_footer(text="Играйте больше и попадайте в топ!")
    await ctx.send(embed=embed)

# 4. Просмотр профиля игрока
@bot.command(name="profile", aliases=["профиль"])
async def profile(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_id = str(member.id)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT roblox_name, wins FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    roblox_name = row[0] if row else "Не зарегистрирован"
    wins = row[1] if row else 0
    
    embed = discord.Embed(
        title=f"👤 Профиль игрока {member.display_name}",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Ник Roblox", value=f"**{roblox_name}**", inline=True)
    embed.add_field(name="🏆 Победы Bedwars", value=f"**{wins}**", inline=True)
    embed.set_footer(text="Используйте `!register <ник>` для привязки аккаунта")
    
    await ctx.send(embed=embed)

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
def run_web_server():
    class HealthCheckHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Bot is alive!")

        def log_message(self, format, *args):
            return

    port = int(os.getenv("PORT", 8080))
    try:
        server = TCPServer(("0.0.0.0", port), HealthCheckHandler)
        print(f"Веб-сервер запущен на порту {port} для Render.")
        server.serve_forever()
    except Exception as e:
        print(f"Не удалось запустить веб-сервер: {e}")

if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()

    if TOKEN:
        try:
            bot.run(TOKEN)
        except Exception as e:
            print(f"Не удалось запустить бота: {e}")
    else:
        print("Запуск бота невозможен без корректного токена.")
