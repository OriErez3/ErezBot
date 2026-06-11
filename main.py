import telegram
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
import os
import asyncio
from google import genai
from google.genai import types
from database import add_to_conversation, read_conversation, read_memory
import tools as t
import google_services as gs
import database
import platform
import inspect
import base64
import logging
import re
from datetime import datetime
from typing import Any
#type: ignore
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
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
            description="Types text into the currently focused element. Set press_enter=True to immediately submit/confirm afterward (e.g. search bars, login forms, chat inputs, game guesses like Wordle) - this is usually what you want instead of typing and then taking a separate action to submit.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "text": types.Schema(
                        type=types.Type.STRING,
                        description="Whatever message you want to type."
                    ),
                    "press_enter": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="Set to true to press Enter right after typing, submitting/confirming the input. Only leave false if you specifically need to type without submitting (e.g. a multi-line text area)."
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
            types.FunctionDeclaration(
            name="gmail_list_messages",
            description="Lists recent Gmail messages, optionally filtered with a Gmail search query. Returns each message's id, sender, subject, date, and a snippet. Use the id with gmail_read_message to see the full message.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "max_results": types.Schema(
                        type=types.Type.INTEGER,
                        description="Maximum number of messages to return. Defaults to 10."
                    ),
                    "query": types.Schema(
                        type=types.Type.STRING,
                        description="Optional Gmail search query, e.g. 'is:unread' or 'from:someone@example.com'."
                    )
                }
            )),
            types.FunctionDeclaration(
            name="gmail_read_message",
            description="Reads the full content (sender, subject, date, body) of a Gmail message by id.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "message_id": types.Schema(
                        type=types.Type.STRING,
                        description="The id of the message, from gmail_list_messages."
                    )
                },
                required=["message_id"]
            )),
            types.FunctionDeclaration(
            name="gmail_send_email",
            description="Sends an email from the user's Gmail account.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "to": types.Schema(
                        type=types.Type.STRING,
                        description="Recipient email address."
                    ),
                    "subject": types.Schema(
                        type=types.Type.STRING,
                        description="Email subject line."
                    ),
                    "body": types.Schema(
                        type=types.Type.STRING,
                        description="Email body text."
                    )
                },
                required=["to", "subject", "body"]
            )),
            types.FunctionDeclaration(
            name="calendar_list_events",
            description="Lists the user's upcoming Google Calendar events, soonest first.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "max_results": types.Schema(
                        type=types.Type.INTEGER,
                        description="Maximum number of events to return. Defaults to 10."
                    )
                }
            )),
            types.FunctionDeclaration(
            name="calendar_create_event",
            description="Creates an event on the user's primary Google Calendar. Use the current date/time from the system info to resolve relative dates like 'tomorrow' or 'next Monday'.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "summary": types.Schema(
                        type=types.Type.STRING,
                        description="Event title."
                    ),
                    "start": types.Schema(
                        type=types.Type.STRING,
                        description="Start time as an RFC3339 datetime with offset, e.g. 2026-06-12T15:00:00-04:00."
                    ),
                    "end": types.Schema(
                        type=types.Type.STRING,
                        description="End time as an RFC3339 datetime with offset, e.g. 2026-06-12T16:00:00-04:00."
                    ),
                    "description": types.Schema(
                        type=types.Type.STRING,
                        description="Optional event description."
                    )
                },
                required=["summary", "start", "end"]
            )),
            types.FunctionDeclaration(
            name="drive_list_files",
            description="Lists files in the user's Google Drive, most recently modified first, optionally filtered with a Drive search query.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(
                        type=types.Type.STRING,
                        description="Optional Drive search query, e.g. \"name contains 'budget'\"."
                    ),
                    "max_results": types.Schema(
                        type=types.Type.INTEGER,
                        description="Maximum number of files to return. Defaults to 10."
                    )
                }
            )),
            types.FunctionDeclaration(
            name="drive_read_file",
            description="Reads the text content of a file in the user's Google Drive by id (Google Docs/Sheets/Slides are exported as text/CSV).",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "file_id": types.Schema(
                        type=types.Type.STRING,
                        description="The id of the file, from drive_list_files."
                    )
                },
                required=["file_id"]
            )),
            types.FunctionDeclaration(
            name="drive_upload_file",
            description="Creates a new file with the given text content in the user's Google Drive.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(
                        type=types.Type.STRING,
                        description="Name for the new file."
                    ),
                    "content": types.Schema(
                        type=types.Type.STRING,
                        description="Text content of the file."
                    ),
                    "mime_type": types.Schema(
                        type=types.Type.STRING,
                        description="MIME type of the content. Defaults to text/plain."
                    )
                },
                required=["name", "content"]
            )),
            ])
            

            


