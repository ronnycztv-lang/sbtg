import os
import json
import discord
from discord.ext import commands
from flask import Flask
from threading import Thread

# ==== Keep Alive ====
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
CHANNEL_POZICE = 1393525512462270564
POZICE_FILE = "pozice.json"

POZICE_EMOJI = {
    "⚽": ("Útočník", "LK/PK/HÚ/SÚ"),
    "🎯": ("Střední záložník", "SOZ/SDZ"),
    "🏃": ("Krajní záložník", "LZ/PZ"),
    "🛡️": ("Obránce", "LO/PO/SO"),
    "🧤": ("Brankář", "GK")
}

# ==== Save/load ====
def load_pozice():
    if os.path.exists(POZICE_FILE):
        with open(POZICE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_pozice():
    with open(POZICE_FILE, "w", encoding="utf-8") as f:
        json.dump(user_choices, f)

user_choices = load_pozice()  # { user_id: [emoji1, emoji2] }
main_message_id = None
status_message_id = None

# ==== Setup ====
async def setup_pozice():
    global main_message_id, status_message_id
    channel = bot.get_channel(CHANNEL_POZICE)

    # hledej původní zprávy
    async for msg in channel.history(limit=30):
        if msg.author == bot.user and msg.embeds and not main_message_id:
            main_message_id = msg.id
        elif msg.author == bot.user and not msg.embeds and not status_message_id:
            status_message_id = msg.id

    # pokud nejsou, vytvoř nové
    if not main_message_id:
        embed = discord.Embed(
            title="📌 Přečti si pozorně a vyber max. 2 pozice!",
            description=(
                "Jakmile vybereš, **nejde to vrátit zpět. ⛔**\n\n"
                "Každý hráč má možnost zvolit **primární a sekundární pozici**.\n\n"
                "**Rozdělení pozic:**\n"
                "⚽ Útočník (LK, PK, HÚ, SÚ)\n"
                "🎯 Střední záložník (SOZ, SDZ)\n"
                "🏃 Krajní záložník (LZ, PZ)\n"
                "🛡️ Obránce (LO, PO, SO)\n"
                "🧤 Brankář (GK)"
            ),
            color=discord.Color.red()
        )
        msg = await channel.send(embed=embed)
        main_message_id = msg.id

        # přidej reakce
        for e in POZICE_EMOJI.keys():
            await msg.add_reaction(e)

    if not status_message_id:
        status_msg = await channel.send("📢 Načítám seznam hráčů…")
        status_message_id = status_msg.id

    await update_status(channel.guild)

async def update_status(guild):
    """Aktualizace zprávy s přehledem hráčů"""
    global status_message_id
    if not status_message_id:
        return

    channel = bot.get_channel(CHANNEL_POZICE)
    status_msg = await channel.fetch_message(status_message_id)

    nezvolili = []
    hotovi = []
    total_members = 0

    for member in guild.members:
        if member.bot:
            continue
        total_members += 1
        choices = user_choices.get(str(member.id), [])
        if len(choices) < 2:
            nezvolili.append(f"{member.mention} ({len(choices)}/2)")
        else:
            pozice_names = [POZICE_EMOJI[e][1] for e in choices]
            hotovi.append(f"{member.mention} ✅ ({', '.join(pozice_names)})")

    text = ""
    if nezvolili:
        text += "📢 Tito hráči ještě nemají 2 pozice:\n" + ", ".join(nezvolili) + "\n\n"
    if hotovi:
        text += "✅ Už vybrali: \n" + ", ".join(hotovi) + "\n\n"

    text += f"📊 Statistika: {len(hotovi)}/{total_members} hráčů má vybrané 2 pozice."

    await status_msg.edit(content=text)

# ==== Eventy ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    await setup_pozice()

@bot.event
async def on_raw_reaction_add(payload):
    global user_choices
    if payload.message_id != main_message_id:
        return
    if payload.user_id == bot.user.id:
        return

    user_id = str(payload.user_id)
    emoji = str(payload.emoji)

    if user_id not in user_choices:
        user_choices[user_id] = []

    # pokud už má 2 a chce třetí → blok
    if len(user_choices[user_id]) >= 2 and emoji not in user_choices[user_id]:
        channel = bot.get_channel(payload.channel_id)
        msg = await channel.fetch_message(payload.message_id)
        user = payload.member
        await msg.remove_reaction(emoji, user)
        try:
            await user.send("❌ Už máš vybrané 2 pozice, další přidat nemůžeš.")
        except:
            pass
        return

    if emoji not in user_choices[user_id]:
        user_choices[user_id].append(emoji)

    save_pozice()

    user = payload.member
    if len(user_choices[user_id]) == 1:
        await user.send(f"👉 Máš vybranou 1. pozici: **{POZICE_EMOJI[emoji][0]}**")
    elif len(user_choices[user_id]) == 2:
        await user.send("✅ Máš vybrané 2 pozice, děkujeme!")

    await update_status(user.guild)

@bot.event
async def on_raw_reaction_remove(payload):
    user_id = str(payload.user_id)
    emoji = str(payload.emoji)

    if payload.message_id != main_message_id or user_id == str(bot.user.id):
        return

    if user_id in user_choices and emoji in user_choices[user_id]:
        user_choices[user_id].remove(emoji)
        save_pozice()

    guild = bot.get_guild(payload.guild_id)
    await update_status(guild)

# ==== Start ====
keep_alive()
bot.run(DISCORD_TOKEN)
