"""Discord bot that announces when your Canvas group assignments get submitted.

Run:  python bot.py
Config comes from environment variables / a .env file (see .env.example).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from canvas import CanvasClient, CanvasError
from tracker import StateStore, find_new_submissions, parse_time, pending_group_assignments

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("canvas-bot")


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required setting {name}. Copy .env.example to .env and fill it in.")
    return value


DISCORD_TOKEN = _require("DISCORD_TOKEN")
CHANNEL_ID = int(_require("DISCORD_CHANNEL_ID"))
GUILD_ID = os.getenv("DISCORD_GUILD_ID", "").strip()
CANVAS_BASE_URL = _require("CANVAS_BASE_URL")
CANVAS_TOKEN = _require("CANVAS_TOKEN")
POLL_MINUTES = max(1, int(os.getenv("POLL_MINUTES", "5")))
COURSE_IDS = [c.strip() for c in os.getenv("COURSE_IDS", "").split(",") if c.strip()]
GROUP_ONLY = os.getenv("GROUP_ONLY", "true").lower() != "false"
ANNOUNCE_RESUBMISSIONS = os.getenv("ANNOUNCE_RESUBMISSIONS", "true").lower() != "false"
STATE_FILE = os.getenv("STATE_FILE", "data/state.json")

store = StateStore(STATE_FILE)
poll_lock = asyncio.Lock()


async def fetch_courses(canvas: CanvasClient) -> list[dict]:
    courses = await canvas.active_courses()
    if COURSE_IDS:
        courses = [c for c in courses if str(c.get("id")) in COURSE_IDS]
    # Courses you can't see assignments in come back with access_restricted_by_date.
    return [c for c in courses if not c.get("access_restricted_by_date")]


async def poll_canvas(announce: bool = True) -> int:
    """Check Canvas once. Returns the number of new submissions announced."""
    async with poll_lock:
        first_run = not store.exists()
        state = store.load()
        new = []
        async with CanvasClient(CANVAS_BASE_URL, CANVAS_TOKEN) as canvas:
            for course in await fetch_courses(canvas):
                try:
                    assignments = await canvas.assignments_with_submission(course["id"])
                except CanvasError as e:
                    log.warning("Skipping course %s: %s", course.get("name"), e)
                    continue
                new.extend(find_new_submissions(course, assignments, state, GROUP_ONLY))
        store.save(state)

        if first_run:
            # Don't flood the channel with everything submitted before the bot existed.
            log.info("First run: recorded %d existing submissions without announcing.", len(new))
            return 0
        if not announce:
            return 0

        channel = client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)
        sent = 0
        for sub in new:
            if sub.is_resubmission and not ANNOUNCE_RESUBMISSIONS:
                continue
            await channel.send(embed=build_embed(sub))
            sent += 1
        if sent:
            log.info("Announced %d new submission(s).", sent)
        return sent


def build_embed(sub) -> discord.Embed:
    verb = f"resubmitted (attempt {sub.attempt})" if sub.is_resubmission else "submitted"
    embed = discord.Embed(
        title=f"📬 {sub.assignment_name}",
        url=sub.assignment_url or None,
        description=f"Our group {verb} this assignment.",
        color=discord.Color.orange() if sub.late else discord.Color.green(),
    )
    embed.add_field(name="Course", value=sub.course_name, inline=False)
    submitted = parse_time(sub.submitted_at)
    if submitted:
        embed.add_field(name="Submitted", value=discord.utils.format_dt(submitted, "f"), inline=True)
    due = parse_time(sub.due_at)
    if due:
        embed.add_field(name="Due", value=discord.utils.format_dt(due, "f"), inline=True)
    if sub.late:
        embed.set_footer(text="⚠️ Canvas marked this as late")
    return embed


# ---------- Discord wiring ----------

intents = discord.Intents.default()  # no privileged intents needed
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@tasks.loop(minutes=POLL_MINUTES)
async def poll_loop() -> None:
    try:
        await poll_canvas()
    except CanvasError as e:
        log.error("Canvas error: %s", e)
    except Exception:
        log.exception("Unexpected error while polling")


@poll_loop.before_loop
async def _wait_ready() -> None:
    await client.wait_until_ready()


@client.event
async def setup_hook() -> None:
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)  # instant in that server
    else:
        await tree.sync()  # global; can take up to an hour to appear
    poll_loop.start()


@client.event
async def on_ready() -> None:
    log.info("Logged in as %s. Polling Canvas every %d min.", client.user, POLL_MINUTES)


@tree.command(name="check", description="Check Canvas for new group submissions right now")
async def check_cmd(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True)
    try:
        sent = await poll_canvas()
    except CanvasError as e:
        await interaction.followup.send(f"Couldn't reach Canvas: {e}")
        return
    msg = f"Found {sent} new submission(s) — posted above." if sent else "No new submissions."
    await interaction.followup.send(msg)


@tree.command(name="pending", description="List upcoming group assignments nobody has submitted yet")
async def pending_cmd(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True)
    items = []
    try:
        async with CanvasClient(CANVAS_BASE_URL, CANVAS_TOKEN) as canvas:
            for course in await fetch_courses(canvas):
                assignments = await canvas.assignments_with_submission(course["id"])
                items.extend(pending_group_assignments(course, assignments))
    except CanvasError as e:
        await interaction.followup.send(f"Couldn't reach Canvas: {e}")
        return
    if not items:
        await interaction.followup.send("🎉 No unsubmitted group assignments coming up.")
        return
    items.sort(key=lambda i: i["due"])
    lines = [
        f"• **[{i['name']}]({i['url']})** — {i['course']} — due "
        f"{discord.utils.format_dt(i['due'], 'R')}"
        for i in items[:15]
    ]
    embed = discord.Embed(title="⏳ Still to submit", description="\n".join(lines),
                          color=discord.Color.blurple())
    if len(items) > 15:
        embed.set_footer(text=f"…and {len(items) - 15} more")
    await interaction.followup.send(embed=embed)


@tree.command(name="botinfo", description="Show what this bot is watching")
async def info_cmd(interaction: discord.Interaction) -> None:
    scope = ", ".join(COURSE_IDS) if COURSE_IDS else "all active courses"
    kind = "group assignments only" if GROUP_ONLY else "all assignments"
    await interaction.response.send_message(
        f"Watching {scope} ({kind}), checking every {POLL_MINUTES} min. "
        f"Tracking {len(store.load())} submitted assignment(s).",
        ephemeral=True,
    )


if __name__ == "__main__":
    client.run(DISCORD_TOKEN, log_handler=None)
