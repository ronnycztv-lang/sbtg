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
POZICE_CHANNEL_ID = 1393525512462270564  # pevně daný kanál #pozice

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
user_choices = {}  # {user_id: [emoji, emoji]}


# ==== Setup pozice ====
async def setup_pozice(guild: discord.Guild):
    global intro_msg_id, status_msg_id, user_choices
    user_choices = {}

    channel = guild.get_channel(POZICE_CHANNEL_ID)
    if not channel:
        print("❌ Kanál nebyl nalezen!")
        return

    # smažeme staré botí zprávy
    async for msg in channel.history(limit=100):
        if msg.author == bot.user:
            await msg.delete()

    # intro zpráva
    intro_text = (
        "📌 **Vyber si max. 2 pozice pomocí reakcí.**\n"
        "⚽ = Útočník\n"
        "🎯 = Střední záložník\n"
        "🏃 = Krajní záložník\n"
        "🛡️ = Obránce\n"
        "🧤 = Brankář\n\n"
        "❗ Každý hráč má **max. 2 pozice.**"
    )
    intro_msg = await channel.send(intro_text)
    intro_msg_id = intro_msg.id
    for e in POZICE_EMOJI.keys():
        await intro_msg.add_reaction(e)

    # status zpráva
    status_msg = await channel.send("⏳ Načítám seznam hráčů...")
    status_msg_id = status_msg.id

    await update_status(guild)


# ==== Update status ====
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


# ==== Reakce ====
@bot.event
async def on_raw_reaction_add(payload):
    global user_choices
    if payload.user_id == bot.user.id:
        return

    emoji = str(payload.emoji)
    if emoji not in POZICE_EMOJI:
        return

    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    user_choices.setdefault(payload.user_id, [])

    if emoji not in user_choices[payload.user_id]:
        if len(user_choices[payload.user_id]) < 2:
            user_choices[payload.user_id].append(emoji)
            # DM podle stavu
            try:
                if len(user_choices[payload.user_id]) == 1:
                    await member.send("ℹ️ Máš vybranou jen **jednu pozici**. Vyber prosím i druhou.")
                elif len(user_choices[payload.user_id]) == 2:
                    await member.send("✅ Děkujeme, vybral sis **dvě pozice**!")
            except:
                pass
        else:
            # nad 2 → smažeme
            channel = bot.get_channel(payload.channel_id)
            msg = await channel.fetch_message(payload.message_id)
            await msg.remove_reaction(emoji, member)
            try:
                await member.send("❌ Můžeš mít jen **dvě pozice**!")
            except:
                pass

    await update_status(guild)


@bot.event
async def on_raw_reaction_remove(payload):
    global user_choices
    emoji = str(payload.emoji)
    if emoji not in POZICE_EMOJI:
        return

    guild = bot.get_guild(payload.guild_id)
    if payload.user_id in user_choices and emoji in user_choices[payload.user_id]:
        user_choices[payload.user_id].remove(emoji)

    await update_status(guild)


# ==== Upomínky každé 4 hodiny ====
@tasks.loop(hours=4)
async def remind_no_position():
    for guild in bot.guilds:
        for member in guild.members:
            if member.bot:
                continue
            choices = user_choices.get(member.id, [])
            if len(choices) == 0:
                try:
                    await member.send("⏰ Připomínka: Stále sis **nevybral žádnou pozici** v kanálu #pozice.")
                except:
                    pass


# ==== Start ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    for guild in bot.guilds:
        await setup_pozice(guild)
    if not remind_no_position.is_running():
        remind_no_position.start()

bot.run(DISCORD_TOKEN)
