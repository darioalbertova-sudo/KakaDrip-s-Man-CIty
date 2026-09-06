"""
KakaDrip's Man City — Matchday Ping Bot
----------------------------------------
Watches a specific channel for @everyone matchday pings and DMs everyone
holding a given role with:
  - a jump link to the ping message
  - the kickoff time (auto-detected from the message)
  - the league (assumed to be the LAST line of the ping message)
  - a reminder to "tick" (RSVP)

Setup:
  1. pip install -r requirements.txt
  2. In the Discord Developer Portal, enable:
       - SERVER MEMBERS INTENT
       - MESSAGE CONTENT INTENT
  3. Set your bot token as an environment variable: DISCORD_BOT_TOKEN
  4. Invite the bot to the server with permission to read messages in the
     ping channel and to DM users (DMs work by default, no special perm needed,
     but users must not have DMs from server members disabled).
  5. Run: python bot.py

Config below matches the IDs you gave me:
  GUILD ROLE ID   = 1262402600624455822  (users to DM)
  PING CHANNEL ID = 1263528254246096997  (channel to watch for @everyone)

If your matchday ping messages don't follow "league on the last line",
tweak `extract_league()` below.
"""

import os
import re
import asyncio
import logging

import discord

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------

ROLE_ID_TO_DM = 1262402600624455822
PING_CHANNEL_ID = 1263528254246096997

# How long to wait between DMs, to stay comfortably under Discord's rate limits
DM_DELAY_SECONDS = 1.0

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("matchday-bot")

# ----------------------------------------------------------------------------
# PARSING HELPERS
# ----------------------------------------------------------------------------

# Matches 12-hour times like "8pm", "8:30 PM", "11:00am"
TIME_12H_RE = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)\b")
# Matches 24-hour times like "20:00", "8:00"
TIME_24H_RE = re.compile(r"\b([01]?\d|2[0-3]):[0-5]\d\b")


def extract_time(content: str) -> str:
    """Best-effort extraction of a kickoff time from the ping message."""
    match = TIME_12H_RE.search(content)
    if match:
        return match.group(0).strip()
    match = TIME_24H_RE.search(content)
    if match:
        return match.group(0).strip()
    return "the time listed in the message"


def extract_league(content: str) -> str:
    """
    Assumes the league is on the last non-empty line of the ping message.
    Strips a leading @everyone/@here mention if the whole ping is one line.
    """
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return "the league listed in the message"

    last_line = lines[-1]

    # If the entire message is a single line, try to pull a trailing
    # "- League Name" or "| League Name" style suffix instead.
    if len(lines) == 1:
        cleaned = re.sub(r"@everyone|@here", "", last_line).strip()
        for sep in (" - ", " – ", " | ", ": "):
            if sep in cleaned:
                return cleaned.split(sep)[-1].strip()
        return cleaned or "the league listed in the message"

    return last_line


# ----------------------------------------------------------------------------
# BOT
# ----------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    log.info(f"Logged in as {client.user} (id: {client.user.id})")


@client.event
async def on_message(message: discord.Message):
    # Ignore DMs / other guilds / bot's own messages
    if message.guild is None or message.author.bot:
        return

    if message.channel.id != PING_CHANNEL_ID:
        return

    # Only fire on genuine @everyone / @here pings
    if not message.mention_everyone:
        return

    role = message.guild.get_role(ROLE_ID_TO_DM)
    if role is None:
        log.warning(f"Role {ROLE_ID_TO_DM} not found in guild {message.guild.id}")
        return

    kickoff_time = extract_time(message.content)
    league = extract_league(message.content)
    jump_url = message.jump_url

    dm_text = (
        f"⚽ **Matchday ping!**\n"
        f"League: **{league}**\n"
        f"Kickoff: **{kickoff_time}**\n"
        f"Don't forget to tick ✅ here: {jump_url}"
    )

    log.info(
        f"Detected @everyone ping in #{message.channel} — "
        f"time='{kickoff_time}', league='{league}'. DMing {len(role.members)} member(s)."
    )

    for member in role.members:
        if member.bot:
            continue
        try:
            await member.send(dm_text)
            log.info(f"DM sent to {member} ({member.id})")
        except discord.Forbidden:
            log.warning(f"Could not DM {member} ({member.id}) — DMs likely disabled.")
        except discord.HTTPException as e:
            log.warning(f"Failed to DM {member} ({member.id}): {e}")

        await asyncio.sleep(DM_DELAY_SECONDS)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "Missing DISCORD_BOT_TOKEN environment variable. "
            "Set it before running the bot, e.g.:\n"
            "  export DISCORD_BOT_TOKEN=your-token-here"
        )
    client.run(TOKEN)
