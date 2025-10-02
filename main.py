import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import json

# ==== Keep Alive server (Render) ====
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

# ==== Konfigurace ====
CHANNEL_POZICE = 1393525512462270564  # kanál pozice
CHANNEL_TURNAJ = 1396254859577004253  # kanál pokec
STATUS_FILE = "pozice_status.json"
LAST_TURNAJ_FILE = "last_turnaj.txt"

# Emojis pro pozice
POZICE = {
    "⚽": "Útočník (LK, PK, HÚ, SÚ)",
    "🎯": "Střední záložník (SOZ, SDZ)",
    "🏃": "Krajní záložník (LZ, PZ)",
    "🛡️": "Obránce (LO, PO, SO)",
    "🧤": "Brankář (GK)"
}

# Paměť pro připomínky
pending_reminders = {}

# ===== Helpers =====
def cz_now():
    return datetime.utcnow() + timedelta(hours=2)

def save_last_turnaj_dt(dt):
    with open(LAST_TURNAJ_FILE, "w") as f:
        f.write(dt.isoformat())

def load_last_turnaj_dt():
    try:
        with open(LAST_TURNAJ_FILE, "r") as f:
            return datetime.fromisoformat(f.read().strip())
    except:
        return None

def save_status_id(mid):
    with open(STATUS_FILE, "w") as f:
        json.dump({"id": mid}, f)

def load_status_id():
    try:
        with open(STATUS_FILE, "r") as f:
            return json.load(f).get("id")
    except:
        return None

# ===== Vyčištění kanálů =====
async def cleanup_channels():
    pozice_ch = bot.get_channel(CHANNEL_POZICE)
    turnaj_ch = bot.get_channel(CHANNEL_TURNAJ)

    # vymazat všechny zprávy bota v #pozice
    async for msg in pozice_ch.history(limit=100):
        if msg.author == bot.user:
            try:
                await msg.delete()
            except:
                pass

    # vymazat všechny zprávy bota v #pokec
    async for msg in turnaj_ch.history(limit=100):
        if msg.author == bot.user:
            try:
                await msg.delete()
            except:
                pass

# ===== Pozice Setup =====
async def setup_pozice():
    channel = bot.get_channel(CHANNEL_POZICE)

    embed = discord.Embed(
        title="📌 Přečti si pozorně a vyber max. 2 pozice!",
        description=(
            "Jakmile vybereš, **nejde to vrátit zpět.** ⛔\n\n"
            "Každý hráč má možnost zvolit **primární a sekundární pozici.**\n\n"
            "**Rozdělení pozic:**\n"
            "⚽ Útočník (LK, PK, HÚ, SÚ)\n"
            "🎯 Střední záložník (SOZ, SDZ)\n"
            "🏃 Krajní záložník (LZ, PZ)\n"
            "🛡️ Obránce (LO, PO, SO)\n"
            "🧤 Brankář (GK)"
        ),
        color=discord.Color.red()
    )

    msg = await channel.send(embed=embed)

    for e in POZICE.keys():
        await msg.add_reaction(e)

    save_status_id(msg.id)

    # status zpráva (kdo nemá 2 pozice)
    status_msg = await channel.send("📢 Načítám seznam hráčů...")
    save_status_id(status_msg.id)

async def update_pozice_status(guild):
    channel = bot.get_channel(CHANNEL_POZICE)
    status_id = load_status_id()
    if not status_id:
        return

    try:
        status_msg = await channel.fetch_message(status_id)
    except:
        return

    members = [m for m in guild.members if not m.bot]
    reactions = await channel.history(limit=20).flatten()
    react_map = {}

    # načti reakce
    for msg in reactions:
        if msg.author == bot.user and msg.embeds:
            for r in msg.reactions:
                users = await r.users().flatten()
                for u in users:
                    if not u.bot:
                        react_map.setdefault(u.id, []).append(str(r.emoji))

    nevybrali = []
    for m in members:
        choices = react_map.get(m.id, [])
        if len(choices) < 2:
            nevybrali.append(f"{m.mention} ({len(choices)}/2)")

            # nastav připomínku pokud má jen 1
            if len(choices) == 1 and m.id not in pending_reminders:
                pending_reminders[m.id] = cz_now() + timedelta(hours=1)

        elif m.id in pending_reminders:
            # pokud už má 2 → smažeme z připomínek
            del pending_reminders[m.id]

    text = "📢 Tito hráči ještě nemají 2 pozice:\n" + (", ".join(nevybrali) if nevybrali else "✅ Všichni mají hotovo!")
    await status_msg.edit(content=text)

# ===== Reakce Pozice =====
@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != CHANNEL_POZICE:
        return
    if str(payload.emoji) not in POZICE:
        return

    channel = bot.get_channel(CHANNEL_POZICE)
    msg = await channel.fetch_message(payload.message_id)
    user = payload.member

    if user.bot:
        await msg.remove_reaction(payload.emoji, user)
        return

    # zkontroluj kolik má reakcí
    all_reacts = []
    for r in msg.reactions:
        users = await r.users().flatten()
        if user in users:
            all_reacts.append(str(r.emoji))

    if len(all_reacts) > 2:
        await msg.remove_reaction(payload.emoji, user)
        try:
            await user.send("❌ Už máš vybrané 2 pozice! Další volbu nelze přidat.")
        except:
            pass

    await update_pozice_status(user.guild)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.channel_id == CHANNEL_POZICE:
        guild = bot.get_guild(payload.guild_id)
        await update_pozice_status(guild)

# ===== Turnaj Loop =====
@tasks.loop(minutes=1)
async def turnaj_loop():
    await bot.wait_until_ready()
    ch = bot.get_channel(CHANNEL_TURNAJ)
    if not isinstance(ch, discord.TextChannel):
        return

    last = load_last_turnaj_dt()
    now = cz_now()

    if last is None:
        save_last_turnaj_dt(now)
        return

    if (now - last).total_seconds() >= 3 * 3600:
        # smaž staré zprávy bota
        async for m in ch.history(limit=100):
            if m.author == bot.user:
                try:
                    await m.delete()
                except:
                    pass

        await ch.send("@everyone 📢 **Dnes je turnaj proti CZ klubům! Připravte se a nezapomeňte hlasovat.**")
        save_last_turnaj_dt(now)

# ===== DM připomínky =====
@tasks.loop(minutes=5)
async def reminder_loop():
    await bot.wait_until_ready()
    now = cz_now()
    for uid, remind_time in list(pending_reminders.items()):
        if now >= remind_time:
            user = bot.get_user(uid)
            if user:
                try:
                    await user.send("⏰ Připomínka: Máš vybranou jen 1 pozici, doplň prosím i druhou pro klid klubu.")
                except:
                    pass
            # nastav novou připomínku za hodinu
            pending_reminders[uid] = now + timedelta(hours=1)

# ===== Start =====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    await cleanup_channels()   # smaže staré zprávy
    await setup_pozice()       # nastaví pozice
    if not turnaj_loop.is_running():
        turnaj_loop.start()
    if not reminder_loop.is_running():
        reminder_loop.start()

keep_alive()
bot.run(os.environ["DISCORD_TOKEN"])
