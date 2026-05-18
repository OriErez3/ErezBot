import telegram
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
import os
from google import genai

load_dotenv()

telegram_key = os.getenv("TELEGRAM_TOKEN")
gemini_key = os.getenv("GEMINI_API_KEY")
if telegram_key is None:
    raise ValueError("TELEGRAM_TOKEN environment variable is required")
if gemini_key is None:
    raise ValueError("GEMINI_API_KEY environment variable is required")

client = genai.Client(api_key=gemini_key)

async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I'm your Telegram bot.")

async def respond(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite", 
        contents=user_message)
    await update.message.reply_text(response.text)

def main() -> None:
    application = ApplicationBuilder().token(telegram_key).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, respond))
    application.run_polling(allowed_updates=telegram.Update.ALL_TYPES)

if __name__ == "__main__":
    main()