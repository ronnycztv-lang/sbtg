import os
import discord
from discord.ext import commands, tasks
from flask import Flask
from threading import Thread

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

# ==== Token ====
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]

# ==== ID kanálů ====
POZICE_CHANNEL_ID = 1393525512462270564  # kanál pro pozice

# ==== Úložiště pozic ====
uzivatele_pozice = {}  # {user_id: [pozice1, pozice2]}

# ==== Možnosti pozic ====
pozice_moznosti = {
    "Útočník (LK, PK, HÚ, SÚ)": "⚽",
    "Střední záložník (SOZ, SDZ)": "🎯",
    "Krajní záložník (LZ, PZ)": "🏃",
    "Obránce (LO, PO, SO)": "🛡️",
    "Brankář (GK)": "🧤"
}

# ==== Funkce pro vypsání pozic ====
async def vypis_pozice():
    channel = bot.get_channel(POZICE_CHANNEL_ID)
    if not channel:
        return

    # smaž všechny staré zprávy bota
    async for msg in channel.history(limit=100):
        if msg.author == bot.user:
            await msg.delete()

    # vytvoř embed s možnostmi
    embed = discord.Embed(
        title="📌 **Přečti si pozorně a vyber max. 2 pozice!**",
        description=(
            "Jakmile vybereš, **nejde to vrátit zpět**. ⛔\n\n"
            "Každý hráč má možnost zvolit **primární a sekundární pozici**.\n\n"
            "**Rozdělení pozic:**"
        ),
        color=discord.Color.red()
    )

    for text, emoji in pozice_moznosti.items():
        embed.add_field(name=f"{emoji} {text}", value=" ", inline=False)

    # pošli embed
    msg = await channel.send(embed=embed)
    for emoji in pozice_moznosti.values():
        await msg.add_reaction(emoji)

# ==== Reakce ====
@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != POZICE_CHANNEL_ID:
        return
    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    if not member:
        return

    emoji = str(payload.emoji)
    pozice = None
    for text, emj in pozice_moznosti.items():
        if emj == emoji:
            pozice = text
            break

    if not pozice:
        return

    # Pokud už má 2 pozice, smaž reakci
    if payload.user_id in uzivatele_pozice and len(uzivatele_pozice[payload.user_id]) >= 2:
        channel = bot.get_channel(payload.channel_id)
        msg = await channel.fetch_message(payload.message_id)
        await msg.remove_reaction(emoji, member)
        return

    # Přidej pozici
    if payload.user_id not in uzivatele_pozice:
        uzivatele_pozice[payload.user_id] = []
    if pozice not in uzivatele_pozice[payload.user_id]:
        uzivatele_pozice[payload.user_id].append(pozice)

    # Pokud už má 2 → pošli potvrzení do DM
    if len(uzivatele_pozice[payload.user_id]) == 2:
        try:
            await member.send("✅ Díky! Vybral sis 2 pozice – to nám pomůže lépe skládat sestavu. ⚽")
        except:
            pass

# ==== Start ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    await vypis_pozice()

keep_alive()
bot.run(DISCORD_TOKEN)
