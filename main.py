import os
import json
import discord
from discord.ext import commands, tasks
from flask import Flask
from threading import Thread

# ==== Keep Alive (Render) ====
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
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
POZICE_CHANNEL_NAME = "pozice"  # jméno kanálu
DATA_FILE = "data.json"

# Emoji → pozice
POZICE_EMOJI = {
    "⚽": "Útočník (LK/PK/HÚ/SÚ)",
    "🎯": "Střední záložník (SOZ/SDZ)",
    "🏃": "Krajní záložník (LZ/PZ)",
    "🛡️": "Obránce (LO/PO/SO)",
    "🧤": "Brankář (GK)"
}

# ==== Data ====
data = {
    "intro_msg_id": None,
    "status_msg_id": None,
    "user_choices": {}
}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f