#Test to make sure everything is working
async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hello! I'm your Google AI assistant.") # type: ignore
##- Username: {username}
#- Current directory: {cwd}
def build_system_instruction(memory: str, browser_url: str, now: str) -> str:
    return f"""You are a personal AI assistant. Be helpful and concise.

System info:
- OS: {os_name}
- Current date/time: {now}

Saved memory about the user:
{memory}

Browser state:
- Current browser page: {browser_url}
- This reflects reality right now, even if earlier conversation mentions a different page. Trust this over anything you previously said about the browser.

Tool rules:
- Use save_memory for important user facts, delete_memory when outdated, read_memory to recall facts
- Use write_file, read_file, list_directory for file operations. Only use run_shell when explicitly asked
- Never give up on a task without actually attempting it first
- Browser: only call browser_navigate for new URLs, never to save files
- Browser: re-navigating to the page you're already on is now a safe no-op (it won't reload), but prefer browser_get_elements/browser_screenshot to inspect the current page instead of calling browser_navigate again
- Browser: always call browser_get_elements before deciding you cannot complete a task
- Browser: use write_file to save any content to disk
- Browser: for a new or ambiguous request, check "Current browser page" above first, and use browser_get_elements/browser_screenshot to see what's actually on screen before acting - don't assume you're still on a page from earlier conversation
- Browser: never call browser_go_back unless the user explicitly asks to go back; it can navigate away from the page you're supposed to be working on
- Browser: when typing into a search bar, form field, or game input that should be submitted (e.g. a Wordle guess), call browser_type with press_enter=True instead of typing and then taking a separate action to submit
- After every browser action check the result before deciding what to do next
- Google account: use gmail_* tools to read/search/send email. Confirm with the user before sending an email unless they explicitly asked you to send it
- Google account: use calendar_* tools to view and create events. Resolve relative dates (e.g. "tomorrow", "next Monday") using the current date/time above
- Google account: use drive_* tools for files in the user's Google Drive - this is separate from the local filesystem tools
- Only ask the user for help if truly stuck after exhausting all options
- Always reply to the user in your own clear words. Never paste raw HTML, element-map/tool output, or URLs with tracking parameters directly into your reply
- If the user changes topic or asks you to abandon the current task, fully switch focus to their new request and disregard unrelated state or results from the abandoned task"""
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
    "move_file": t.move_file,
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
    "gmail_list_messages": gs.gmail_list_messages,
    "gmail_read_message": gs.gmail_read_message,
    "gmail_send_email": gs.gmail_send_email,
    "calendar_list_events": gs.calendar_list_events,
    "calendar_create_event": gs.calendar_create_event,
    "drive_list_files": gs.drive_list_files,
    "drive_read_file": gs.drive_read_file,
    "drive_upload_file": gs.drive_upload_file,
}
screenshot_tools = {"browser_navigate", "browser_screenshot", "browser_click", "browser_type", "browser_scroll", "browser_click_element", "browser_go_back"}
MAX_TOOL_ITERATIONS = 20
KEEP_RECENT_SCREENSHOTS = 2
# Matches raw element-map lines (e.g. "[12] a: 'text' at (100, 200)") or pasted-HTML fragments
INVALID_REPLY_PATTERN = re.compile(r"^\[\d+\]\s+\w+:|target=\"_blank\"|utm_source=")

def _validate_tool_registrations() -> None:
    declared = {fd.name for fd in tools.function_declarations} #type: ignore
    registered = set(tool_dict)
    if declared != registered:
        raise RuntimeError(
            f"Tool registration mismatch - declared only: {declared - registered}, "
            f"tool_dict only: {registered - declared}"
        )
    if not screenshot_tools <= registered:
        raise RuntimeError(f"screenshot_tools has unknown tools: {screenshot_tools - registered}")

_validate_tool_registrations()

async def _execute_tool(tool_name: str, args: dict) -> Any:
    """Looks up and runs a tool by name, returning its result (or an error string)."""
    if tool_name not in tool_dict:
        return f'Tool: {tool_name} not found'
    try:
        if inspect.iscoroutinefunction(tool_dict[tool_name]):
            return await tool_dict[tool_name](**args)
        return tool_dict[tool_name](**args)
    except Exception as e:
        result = f"Error executing {tool_name}: {e}"
        logger.warning(result)
        return result

def _send_tool_result(chat: Any, func: Any, tool_name: str, result: Any) -> Any:
    """Sends a tool's result back to the chat, attaching an image if the result includes one."""
    if isinstance(result, tuple):
        # Has both image and element map
        image_b64, element_map = result
        image_bytes = base64.b64decode(image_b64)
        return chat.send_message([
            types.Part(
                function_response=types.FunctionResponse(
                    name=tool_name,
                    id=func.id,
                    response={"result": element_map}
                )
            ),
            types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        ])
    if tool_name in screenshot_tools and not result.startswith("Error"):
        image_bytes = base64.b64decode(result)
        return chat.send_message([
            types.Part(
                function_response=types.FunctionResponse(
                    name=tool_name,
                    id=func.id,
                    response={"result": "Screenshot taken successfully"}
                )
            ),
            types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        ])
    return chat.send_message(types.Part(
        function_response=types.FunctionResponse(
            name=tool_name,
            id=func.id,
            response={"result": result}
        )
    ))

