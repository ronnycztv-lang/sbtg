import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, time, timedelta
from flask import Flask
from threading import Thread
from groq import Groq

# ==== Keep Alive server (Render) ====
app = Flask('')

@app.route('/')
def home():
    return "Bot běží!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==== Discord Intents ====
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==== Tokens ====
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

# ==== Config ====
CHANNEL_ID = 1396253060745007216   # kanál hlasování
POKEC_ID = 1396254859577004253     # kanál pokec
hlasovali_yes = set()
hlasovali_no = set()
hlasovaci_zprava_id = None

# ==== AI klient (jen pro odpovědi na zmínky) ====
groq_client = Groq(api_key=GROQ_API_KEY)

async def ai_respond(prompt: str):
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ Chyba AI: {e}"

# ==== Turnaj každé 3 hodiny ====
@tasks.loop(hours=3)
async def posli_turnaj():
    channel = bot.get_channel(POKEC_ID)
    await channel.send("@everyone 🎮 **Dnes je turnaj (proti CZ klubům)!**")

# ==== Úklid starých vtipů ====
async def smaz_stare_vtipy():
    channel = bot.get_channel(POKEC_ID)
    if not channel:
        return
    async for msg in channel.history(limit=200):
        if msg.author == bot.user and "😂 Vtip:" in msg.content:
            try:
                await msg.delete()
            except:
                pass

# ==== Odpovědi na zmínku ====
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if bot.user.mentioned_in(message):
        reply = await ai_respond(message.content)
        await message.channel.send(reply)
    await bot.process_commands(message)

# ==== Příkaz test ====
@bot.command()
async def test(ctx):
    await ctx.send("✅ Bot je online a funguje.")

# ==== Start ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    await smaz_stare_vtipy()  # smaže staré vtipy
    if not posli_turnaj.is_running():
        posli_turnaj.start()

keep_alive()
bot.run(DISCORD_TOKEN)
