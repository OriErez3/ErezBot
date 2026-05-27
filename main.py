import telegram
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
import os
from google import genai
from google.genai import types
from database import add_to_conversation, read_conversation, read_memory, add_to_memory
from tools import run_shell, save_memory, delete_memory
from database import clear_conversation

load_dotenv()

telegram_key = os.getenv("TELEGRAM_TOKEN")
gemini_key = os.getenv("GEMINI_API_KEY")
if telegram_key is None:
    raise ValueError("TELEGRAM_TOKEN environment variable is required")
if gemini_key is None:
    raise ValueError("GEMINI_API_KEY environment variable is required")

client = genai.Client(api_key=gemini_key)
tools = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="run_shell",
            description="Runs a shell command on the user's computer and returns the output. Use this to interact with the file system, run scripts, or execute system commands.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "command": types.Schema(
                        type=types.Type.STRING,
                        description="The shell command to run"
                    )
                },
                required=["command"]
            )
        ),
        types.FunctionDeclaration(
            name="save_memory",
            description="Saves a key-value pair to the bot's memory. Use this to remember important information about the user, such as their name, preferences, goals, or facts about their life.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "key": types.Schema(
                        type=types.Type.STRING,
                        description="The key to identify the memory"
                    ),
                    "value": types.Schema(
                        type=types.Type.STRING,
                        description="The value to remember"
                    )
                },
                required=["key", "value"]
            )
        ),
        types.FunctionDeclaration(
            name="delete_memory",
            description="Deletes a key-value pair from the bot's memory. Use this to remove information that is no longer relevant or that the user wants to forget.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "key": types.Schema(
                        type=types.Type.STRING,
                        description="The key of the memory to delete"
                    )
                },
                required=["key"]
            )
        )
    ]
)   
async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I'm your Telegram bot.") # type: ignore

async def respond(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text # type: ignore
    add_to_conversation("user", user_message)
    conversation = read_conversation(10)
    print("CONVERSATION:", conversation)
    memory = read_memory()
    print("MEMORY:", memory)

    contents=[types.Content(role=msg["role"], parts=[types.Part(text=msg["parts"][0])])
            for msg in conversation]
    max_iterations = 5
    iteration = 0
    while iteration< max_iterations:
        iteration += 1 
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            config=types.GenerateContentConfig(tools=[tools],
                system_instruction=f"""You are a personal AI assistant. Be helpful, conversational, and concise.

            Here is what you remember about the user:
            {memory}

            You have access to these tools:
            - Use save_memory when the user tells you something personal worth remembering permanently, like their name, preferences, or goals
            - Use delete_memory when a stored fact is no longer accurate
            - Use run_shell to execute commands on the user's computer

            Only use tools when necessary. For normal conversation just respond naturally.
            After using any tool, always follow up with a direct response to the user's original message."""
        ),
            contents=contents)
        part = response.candidates[0].content.parts[0]
        print(part)
        if part.function_call:
            function_call = part.function_call
            if function_call.name == "run_shell":
                result = run_shell(function_call.args["command"])
            elif function_call.name == "save_memory":
                result = save_memory(function_call.args["key"], function_call.args["value"])
            elif function_call.name == "delete_memory":
                result = delete_memory(function_call.args["key"])
            contents.append(types.Content(role="model", parts=[part]))
            contents.append(types.Content(
                role="user",
                parts=[types.Part(
                    function_response=types.FunctionResponse(
                        name=function_call.name,
                        response={"result": result}
                        )
                        )]
            ))
        else:
            if not response.text or not response.text.strip():
                follow_up = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                config=types.GenerateContentConfig(
                system_instruction=f"""You are a personal AI assistant.
    Here is what you remember about the user:
    {read_memory()}"""
            ),
            contents=contents + [types.Content(
                role="user",
                parts=[types.Part(text="Acknowledge what you just did and respond naturally.")]
            )]
        )
                checked_response = follow_up.text.strip() if follow_up.text else "Done!"
                add_to_conversation("model", checked_response)
                await update.message.reply_text(checked_response)
                break
async def clear(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    clear_conversation()
    await update.message.reply_text("Conversation cleared!")       
        

def main() -> None:
    application = ApplicationBuilder().token(telegram_key).build() # type: ignore
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, respond))
    application.run_polling(allowed_updates=telegram.Update.ALL_TYPES)

if __name__ == "__main__":
    main()