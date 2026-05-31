import telegram
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
import os
import asyncio
from google import genai
from google.genai import types
from database import add_to_conversation, read_conversation, read_memory, add_to_memory
import tools as t
import database
import platform
import inspect 
import base64
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
        ),
        types.FunctionDeclaration(
            name="list_directory",
            description="Returns the directory list of whatever path is inputted.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(
                        type=types.Type.STRING,
                        description="The path to list."
                    )
                },
                required=["path"]
            )
            ),
        types.FunctionDeclaration(
            name="read_file",
            description="Reads a given path to a file, and returns the contents of the file. ",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "file_path": types.Schema(
                        type=types.Type.STRING,
                        description="The path to read."
                    )
                },
                required=["file_path"]
            )
            ),
        types.FunctionDeclaration(
            name="write_file",
            description="Writes a file to whatever path is inputted. Takes two inputs, the path, and the content of the file. ",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(
                        type=types.Type.STRING,
                        description="The path to write a file to."
                    ),
                    "content": types.Schema(
                        type=types.Type.STRING,
                        description="The content of whats in the file."
                    )
                },
                required=["path","content"]
            )),
        types.FunctionDeclaration(
            name="find_file",
            description="Searches for a file by name in common directories including Desktop, Documents, and Downloads. Use this when the user wants to find a file but doesn't know the exact path.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "filename": types.Schema(
                        type=types.Type.STRING,
                        description="The file you want to look for"
                    )
                },
                required=["filename"]
            )),
        types.FunctionDeclaration(
        name="move_file",
        description="Moves a file from a given source to a given destination.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "source": types.Schema(
                    type=types.Type.STRING,
                    description="The path of the file you want moved"
                    ),
                "destination": types.Schema(
                    type=types.Type.STRING,
                    description="The path of where the file is going"
                    )
                },
                required=["source","destination"]
            )),
        types.FunctionDeclaration(
        name="web_search",
        description="Searches the web. Takes a query input, returns a formulated answer, as well as sources.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(
                    type=types.Type.STRING,
                    description="What you want to search up."
                    )
                },
                required=["query"]
            )),
        types.FunctionDeclaration(
        name="browser_navigate",
        description="Goes to a given URL and returns the screenshot data.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "url": types.Schema(
                    type=types.Type.STRING,
                    description="The website you want to go"
                    )
                },
                required=["url"]
            )),
            types.FunctionDeclaration(
            name="browser_screenshot",
            description="Takes a screenshot of the current browser page and returns it. Use this to see the current state of the page after any action.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={}
            ))
            ])
            

            


#Test to make sure everything is working
async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I'm your Google AI assistant.") # type: ignore

system_instruction = f"""You are a personal AI assistant. Be helpful, conversational, and concise.
            Whenever using any tools, keep in mind you are on {os_name}, so use the right syntax.  

            Only use tools when necessary. For normal conversation just respond naturally.
            If you can't find a file, please ask the user for the directory. If it's an important directory be sure to save it to memory. 
            After using any tool, always follow up with a direct response to the user's original message."""
#Function to handle messages. Used the most often. 

tool_dict = {
    "run_shell": t.run_shell,
    "list_directory": t.list_directory,
    "read_file": t.read_file,
    "write_file": t.write_file,
    "save_memory": t.save_memory,
    "delete_memory": t.delete_memory,
    "find_file": t.find_file,
    "web_search": t.web_search,
    "browser_navigate": t.browser_navigate,
    "browser_screenshot": t.browser_screenshot
}
screenshot_tools = {"browser_navigate", "browser_screenshot"}
async def respond(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_message = update.message.text # type: ignore
        memory = read_memory() #Reads the bot's memory. This memory stores important information only. 
        memory_context = [types.Content(role="user", parts=[types.Part(text="What do you know about me?")]), types.Content(role="model", parts=[types.Part(text=f"Here is what I know about you:\n{memory}")])] #Creating a fake conversation with memory to provide context for the AI. This way, the AI can refer to its memory when generating a response to the user's message.
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
        #Everything below is for handling tool calls. 
        seen_calls = set()
        while response.function_calls: #Checks if the AI called any tools in its response
            for func in response.function_calls: #If it did, it executes the tool calls and gets the results
                call_key = f"{func.name}_{func.args}"
                tool_name = func.name
                print(call_key)
                
                if call_key in seen_calls:
                    result = "This approach isn't working. Tell the user you're unable to complete the task and ask them for more information."
                    response = chat.send_message(types.Part(
                        function_response=types.FunctionResponse(
                    name=tool_name,
                    id=func.id,
                    response={"result": result})))
                    break
                seen_calls.add(call_key)
                
                if tool_name in tool_dict:
                    try:
                        if inspect.iscoroutinefunction(tool_dict[tool_name]):
                            result = await tool_dict[tool_name](**func.args) #Executes the tool function with the provided arguments and gets the result
                            print(result)
                    except Exception as e:
                        result = f"Error excecuting {tool_name}: {e}"
                        print(result)
                else:
                    result = f'Tool: {tool_name} not found'
                
                if tool_name in screenshot_tools and not result.startswith("Error"):
                    image_bytes = base64.b64decode(result)
                    response = chat.send_message([types.Part(
                        function_response=types.FunctionResponse(
                            name=tool_name,
                            id=func.id,
                            response = {"result": "Screenshot taken successfully"}
                        )

                    ),
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/png"
                    )
                    ])
                else:
                    response = chat.send_message(types.Part(
                function_response=types.FunctionResponse(
                    name=tool_name,
                    id=func.id,
                    response={"result": result}
                )
            ))
        add_to_conversation("model", response.text) #type: ignore #Saves the AI's response to the conversation history in the database
        await update.message.reply_text(response.text) #type: ignore #Sends the AI's response back to the user on Telegram
    except Exception as e:
        error_message = str(e)
        if "429" in error_message or "quota" in error_message.lower() or "exhausted" in error_message.lower():
            await update.message.reply_text("I've hit my API rate limit. Please wait a moment and try again.")
        elif "503" in error_message or "unavailable" in error_message.lower():
            await update.message.reply_text("Gemini is currently unavailable. Please try again in a few minutes.")
        elif "token" in error_message.lower():
            await update.message.reply_text("The conversation is too long. Try /clear and start fresh.")
        else:
            await update.message.reply_text(f"Something went wrong: {error_message}")
   

   
    
   
async def clear(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    database.clear_conversation()
    await update.message.reply_text("Conversation cleared!") #type: ignore      
        

def main() -> None:
    application = ApplicationBuilder().token(telegram_key).build() # type: ignore
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, respond))
    application.run_polling(allowed_updates=telegram.Update.ALL_TYPES)

if __name__ == "__main__":
    main()