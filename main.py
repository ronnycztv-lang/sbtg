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

    # 8:00 → vytvoří hlasování
    if now.hour == 8 and now.minute == 0:
        for guild in bot.guilds:
            await create_attendance_poll(guild)

    # každou hodinu mezi 15–19 připomene těm s otazníkem nebo bez hlasu
    if 15 <= now.hour <= 19 and now.minute == 0:
        for guild in bot.guilds:
            await remind_pending(guild)

    # 19:00 → vyhodnocení hlasování
    if now.hour == 19 and now.minute == 0:
        for guild in bot.guilds:
            await summarize_poll(guild)

    # 21:00 → smaže hlasování
    if now.hour == 21 and now.minute == 0:
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


async def remind_pending(guild):
    global user_votes
    for member in guild.members:
        if member.bot:
            continue
        if member.id not in user_votes or user_votes.get(member.id) == "maybe":
            try:
                await member.send("⏰ Připomínka: Nezapomeň hlasovat, zda přijdeš na dnešní trénink!")
            except:
                pass


async def summarize_poll(guild):
    global user_votes
    channel = guild.get_channel(ATTENDANCE_CHANNEL_ID)
    if not channel:
        return

    yes_list, no_list, missing_list = [], [], []

    for member in guild.members:
        if member.bot:
            continue
        vote = user_votes.get(member.id)
        if vote == "yes":
            yes_list.append(member.mention)
        elif vote == "no":
            no_list.append(member.mention)
        else:
            missing_list.append(member)

    text = (
        "📊 **Výsledky docházky:**\n\n"
        f"✅ Přijdou: {', '.join(yes_list) if yes_list else 'Nikdo'}\n"
        f"❌ Nepřijdou: {', '.join(no_list) if no_list else 'Nikdo'}\n"
    )
    await channel.send(text)

    for m in missing_list:
        try:
            await m.send("⚠️ Nebyl jsi schopen hlasovat. Omluv se a počítej s černým puntíkem.")
        except:
            pass


async def clear_poll(guild):
    global attendance_msg_id
    if not attendance_msg_id:
        return
    channel = guild.get_channel(ATTENDANCE_CHANNEL_ID)
    if not channel:
        return
    try:
        msg = await channel.fetch_message(attendance_msg_id)
        await msg.delete()
        attendance_msg_id = None
        await channel.send("🗑️ Hlasování bylo smazáno, zítra bude nové v 8:00.")
    except:
        pass


# ==================================================
# 📌 2. Pozice hráčů
# ==================================================
async def setup_pozice(guild: discord.Guild):
    global intro_msg_id, status_msg_id, user_choices
    user_choices = {}

    channel = guild.get_channel(POZICE_CHANNEL_ID)
    if not channel:
        print("❌ Kanál pozice nebyl nalezen!")
        return

    # smažeme staré zprávy bota
    async for msg in channel.history(limit=100):
        if msg.author == bot.user:
            await msg.delete()

    # intro zpráva
    intro_text = (
        "📌 **Vyber si max. 2 pozice pomocí reakcí.**\n" +
        "\n".join([f"{k} = {v}" for k, v in POZICE_EMOJI.items()]) +
        "\n\n❗ Každý hráč má max. 2 pozice."
    )
    intro_msg = await channel.send(intro_text)
    intro_msg_id = intro_msg.id
    for e in POZICE_EMOJI.keys():
        await intro_msg.add_reaction(e)

    status_msg = await channel.send("⏳ Načítám seznam hráčů...")
    status_msg_id = status_msg.id
    await update_status(guild)


async def update_status(guild: discord.Guild):
    global status_msg_id
    channel = guild.get_channel(POZICE_CHANNEL_ID)
    if not channel or not status_msg_id:
        return

    msg = await channel.fetch_message(status_msg_id)

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
            pozice_text = POZICE_EMOJI[choices[0]]
            lines.append(f"{member.mention} (1/2) – {pozice_text}")
        elif len(choices) == 2:
            pozice_text = ", ".join([POZICE_EMOJI[c] for c in choices])
            lines.append(f"{member.mention} (2/2) ✅ – {pozice_text}")
            finished += 1

    if finished == total and total > 0:
        status_text = "🎉 **Skvělá zpráva! Všichni dali svoje pozice!**"
    else:
        status_text = "\n".join(lines) + f"\n\n📊 **Statistika:** {finished}/{total} hráčů má vybrané 2 pozice."

    await msg.edit(content=status_text)


@bot.event
async def on_raw_reaction_add(payload):
    global user_votes, user_choices, warned_users, attendance_msg_id
    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    emoji = str(payload.emoji)

    # ==== Docházka ====
    if payload.message_id == attendance_msg_id:
        if emoji == YES_EMOJI:
            user_votes[member.id] = "yes"
            await safe_dm(member, "✅ Děkujeme, že přijdeš dnes na trénink, budeme se na tebe těšit.")
        elif emoji == NO_EMOJI:
            user_votes[member.id] = "no"
            await safe_dm(member, "❌ Nezapomeň se omluvit, proč nejdeš. Pokud si to rozmyslíš, můžeš změnit reakci.")
        elif emoji == MAYBE_EMOJI:
            user_votes[member.id] = "maybe"
            await safe_dm(member, "❓ Nezapomeň během dne hlasovat, budeme na to čekat.")

    # ==== Pozice ====
    elif payload.channel_id == POZICE_CHANNEL_ID and emoji in POZICE_EMOJI:
        user_choices.setdefault(payload.user_id, [])
        if emoji not in user_choices[payload.user_id]:
            if len(user_choices[payload.user_id]) < 2:
                user_choices[payload.user_id].append(emoji)
                if len(user_choices[payload.user_id]) == 1:
                    await safe_dm(member, "ℹ️ Máš vybranou jen jednu pozici. Vyber prosím i druhou.")
                elif len(user_choices[payload.user_id]) == 2:
                    await safe_dm(member, "✅ Děkujeme, vybral sis dvě pozice!")
            else:
                # smazat reakci navíc
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


# ==== Helper pro DM ====
async def safe_dm(member, text):
    try:
        await member.send(text)
    except:
        pass


# ==== Start ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    for guild in bot.guilds:
        await setup_pozice(guild)
    if not attendance_scheduler.is_running():
        attendance_scheduler.start()

bot.run(DISCORD_TOKEN)
