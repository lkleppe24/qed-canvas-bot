# Canvas Group Submission Bot

A Discord bot that posts in your server whenever your group turns in a Canvas assignment.

**How it works:** For group assignments, Canvas copies the group's submission onto every member. So the bot only needs *your* Canvas token: every few minutes it checks your submission status on each group assignment, and when one flips to "submitted" it posts an announcement in Discord.

```
Canvas API ──(poll every 5 min, your token)──▶ bot.py ──▶ #your-channel
                                                 │
                                       data/state.json (what's been announced)
```

**What you get**
- An announcement embed for each new group submission: assignment, course, submit time, due date, and a late warning
- Resubmission announcements (attempt 2, 3, …), which you can turn off
- `/check` checks Canvas right now
- `/pending` lists upcoming group assignments nobody has submitted yet
- `/botinfo` shows what the bot is watching
- On the first run, the bot quietly records everything already submitted, so it doesn't spam old assignments

**Limitations to know**
- Canvas doesn't show students *which* groupmate submitted, so the message says "our group submitted."
- Announcements can lag by up to `POLL_MINUTES`. Students can't get Canvas webhooks.
- The bot runs on your token, so it only sees courses *you're* in.

---

## Step-by-step implementation plan

Plan for about 30–45 minutes the first time.

### Phase 1 — Get your Canvas access (5 min)

1. **Find your Canvas URL.** It's the address you log into, like `https://canvas.youruni.edu` or `https://youruni.instructure.com`. Use this as `CANVAS_BASE_URL`, with no trailing slash.
2. **Create an access token.** In Canvas, go to **Account → Settings**, scroll to **Approved Integrations**, and click **+ New Access Token**.
   - Purpose: `Discord group bot`. You can leave the expiry blank or set it to the end of the term.
   - Copy the token **right away**, because Canvas only shows it once. Use it as `CANVAS_TOKEN`.
   - ⚠️ If there's no "New Access Token" button, your school has disabled student tokens. Ask your school's IT/LMS team, because the bot can't work without one.
3. **Treat the token like a password.** It has full access to your Canvas account. Never paste it in Discord or commit it to GitHub.

### Phase 2 — Create the Discord bot (10 min)

4. Go to <https://discord.com/developers/applications>, click **New Application**, and name it, for example "Group Tracker."
5. Open the **Bot** tab and click **Reset Token**. Copy the token and use it as `DISCORD_TOKEN`.
   - You do **not** need any Privileged Gateway Intents, so leave them off.
6. Open **OAuth2 → URL Generator**:
   - Scopes: ✅ `bot` ✅ `applications.commands`
   - Bot permissions: ✅ View Channels ✅ Send Messages ✅ Embed Links
   - Open the generated URL, pick your server, and click **Authorize**.
7. Get the IDs:
   - In Discord, go to **User Settings → Advanced** and turn on **Developer Mode**.
   - Right-click the channel the bot should post in and choose **Copy Channel ID**. That's `DISCORD_CHANNEL_ID`.
   - Right-click your server icon and choose **Copy Server ID**. That's `DISCORD_GUILD_ID`. It's optional but recommended, because it makes slash commands show up instantly.
8. Make sure the bot's role can see and post in that channel, especially if it's a private channel.

### Phase 3 — Set up the project (5 min)

9. Install **Python 3.10+** (`python3 --version` to check).
10. Unzip this folder, then in a terminal inside it:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate        # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    ```
11. Copy the config template and fill it in:
    ```bash
    cp .env.example .env             # Windows: copy .env.example .env
    ```
    Open `.env` and fill in at least `DISCORD_TOKEN`, `DISCORD_CHANNEL_ID`, `CANVAS_BASE_URL`, and `CANVAS_TOKEN`.

### Phase 4 — Test Canvas before touching Discord (2 min)

12. Run the checker:
    ```bash
    python check_canvas.py
    ```
    You should see your courses with their IDs and each group assignment marked `✔ submitted` or `… not yet`.
    - **401 error:** the token is wrong or expired. Redo step 2.
    - **No group assignments listed:** your instructor may not have set the assignment up as a Canvas *group* assignment. See Troubleshooting.
