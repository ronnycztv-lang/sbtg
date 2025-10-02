import os
import discord
from discord.ext import commands, tasks
from datetime import datetime
import pytz

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

ATTENDANCE_CHANNEL_ID = 1396253060745007216
POZICE_CHANNEL_ID = 1393525512462270564
POKEC_CHANNEL_ID = 1396254859577004253

YES_EMOJI = "👍"
NO_EMOJI = "❌"
MAYBE_EMOJI = "❓"

POZICE_EMOJI = {
    "⚽": "Útočník (LK/PK/HÚ/SÚ)",
    "🎯": "Střední záložník (SOZ/SDZ)",
    "🏃": "Krajní záložník (LZ/PZ)",
    "🛡️": "Obránce (LO/PO/SO)",
    "🧤": "Brankář (GK)"
}

attendance_msg_id = None
status_msg_id = None
user_votes = {}
user_choices = {}
warned_users = set()

# ====== Docházka ======
@tasks.loop(minutes=1)
async def attendance_scheduler():
    prague = pytz.timezone("Europe/Prague")
    now = datetime.now(prague)

    if now.hour == 8 and now.minute == 0:
        for guild in bot.guilds:
            await create_attendance_poll(guild)

    if 15 <= now.hour <= 19 and now.minute == 0:
        for guild in bot.guilds:
            await remind_pending(guild)

    if now.hour == 19 and now.minute == 0:
        for guild in bot.guilds:
            await summarize_poll(guild)

    if now.hour == 21 and now.minute == 0:
        for guild in bot.guilds:
            await clear_poll(guild)

async def create_attendance_poll(guild):
    global attendance_msg_id, user_votes
    user_votes = {}
    channel = guild.get_channel(ATTENDANCE_CHANNEL_ID)

    async for msg in channel.history(limit=50):
        if msg.author == bot.user:
            await msg.delete()

    poll = await channel.send(
        f"📢 **Docházka na dnešní trénink**\n"
        f"{YES_EMOJI} = přijdu\n"
        f"{NO_EMOJI} = nepřijdu\n"
        f"{MAYBE_EMOJI} = zatím nevím"
    )
    attendance_msg_id = poll.id
    for e in [YES_EMOJI, NO_EMOJI, MAYBE_EMOJI]:
        await poll.add_reaction(e)
        await poll.remove_reaction(e, bot.user)

async def remind_pending(guild):
    for member in guild.members:
        if member.bot: continue
        if member.id not in user_votes or user_votes.get(member.id) == "maybe":
            await safe_dm(member, "⏰ Připomínka: Nezapomeň hlasovat na dnešní trénink!")

async def summarize_poll(guild):
    channel = guild.get_channel(ATTENDANCE_CHANNEL_ID)
    yes_list, no_list, missing_list = [], [], []
    for member in guild.members:
        if member.bot: continue
        vote = user_votes.get(member.id)
        if vote == "yes": yes_list.append(member.mention)
        elif vote == "no": no_list.append(member.mention)
        else: missing_list.append(member)

    await channel.send(
        f"📊 **Výsledky:**\n"
        f"✅ Přijdou: {', '.join(yes_list) or 'Nikdo'}\n"
        f"❌ Nepřijdou: {', '.join(no_list) or 'Nikdo'}"
    )
    for m in missing_list:
        await safe_dm(m, "⚠️ Nehlasoval jsi, omluv se a počítej s černým puntíkem.")

async def clear_poll(guild):
    global attendance_msg_id
    if not attendance_msg_id: return
    channel = guild.get_channel(ATTENDANCE_CHANNEL_ID)
    try:
        msg = await channel.fetch_message(attendance_msg_id)
        await msg.delete()
        attendance_msg_id = None
    except: pass

# ====== Pozice ======
async def setup_pozice(guild):
    global status_msg_id, user_choices
    user_choices = {}
    channel = guild.get_channel(POZICE_CHANNEL_ID)

    async for msg in channel.history(limit=50):
        if msg.author == bot.user:
            await msg.delete()

    intro = await channel.send(
        "📌 **Vyber si max. 2 pozice pomocí reakcí.**\n" +
        "\n".join([f"{k} = {v}" for k,v in POZICE_EMOJI.items()])
    )
    for e in POZICE_EMOJI.keys():
        await intro.add_reaction(e)
        await intro.remove_reaction(e, bot.user)

    status = await channel.send("⏳ Načítám seznam hráčů...")
    status_msg_id = status.id
    await update_status(guild)

async def update_status(guild):
    global status_msg_id
    channel = guild.get_channel(POZICE_CHANNEL_ID)
    try:
        msg = await channel.fetch_message(status_msg_id)
    except:
        status = await channel.send("⏳ Načítám seznam hráčů...")
        status_msg_id = status.id
        msg = status

    lines, finished = [], 0
    total = len([m for m in guild.members if not m.bot])
    for m in guild.members:
        if m.bot: continue
        ch = user_choices.get(m.id, [])
        if len(ch) == 0: lines.append(f"{m.mention} (0/2)")
        elif len(ch) == 1: lines.append(f"{m.mention} (1/2) – {POZICE_EMOJI[ch[0]]}")
        elif len(ch) == 2:
            finished += 1
            pos = ", ".join([POZICE_EMOJI[c] for c in ch])
            lines.append(f"{m.mention} (2/2) ✅ – {pos}")

    text = "🎉 Všichni dali svoje pozice!" if finished==total and total>0 \
        else "\n".join(lines) + f"\n\n📊 {finished}/{total} hráčů má 2 pozice"
    await msg.edit(content=text)

# ====== Turnaj připomínky ======
@tasks.loop(hours=3)
async def turnaj_notifikace():
    for guild in bot.guilds:
        channel = guild.get_channel(POKEC_CHANNEL_ID)
        if channel:
            await channel.send("@everyone 📢 Dneska je turnaj, nezapomeň! ⚽🔥")

# ====== DM helper ======
async def safe_dm(member, text):
    try: await member.send(text)
    except: pass

# ====== Start ======
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    for guild in bot.guilds:
        await create_attendance_poll(guild)
        await setup_pozice(guild)
    if not attendance_scheduler.is_running():
        attendance_scheduler.start()
    if not turnaj_notifikace.is_running():
        turnaj_notifikace.start()

bot.run(DISCORD_TOKEN)
