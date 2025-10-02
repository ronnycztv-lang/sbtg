import os
import discord
from discord.ext import commands
from flask import Flask
from threading import Thread
import json
import re

# ==== Keep Alive server ====
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

# ==== Config ====
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
POZICE_CHANNEL_ID = 1393525512462270564  # kanál #pozice
STATUS_FILE = "pozice.json"

# Emoji → pozice
POZICE_EMOJI = {
    "⚽": "Útočník (LK/PK/HÚ/SÚ)",
    "🎯": "Střední záložník (SOZ/SDZ)",
    "🏃": "Krajní záložník (LZ/PZ)",
    "🛡️": "Obránce (LO/PO/SO)",
    "🧤": "Brankář (GK)"
}

status_pozice_id = None
intro_msg_id = None
user_choices = {}

# ==== Persistence ====
def load_data():
    global status_pozice_id, user_choices, intro_msg_id
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            status_pozice_id = data.get("status_msg_id")
            intro_msg_id = data.get("intro_msg_id")
            user_choices = data.get("choices", {})
    else:
        status_pozice_id = None
        intro_msg_id = None
        user_choices = {}

def save_data():
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "status_msg_id": status_pozice_id,
            "intro_msg_id": intro_msg_id,
            "choices": user_choices
        }, f, indent=2, ensure_ascii=False)

# ==== Helper ====
async def update_pozice_status(guild):
    global status_pozice_id
    channel = bot.get_channel(POZICE_CHANNEL_ID)

    all_members = [m for m in guild.members if not m.bot]
    nezvolili = [m for m in all_members if str(m.id) not in user_choices or len(user_choices[str(m.id)]) < 2]
    zvolili = {m: user_choices[str(m.id)] for m in all_members if str(m.id) in user_choices and len(user_choices[str(m.id)]) >= 2}

    # Text výpisu
    text = "📢 **Tito hráči ještě nemají 2 pozice:**\n"
    if nezvolili:
        text += ", ".join([f"{m.mention} ({len(user_choices.get(str(m.id), []))}/2)" for m in nezvolili])
    else:
        text += "✅ Všichni mají vybrané 2 pozice!"

    text += "\n\n✅ **Už vybrali:**\n"
    if zvolili:
        for m, pos in zvolili.items():
            pozice_text = ", ".join(pos)
            text += f"{m.mention} ✅ ({pozice_text})\n"
    else:
        text += "Nikdo zatím."

    text += f"\n\n📊 **Statistika:** {len(zvolili)}/{len(all_members)} hráčů má vybrané 2 pozice."

    if status_pozice_id:
        try:
            msg = await channel.fetch_message(status_pozice_id)
            await msg.edit(content=text)
        except:
            new_msg = await channel.send(text)
            status_pozice_id = new_msg.id
            save_data()
    else:
        new_msg = await channel.send(text)
        status_pozice_id = new_msg.id
        save_data()

# Funkce na update přezdívky
async def update_nickname(member, positions):
    try:
        base_name = re.sub(r"\s*\(.*?\)$", "", member.display_name)  # odstraní staré závorky
        if positions:
            new_name = f"{base_name} ({', '.join(positions)})"
        else:
            new_name = base_name
        await member.edit(nick=new_name)
    except discord.Forbidden:
        print(f"⚠️ Nemám práva změnit přezdívku: {member.display_name}")

# ==== Setup ====
async def setup_pozice():
    global intro_msg_id, status_pozice_id
    channel = bot.get_channel(POZICE_CHANNEL_ID)

    # smaže staré zprávy bota
    async for msg in channel.history(limit=50):
        if msg.author == bot.user:
            await msg.delete()

    # Intro zpráva
    intro_text = (
        "📌 **Přečti si pozorně a vyber max. 2 pozice!**\n"
        "Jakmile vybereš, ❌ **nejde to vrátit zpět.**\n\n"
        "Každý hráč má možnost zvolit **primární a sekundární pozici.**\n\n"
        "**Rozdělení pozic:**\n"
        "⚽ Útočník (LK/PK/HÚ/SÚ)\n"
        "🎯 Střední záložník (SOZ/SDZ)\n"
        "🏃 Krajní záložník (LZ/PZ)\n"
        "🛡️ Obránce (LO/PO/SO)\n"
        "🧤 Brankář (GK)"
    )
    intro_msg = await channel.send(intro_text)
    intro_msg_id = intro_msg.id
    for e in POZICE_EMOJI.keys():
        await intro_msg.add_reaction(e)

    # Status zpráva
    status_msg = await channel.send("⏳ Načítám seznam hráčů...")
    status_pozice_id = status_msg.id
    save_data()

    await update_pozice_status(channel.guild)

# ==== Events ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    load_data()
    guild = bot.guilds[0]
    if not intro_msg_id or not status_pozice_id:
        await setup_pozice()
    else:
        await update_pozice_status(guild)

@bot.event
async def on_raw_reaction_add(payload):
    global user_choices
    if payload.channel_id != POZICE_CHANNEL_ID or payload.user_id == bot.user.id:
        return
    emoji = payload.emoji.name
    if emoji not in POZICE_EMOJI:
        return

    user_id = str(payload.user_id)
    pos = POZICE_EMOJI[emoji]

    if user_id not in user_choices:
        user_choices[user_id] = []
    if len(user_choices[user_id]) >= 2:
        member = payload.member
        await member.send("❌ Už máš vybrané 2 pozice, další přidat nemůžeš.")
        channel = bot.get_channel(payload.channel_id)
        msg = await channel.fetch_message(payload.message_id)
        await msg.remove_reaction(payload.emoji, payload.member)
        return

    if pos not in user_choices[user_id]:
        user_choices[user_id].append(pos)

    save_data()
    await update_pozice_status(payload.member.guild)

    # Update přezdívky
    if len(user_choices[user_id]) == 2:
        await update_nickname(payload.member, user_choices[user_id])

@bot.event
async def on_raw_reaction_remove(payload):
    global user_choices
    if payload.channel_id != POZICE_CHANNEL_ID or payload.user_id == bot.user.id:
        return
    emoji = payload.emoji.name
    if emoji not in POZICE_EMOJI:
        return

    user_id = str(payload.user_id)
    pos = POZICE_EMOJI[emoji]
    if user_id in user_choices and pos in user_choices[user_id]:
        user_choices[user_id].remove(pos)
        save_data()
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        await update_pozice_status(guild)
        await update_nickname(member, user_choices[user_id])

# ==== Start ====
keep_alive()
bot.run(DISCORD_TOKEN)
