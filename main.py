import os
import discord
from discord.ext import commands, tasks

# ==== Intents ====
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==== Config ====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
POZICE_CHANNEL_ID = 1393525512462270564  # tvůj kanál #pozice

# Emoji → pozice
POZICE_EMOJI = {
    "⚽": "Útočník (LK/PK/HÚ/SÚ)",
    "🎯": "Střední záložník (SOZ/SDZ)",
    "🏃": "Krajní záložník (LZ/PZ)",
    "🛡️": "Obránce (LO/PO/SO)",
    "🧤": "Brankář (GK)"
}

# ==== Globální proměnné ====
intro_msg_id = None
status_msg_id = None
user_choices = {}   # {user_id: [emoji, emoji]}
warned_users = set()  # uživatele, kterým už se poslalo varování


# ==== Setup ====
async def setup_pozice(guild: discord.Guild):
    global intro_msg_id, status_msg_id, user_choices
    user_ch_
