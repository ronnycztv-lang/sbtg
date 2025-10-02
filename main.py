import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread

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
CHANNEL_POZICE = 1393525512462270564  # tvůj kanál #pozice

# Emoji pro pozice
POZICE_EMOJI = {
    "⚽": "Útočník (LK, PK, HÚ, SÚ)",
    "🎯": "Střední záložník (SOZ, SDZ)",
    "🏃": "Krajní záložník (LZ, PZ)",
    "🛡️": "Obránce (LO, PO, SO)",
    "🧤": "Brankář (GK)"
}

# Ukládání vybraných pozic
user_choices = {}  # {user_id: set(emoji)}
main_message_id = None
status_message_id = None

# ==== Funkce pro nastavení pozic ====
async def setup_pozice():
    global main_message_id, status_message_id
    channel = bot.get_channel(CHANNEL_POZICE)

    # smaž staré zprávy od bota
    async for msg in channel.history(limit=50):
        if msg.author == bot.user:
            await msg.delete()

    # vytvoř embed
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

    # status – kdo ještě nehlasoval
    status_msg = await channel.send("📢 Načítám seznam hráčů…")
    status_message_id = status_msg.id
    await update_status(channel.guild)

async def update_status(guild):
    """Aktualizuje seznam hráčů, co nemají 2 pozice"""
    global status_message_id
    channel = bot.get_channel(CHANNEL_POZICE)

    if status_message_id is None:
        return

    status_msg = await channel.fetch_message(status_message_id)

    nezvolili = []
    for member in guild.members:
        if not member.bot:
            count = len(user_choices.get(member.id, []))
            if count < 2:
                nezvolili.append(f"{member.mention} ({count}/2)")

    if nezvolili:
        text = "📢 Tito hráči ještě nemají 2 pozice:\n" + ", ".join(nezvolili)
    else:
        text = "✅ Všichni už mají vybrané 2 pozice!"

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

    user_id = payload.user_id
    emoji = str(payload.emoji)

    # inicializace
    if user_id not in user_choices:
        user_choices[user_id] = set()

    # kontrola počtu
    if len(user_choices[user_id]) >= 2 and emoji not in user_choices[user_id]:
        # smaž 3. reakci
        channel = bot.get_channel(payload.channel_id)
        msg = await channel.fetch_message(payload.message_id)
        user = payload.member
        await msg.remove_reaction(emoji, user)
        try:
            await user.send("❌ Už máš vybrané 2 pozice, další přidat nemůžeš.")
        except:
            pass
        return

    # přidej pozici
    user_choices[user_id].add(emoji)

    # DM podle počtu
    user = payload.member
    if len(user_choices[user_id]) == 1:
        await user.send(f"👉 Máš vybranou 1. pozici: **{POZICE_EMOJI[emoji]}**")
    elif len(user_choices[user_id]) == 2:
        await user.send(f"✅ Máš vybrané 2 pozice, děkujeme!")

    await update_status(user.guild)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.message_id != main_message_id:
        return
    if payload.user_id == bot.user.id:
        return

    user_id = payload.user_id
    emoji = str(payload.emoji)

    if user_id in user_choices and emoji in user_choices[user_id]:
        user_choices[user_id].remove(emoji)

    guild = bot.get_guild(payload.guild_id)
    await update_status(guild)

# ==== Start ====
keep_alive()
bot.run(DISCORD_TOKEN)
