import telegram
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
import os
from google import genai
from google.genai import types
from database import add_to_conversation, read_conversation, read_memory, add_to_memory


load_dotenv()

telegram_key = os.getenv("TELEGRAM_TOKEN")
gemini_key = os.getenv("GEMINI_API_KEY")
if telegram_key is None:
    raise ValueError("TELEGRAM_TOKEN environment variable is required")
if gemini_key is None:
    raise ValueError("GEMINI_API_KEY environment variable is required")

client = genai.Client(api_key=gemini_key)

def strip_response(response: str):
    if response.startswith("REMEMBER"):
        try:
            lines = response.split("\n", 1)
            remember_line = lines[0]
            _, kv = remember_line.split(" ", 1)
            key, value = kv.split(":", 1)
            add_to_memory(key.strip(), value.strip())
            checked_response = lines[1].strip() if len(lines) > 1 else "Got it, I'll remember that!"
            if not checked_response:
                checked_response = "Got it, I'll remember that!"
        except ValueError:
            checked_response = "Got it, I'll remember that!"
    return checked_response

async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I'm your Telegram bot.") # type: ignore

async def respond(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text # type: ignore
    add_to_conversation("user", user_message)
    conversation = read_conversation(20)
    memory = read_memory()
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        config=types.GenerateContentConfig(
            system_instruction=f"""You are a personal AI assistant.

        Here is what you remember about the user:
            {memory}

        If the user tells you something important, you MUST format your response exactly like this:
        REMEMBER key:value
        Your normal response here on the next line.

        The REMEMBER line must always be followed by a normal response on a new line. Never put the REMEMBER and your response on the same line. Only use REMEMBER for personal information about the user specifically — things like their name, preferences, goals, or facts about their life. Never use REMEMBER for general world facts, trivia, or things that aren't specific to the user."""
    ),
        contents=[types.Content(role=msg["role"], parts=[types.Part(text=msg["parts"][0])])
        for msg in conversation])
    checked_response = strip_response(response.text)
    add_to_conversation("model", checked_response)
    await update.message.reply_text(checked_response) # type: ignore

def main() -> None:
    application = ApplicationBuilder().token(telegram_key).build() # type: ignore
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, respond))
    application.run_polling(allowed_updates=telegram.Update.ALL_TYPES)

if __name__ == "__main__":
    main()