def _prune_old_screenshots(chat: Any, keep_recent: int = KEEP_RECENT_SCREENSHOTS) -> None:
    """Strips inline image data from older tool-result turns in the live chat history,
    keeping only the most recent `keep_recent` screenshots so context size stays bounded
    no matter how many tool calls the loop makes."""
    history = chat.get_history(curated=True)
    image_indices = [
        i for i, content in enumerate(history)
        if content.parts and any(p.inline_data is not None for p in content.parts)
    ]
    for i in image_indices[:-keep_recent] if keep_recent else image_indices:
        content = history[i]
        content.parts = [
            types.Part(text="[older screenshot omitted to save context]")
            if p.inline_data is not None else p
            for p in content.parts
        ]

async def _run_tool_loop(chat: Any, response: Any) -> tuple[Any, bool]:
    """Repeatedly executes tool calls requested by the model until it stops calling tools,
    a duplicate call is detected, or MAX_TOOL_ITERATIONS is exceeded. Returns the final
    response and whether the loop gave up early."""
    seen_calls = set()
    give_up = False
    iteration_count = 0
    while response.function_calls and not give_up: #Checks if the AI called any tools in its response
        for func in response.function_calls: #If it did, it executes the tool calls and gets the results
            call_key = f"{func.name}_{func.args}"
            tool_name = func.name
            logger.debug("Tool call: %s", tool_name)

            iteration_count += 1
            if iteration_count > MAX_TOOL_ITERATIONS:
                result = "You've taken too many actions on this task. Stop here and respond to the user now, summarizing what you've done so far and what's left."
                response = chat.send_message(types.Part(
                    function_response=types.FunctionResponse(
                name=tool_name,
                id=func.id,
                response={"result": result})))
                give_up = True
                break

            if call_key in seen_calls:
                result = "This approach isn't working. Tell the user you're unable to complete the task and ask them for more information."
                response = chat.send_message(types.Part(
                    function_response=types.FunctionResponse(
                name=tool_name,
                id=func.id,
                response={"result": result})))
                give_up = True
                break
            seen_calls.add(call_key)

            result = await _execute_tool(tool_name, func.args)
            response = _send_tool_result(chat, func, tool_name, result)
            _prune_old_screenshots(chat)
    return response, give_up

def _finalize_reply(response: Any, give_up: bool) -> str:
    """Validates the model's final text, substituting a friendly message if it's empty or
    looks like raw tool/HTML output that shouldn't be shown to the user."""
    final_text = response.text #type: ignore
    if not final_text or not final_text.strip():
        finish_reason = None
        try:
            finish_reason = response.candidates[0].finish_reason #type: ignore
        except (IndexError, AttributeError):
            pass
        logger.warning("Model returned an empty response (finish_reason=%s, give_up=%s)", finish_reason, give_up)
        if give_up:
            return "I got stuck while working on that and wasn't able to finish. Could you give me more guidance, or try a different approach?"
        return "Sorry, I couldn't come up with a response there. Could you try rephrasing?"
    if INVALID_REPLY_PATTERN.search(final_text):
        logger.warning("Model returned an invalid/raw reply, discarding: %r", final_text)
        return "Sorry, I couldn't come up with a response there. Could you try rephrasing?"
    return final_text

async def respond(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_message = update.message.text # type: ignore
        memory = read_memory() #Reads the bot's memory. This memory stores important information only.
        conversation = read_conversation(30) #Reads the recent conversation history to provide context for the AI's response
        contents=[types.Content(role=msg["role"], parts=[types.Part(text=msg["parts"][0])]) for msg in conversation] #Converts the conversation history into the correct format for Gemini API
        browser_url = t.browser_current_url() #Grounds the model in the browser's actual current page, regardless of what past conversation text says
        now = datetime.now().astimezone().isoformat() #Grounds the model in the current date/time for resolving relative dates (e.g. calendar events)
        chat = client.chats.create(
                model="gemini-3.1-flash-lite",
                history=contents, #type: ignore
                config=types.GenerateContentConfig(tools=[tools],
                    system_instruction=build_system_instruction(memory, browser_url, now)
            ),)
        add_to_conversation("user", user_message)#type: ignore #Saves the user's message to the conversation history in the database
        response = chat.send_message(user_message)
        response, give_up = await _run_tool_loop(chat, response) #Executes any tool calls the model requested
        final_text = _finalize_reply(response, give_up)
        add_to_conversation("model", final_text) #Saves the AI's response to the conversation history in the database
        await update.message.reply_text(final_text) #Sends the AI's response back to the user on Telegram
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
   

   
    
   
async def clear(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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