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
    "channel_id": None,
    "intro_msg_id": None,
    "status_msg_id": None,
    "user_choices": {}
}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_data():
    global data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)


# ==== Setup pozice (jen při prvním spuštění) ====
async def setup_pozice(guild: discord.Guild):
    global data
    user_choices = {}

    # smažeme starý kanál pokud existuje
    old_channel = discord.utils.get(guild.text_channels, id=data.get("channel_id")) \
                   or discord.utils.get(guild.text_channels, name="pozice")
    if old_channel:
        await old_channel.delete()

    # vytvoříme nový kanál
    channel = await guild.create_text_channel("pozice")
    data["channel_id"] = channel.id

    # intro zpráva
    intro_text = (
        "📌 **Přečti si pozorně a vyber max. 2 pozice!**\n"
        "Jakmile vybereš, ❌ **nejde to vrátit zpět.**\n\n"
        "Každý hráč má možnost zvolit **primární a sekundární pozici.**\n\n"
        "**Rozdělení pozic a emoji pro hlasování:**\n"
        "⚽ = Útočník (LK/PK/HÚ/SÚ)\n"
        "🎯 = Střední záložník (SOZ/SDZ)\n"
        "🏃 = Krajní záložník (LZ/PZ)\n"
        "🛡️ = Obránce (LO/PO/SO)\n"
        "🧤 = Brankář (GK)"
    )
    intro_msg = await channel.send(intro_text)
    data["intro_msg_id"] = intro_msg.id

    for e in POZICE_EMOJI.keys():
        await intro_msg.add_reaction(e)

    # status zpráva
    status_msg = await channel.send("⏳ Načítám seznam hráčů...")
    data["status_msg_id"] = status_msg.id

    save_data()
    await update_status(guild)


# ==== Update status ====
async def update_status(guild: discord.Guild):
    channel = guild.get_channel(data["channel_id"])
    msg = await channel.fetch_message(data["status_msg_id"])

    not_done = []
    done = []

    for member in guild.members:
        if member.bot:
            continue
        choices = data["user_choices"].get(str(member.id), [])
        if len(choices) == 2:
            pozice_text = ", ".join([POZICE_EMOJI[c] for c in choices])
            done.append(f"{member.mention} ✅ ({pozice_text})")
        else:
            not_done.append(f"{member.mention} ({len(choices)}/2)")

    total = len([m for m in guild.members if not m.bot])
    finished = len(done)

    status_text = (
        f"✅ **Už vybrali:**\n" + ("\n".join(done) if done else "Nikdo zatím.") +
        f"\n\n📢 **Tito hráči ještě nemají 2 pozice:**\n" +
        ("\n".join(not_done) if not_done else "Nikdo 🎉") +
        f"\n\n📊 **Statistika:** {finished}/{total} hráčů má vybrané 2 pozice."
    )

    await msg.edit(content=status_text)


# ==== Reakce ====
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    if payload.channel_id != data["channel_id"]:
        return

    guild = bot.get_guild(payload.guild_id)
    channel = guild.get_channel(payload.channel_id)
    emoji = str(payload.emoji)

    if emoji not in POZICE_EMOJI:
        return

    data["user_choices"].setdefault(str(payload.user_id), [])
    if emoji not in data["user_choices"][str(payload.user_id)]:
        if len(data["user_choices"][str(payload.user_id)]) < 2:
            data["user_choices"][str(payload.user_id)].append(emoji)
            save_data()
        else:
            msg = await channel.fetch_message(payload.message_id)
            member = guild.get_member(payload.user_id)
            await msg.remove_reaction(emoji, member)
            await channel.send(f"{member.mention} ❌ Už máš vybrané 2 pozice!")

    await update_status(guild)


@bot.event
async def on_raw_reaction_remove(payload):
    if payload.channel_id != data["channel_id"]:
        return

    guild = bot.get_guild(payload.guild_id)
    emoji = str(payload.emoji)

    if emoji in POZICE_EMOJI and str(payload.user_id) in data["user_choices"]:
        if emoji in data["user_choices"][str(payload.user_id)]:
            data["user_choices"][str(payload.user_id)].remove(emoji)
            save_data()

    await update_status(guild)


# ==== Turnaj reminder ====
@tasks.loop(hours=3)
async def turnaj_notifikace():
    for guild in bot.guilds:
        channel = guild.get_channel(data["channel_id"])
        if channel:
            await channel.send("📢 Připomínka: Dnes je turnaj!")


# ==== Start ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    load_data()
    for guild in bot.guilds:
        if not data["channel_id"]:  # jen při prvním spuštění
            await setup_pozice(guild)
        else:
            await update_status(guild)
    if not turnaj_notifikace.is_running():
        turnaj_notifikace.start()

keep_alive()
bot.run(DISCORD_TOKEN)