13. *(Optional)* To watch only certain classes, copy their IDs into `.env`, like `COURSE_IDS=12345,67890`.

### Phase 5 — Run the bot (2 min)

14. Start it:
    ```bash
    python bot.py
    ```
    You should see `Logged in as Group Tracker#1234. Polling Canvas every 5 min.`
15. The first check records every assignment that's *already* submitted without announcing it. That's expected.
16. In Discord, type `/botinfo`, then `/pending`. If the commands don't appear, make sure `DISCORD_GUILD_ID` is set and restart the bot.

### Phase 6 — Test end to end (5 min)

17. Use `/check` any time to force a check instead of waiting.
18. The real test is the next time anyone in your group submits. Within `POLL_MINUTES`, or right away after `/check`, a 📬 message should appear.
    - To test sooner, stop the bot, delete one line from `data/state.json` for an assignment you've already submitted, and start the bot again. It will treat that submission as new and announce it.

### Phase 7 — Keep it running 24/7 (10 min)

The bot only works while it's running. Pick one option:

| Option | Good for | Notes |
|---|---|---|
| **Your own computer** | Trying it out | Stops when your laptop sleeps. |
| **Raspberry Pi / always-on PC** | Free and reliable | Run it with `systemd` or in `tmux`, as shown below. |
| **Railway / Render / Fly.io** | Set-and-forget cloud | Use the included `Dockerfile`, and attach a **volume at `/app/data`** so the bot doesn't forget its state on redeploy. Check each host's current pricing; free tiers change often. |

**Always-on Linux box (systemd):** create `/etc/systemd/system/canvas-bot.service`:
```ini
[Unit]
Description=Canvas group submission bot
After=network-online.target

[Service]
WorkingDirectory=/home/pi/canvas-group-bot
ExecStart=/home/pi/canvas-group-bot/.venv/bin/python bot.py
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```
Then run `sudo systemctl enable --now canvas-bot`. To view logs, use `journalctl -u canvas-bot -f`.

**Cloud host (Docker):** push this folder to a **private** GitHub repo. `.gitignore` already keeps `.env` out of it. Create a new service from the repo, which will auto-detect the Dockerfile. Enter each `.env` value as an environment variable in the host's dashboard, and add a persistent volume mounted at `/app/data`.

### Phase 8 — Maintain it

19. **Each new term:** Canvas tokens can expire. If the logs show a 401, generate a new token and update `CANVAS_TOKEN`. Update `COURSE_IDS` if you set it.
20. **If the Discord token leaks:** reset it in the Developer Portal right away and update `.env`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Missing required setting …` on start | That value is blank in `.env`. |
| Slash commands don't appear | Set `DISCORD_GUILD_ID` and restart. Without it, global commands can take up to an hour to appear. Also re-invite the bot with the `applications.commands` scope. |
| Bot is online but never posts | Check that the channel ID is correct and that the bot has View/Send/Embed permissions in that channel. |
| A group project isn't detected | The instructor may have created it as a normal assignment where each person submits separately. Set `GROUP_ONLY=false` to track every assignment you submit, though then it only fires when *you* submit. |
| `Canvas 403` on one course | Canvas restricts access to that course, which happens often with past or future terms. The bot skips it automatically. |
| Old assignments got announced | The state file was deleted or not persisted. On cloud hosts, make sure the `/app/data` volume is attached. |

## Files

| File | Purpose |
|---|---|
| `bot.py` | The Discord bot: polling loop, announcements, slash commands |
| `canvas.py` | Small Canvas API client with pagination handling |
| `tracker.py` | Detection logic and state file, kept separate from the network code |
| `check_canvas.py` | Standalone script to verify your Canvas token and preview what will be tracked |
| `test_tracker.py` | Tests for the detection logic (`python -m pytest`) |
| `.env.example` | Config template. Copy it to `.env` |
| `Dockerfile` | For cloud hosting |
