"""One-time interactive setup for the bot. Run: python setup_bot.py

Safe to re-run at any time - it skips what's already done (installed packages are
re-checked cheaply, existing .env values can be kept by pressing Enter, and the
Google consent flow is only offered if token.json doesn't exist yet).
"""
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

#(env var, required, how to get it)
ENV_VARS = [
    ("TELEGRAM_TOKEN", True,
     "Message @BotFather on Telegram, create a bot with /newbot, copy the token."),
    ("GEMINI_API_KEY", True,
     "Create one at https://aistudio.google.com/apikey"),
    ("ALLOWED_USER_ID", True,
     "Your numeric Telegram user id (message @userinfobot to get it)."),
    ("TAVILY_KEY", False,
     "Sign up at https://tavily.com (free tier). Powers the web_search tool; "
     "leave blank to skip - everything else still works."),
]


def _mask(value: str) -> str:
    """Shows just enough of a saved secret to recognize it without exposing it."""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def check_python() -> None:
    if sys.version_info < (3, 10):
        sys.exit(f"Python 3.10+ is required (you're on {sys.version.split()[0]}). "
                 "Install a newer Python and re-run.")
    print(f"[ok] Python {sys.version.split()[0]}")
    #Modern Linux/macOS Pythons (PEP 668) refuse system-wide pip installs - catch it up
    #front with clear instructions instead of failing halfway through the install step.
    in_venv = sys.prefix != sys.base_prefix
    if in_venv:
        print(f"[ok] Virtual environment: {sys.prefix}")
    elif sys.platform != "win32":
        venv_dir = os.path.join(BASE_DIR, ".venv")
        sys.exit(
            "You're using the system Python, which will refuse to install packages\n"
            "(externally-managed-environment). Create and activate a virtual environment first:\n\n"
            f"    python3 -m venv {venv_dir}\n"
            f"    source {os.path.join(venv_dir, 'bin', 'activate')}\n"
            "    python setup_bot.py\n\n"
            "(The bot's service files and deploy script expect the venv at exactly that .venv path.)"
        )


def install_dependencies() -> None:
    print("\n--- Installing dependencies ---")
    requirements = os.path.join(BASE_DIR, "requirements.txt")
    result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", requirements])
    if result.returncode != 0:
        sys.exit("pip install failed - fix the error above and re-run.")
    print("\n--- Installing the Playwright browser (Chromium) ---")
    result = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    if result.returncode != 0:
        sys.exit("playwright install failed - fix the error above and re-run.")
    print("[ok] Dependencies installed")


def read_env() -> dict:
    """Parses the existing .env by hand - python-dotenv may not be installed yet."""
    values = {}
    if not os.path.exists(ENV_FILE):
        return values
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def configure_env() -> None:
    print("\n--- Configuring .env ---")
    existing = read_env()
    values = dict(existing)
    for name, required, help_text in ENV_VARS:
        current = existing.get(name, "")
        print(f"\n{name}{' (required)' if required else ' (optional)'}")
        print(f"  {help_text}")
        while True:
            if current:
                entered = input(f"  Value [{_mask(current)} - Enter to keep]: ").strip()
                if not entered:
                    entered = current
            else:
                entered = input("  Value: ").strip()
            if name == "ALLOWED_USER_ID" and entered and not entered.isdigit():
                print("  That doesn't look like a numeric Telegram user id - it should be "
                      "all digits (not your @username). Try again.")
                current = ""
                continue
            if entered or not required:
                break
            print("  This one is required - the bot won't start without it.")
        if entered:
            values[name] = entered
        elif name in values:
            del values[name]
    known = {name for name, _, _ in ENV_VARS}
    lines = [f"{name}={values[name]}" for name, _, _ in ENV_VARS if name in values]
    lines += [f"{k}={v}" for k, v in values.items() if k not in known]  # preserve any extra vars
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n[ok] Wrote {ENV_FILE}")


def setup_google() -> None:
    print("\n--- Google account (Gmail, Calendar, Drive) ---")
    if os.path.exists(TOKEN_FILE):
        print("[ok] token.json already exists - Google account is connected. "
              "(Delete token.json and re-run this script to reconnect.)")
        return
    if not os.path.exists(CREDENTIALS_FILE):
        print("credentials.json not found - skipping. To enable the Google tools later:\n"
              "  1. In Google Cloud Console, create a project and enable the Gmail,\n"
              "     Calendar, and Drive APIs.\n"
              "  2. Create an OAuth client ID of type 'Desktop app' and download the\n"
              "     client secret JSON as credentials.json in this folder.\n"
              "  3. Re-run this script.\n"
              "The bot runs fine without it - the gmail_*/calendar_*/drive_* tools just\n"
              "won't work until it's set up.")
        return
    answer = input("credentials.json found. Open a browser now to connect your Google "
                   "account? [Y/n]: ").strip().lower()
    if answer in ("", "y", "yes"):
        import google_services  # deferred - its dependencies were installed in step 2
        google_services.setup_auth()
    else:
        print("Skipped. Re-run this script (or run google_services.setup_auth()) later.")


def main() -> None:
    print("=== ErezBot setup ===")
    check_python()
    install_dependencies()
    configure_env()
    setup_google()
    print("\n=== Setup complete ===")
    print("Start the bot with:  python main.py")
    print("Then message your bot on Telegram.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSetup cancelled - re-run python setup_bot.py to pick up where you left off.")
