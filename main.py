import telegram
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
import os
from google import genai
from google.genai import types
from database import add_to_conversation, read_conversation, read_memory, add_to_memory
from tools import run_shell, save_memory, delete_memory
from database import clear_conversation
import platform
#type: ignore
load_dotenv()
#Loads the environment variables for the APIs
telegram_key = os.getenv("TELEGRAM_TOKEN")
gemini_key = os.getenv("GEMINI_API_KEY")
if telegram_key is None:
    raise ValueError("TELEGRAM_TOKEN environment variable is required")
if gemini_key is None:
    raise ValueError("GEMINI_API_KEY environment variable is required")

client = genai.Client(api_key=gemini_key)
os_name = platform.system()
#Loads the tools for the AI to use. 
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

#Test to make sure everything is working
async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I'm your Google AI assistant.") # type: ignore

system_instruction = f"""You are a personal AI assistant. Be helpful, conversational, and concise.
            You have access to these tools:
            - Use save_memory when the user tells you something personal worth remembering permanently, like their name, preferences, or goals
            - Use delete_memory when a stored fact is no longer accurate
            - Use run_shell to execute commands on the user's computer. Keep in mind you are on {os_name}. Use the correct commands for this OS. 

            Only use tools when necessary. For normal conversation just respond naturally.
            After using any tool, always follow up with a direct response to the user's original message."""
#Function to handle messages. Used the most often. 
tool_dict = {
    "run_shell": run_shell,
    "save_memory": save_memory,
    "delete_memory": delete_memory
}
async def respond(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text # type: ignore
    memory = read_memory() #Reads the bot's memory. This memory stores important information only. 
    memory_context = [
    types.Content(role="user", parts=[types.Part(text="What do you know about me?")]),
    types.Content(role="model", parts=[types.Part(text=f"Here is what I know about you:\n{memory}")])
] #Creating a fake conversation with memory to provide context for the AI. This way, the AI can refer to its memory when generating a response to the user's message.
    conversation = read_conversation(10) #Reads the last 10 messages from the conversation history to provide context for the AI's response
    contents=[types.Content(role=msg["role"], parts=[types.Part(text=msg["parts"][0])]) for msg in conversation] #Converts the conversation history into the correct format for Gemini API
    chat = client.chats.create(
            model="gemini-3.1-flash-lite",
            history=memory_context+contents, #type: ignore 
            config=types.GenerateContentConfig(tools=[tools],
                system_instruction=system_instruction
        ),)
    add_to_conversation("user", user_message)#type: ignore #Saves the user's message to the conversation history in the database
    response = chat.send_message(user_message)
    while response.function_calls: #Checks if the AI called any tools in its response
        for func in response.function_calls: #If it did, it executes the tool calls and gets the results
            tool_name = func.name
            if tool_name in tool_dict:
                result = tool_dict[tool_name](**func.args) #Executes the tool function with the provided arguments and gets the result
                function_response_part = chat.send_message(types.Part(
        function_response=types.FunctionResponse(
            name=tool_name,
            id=func.id,
            response={"result": result}
        )
    ))
    await update.message.reply_text(response.text) #type: ignore #Sends the AI's response back to the user on Telegram
    add_to_conversation("model", response.text) #type: ignore #Saves the AI's response to the conversation history in the database

   
    
   
async def clear(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    clear_conversation()
    await update.message.reply_text("Conversation cleared!") #type: ignore      
        

def main() -> None:
    application = ApplicationBuilder().token(telegram_key).build() # type: ignore
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, respond))
    application.run_polling(allowed_updates=telegram.Update.ALL_TYPES)

if __name__ == "__main__":
    main()