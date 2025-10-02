import os
import json
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread

# ==== Keep Alive server ====
app = Flask('')

@app.route('/')
def home():
    return "Bot běží!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==== Discord Intents ====
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==== Config ====
CHANNEL_POZICE = 1393525512462270564  # kanál pro pozice
DATA_FILE = "pozice.json"

# ==== Global ====
user_choices = {}       # {user_id: [emoji1, emoji2]}
main_message_id = None  # id hlavní zprávy (embed s pozicemi)
status_message_id = None  # id status zprávy (seznam kdo má/nemá)

# ==== Ukládání ====
def load_pozice():
    global user_choices, main_message_id, status_message_id
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            user_choices = data.get("user_choices", {})
            main_message_id = data.get("main_message_id", None)
            status_message_id = data.get("status_message_id", None)

def save_pozice():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "user_choices": user_choices,
            "main_message_id": main_message_id,
            "status_message_id": status_message_id
        }, f, indent=2, ensure_ascii=False)

# ==== Embed hlavní zprávy ====
def build_main_embed():
    embed = discord.Embed(
        title="📌 Přečti si pozorně a vyber max. 2 pozice!",
        description="Jakmile vybereš, **nejde to vrátit zpět. ⛔**\n\n"
                    "Každý hráč má možnost zvolit **primární a sekundární** pozici.\n\n"
                    "**Rozdělení pozic:**\n"
                    "⚽ Útočník (LK, PK, HÚ, SÚ)\n"
                    "🎯 Střední záložník (SOZ, SDZ)\n"
                    "🏃 Krajní záložník (LZ, PZ)\n"
                    "🛡️ Obránce (LO, PO, SO)\n"
                    "🧤 Brankář (GK)",
        color=discord.Color.red()
    )
    return embed

# ==== Synchronizace reakcí ====
async def sync_reactions_with_choices():
    """Načti reakce z hlavní zprávy a aktualizuj user_choices"""
    global main_message_id
    if not main_message_id:
        return
    channel = bot.get_channel(CHANNEL_POZICE)
    try:
        main_msg = await channel.fetch_message(main_message_id)
    except:
        return

    new_choices = {}
    for reaction in main_msg.reactions:
        async for user in reaction.users():
            if user.bot:
                continue
            new_choices.setdefault(str(user.id), []).append(str(reaction.emoji))

    user_choices.clear()
    user_choices.update(new_choices)
    save_pozice()

# ==== Update status zprávy ====
async def update_status(guild):
    global status_message_id
    await sync_reactions_with_choices()

    channel = bot.get_channel(CHANNEL_POZICE)
    members = [m for m in guild.members if not m.bot]
    total = len(members)

    done = []
    not_done = []
    for m in members:
        choices = user_choices.get(str(m.id), [])
        if len(choices) >= 2:
            done.append(f"{m.mention} ✅ ({', '.join(choices)})")
        else:
            not_done.append(f"{m.mention} ({len(choices)}/2)")

    text = ""
    if not_done:
        text += "📢 Tito hráči ještě nemají 2 pozice:\n" + ", ".join(not_done) + "\n\n"
    if done:
        text += "✅ Už vybrali:\n" + ", ".join(done) + "\n\n"

    text += f"📊 Statistika: {len(done)}/{total} hráčů má vybrané 2 pozice."

    # aktualizace / vytvoření zprávy
    if status_message_id:
        try:
            msg = await channel.fetch_message(status_message_id)
            await msg.edit(content=text)
            return
        except:
            pass

    msg = await channel.send("⏳ Načítám seznam hráčů...")
    status_message_id = msg.id
    save_pozice()
    await msg.edit(content=text)

# ==== Setup při spuštění ====
async def setup_pozice():
    global main_message_id
    channel = bot.get_channel(CHANNEL_POZICE)

    if not main_message_id:
        embed = build_main_embed()
        msg = await channel.send(embed=embed)
        main_message_id = msg.id
        save_pozice()

        # přidej emoji pro volby
        emojis = ["⚽", "🎯", "🏃", "🛡️", "🧤"]
        for e in emojis:
            await msg.add_reaction(e)

# ==== Events ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    load_pozice()
    await setup_pozice()
    await update_status(bot.guilds[0])

@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != CHANNEL_POZICE:
        return
    if payload.user_id == bot.user.id:
        return

    user_id = str(payload.user_id)
    emoji = str(payload.emoji)

    choices = user_choices.get(user_id, [])
    if emoji not in choices:
        choices.append(emoji)
    if len(choices) > 2:
        # smaž tu třetí reakci
        channel = bot.get_channel(payload.channel_id)
        msg = await channel.fetch_message(payload.message_id)
        await msg.remove_reaction(payload.emoji, payload.member)
        return

    user_choices[user_id] = choices
    save_pozice()
    await update_status(payload.member.guild)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.channel_id != CHANNEL_POZICE:
        return
    if payload.user_id == bot.user.id:
        return

    user_id = str(payload.user_id)
    emoji = str(payload.emoji)

    choices = user_choices.get(user_id, [])
    if emoji in choices:
        choices.remove(emoji)
        user_choices[user_id] = choices
        save_pozice()
        guild = bot.get_guild(payload.guild_id)
        await update_status(guild)

# ==== Start ====
keep_alive()
bot.run(os.environ["DISCORD_TOKEN"])
