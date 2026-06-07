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
            description="Writes a file to whatever path is inputted. Takes three inputs, the path, the content of the file, and whether the file in binary or not",
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
                    ),
                    "binary": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="Determines whether the content is binary or not."
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
            )),
            types.FunctionDeclaration(
            name="browser_click",
            description="Clicks at whatever coordinate you want, waits for it to load, and returns a screenshot of what happened",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "x": types.Schema(
                        type=types.Type.INTEGER,
                        description="The X-axis of where you want to click"
                    ),
                    "y": types.Schema(
                        type=types.Type.INTEGER,
                        description="The Y-axis of where you want to click"
                    )
                },
                required=["x","y"]
            )),
            types.FunctionDeclaration(
            name="browser_type",
            description="Types whatever is passed in and can press the enter button to submit it to a form.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "text": types.Schema(
                        type=types.Type.STRING,
                        description="Whatever message you want to type."
                    ),
                    "press_enter": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="Use to press enter if needed. Defaults to False"
                    )
                },
                required=["text"]
            )),
            types.FunctionDeclaration(
            name="browser_scroll",
            description="Scrolls up or down depending on whats passed in.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "direction": types.Schema(
                        type=types.Type.STRING,
                        description="Takes either up or down as directions to scroll."
                    ),
                    "amount": types.Schema(
                        type=types.Type.INTEGER,
                        description="Used to define how much to scroll up or down. Defaults to 300"
                    )
                },
                required=["direction"]
            )),
            types.FunctionDeclaration(
            name="browser_click_element",
            description="Allows you to click an element in the text map generated by browser_screenshot_annotated. Takes the index of the element, returns the updated screen after you click the button.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"index": types.Schema(
                    type=types.Type.INTEGER,
                    description="Clicks the index of the integer given for you."
                )},
                required=["index"]         
            )),
            types.FunctionDeclaration(
            name="browser_get_elements",
            description="Gives you a text map, and an annotated image of all the elements on a website. Takes a boolean, which determines if you need the annotated screenshot.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"screenshot": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Returns a screenshot with the elements annotated if set to true"
                )}
                    
            )),
            types.FunctionDeclaration(
            name="browser_go_back",
            description="Goes back to the previous page.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={}         
            )),
            types.FunctionDeclaration(
            name="read_memory",
            description="Reads the memory and returns it to you",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={}         
            )),
            types.FunctionDeclaration(
            name="browser_current_url",
            description="Returns the current browser URL. Use to see if you actually need to change URLs.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={}         
            )),
            ])
            

            


#Test to make sure everything is working
async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I'm your Google AI assistant.") # type: ignore
##- Username: {username}
#- Current directory: {cwd}
system_instruction = f"""You are a personal AI assistant. Be helpful and concise.

System info:
- OS: {os_name}


Tool rules:
- Use save_memory for important user facts, delete_memory when outdated, read_memory to recall facts
- Use write_file, read_file, list_directory for file operations. Only use run_shell when explicitly asked
- Never give up on a task without actually attempting it first
- Browser: only call browser_navigate for new URLs, never to save files
- Browser: always call browser_get_elements before deciding you cannot complete a task
- Browser: use write_file to save any content to disk
- After every browser action check the result before deciding what to do next
- Only ask the user for help if truly stuck after exhausting all options"""
#Function to handle messages. Used the most often. 

tool_dict = {
    "run_shell": t.run_shell,
    "list_directory": t.list_directory,
    "read_file": t.read_file,
    "write_file": t.write_file,
    "save_memory": t.save_memory,
    "delete_memory": t.delete_memory,
    "read_memory": t.read_memory,
    "find_file": t.find_file,
    "web_search": t.web_search,
    "browser_navigate": t.browser_navigate,
    "browser_screenshot": t.browser_screenshot,
    "browser_click": t.browser_click,
    "browser_type": t.browser_type,
    "browser_scroll": t.browser_scroll,
    "browser_get_elements": t.browser_get_elements,
    "browser_click_element" : t.browser_click_element,
    "browser_go_back": t.browser_go_back,
    "browser_current_url": t.browser_current_url,
    
}
screenshot_tools = {"browser_navigate", "browser_screenshot", "browser_click", "browser_type", "browser_scroll", "browser_click_element", "browser_go_back"}
async def respond(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_message = update.message.text # type: ignore
        memory = read_memory() #Reads the bot's memory. This memory stores important information only. 
        conversation = read_conversation(30) #Reads the last 7 messages from the conversation history to provide context for the AI's response
        contents=[types.Content(role=msg["role"], parts=[types.Part(text=msg["parts"][0])]) for msg in conversation] #Converts the conversation history into the correct format for Gemini API
        chat = client.chats.create(
                model="gemini-3.1-flash-lite",
                history=contents, #type: ignore 
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
                print(func.name)
                
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
                        else:
                            result = tool_dict[tool_name](**func.args)
                    except Exception as e:
                        result = f"Error excecuting {tool_name}: {e}"
                        print(result)
                else:
                    result = f'Tool: {tool_name} not found'
                if isinstance(result, tuple):
                    # Has both image and element map
                    image_b64, element_map = result
                    image_bytes = base64.b64decode(image_b64)
                    response = chat.send_message([
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=tool_name,
                                id=func.id,
                                response={"result": element_map}
                            )
                        ),
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png")
                    ])
                elif tool_name in screenshot_tools and not result.startswith("Error"):
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