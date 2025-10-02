import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import aiohttp

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

# ==== Intents ====
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==== Config ====
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

CHANNEL_POZICE = 1393525512462270564
CHANNEL_HLASOVANI = 1396253060745007216
CHANNEL_POKEC = 1396254859577004253

hlasovaci_zprava_id = None
hlasovali_yes = set()
hlasovali_no = set()
uzivatele_pozice = {}   # {user_id: [emoji]}

posledni_turnaj = None

# ==== Pomocné ====
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

# ==== Hlasování ====
@tasks.loop(minutes=1)
async def denni_hlasovani():
    global hlasovaci_zprava_id, hlasovali_yes, hlasovali_no
    now = datetime.utcnow() + timedelta(hours=2)
    channel = bot.get_channel(CHANNEL_HLASOVANI)
    guild = channel.guild

    if je_cas(datetime.strptime("08:00", "%H:%M").time()):
        msg = await channel.send("🗳️ **Hlasování o účasti na tréninku!**\n👍 = Jdu\n❌ = Nejdů")
        await msg.add_reaction("👍")
        await msg.add_reaction("❌")
        hlasovaci_zprava_id = msg.id
        hlasovali_yes.clear()
        hlasovali_no.clear()

    if now.hour in [16, 17, 18]:
        nehlasujici = [m.mention for m in guild.members if not m.bot and m.id not in hlasovali_yes and m.id not in hlasovali_no]
        if nehlasujici:
            await channel.send(f"⏰ Připomínka! Ještě nehlasovali: {', '.join(nehlasujici)}")

    if je_cas(datetime.strptime("19:00", "%H:%M").time()):
        nehlasujici = [m.mention for m in guild.members if not m.bot and m.id not in hlasovali_yes and m.id not in hlasovali_no]
        if nehlasujici:
            await channel.send(f"⚠️ Poslední výzva! Nehlasovali: {', '.join(nehlasujici)}")

    if je_cas(datetime.strptime("21:00", "%H:%M").time()) and hlasovaci_zprava_id:
        await posli_souhrn(channel, guild, "📊 Večerní souhrn ve 21:00")
        try:
            msg = await channel.fetch_message(hlasovaci_zprava_id)
            await msg.delete()
        except:
            pass
        hlasovaci_zprava_id = None

# ==== Turnaj každé 3h ====
@tasks.loop(minutes=5)
async def turnaj_msg():
    global posledni_turnaj
    channel = bot.get_channel(CHANNEL_POKEC)
    now = datetime.utcnow()
    if not posledni_turnaj or (now - posledni_turnaj).total_seconds() >= 10800:
        await channel.send("@everyone ⚽ **Dnes je turnaj proti CZ klubům!**")
        posledni_turnaj = now

# ==== Reakce ====
@bot.event
async def on_raw_reaction_add(payload):
    global hlasovali_yes, hlasovali_no

    # ---- HLÁSOVÁNÍ ----
    if payload.channel_id == CHANNEL_HLASOVANI and payload.message_id == hlasovaci_zprava_id:
        channel = bot.get_channel(payload.channel_id)
        msg = await channel.fetch_message(payload.message_id)

        if payload.user_id == bot.user.id:
            # smaže svoje reakce
            await msg.remove_reaction(payload.emoji, bot.user)
            return

        if payload.emoji.name == "👍":
            if payload.user_id in hlasovali_no:
                user = await bot.fetch_user(payload.user_id)
                await user.send("👏 Jsme rádi, že sis nakonec našel čas, že dorazíš!")
            hlasovali_yes.add(payload.user_id)
            hlasovali_no.discard(payload.user_id)

        elif payload.emoji.name == "❌":
            if payload.user_id in hlasovali_yes:
                user = await bot.fetch_user(payload.user_id)
                await user.send("🙏 Prosím, ihned se omluv spoluhráčům.")
            hlasovali_no.add(payload.user_id)
            hlasovali_yes.discard(payload.user_id)

    # ---- POZICE ----
    if payload.channel_id == CHANNEL_POZICE:
        channel = bot.get_channel(payload.channel_id)
        msg = await channel.fetch_message(payload.message_id)
        user = await bot.fetch_user(payload.user_id)

        if user.bot:
            # smaže svoje reakce
            await msg.remove_reaction(payload.emoji, bot.user)
            return

        if payload.user_id not in uzivatele_pozice:
            uzivatele_pozice[payload.user_id] = []

        if len(uzivatele_pozice[payload.user_id]) >= 2:
            await msg.remove_reaction(payload.emoji, user)
            await user.send("⚠️ Už máš vybrané 2 pozice, další nejde přidat.")
        else:
            uzivatele_pozice[payload.user_id].append(payload.emoji.name)
            if len(uzivatele_pozice[payload.user_id]) == 2:
                await user.send("✅ Díky, vybral sis 2 pozice. To nám pomůže s tvorbou sestavy!")
            elif len(uzivatele_pozice[payload.user_id]) == 1:
                await user.send("⏳ Máš zatím jen 1 pozici. Prosím, doplň i druhou pro klid klubu!")

# ==== Kontrola pozic každou hodinu ====
@tasks.loop(hours=1)
async def kontrola_pozic():
    channel = bot.get_channel(CHANNEL_POZICE)
    guild = channel.guild
    nedali = [m.mention for m in guild.members if not m.bot and (m.id not in uzivatele_pozice or len(uzivatele_pozice[m.id]) < 2)]
    if nedali:
        await channel.send(f"📢 Tito hráči ještě nemají 2 pozice: {', '.join(nedali)}")
    else:
        await channel.send("✅ Všichni mají vybrané 2 pozice!")

# ==== Bot mention + AI odpověď ====
@bot.event
async def on_message(message):
    if bot.user.mentioned_in(message) and not message.author.bot:
        user_input = message.content.replace(f"<@{bot.user.id}>", "").strip()
        if not user_input:
            user_input = "Ahoj, máš pro mě něco?"

        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
                data = {
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": "Odpovídej vždy česky, věcně a srozumitelně."},
                        {"role": "user", "content": user_input}
                    ],
                    "max_tokens": 200
                }
                async with session.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data) as resp:
                    result = await resp.json()
                    reply = result["choices"][0]["message"]["content"]
        except Exception as e:
            reply = f"⚠️ Něco se pokazilo s AI: {e}"

        await message.channel.send(f"{message.author.mention} {reply}")

    await bot.process_commands(message)

# ==== Start ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    if not denni_hlasovani.is_running():
        denni_hlasovani.start()
    if not turnaj_msg.is_running():
        turnaj_msg.start()
    if not kontrola_pozic.is_running():
        kontrola_pozic.start()
    await kontrola_pozic()  # hned po startu vypíše, kdo nemá 2 pozice

keep_alive()
bot.run(DISCORD_TOKEN)
