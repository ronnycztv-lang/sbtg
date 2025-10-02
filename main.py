import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, time, timedelta
from flask import Flask
from threading import Thread

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

# ==== Discord Intents ====
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==== Tokens ====
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]

# ==== ID kanálů ====
HLASOVANI_CHANNEL_ID = 1396253060745007216   # kanál hlasování
POKEC_CHANNEL_ID = 1396254859577004253       # kanál pokec
POZICE_CHANNEL_ID = 1393525512462270564      # kanál pozice

# ==== Hlasování systém ====
hlasovali_yes = set()
hlasovali_no = set()
hlasovaci_zprava_id = None

def je_cas(target_time):
    now = datetime.utcnow() + timedelta(hours=2)
    return now.hour == target_time.hour and now.minute == target_time.minute

async def posli_souhrn(channel, guild, nadpis="📊 Souhrn hlasování"):
    hlasujici_yes = [m.mention for m in guild.members if not m.bot and m.id in hlasovali_yes]
    hlasujici_no = [m.mention for m in guild.members if not m.bot and m.id in hlasovali_no]
    nehlasujici = [m.mention for m in guild.members if not m.bot and m.id not in hlasovali_yes and m.id not in hlasovali_no]

    report = f"{nadpis}\n\n"
    report += f"👍 Půjdou: {', '.join(hlasujici_yes) if hlasujici_yes else 'Nikdo'}\n"
    report += f"❌ Nepůjdou: {', '.join(hlasujici_no) if hlasujici_no else 'Nikdo'}\n"
    report += f"❓ Nehlasovali: {', '.join(nehlasujici) if nehlasujici else 'Nikdo'}"

    await channel.send(report)

@tasks.loop(minutes=1)
async def denni_hlasovani():
    global hlasovaci_zprava_id, hlasovali_yes, hlasovali_no
    now = datetime.utcnow() + timedelta(hours=2)
    channel = bot.get_channel(HLASOVANI_CHANNEL_ID)
    guild = channel.guild

    if je_cas(time(7,0)):
        if hlasovaci_zprava_id:
            await posli_souhrn(channel, guild, "📊 Ranní souhrn v 07:00")
            hlasovaci_zprava_id = None
            hlasovali_yes.clear()
            hlasovali_no.clear()

    if je_cas(time(8,0)):
        msg = await channel.send("🗳️ **Hlasování o účasti na tréninku!**\n👍 = Jdu\n❌ = Nejdů")
        await msg.add_reaction("👍")
        await msg.add_reaction("❌")
        hlasovaci_zprava_id = msg.id
        hlasovali_yes.clear()
        hlasovali_no.clear()

    if je_cas(time(16,0)) or je_cas(time(17,0)) or je_cas(time(18,0)):
        nehlasujici = [m.mention for m in guild.members if not m.bot and m.id not in hlasovali_yes and m.id not in hlasovali_no]
        if nehlasujici:
            await channel.send(f"⏰ Připomínka! Ještě nehlasovali: {', '.join(nehlasujici)}")

    if je_cas(time(19,0)):
        nehlasujici = [m.mention for m in guild.members if not m.bot and m.id not in hlasovali_yes and m.id not in hlasovali_no]
        if nehlasujici:
            await channel.send(f"⚠️ Poslední výzva před tréninkem! Nehlasovali: {', '.join(nehlasujici)}")

    if je_cas(time(21,0)) and hlasovaci_zprava_id:
        await posli_souhrn(channel, guild, "📊 Večerní souhrn ve 21:00")
        try:
            msg = await channel.fetch_message(hlasovaci_zprava_id)
            await msg.delete()
        except:
            await channel.send("⚠️ Nepodařilo se smazat hlasovací zprávu.")
        hlasovaci_zprava_id = None

# ==== Turnaj každé 3h ====
last_turnaj_msg_id = None

@tasks.loop(hours=3)
async def turnaj_oznameni():
    global last_turnaj_msg_id
    channel = bot.get_channel(POKEC_CHANNEL_ID)
    if channel:
        # smaž staré zprávy bota kromě poslední
        async for msg in channel.history(limit=50):
            if msg.author == bot.user:
                if last_turnaj_msg_id and msg.id == last_turnaj_msg_id:
                    continue
                await msg.delete()

        # pokud není uložená zpráva → pošli novou
        if not last_turnaj_msg_id:
            msg = await channel.send("@everyone 📢 **Dnes je turnaj proti CZ KLUBŮM!** ⚽🔥")
            last_turnaj_msg_id = msg.id

# ==== Pozice systém ====
pozice_moznosti = {
    "Útočník (LK, PK, HÚ, SÚ)": "⚽",
    "Střední záložník (SOZ, SDZ)": "🎯",
    "Krajní záložník (LZ, PZ)": "🏃",
    "Obránce (LO, PO, SO)": "🛡️",
    "Brankář (GK)": "🧤"
}
uzivatele_pozice = {}
last_pozice_msg_id = None

async def vypis_pozice():
    global last_pozice_msg_id
    channel = bot.get_channel(POZICE_CHANNEL_ID)

    if channel:
        # smaž staré zprávy kromě poslední
        async for msg in channel.history(limit=50):
            if msg.author == bot.user:
                if last_pozice_msg_id and msg.id == last_pozice_msg_id:
                    continue
                await msg.delete()

        if not last_pozice_msg_id:
            embed = discord.Embed(
                title="📌 **Přečti si pozorně a vyber max. 2 pozice!**",
                description=(
                    "Jakmile vybereš, **nejde to vrátit zpět**. ⛔\n\n"
                    "Každý hráč má možnost zvolit **primární a sekundární pozici**.\n\n"
                    "**Rozdělení pozic:**"
                ),
                color=discord.Color.red()
            )
            for text, emoji in pozice_moznosti.items():
                embed.add_field(name=f"{emoji} {text}", value=" ", inline=False)

            msg = await channel.send(embed=embed)
            for emoji in pozice_moznosti.values():
                await msg.add_reaction(emoji)

            last_pozice_msg_id = msg.id

@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != POZICE_CHANNEL_ID:
        return
    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    if not member:
        return

    emoji = str(payload.emoji)
    pozice = None
    for text, emj in pozice_moznosti.items():
        if emj == emoji:
            pozice = text
            break

    if not pozice:
        return

    if payload.user_id in uzivatele_pozice and len(uzivatele_pozice[payload.user_id]) >= 2:
        channel = bot.get_channel(payload.channel_id)
        msg = await channel.fetch_message(payload.message_id)
        await msg.remove_reaction(emoji, member)
        return

    if payload.user_id not in uzivatele_pozice:
        uzivatele_pozice[payload.user_id] = []
    if pozice not in uzivatele_pozice[payload.user_id]:
        uzivatele_pozice[payload.user_id].append(pozice)

    if len(uzivatele_pozice[payload.user_id]) == 2:
        try:
            await member.send("✅ Díky! Vybral sis 2 pozice – to nám pomůže lépe skládat sestavu. ⚽")
        except:
            pass

# ==== Start ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    if not denni_hlasovani.is_running():
        denni_hlasovani.start()
    if not turnaj_oznameni.is_running():
        turnaj_oznameni.start()
    await vypis_pozice()

keep_alive()
bot.run(DISCORD_TOKEN)
