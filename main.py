import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import json

# ==== TOKEN ====
TOKEN = os.environ["DISCORD_TOKEN"]

# ==== ID kanálů ====
CHANNEL_TURNAJ = 1396254859577004253   # pokec / turnaje
CHANNEL_POZICE = 1393525512462270564   # pozice
CHANNEL_HLASOVANI = 1396253060745007216  # hlasování

# ==== Soubory ====
LAST_TURNAJ_FILE = "last_turnaj.txt"
POZICE_FILE = "pozice.json"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ==== POZICE ====
POZICE_EMOJI = {
    "⚽": "Útočník (LK, PK, HÚ, SÚ)",
    "🎯": "Střední záložník (SOZ, SDZ)",
    "🏃": "Krajní záložník (LZ, PZ)",
    "🛡️": "Obránce (LO, PO, SO)",
    "🧤": "Brankář (GK)"
}
pozice_data = {}
pozice_msg_id = None
status_pozice_id = None

# ==== HLASOVÁNÍ ====
hlasovani_msg_id = None
status_hlasovani_id = None
hlas_data = {}  # {user_id: "👍" / "❌" / "❓"}

# ==== Utility ====
def load_last_turnaj():
    try:
        with open(LAST_TURNAJ_FILE, "r") as f:
            return datetime.fromisoformat(f.read().strip())
    except:
        return None

def save_last_turnaj(time):
    with open(LAST_TURNAJ_FILE, "w") as f:
        f.write(time.isoformat())

def load_pozice():
    global pozice_data
    try:
        with open(POZICE_FILE, "r") as f:
            pozice_data = json.load(f)
    except:
        pozice_data = {}

def save_pozice():
    with open(POZICE_FILE, "w") as f:
        json.dump(pozice_data, f)

# ==== TURNaj ====
@tasks.loop(minutes=1)
async def turnaj_loop():
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_TURNAJ)

    last = load_last_turnaj()
    now = datetime.utcnow() + timedelta(hours=2)
    if not last or (now - last).total_seconds() >= 3*3600:
        async for msg in channel.history(limit=100):
            if msg.author == bot.user:
                await msg.delete()
        await channel.send("@everyone 📢 **Dnes je turnaj proti CZ klubům! Připravte se a nezapomeňte hlasovat.**")
        save_last_turnaj(now)

# ==== POZICE ====
async def setup_pozice():
    global pozice_msg_id, status_pozice_id
    channel = bot.get_channel(CHANNEL_POZICE)
    async for msg in channel.history(limit=100):
        if msg.author == bot.user:
            await msg.delete()

    embed = discord.Embed(
        title="📌 Přečti si pozorně a vyber max. 2 pozice!",
        description="Jakmile vybereš, **nejde to vrátit zpět. ⛔**\n\n" +
                    "\n".join([f"{e} {t}" for e, t in POZICE_EMOJI.items()]),
        color=discord.Color.red()
    )
    msg = await channel.send(embed=embed)
    pozice_msg_id = msg.id
    for e in POZICE_EMOJI.keys():
        await msg.add_reaction(e)

    status = await channel.send("📢 Seznam se načítá...")
    status_pozice_id = status.id
    await update_pozice_status(channel.guild)

async def update_pozice_status(guild):
    channel = bot.get_channel(CHANNEL_POZICE)
    msg = await channel.fetch_message(status_pozice_id)
    text = "📢 Tito hráči ještě nemají 2 pozice:\n"
    for m in guild.members:
        if not m.bot:
            pocet = len(pozice_data.get(str(m.id), []))
            if pocet < 2:
                text += f"{m.mention} ({pocet}/2)\n"
    await msg.edit(content=text)

