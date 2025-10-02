import os
import discord
from discord.ext import commands, tasks
from datetime import datetime
import pytz

# ==== Intents ====
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==== Config ====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# ID kanálů
ATTENDANCE_CHANNEL_ID = 1396253060745007216  # hlasování
POZICE_CHANNEL_ID = 1393525512462270564      # pozice
POKEC_CHANNEL_ID = 1396254859577004253       # pokec (turnaj)

# Emoji pro hlasování
YES_EMOJI = "👍"
NO_EMOJI = "❌"
MAYBE_EMOJI = "❓"

# Emoji pro pozice
POZICE_EMOJI = {
    "⚽": "Útočník (LK/PK/HÚ/SÚ)",
    "🎯": "Střední záložník (SOZ/SDZ)",
    "🏃": "Krajní záložník (LZ/PZ)",
    "🛡️": "Obránce (LO/PO/SO)",
    "🧤": "Brankář (GK)"
}

# ==== Globální proměnné ====
attendance_msg_id = None
user_votes = {}        # {user_id: "yes"/"no"/"maybe"}

intro_msg_id = None
status_msg_id = None
user_choices = {}      # {user_id: [emoji, emoji]}
warned_users = set()


# ==================================================
# 📌 1. Denní hlasování
# ==================================================
@tasks.loop(minutes=1)
async def attendance_scheduler():
    prague = pytz.timezone("Europe/Prague")
    now = datetime.now(prague)

    if now.hour == 8 and now.minute == 0:  # 8:00 → vytvoří hlasování
        for guild in bot.guilds:
            await create_attendance_poll(guild)

    if 15 <= now.hour <= 19 and now.minute == 0:  # připomínky 15–19h
        for guild in bot.guilds:
            await remind_pending(guild)

    if now.hour == 19 and now.minute == 0:  # 19:00 → shrnutí
        for guild in bot.guilds:
            await summarize_poll(guild)

    if now.hour == 21 and now.minute == 0:  # 21:00 → smaže hlasování
        for guild in bot.guilds:
            await clear_poll(guild)


async def create_attendance_poll(guild):
    global attendance_msg_id, user_votes
    user_votes = {}

    channel = guild.get_channel(ATTENDANCE_CHANNEL_ID)
    if not channel:
        return

    msg = await channel.send(
        "📢 **Docházka na dnešní trénink**\n"
        f"{YES_EMOJI} = přijdu\n"
        f"{NO_EMOJI} = nepřijdu\n"
        f"{MAYBE_EMOJI} = zatím nevím\n\n"
        "Prosím hlasujte co nejdříve!"
    )
    attendance_msg_id = msg.id
    await msg.add_reaction(YES_EMOJI)
    await msg.add_reaction(NO_EMOJI)
    await msg.add_reaction(MAYBE_EMOJI)

    # smaže botovy reakce
    await msg.remove_reaction(YES_EMOJI, bot.user)
    await msg.remove_reaction(NO_EMOJI, bot.user)
    await msg.remove_reaction(MAYBE_EMOJI, bot.user)


async def remind_pending(guild):
    global user_votes
    for member in guild.members:
        if member.bot:
            continue
        if member.id not in user_votes or user_votes.get(member.id) == "maybe":
            await safe_dm(member, "⏰ Připomínka: Nezapomeň hlasovat, zda přijdeš na dnešní trénink!")

