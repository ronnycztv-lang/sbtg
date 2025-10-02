import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import json

TOKEN = os.environ["DISCORD_TOKEN"]

# ID kanálů
CHANNEL_POZICE = 1393525512462270564
CHANNEL_TURNAJ = 1396254859577004253

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# Uložené data
uzivatele_pozice = {}
status_msg_id = None
LAST_TURNAJ_FILE = "last_turnaj.txt"
POZICE_FILE = "pozice.txt"

# Emoji pro pozice
POZICE_EMOJI = {
    "⚽": "Útočník (LK, PK, HÚ, SÚ)",
    "🎯": "Střední záložník (SOZ, SDZ)",
    "🏃": "Krajní záložník (LZ, PZ)",
    "🛡️": "Obránce (LO, PO, SO)",
    "🧤": "Brankář (GK)"
}

# --- Pomocné funkce ---
def save_pozice():
    with open("pozice.json", "w", encoding="utf-8") as f:
        json.dump(uzivatele_pozice, f)

def load_pozice():
    global uzivatele_pozice
    try:
        with open("pozice.json", "r", encoding="utf-8") as f:
            uzivatele_pozice = json.load(f)
    except FileNotFoundError:
        uzivatele_pozice = {}

def save_last_turnaj(ts):
    with open(LAST_TURNAJ_FILE, "w") as f:
        f.write(str(ts))

def load_last_turnaj():
    try:
        with open(LAST_TURNAJ_FILE, "r") as f:
            return float(f.read().strip())
    except:
        return 0

def save_nehlasujici_txt(nehlasujici):
    with open(POZICE_FILE, "w", encoding="utf-8") as f:
        for radek in nehlasujici:
            f.write(radek + "\n")

# --- UPDATE nehlasujících ---
async def update_nehlasujici():
    global status_msg_id
    channel = bot.get_channel(CHANNEL_POZICE)
    guild = channel.guild

    nehlasujici = []
    for m in guild.members:
        if m.bot:
            continue
        pocet = len(uzivatele_pozice.get(str(m.id), []))
        if pocet < 2:
            nehlasujici.append(f"{m.mention} ({pocet}/2)")

    text = "📢 Tito hráči ještě nemají 2 pozice:\n"
    text += ", ".join(nehlasujici) if nehlasujici else "✅ Všichni už mají vybráno!"

    save_nehlasujici_txt(nehlasujici)

    if status_msg_id:
        try:
            msg = await channel.fetch_message(status_msg_id)
            await msg.edit(content=text)
        except:
            new_msg = await channel.send(text)
            status_msg_id = new_msg.id
    else:
        new_msg = await channel.send(text)
        status_msg_id = new_msg.id

# --- Inicializace zprávy s pozicemi ---
async def setup_pozice():
    global status_msg_id
    channel = bot.get_channel(CHANNEL_POZICE)

    # smaže staré zprávy
    await channel.purge(limit=50)

    embed = discord.Embed(
        title="📌 Přečti si pozorně a vyber max. 2 pozice!",
        description="Jakmile vybereš, **nejde to vrátit zpět. ⛔**\n\n"
                    "Každý hráč má možnost zvolit **primární a sekundární pozici.**\n\n"
                    "**Rozdělení pozic:**\n"
                    "⚽ Útočník (LK, PK, HÚ, SÚ)\n"
                    "🎯 Střední záložník (SOZ, SDZ)\n"
                    "🏃 Krajní záložník (LZ, PZ)\n"
                    "🛡️ Obránce (LO, PO, SO)\n"
                    "🧤 Brankář (GK)\n",
        color=discord.Color.red()
    )

    msg = await channel.send(embed=embed)

    # přidá reakce
    for emoji in POZICE_EMOJI.keys():
        await msg.add_reaction(emoji)

    status_msg_id = None
    await update_nehlasujici()

# --- Eventy ---
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    load_pozice()
    await setup_pozice()
    kontrola_pozic.start()
    turnaj_notifikace.start()

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    if payload.channel_id != CHANNEL_POZICE:
        return
    if str(payload.emoji) not in POZICE_EMOJI:
        return

    user_id = str(payload.user_id)
    pozice = uzivatele_pozice.get(user_id, [])

    if str(payload.emoji) in pozice:
        return

    if len(pozice) >= 2:
        # smaže reakci
        channel = bot.get_channel(payload.channel_id)
        msg = await channel.fetch_message(payload.message_id)
        member = msg.guild.get_member(payload.user_id)
        await msg.remove_reaction(payload.emoji, member)
        await channel.send(f"{member.mention} ❌ Už máš vybrané 2 pozice!", delete_after=5)
        return

    pozice.append(str(payload.emoji))
    uzivatele_pozice[user_id] = pozice
    save_pozice()

    member = bot.get_channel(payload.channel_id).guild.get_member(payload.user_id)
    if len(pozice) == 2:
        try:
            await member.send("✅ Díky! Úspěšně sis vybral dvě pozice. To nám usnadní sestavu!")
        except:
            pass

    await update_nehlasujici()

@bot.event
async def on_raw_reaction_remove(payload):
    # zabrání odstranění – pozice jsou trvalé
    if payload.channel_id == CHANNEL_POZICE:
        channel = bot.get_channel(payload.channel_id)
        msg = await channel.fetch_message(payload.message_id)
        member = msg.guild.get_member(payload.user_id)
        await msg.add_reaction(payload.emoji)

# --- Kontrola každých 30 min ---
@tasks.loop(minutes=30)
async def kontrola_pozic():
    await update_nehlasujici()

# --- Turnaj ---
@tasks.loop(minutes=5)
async def turnaj_notifikace():
    channel = bot.get_channel(CHANNEL_TURNAJ)
    now = datetime.utcnow().timestamp()
    last_sent = load_last_turnaj()

    if now - last_sent >= 3 * 3600:  # 3 hodiny
        msg = await channel.send("@everyone 📢 **Dnes je turnaj proti CZ klubům!**")
        save_last_turnaj(now)

# --- Odpověď při označení ---
@bot.event
async def on_message(message):
    if bot.user.mentioned_in(message) and not message.author.bot:
        await message.channel.send(f"{message.author.mention} ✅ Jsem tady, jsem připraven!")
    await bot.process_commands(message)

bot.run(TOKEN)
