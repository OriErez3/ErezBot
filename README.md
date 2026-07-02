# ClawBotClone

A personal AI assistant that lives in Telegram. It's powered by Gemini and can use a real set of tools on your machine: run shell commands, manage files, browse the web with a visible browser, search the web, read and send Gmail, manage Google Calendar and Drive, remember facts about you, and run tasks on a schedule — including proactively checking your email and calendar every hour and messaging you if something needs your attention.

The bot only responds to a single Telegram user (you). Anyone else who messages it is ignored.

## Features

- **Agentic tool loop** — the model chains tool calls (up to 20 per request, 100 in persist mode) until the task is done, with duplicate-call detection so it can't get stuck repeating itself.
- **Shell access with guardrails** — risky tools (shell commands, background processes, sending email, moving files) require a yes/no confirmation in the chat before they run. Truly destructive commands (`format`, `diskpart`, fork bombs, ...) are always blocked, even if approved.
- **Long-running processes** — servers and watchers run in the background with an ID; the bot can read their output, list them, and stop them. A shell command that turns out to be long-running is automatically moved to the background instead of hanging.
- **Browser automation** — a visible Chromium window driven by Playwright: navigate, screenshot, click (by coordinate or by indexed element map), type, scroll.
- **Google integration** — Gmail (list/read/send/mark read), Calendar (list/create events), Drive (list/read/upload).
- **Memory** — the bot saves important facts about you to a local SQLite database and loads them into every conversation.
- **Multiple conversations** — create, list, switch, and rename separate conversation histories.
- **Scheduled tasks** — "remind me at 5pm to..." style tasks persist in the database, survive restarts, and execute with the full tool loop.
- **Proactive check-ins** — every hour the bot checks for unread email and upcoming calendar events and messages you only if there's something new worth flagging.

## Setup

### Quick start (recommended)

Requires Python 3.10+. Run the interactive setup script and follow the prompts:

```
python setup_bot.py
```

It installs the dependencies and the Playwright browser, walks you through creating the `.env`, and connects your Google account if `credentials.json` is present. It's safe to re-run at any time. The sections below explain the same steps manually, including how to obtain each key and `credentials.json`.

### 1. Install dependencies

Requires Python 3.10+.

```
pip install -r requirements.txt
playwright install chromium
```

### 2. Create a `.env` file

In the project root:

```
TELEGRAM_TOKEN=<your bot token from @BotFather>
GEMINI_API_KEY=<your key from Google AI Studio>
TAVILY_KEY=<your key from tavily.com, used for web search>
ALLOWED_USER_ID=<your numeric Telegram user id>
```

- **TELEGRAM_TOKEN**: message [@BotFather](https://t.me/BotFather) on Telegram, create a bot with `/newbot`, and copy the token.
- **GEMINI_API_KEY**: create one at [Google AI Studio](https://aistudio.google.com/apikey).
- **TAVILY_KEY**: sign up at [tavily.com](https://tavily.com) (free tier is fine).
- **ALLOWED_USER_ID**: your own Telegram user id (a number, not your @username). Message [@userinfobot](https://t.me/userinfobot) to get it. This is required — the bot has shell and email access, so it must only obey you.

### 3. Connect your Google account

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable the **Gmail API**, **Google Calendar API**, and **Google Drive API**.
2. Create an **OAuth client ID** of type **Desktop app** (you may need to configure the OAuth consent screen first and add yourself as a test user).
3. Download the client secret JSON and save it as `credentials.json` in the project root.
4. Run the one-time consent flow from a terminal:

```
python -c "import google_services; google_services.setup_auth()"
```

A browser opens; sign in and approve the scopes. This writes `token.json`, which the bot uses from then on (it refreshes itself automatically).

`credentials.json`, `token.json`, and the `memory.db` database are gitignored — never commit them.

### 4. Run the bot

```
python main.py
```

Then message your bot on Telegram. The first message also registers your chat as the destination for proactive check-ins and scheduled-task reports.

## Bot commands

| Command | What it does |
|---|---|
| `/start` | Greet the bot (sanity check that it's running) |
| `/clear` | Clear the active conversation's history |
| `/new` | Start a new conversation |
| `/list` | List all conversations |
| `/switch <number>` | Switch to a conversation by number |
| `/rename <name>` | Rename the active conversation |
| `/persist` | Toggle persistent mode — the bot won't give up on a task until it's done (raises the tool-call cap from 20 to 100) |
| `/bypass` | ⚠️ Toggle skipping the confirmation prompt for risky actions. The hard blocklist still applies. Use with care. |

## Project layout

| File | Purpose |
|---|---|
| `main.py` | Telegram handlers, system prompt, the tool loop, confirmations, scheduled-task and check-in jobs |
| `tools.py` | Local tools: shell, background processes, files, downloads, web search, memory, browser automation |
| `google_services.py` | Gmail, Calendar, and Drive tools plus the OAuth flow |
| `database.py` | SQLite storage: conversations, memory, settings, scheduled tasks |

Tool declarations are generated automatically from each function's signature and docstring — to add a tool, write the function and register it in `tool_dict` in `main.py`.

## Security notes

- The bot answers **only** the `ALLOWED_USER_ID` account. Keep it that way — it can run shell commands and send email as you.
- Risky tools prompt for confirmation with a 2-minute timeout that defaults to deny.
- `/bypass` disables those prompts. The blocklist of unrecoverable commands is enforced regardless, but bypass mode still means the bot can act (send email, run commands) without asking. Leave it off unless you're actively supervising.
