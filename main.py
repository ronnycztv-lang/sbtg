import os
import discord
from discord.ext import commands
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
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
POZICE_CHANNEL_ID = 1393525512462270564  # ID kanálu #pozice

# Emoji → pozice
POZICE_EMOJI = {
    "⚽": "Útočník (LK/PK/HÚ/SÚ)",
    "🎯": "Střední záložník (SOZ/SDZ)",
    "🏃": "Krajní záložník (LZ/PZ)",
    "🛡️": "Obránce (LO/PO/SO)",
    "🧤": "Brankář (GK)"
}

intro_msg_id = None
status_msg_id = None
user_choices = {}

# ==== Setup ====
async def setup_pozice():
    global intro_msg_id, status_msg_id, user_choices
    channel = bot.get_channel(POZICE_CHANNEL_ID)

    # 🧹 smažeme všechny zprávy bota v kanálu
    async for msg in channel.history(limit=100):
        if msg.author == bot.user:
            await msg.delete()

    user_choices = {}  # reset všech voleb

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
    intro_msg_id = intro_msg.id

    for e in POZICE_EMOJI.keys():
        await intro_msg.add_reaction(e)

    # status zpráva
    status_msg = await channel.send("⏳ Načítám seznam hráčů...")
    status_msg_id = status_msg.id

    await update_status(channel.guild)

# ==== Update status ====
async def update_status(guild):
    global status_msg_id
    channel = bot.get_channel(POZICE_CHANNEL_ID)
    try:
        msg = await channel.fetch_message(status_msg_id)
    except:
        msg = await channel.send("⏳ Načítám seznam hráčů...")
        status_msg_id = msg.id

    not_done = []
    done = []
    for member in guild.members:
        if member.bot:
            continue
        choices = user_choices.get(member.id, [])
        if len(choices) == 2:
            pozice_text = ", ".join([POZICE_EMOJI[c] for c in choices])
            done.append(f"{member.mention} ✅ ({pozice_text})")
        else:
            not_done.append(f"{member.mention} ({len(choices)}/2)")

    total = len([m for m in guild.members if not m.bot])
    finished = len(done)

    status_text = (
        f"📢 Tito hráči ještě nemají 2 pozice:\n" + (", ".join(not_done) if not_done else "Nikdo 🎉") +
        "\n\n✅ **Už vybrali:**\n" + ("\n".join(done) if done else "Nikdo zatím.") +
        f"\n\n📊 **Statistika:** {finished}/{total} hráčů má vybrané 2 pozice."
    )
    await msg.edit(content=status_text)

# ==== Reakce ====
@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != POZICE_CHANNEL_ID or payload.user_id == bot.user.id:
        return
    emoji = str(payload.emoji)
    if emoji not in POZICE_EMOJI:
        return

    user_choices.setdefault(payload.user_id, [])
    if emoji not in user_choices[payload.user_id]:
        if len(user_choices[payload.user_id]) < 2:
            user_choices[payload.user_id].append(emoji)
        else:
            # smaže nadbytečnou reakci
            channel = bot.get_channel(payload.channel_id)
            msg = await channel.fetch_message(payload.message_id)
            member = payload.member
            await msg.remove_reaction(emoji, member)
            try:
                await member.send("❌ Už máš vybrané 2 pozice, další nelze přidat!")
            except:
                pass

    guild = bot.get_guild(payload.guild_id)
    if guild:
        await update_status(guild)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.channel_id != POZICE_CHANNEL_ID:
        return
    emoji = str(payload.emoji)
    if emoji not in POZICE_EMOJI:
        return
    if payload.user_id in user_choices and emoji in user_choices[payload.user_id]:
        user_choices[payload.user_id].remove(emoji)
        guild = bot.get_guild(payload.guild_id)
        if guild:
            await update_status(guild)

# ==== Start ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    await setup_pozice()

keep_alive()
bot.run(DISCORD_TOKEN)