# ==== Reakce na pozice ====
@bot.event
async def on_raw_reaction_add(payload):
    # ---- POZICE ----
    if payload.channel_id == CHANNEL_POZICE and str(payload.emoji) in POZICE_EMOJI:
        uid = str(payload.user_id)
        if uid not in pozice_data:
            pozice_data[uid] = []
        if len(pozice_data[uid]) >= 2:
            channel = bot.get_channel(payload.channel_id)
            msg = await channel.fetch_message(payload.message_id)
            await msg.remove_reaction(payload.emoji, payload.member)
            try:
                await payload.member.send("❌ Už máš vybrané 2 pozice, další nemůžeš přidat!")
            except: pass
            return
        pozice_data[uid].append(str(payload.emoji))
        save_pozice()
        await update_pozice_status(payload.member.guild)
        msg = await bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
        await msg.remove_reaction(payload.emoji, bot.user)
        if len(pozice_data[uid]) == 2:
            try:
                await payload.member.send("✅ Díky! Vybral sis 2 pozice.")
            except: pass

    # ---- HLASOVÁNÍ ----
    if payload.channel_id == CHANNEL_HLASOVANI and str(payload.emoji) in ["👍","❌","❓"]:
        uid = str(payload.user_id)
        if payload.user_id == bot.user.id: return
        hlas_data[uid] = str(payload.emoji)

        # vždy jen 1 reakce
        channel = bot.get_channel(payload.channel_id)
        msg = await channel.fetch_message(payload.message_id)
        for e in ["👍","❌","❓"]:
            if e != str(payload.emoji):
                await msg.remove_reaction(e, payload.member)

        # DM feedback
        try:
            if str(payload.emoji) == "👍":
                await payload.member.send("✅ Jsme rádi, že dorazíš na trénink!")
            elif str(payload.emoji) == "❌":
                await payload.member.send("⚠️ Nezapomeň se omluvit spoluhráčům, že nepřijdeš.")
        except: pass

        await update_hlasovani_status(payload.member.guild)

# ==== Hlasování ====
async def start_hlasovani():
    global hlasovani_msg_id, status_hlasovani_id
    channel = bot.get_channel(CHANNEL_HLASOVANI)
    async for msg in channel.history(limit=100):
        if msg.author == bot.user:
            await msg.delete()

    msg = await channel.send("🗳️ **Kdo jde na trénink?**\n👍 = Jdu\n❌ = Nejdou\n❓ = Ještě nevím")
    hlasovani_msg_id = msg.id
    for e in ["👍","❌","❓"]:
        await msg.add_reaction(e)

    guild = channel.guild
    for m in guild.members:
        if not m.bot:
            hlas_data[str(m.id)] = "❓"

    status = await channel.send("📢 Hlasování se načítá...")
    status_hlasovani_id = status.id
    await update_hlasovani_status(guild)

async def update_hlasovani_status(guild):
    channel = bot.get_channel(CHANNEL_HLASOVANI)
    msg = await channel.fetch_message(status_hlasovani_id)

    yes = [m.mention for m in guild.members if hlas_data.get(str(m.id))=="👍"]
    no = [m.mention for m in guild.members if hlas_data.get(str(m.id))=="❌"]
    maybe = [m.mention for m in guild.members if hlas_data.get(str(m.id))=="❓"]

    text = "📊 **Souhrn hlasování:**\n"
    text += f"👍 Půjdou: {', '.join(yes) if yes else 'Nikdo'}\n"
    text += f"❌ Nepůjdou: {', '.join(no) if no else 'Nikdo'}\n"
    text += f"❓ Nehlasovali: {', '.join(maybe) if maybe else 'Nikdo'}"
    await msg.edit(content=text)

# ==== Denní smyčka ====
@tasks.loop(minutes=1)
async def denni_hlasovani():
    now = datetime.utcnow() + timedelta(hours=2)

    # 08:00 = nové hlasování
    if now.hour == 8 and now.minute == 0:
        await start_hlasovani()

    # Připomínky
    if (now.hour, now.minute) in [(16,0), (17,0), (18,0)]:
        channel = bot.get_channel(CHANNEL_HLASOVANI)
        nehlasujici = [m.mention for m in channel.guild.members if hlas_data.get(str(m.id))=="❓"]
        if nehlasujici:
            await channel.send(f"⏰ Připomínka! Ještě nehlasovali: {', '.join(nehlasujici)}")

    # Poslední výzva 19:00
    if now.hour == 19 and now.minute == 0:
        channel = bot.get_channel(CHANNEL_HLASOVANI)
        nehlasujici = [m.mention for m in channel.guild.members if hlas_data.get(str(m.id))=="❓"]
        if nehlasujici:
            await channel.send(f"⚠️ Poslední výzva před tréninkem! Nehlasovali: {', '.join(nehlasujici)}")

    # Souhrn + smazání v 21:00
    if now.hour == 21 and now.minute == 0 and hlasovani_msg_id:
        channel = bot.get_channel(CHANNEL_HLASOVANI)
        await update_hlasovani_status(channel.guild)
        try:
            msg = await channel.fetch_message(hlasovani_msg_id)
            await msg.delete()
        except: pass

# ==== Ready ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    load_pozice()
    await setup_pozice()
    if not turnaj_loop.is_running():
        turnaj_loop.start()
    if not denni_hlasovani.is_running():
        denni_hlasovani.start()

bot.run(TOKEN)
