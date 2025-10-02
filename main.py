import os
import json
import discord
from discord.ext import commands, tasks
from datetime import datetime, time, timedelta
from flask import Flask
from threading import Thread
from discord import Embed

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

# ==== Config ====
CHANNEL_HLASOVANI = 1396253060745007216  # kanál hlasování
CHANNEL_POZICE = 1393525512462270564    # kanál pozice
CHANNEL_TURNAJ = 1396254859577004253    # kanál turnaj (pokec)

hlasovali_yes = set()
hlasovali_no = set()
hlasovaci_zprava_id = None
last_turnaj_sent = None  # poslední čas odeslání turnaje

# ==== Soubory ====
LAST_TURNAJ_FILE = "last_turnaj.txt"
POZICE_FILE = "pozice.json"
POZICE_TXT = "pozice.txt"

# ==== POZICE ====
POZICE_EMOJI = {
    "⚽": "Útočník (LK, PK, HÚ, SÚ)",
    "🎯": "Střední záložník (SOZ, SDZ)",
    "🏃": "Krajní záložník (LZ, PZ)",
    "🛡️": "Obránce (LO, PO, SO)",
    "🧤": "Brankář (GK)"
}

uzivatele_pozice = {}
status_msg_id = None
embed_msg_id = None

# ==== Souborové funkce ====
def load_last_turnaj():
    global last_turnaj_sent
    if os.path.exists(LAST_TURNAJ_FILE):
        with open(LAST_TURNAJ_FILE, "r") as f:
            ts = f.read().strip()
            if ts:
                last_turnaj_sent = datetime.fromisoformat(ts)

def save_last_turnaj():
    if last_turnaj_sent:
        with open(LAST_TURNAJ_FILE, "w") as f:
            f.write(last_turnaj_sent.isoformat())

def load_pozice():
    global uzivatele_pozice
    if os.path.exists(POZICE_FILE):
        with open(POZICE_FILE, "r", encoding="utf-8") as f:
            uzivatele_pozice = json.load(f)

def save_pozice():
    with open(POZICE_FILE, "w", encoding="utf-8") as f:
        json.dump(uzivatele_pozice, f, ensure_ascii=False)

def save_nehlasujici_txt(seznam):
    with open(POZICE_TXT, "w", encoding="utf-8") as f:
        if seznam:
            f.write("\n".join(seznam))
        else:
            f.write("Všichni už mají vybráno ✅")


# ==== TURNAJ ====
@tasks.loop(minutes=5)
async def kontrola_turnaje():
    global last_turnaj_sent
    channel = bot.get_channel(CHANNEL_TURNAJ)
    now = datetime.utcnow()

    if not last_turnaj_sent or (now - last_turnaj_sent).total_seconds() >= 3*3600:
        await channel.send("@everyone ⚽ Dnes je turnaj proti CZ klubům! Připravte se a nezapomeňte hlasovat.")
        last_turnaj_sent = now
        save_last_turnaj()


# ==== POZICE ====
async def setup_pozice():
    global status_msg_id, embed_msg_id
    channel = bot.get_channel(CHANNEL_POZICE)

    # smažeme vše
    async for msg in channel.history(limit=100):
        await msg.delete()

    embed = Embed(
        title="📌 Přečti si pozorně a vyber max. 2 pozice!",
        description=(
            "Jakmile vybereš, **nejde to vrátit zpět** ⛔\n\n"
            "Každý hráč má možnost zvolit **primární a sekundární pozici.**\n\n"
            "**Rozdělení pozic:**\n"
            "⚽ Útočník (LK, PK, HÚ, SÚ)\n"
            "🎯 Střední záložník (SOZ, SDZ)\n"
            "🏃 Krajní záložník (LZ, PZ)\n"
            "🛡️ Obránce (LO, PO, SO)\n"
            "🧤 Brankář (GK)\n"
        ),
        color=discord.Color.red()
    )

    embed_msg = await channel.send(embed=embed)
    embed_msg_id = embed_msg.id

    for emoji in POZICE_EMOJI:
        await embed_msg.add_reaction(emoji)

    status_msg = await channel.send("📢 Kontrola pozic probíhá...")
    status_msg_id = status_msg.id

    await update_nehlasujici()


async def update_nehlasujici():
    global status_msg_id
    channel = bot.get_channel(CHANNEL_POZICE)
    guild = channel.guild

    # hráči bez 2 pozic
    nehlasujici = [m.mention for m in guild.members if not m.bot and len(uzivatele_pozice.get(str(m.id), [])) < 2]

    text = "📢 Tito hráči ještě nemají 2 pozice:\n"
    text += ", ".join(nehlasujici) if nehlasujici else "✅ Všichni už mají vybráno!"

    # uložíme i do TXT
    save_nehlasujici_txt(nehlasujici)

    if status_msg_id:
        try:
            msg = await channel.fetch_message(status_msg_id)
            await msg.edit(content=text)
        except:
            new_msg = await channel.send(text)
            status_msg_id = new_msg.id


@tasks.loop(minutes=30)
async def kontrola_pozic():
    await update_nehlasujici()


@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id == CHANNEL_POZICE:
        user_id = str(payload.user_id)
        if user_id == str(bot.user.id):
            return

        if user_id not in uzivatele_pozice:
            uzivatele_pozice[user_id] = []

        if len(uzivatele_pozice[user_id]) >= 2:
            channel = bot.get_channel(payload.channel_id)
            msg = await channel.fetch_message(payload.message_id)
            member = payload.member
            await msg.remove_reaction(payload.emoji, member)
            try:
                await member.send("❌ Už máš vybrané 2 pozice! Nelze přidat další.")
            except:
                pass
            return

        uzivatele_pozice[user_id].append(str(payload.emoji))
        save_pozice()
        await update_nehlasujici()
        if len(uzivatele_pozice[user_id]) == 2:
            try:
                member = payload.member
                await member.send("✅ Děkujeme, už máš vybrané obě pozice – usnadníš nám sestavu!")
            except:
                pass


# ==== Bot odpověď na zmínku ====
@bot.event
async def on_message(message):
    if bot.user.mentioned_in(message) and not message.author.bot:
        await message.channel.send(f"{message.author.mention} 👋 jsem tady! Jak ti můžu pomoct?")
    await bot.process_commands(message)


# ==== Start ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")

    load_last_turnaj()
    load_pozice()

    if not kontrola_turnaje.is_running():
        kontrola_turnaje.start()
    if not kontrola_pozic.is_running():
        kontrola_pozic.start()

    await setup_pozice()

keep_alive()
bot.run(DISCORD_TOKEN)
