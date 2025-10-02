import os
import discord
from discord.ext import commands, tasks
from groq import Groq
from datetime import time
from flask import Flask
from threading import Thread

# ===== Keep Alive Server (pro Replit) =====
app = Flask('')

@app.route('/')
def home():
    return "Bot běží!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ===== Discord Intents =====
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ===== API Keys (z Replit Secrets) =====
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]


client = Groq(api_key=GROQ_API_KEY)

CHANNEL_ID = 1396253060745007216  # ID kanálu "hlasovaní"

# ===== Časy v UTC (CZ = UTC+2) =====
VOTE_TIME = time(6, 0)        # 08:00 CZ - hlasování
REMINDER1 = time(14, 0)       # 16:00 CZ - připomínka nehlasujícím
REMINDER2 = time(15, 0)       # 17:00 CZ
REMINDER3 = time(16, 0)       # 18:00 CZ
FINAL_REMINDER = time(17, 0)  # 19:00 CZ - finální vyhodnocení

# ===== Účastníci =====
participants_yes = set()
participants_no = set()
event_message = None  # aktivní hlasovací zpráva


# ===== AI odpověď =====
async def ai_response(prompt: str) -> str:
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Odpovídej vždy česky, jasně a přátelsky. "
                        "Piš jako člověk, stručně a srozumitelně."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=300
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ Chyba AI: {e}"


# ===== Bezpečné posílání zpráv =====
async def safe_send(member, text, channel):
    try:
        await member.send(text)  # DM
    except:
        await channel.send(f"{member.mention} {text}")  # fallback


# ===== Události =====
@bot.event
async def on_ready():
    print(f"✅ Bot {bot.user} běží!")
    daily_vote.start()
    reminder1.start()
    reminder2.start()
    reminder3.start()
    final_reminder.start()


# ===== 08:00 hlasování =====
@tasks.loop(time=VOTE_TIME)
async def daily_vote():
    global participants_yes, participants_no, event_message
    participants_yes.clear()
    participants_no.clear()

    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        event_message = await channel.send(
            "📢 @everyone Trénink dnes ve 20:00!\nDej 👍 pokud jdeš, ❌ pokud nejdeš."
        )
        await event_message.add_reaction("👍")
        await event_message.add_reaction("❌")
        print("📢 Hlasování odesláno.")


# ===== Připomínky nehlasujícím =====
async def remind_non_voters():
    if event_message is None:  # ⛔ Bez hlasování nic neposílej
        return

    guild = bot.get_channel(CHANNEL_ID).guild
    channel = bot.get_channel(CHANNEL_ID)
    no_vote = [m for m in guild.members if not m.bot and m not in participants_yes and m not in participants_no]

    for member in no_vote:
        await safe_send(member, "⚠️ Ještě jsi nehlasoval o dnešním tréninku! Dej 👍 nebo ❌ v kanálu #hlasovaní.", channel)

@tasks.loop(time=REMINDER1)
async def reminder1():
    await remind_non_voters()

@tasks.loop(time=REMINDER2)
async def reminder2():
    await remind_non_voters()

@tasks.loop(time=REMINDER3)
async def reminder3():
    await remind_non_voters()


# ===== 19:00 finální připomenutí =====
@tasks.loop(time=FINAL_REMINDER)
async def final_reminder():
    if event_message is None:  # ⛔ Bez hlasování nic neposílej
        return

    guild = bot.get_channel(CHANNEL_ID).guild
    channel = bot.get_channel(CHANNEL_ID)
    no_vote = [m for m in guild.members if not m.bot and m not in participants_yes and m not in participants_no]

    # 👍 Jdou
    for member in participants_yes:
        await safe_send(member, "⏰ Připomínka: V 20:00 začíná trénink! Připrav se.", channel)

    # ❌ Nejdou
    for member in participants_no:
        await safe_send(member, "❌ Rychle se omluv, proč dnes nejdeš na trénink!", channel)

    # ❓ Nehlasovali
    for member in no_vote:
        await safe_send(member, "🚨 Nehlasoval jsi o dnešním tréninku. Tohle může být tvůj konec v týmu!", channel)


# ===== Reakce (jen na hlasovací zprávu) =====
@bot.event
async def on_raw_reaction_add(payload):
    global participants_yes, participants_no, event_message

    if event_message and payload.message_id == event_message.id:  # jen ta hlasovací zpráva
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)

        if member and not member.bot:
            if str(payload.emoji) == "👍":
                participants_yes.add(member)
                participants_no.discard(member)
            elif str(payload.emoji) == "❌":
                participants_no.add(member)
                participants_yes.discard(member)
            else:
                # smaže jiné reakce
                channel = bot.get_channel(payload.channel_id)
                msg = await channel.fetch_message(payload.message_id)
                for reaction in msg.reactions:
                    if str(reaction.emoji) == str(payload.emoji):
                        await reaction.remove(member)


# ===== Testovací příkaz =====
@bot.command()
async def test(ctx):
    await ctx.send("✅ Bot funguje! Toto je odpověď na !test")


# ===== AI příkaz =====
@bot.command()
async def ai(ctx, *, prompt: str):
    reply = await ai_response(prompt)
    await ctx.send(reply)


# ===== AI při označení =====
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user.mentioned_in(message):
        user_input = message.content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
        reply = await ai_response(user_input or "Ahoj!")
        await message.channel.send(reply)

    await bot.process_commands(message)


# ===== Start =====
keep_alive()
bot.run(DISCORD_TOKEN)
