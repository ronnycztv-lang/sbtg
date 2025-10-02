import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, time, timedelta
from flask import Flask
from threading import Thread
from groq import Groq

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
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

# ==== Config ====
CHANNEL_ID = 1396253060745007216   # kanál hlasování
POKEC_ID = 1396254859577004253     # kanál pokec
hlasovali_yes = set()
hlasovali_no = set()
hlasovaci_zprava_id = None

# ==== AI klient ====
groq_client = Groq(api_key=GROQ_API_KEY)

async def ai_respond(prompt: str):
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",  # funkční model zdarma
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=100
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ Chyba AI: {e}"

# ==== Pomocné funkce ====
def je_cas(target_time):
    now = datetime.utcnow() + timedelta(hours=2)  # CZ čas
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

# ==== Denní hlasování ====
@tasks.loop(minutes=1)
async def denni_hlasovani():
    global hlasovaci_zprava_id, hlasovali_yes, hlasovali_no
    now = datetime.utcnow() + timedelta(hours=2)
    channel = bot.get_channel(CHANNEL_ID)
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

# ==== Vtipy každé 3 hodiny ====
@tasks.loop(hours=3)
async def posli_vtip():
    channel = bot.get_channel(POKEC_ID)
    vtip = await ai_respond("Řekni mi krátký a vtipný vtip v češtině.")
    await channel.send(f"😂 Vtip: {vtip}")

# ==== Reakce ====
@bot.event
async def on_raw_reaction_add(payload):
    global hlasovali_yes, hlasovali_no
    if payload.channel_id == CHANNEL_ID and payload.emoji.name in ["👍", "❌"]:
        if payload.emoji.name == "👍":
            hlasovali_yes.add(payload.user_id)
            hlasovali_no.discard(payload.user_id)
        elif payload.emoji.name == "❌":
            hlasovali_no.add(payload.user_id)
            hlasovali_yes.discard(payload.user_id)

@bot.event
async def on_raw_reaction_remove(payload):
    global hlasovali_yes, hlasovali_no
    if payload.channel_id == CHANNEL_ID and payload.emoji.name in ["👍", "❌"]:
        if payload.emoji.name == "👍":
            hlasovali_yes.discard(payload.user_id)
        elif payload.emoji.name == "❌":
            hlasovali_no.discard(payload.user_id)

# ==== AI odpovědi na zmínky ====
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if bot.user.mentioned_in(message):
        odpoved = await ai_respond(message.content)
        await message.channel.send(odpoved)
    await bot.process_commands(message)

# ==== Ostatní příkazy ====
@bot.command()
async def test(ctx):
    await ctx.send("✅ Bot je online a funguje.")

# ==== Start ====
@bot.event
async def on_ready():
    print(f"✅ Přihlášen jako {bot.user}")
    if not denni_hlasovani.is_running():
        denni_hlasovani.start()
    if not posli_vtip.is_running():
        posli_vtip.start()

keep_alive()
bot.run(DISCORD_TOKEN)
