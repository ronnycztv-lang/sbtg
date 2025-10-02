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
POZICE_CHANNEL_NAME = "pozice"  # název kanálu, ne ID
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

# ==== Helpers ====
def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_data():
    global data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

# ==== Setup pozice ====
async def setup_pozice():
    guild = bot.guilds[0]
    channel = discord.utils.get(guild.text_channels, name=POZICE_CHANNEL_NAME)
    if not channel:
        print("❌ Kanál 'pozice' nebyl nalezen!")
        return

    # smažeme všechny zprávy bota v kanálu
    async for msg in channel.history(limit=100):
        if msg.author == bot.user:
            await msg.delete()

    data["user_choices"] = {}
    save_data()

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
async def update_status(guild):
    channel = discord.utils.get(guild.text_channels, name=POZICE_CHANNEL_NAME)
    try:
        msg = await channel.fetch_message(data["status_msg_id"])
    except:
        msg = await channel.send("⏳ Načítám seznam hráčů...")
        data["status_msg_id"] = msg.id
        save_data()

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

    guild = bot.get_guild(payload.guild_id)
    channel = bot.get_channel(payload.channel_id)

    if channel.name != POZICE_CHANNEL_NAME:
        return

    emoji = str(payload.emoji)
    if emoji not in POZICE_EMOJI:
        return

    data["user_choices"].setdefault(str(payload.user_id), [])
    if emoji not in data["user_choices"][str(payload.user_id)]:
        if len(data["user_choices"][str(payload.user_id)]) < 2:
            data["user_choices"][str(payload.user_id)].append(emoji)
            save_data()
        else:
            # smazání nadbytečné reakce
            msg = await channel.fetch_message(payload.message_id)
            member = guild.get_member(payload.user_id)
            await msg.remove_reaction(emoji, member)
            try:
                await member.send("❌ Už máš vybrané 2 pozice, další nelze přidat!")
            except:
                pass

    await update_status(guild)

@bot.event
async def on_raw_reaction_remove(payload):
    guild = bot.get_guild(payload.guild_id)
    channel = bot.get_channel(payload.channel_id)
    if channel.name != POZICE_CHANNEL_NAME:
        return

    emoji = str(payload.emoji)
    if emoji not in POZICE_EMOJI:
        return

    if str(payload.user_id) in data["user_choices"] and emoji in data["user_choices"][str(payload.user_id)]:
        data["user_choices"][str(payload.user_id)].remove(emoji)
        save_data()
        await update_status(guild)

# ==== Turnaj reminder ====
@tasks.loop(hours=3)
async def turnaj_notifikace():
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=POZICE_CHANNEL_NAME)
        if channel:
            await channel.send("📢 Připomínka: Dnes je turnaj!")

# ==== Komunikace bota ====
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if "ahoj bot" in message.content.lower():
        await message.channel.send(f"Ahoj {message.author.mention} 👋")
    await bot.process_commands(message)

# ==== Start ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    load_data()
    if not data["intro_msg_id"] or not data["status_msg_id"]:
        await setup_pozice()
    else:
        await update_status(bot.guilds[0])

    if not turnaj_notifikace.is_running():
        turnaj_notifikace.start()

keep_alive()
bot.run(DISCORD_TOKEN)
