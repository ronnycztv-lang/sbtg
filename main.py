import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import json

# ==== Keep Alive (Render) ====
app = Flask('')

@app.route('/')
def home():
    return "Bot běží!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==== Intents ====
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==== Tokens ====
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]

# ==== Config ====
POZICE_CHANNEL_ID = 1393525512462270564  # kanál #pozice

POZICE_EMOJI = {
    "⚽": "Útočník (LK/PK/HÚ/SÚ)",
    "🎯": "Střední záložník (SOZ/SDZ)",
    "🏃": "Krajní záložník (LZ/PZ)",
    "🛡️": "Obránce (LO/PO/SO)",
    "🧤": "Brankář (GK)"
}

DATA_FILE = "pozice.json"

# globální proměnné
intro_msg_id = None
status_pozice_id = None
user_choices = {}  # {user_id: [emoji1, emoji2]}

# ==== Helpery pro ukládání ====
def save_data():
    data = {
        "intro_msg_id": intro_msg_id,
        "status_pozice_id": status_pozice_id,
        "user_choices": user_choices
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

def load_data():
    global intro_msg_id, status_pozice_id, user_choices
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            intro_msg_id = data.get("intro_msg_id")
            status_pozice_id = data.get("status_pozice_id")
            user_choices = {int(k): v for k, v in data.get("user_choices", {}).items()}

# ==== Setup ====
async def setup_pozice():
    global intro_msg_id, status_pozice_id
    channel = bot.get_channel(POZICE_CHANNEL_ID)

    # smaže staré zprávy bota
    async for msg in channel.history(limit=50):
        if msg.author == bot.user:
            await msg.delete()

    # Intro zpráva s vysvětlivkami
    intro_text = (
        "📌 **Přečti si pozorně a vyber max. 2 pozice!**\n"
        "Jakmile vybereš, ❌ **nejde to vrátit zpět.**\n\n"
        "Každý hráč má možnost zvolit **primární a sekundární pozici.**\n\n"
        "**Rozdělení pozic a emoji pro hlasování:**\n"
        "⚽ = Útočník (LK/PK/HÚ/SÚ)\n"
        "🎯 = Střední záložník (SOZ/SDZ)\n"
        "🏃 = Krajní záložník (LZ/PZ)\n"
        "🛡️ = Obránce (LO/PO/SO)\n"
        "🧤 = Brankář (GK)"
    )
    intro_msg = await channel.send(intro_text)
    intro_msg_id = intro_msg.id

    # Přidání emoji
    for e in POZICE_EMOJI.keys():
        await intro_msg.add_reaction(e)

    # Status zpráva
    status_msg = await channel.send("⏳ Načítám seznam hráčů...")
    status_pozice_id = status_msg.id
    save_data()

    await update_pozice_status(channel.guild)

# ==== Update status ====
async def update_pozice_status(guild):
    global status_pozice_id
    channel = bot.get_channel(POZICE_CHANNEL_ID)
    if not status_pozice_id:
        return
    try:
        msg = await channel.fetch_message(status_pozice_id)
    except:
        msg = await channel.send("⏳ Načítám seznam hráčů...")
        status_pozice_id = msg.id
        save_data()

    not_done = []
    done = []
    for member in guild.members:
        if member.bot:
            continue
        choices = user_choices.get(member.id, [])
        if len(choices) == 2:
            pozice_text = ", ".join([POZICE_EMOJI[c] for c in choices])
            done.append(f"{member.mention} ✅ ({pozice_text})")
        else:
            not_done.append(f"{member.mention} ({len(choices)}/2)")

    total = len([m for m in guild.members if not m.bot])
    finished = len(done)

    status_text = (
        f"📢 Tito hráči ještě nemají 2 pozice:\n" + (", ".join(not_done) if not_done else "Nikdo 🎉") +
        "\n\n✅ **Už vybrali:**\n" + (", ".join(done) if done else "Nikdo zatím.") +
        f"\n\n📊 **Statistika:** {finished}/{total} hráčů má vybrané 2 pozice."
    )
    await msg.edit(content=status_text)

# ==== Reakce ====
@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != POZICE_CHANNEL_ID:
        return
    if payload.user_id == bot.user.id:
        return
    emoji = str(payload.emoji)
    if emoji not in POZICE_EMOJI:
        return

    user_choices.setdefault(payload.user_id, [])
    if emoji not in user_choices[payload.user_id]:
        if len(user_choices[payload.user_id]) < 2:
            user_choices[payload.user_id].append(emoji)
        else:
            # smaže nadbytečnou reakci
            channel = bot.get_channel(payload.channel_id)
            msg = await channel.fetch_message(payload.message_id)
            member = payload.member
            await msg.remove_reaction(emoji, member)
            try:
                await member.send("❌ Už máš vybrané 2 pozice, další nelze přidat!")
            except:
                pass
    save_data()
    await update_pozice_status(payload.member.guild)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.channel_id != POZICE_CHANNEL_ID:
        return
    emoji = str(payload.emoji)
    if emoji not in POZICE_EMOJI:
        return

    if payload.user_id in user_choices and emoji in user_choices[payload.user_id]:
        user_choices[payload.user_id].remove(emoji)
        save_data()
        guild = bot.get_guild(payload.guild_id)
        if guild:
            await update_pozice_status(guild)

# ==== Start ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    load_data()
    await setup_pozice()
