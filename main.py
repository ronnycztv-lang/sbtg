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
POZICE_CHANNEL_NAME = "pozice"
POKEC_CHANNEL_NAME = "pokec"

# Emoji → pozice
POZICE_EMOJI = {
    "⚽": "Útočník (LK/PK/HÚ/SÚ)",
    "🎯": "Střední záložník (SOZ/SDZ)",
    "🏃": "Krajní záložník (LZ/PZ)",
    "🛡️": "Obránce (LO/PO/SO)",
    "🧤": "Brankář (GK)"
}

# Globální proměnné
intro_msg_id = None
status_msg_id = None
user_choices = {}  # {user_id: [emoji, emoji]}
turnaj_on = False


# ==== Setup pozice ====
async def setup_pozice(guild: discord.Guild):
    global intro_msg_id, status_msg_id, user_choices
    user_choices = {}

    # smažeme starý kanál #pozice
    old_channel = discord.utils.get(guild.text_channels, name=POZICE_CHANNEL_NAME)
    if old_channel:
        await old_channel.delete()
        print("🗑️ Starý kanál #pozice smazán")

    # vytvoříme nový kanál
    channel = await guild.create_text_channel(POZICE_CHANNEL_NAME)
    print("✅ Nový kanál #pozice vytvořen")

    # intro zpráva
    intro_text = (
        "📌 **Hlasování o pozicích!**\n"
        "Vyber si **max. 2 pozice** (primární + sekundární).\n"
        "Jakmile vybereš, ❌ **nejde to vrátit zpět.**\n\n"
        "**Emoji pro pozice:**\n"
        "⚽ = Útočník\n"
        "🎯 = Střední záložník\n"
        "🏃 = Krajní záložník\n"
        "🛡️ = Obránce\n"
        "🧤 = Brankář"
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
    channel = discord.utils.get(guild.text_channels, name=POZICE_CHANNEL_NAME)
    if not channel or not status_msg_id:
        return

    msg = await channel.fetch_message(status_msg_id)

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
        f"✅ **Vybrali (2/2):**\n" + ("\n".join(done) if done else "Nikdo zatím.") +
        f"\n\n📢 **Ještě nemají 2 pozice:**\n" +
        ("\n".join(not_done) if not_done else "Nikdo 🎉") +
        f"\n\n📊 **Statistika:** {finished}/{total}"
    )

    await msg.edit(content=status_text)


# ==== Reakce ====
@bot.event
async def on_raw_reaction_add(payload):
    global user_choices
    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    channel = bot.get_channel(payload.channel_id)
    emoji = str(payload.emoji)

    if channel.name != POZICE_CHANNEL_NAME:
        return
    if emoji not in POZICE_EMOJI:
        return

    user_choices.setdefault(payload.user_id, [])
    if emoji not in user_choices[payload.user_id]:
        if len(user_choices[payload.user_id]) < 2:
            user_choices[payload.user_id].append(emoji)
        else:
            # smažeme nadbytečnou reakci
            msg = await channel.fetch_message(payload.message_id)
            member = guild.get_member(payload.user_id)
            await msg.remove_reaction(emoji, member)
            await channel.send(f"{member.mention} ❌ Už máš vybrané 2 pozice!")

    await update_status(guild)


@bot.event
async def on_raw_reaction_remove(payload):
    global user_choices
    guild = bot.get_guild(payload.guild_id)
    channel = bot.get_channel(payload.channel_id)
    emoji = str(payload.emoji)

    if channel.name != POZICE_CHANNEL_NAME:
        return
    if emoji not in POZICE_EMOJI:
        return

    if payload.user_id in user_choices and emoji in user_choices[payload.user_id]:
        user_choices[payload.user_id].remove(emoji)

    await update_status(guild)


# ==== Turnaj reminder (jen do #pokec) ====
@tasks.loop(hours=3)
async def turnaj_notifikace():
    for guild in bot.guilds:
        pokec_channel = discord.utils.get(guild.text_channels, name=POKEC_CHANNEL_NAME)
        if pokec_channel:
            embed = discord.Embed(
                title="📢 DNES JE TURNAJ!",
                description="Prosím **hlasujte o svých pozicích** ⚽🎯🏃🛡️🧤",
                color=discord.Color.red()
            )
            embed.set_footer(text="Hlasujte v kanálu #pozice")
            await pokec_channel.send("@everyone", embed=embed)


# ==== Příkazy pro turnaj ====
@bot.command()
async def turnaj(ctx):
    """Zapne turnajový režim a spustí připomínky"""
    global turnaj_on
    if turnaj_on:
        await ctx.send("✅ Turnaj už je zapnutý!")
        return
    turnaj_on = True
    turnaj_notifikace.start()

    embed = discord.Embed(
        title="📢 DNES JE TURNAJ!",
        description="Prosím **hlasujte o svých pozicích** ⚽🎯🏃🛡️🧤",
        color=discord.Color.red()
    )
    embed.set_footer(text="Hlasujte v kanálu #pozice")
    await ctx.send("@everyone", embed=embed)

@bot.command()
async def turnajne(ctx):
    """Vypne turnajový režim a připomínky"""
    global turnaj_on
    if not turnaj_on:
        await ctx.send("❌ Turnaj není zapnutý.")
        return
    turnaj_on = False
    turnaj_notifikace.stop()
    await ctx.send("🛑 Turnajový režim byl vypnut.")


# ==== Komunikace bota ====
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if "ahoj bot" in message.content.lower():
        await message.channel.send(f"Ahoj {message.author.mention} 👋 Jsem tady pro tebe!")
    await bot.process_commands(message)


# ==== Start ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    for guild in bot.guilds:
        await setup_pozice(guild)

bot.run(DISCORD_TOKEN)
