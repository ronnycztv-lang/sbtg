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

# Globální proměnné
attendance_msg_id = None
status_msg_id = None
user_votes = {}
user_choices = {}
warned_users = set()


# ==================================================
# 📌 Setup hlasování (každé ráno)
# ==================================================
async def create_attendance_poll(guild):
    global attendance_msg_id, user_votes
    user_votes = {}
    channel = guild.get_channel(ATTENDANCE_CHANNEL_ID)

    # smažeme staré zprávy bota
    async for msg in channel.history(limit=50):
        if msg.author == bot.user:
            await msg.delete()

    poll = await channel.send(
        "📢 **Docházka na dnešní trénink**\n"
        f"{YES_EMOJI} = přijdu\n"
        f"{NO_EMOJI} = nepřijdu\n"
        f"{MAYBE_EMOJI} = zatím nevím"
    )
    attendance_msg_id = poll.id
    for e in [YES_EMOJI, NO_EMOJI, MAYBE_EMOJI]:
        await poll.add_reaction(e)
        await poll.remove_reaction(e, bot.user)  # smaže reakci bota


# ==================================================
# 📌 Setup pozic
# ==================================================
async def setup_pozice(guild):
    global status_msg_id, user_choices
    user_choices = {}
    channel = guild.get_channel(POZICE_CHANNEL_ID)

    # smažeme staré zprávy bota
    async for msg in channel.history(limit=50):
        if msg.author == bot.user:
            await msg.delete()

    intro = await channel.send(
        "📌 **Vyber si max. 2 pozice pomocí reakcí.**\n" +
        "\n".join([f"{k} = {v}" for k, v in POZICE_EMOJI.items()])
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
        return  # zpráva není -> vynech

    lines = []
    total = len([m for m in guild.members if not m.bot])
    finished = 0
    for member in guild.members:
        if member.bot:
            continue
        choices = user_choices.get(member.id, [])
        if len(choices) == 0:
            lines.append(f"{member.mention} (0/2)")
        elif len(choices) == 1:
            lines.append(f"{member.mention} (1/2) – {POZICE_EMOJI[choices[0]]}")
        elif len(choices) == 2:
            finished += 1
            pos = ", ".join([POZICE_EMOJI[c] for c in choices])
            lines.append(f"{member.mention} (2/2) ✅ – {pos}")

    if finished == total and total > 0:
        text = "🎉 **Skvělá zpráva! Všichni dali svoje pozice!**"
    else:
        text = "\n".join(lines) + f"\n\n📊 {finished}/{total} hráčů má 2 pozice"
    await msg.edit(content=text)


# ==================================================
# 📌 Turnaj každé 3h
# ==================================================
@tasks.loop(hours=3)
async def turnaj_notifikace():
    for guild in bot.guilds:
        channel = guild.get_channel(POKEC_CHANNEL_ID)
        if channel:
            await channel.send("@everyone 📢 Dneska je turnaj, nezapomeň! ⚽🔥")


# ==================================================
# 📌 Reakce
# ==================================================
@bot.event
async def on_raw_reaction_add(payload):
    global user_votes, user_choices, warned_users, attendance_msg_id
    if payload.user_id == bot.user.id:
        return
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    emoji = str(payload.emoji)

    # Docházka
    if payload.message_id == attendance_msg_id:
        if emoji == YES_EMOJI:
            user_votes[member.id] = "yes"
            await safe_dm(member, "✅ Děkujeme, že přijdeš na trénink.")
        elif emoji == NO_EMOJI:
            user_votes[member.id] = "no"
            await safe_dm(member, "❌ Nezapomeň se omluvit, proč nejdeš.")
        elif emoji == MAYBE_EMOJI:
            user_votes[member.id] = "maybe"
            await safe_dm(member, "❓ Nezapomeň během dne hlasovat.")

    # Pozice
    elif payload.channel_id == POZICE_CHANNEL_ID and emoji in POZICE_EMOJI:
        user_choices.setdefault(payload.user_id, [])
        if emoji not in user_choices[payload.user_id]:
            if len(user_choices[payload.user_id]) < 2:
                user_choices[payload.user_id].append(emoji)
                if len(user_choices[payload.user_id]) == 1:
                    await safe_dm(member, "ℹ️ Máš jen jednu pozici, vyber ještě druhou.")
                elif len(user_choices[payload.user_id]) == 2:
                    await safe_dm(member, "✅ Děkujeme, vybral sis dvě pozice!")
            else:
                channel = bot.get_channel(payload.channel_id)
                msg = await channel.fetch_message(payload.message_id)
                await msg.remove_reaction(emoji, member)
                if member.id not in warned_users:
                    await safe_dm(member, "❌ Už máš vybrané 2 pozice!")
                    warned_users.add(member.id)
        await update_status(guild)


@bot.event
async def on_raw_reaction_remove(payload):
    global user_choices
    emoji = str(payload.emoji)
    if payload.channel_id == POZICE_CHANNEL_ID and emoji in POZICE_EMOJI:
        guild = bot.get_guild(payload.guild_id)
        if payload.user_id in user_choices and emoji in user_choices[payload.user_id]:
            user_choices[payload.user_id].remove(emoji)
        await update_status(guild)


# ==================================================
# 📌 Helper
# ==================================================
async def safe_dm(member, text):
    try:
        await member.send(text)
    except:
        pass


# ==================================================
# 📌 Start
# ==================================================
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    for guild in bot.guilds:
        # vždy vytvoří čerstvé zprávy
        await create_attendance_poll(guild)
        await setup_pozice(guild)
    if not turnaj_notifikace.is_running():
        turnaj_notifikace.start()

bot.run(DISCORD_TOKEN)
