import telegram
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
import os
import asyncio
from google import genai
from google.genai import errors, types
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
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
#Loads the environment variables for the APIs
telegram_key = os.getenv("TELEGRAM_TOKEN")
gemini_key = os.getenv("GEMINI_API_KEY")
allowed_user_id = os.getenv("ALLOWED_USER_ID")
if telegram_key is None:
    raise ValueError("TELEGRAM_TOKEN environment variable is required")
if gemini_key is None:
    raise ValueError("GEMINI_API_KEY environment variable is required")
if allowed_user_id is None:
    raise ValueError("ALLOWED_USER_ID environment variable is required - the bot has shell access, so it must only answer you. Set it to your Telegram user id.")
ALLOWED_USER_ID = int(allowed_user_id)

client = genai.Client(api_key=gemini_key)

os_name = platform.system()
#Tool declarations are generated from the functions in tool_dict below: the signature
#(parameter names, type hints, defaults) becomes the schema and the docstring becomes
#the description the model reads. To add a tool, write the function and register it here.
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
    "gmail_mark_as_read": gs.gmail_mark_as_read,
    "calendar_list_events": gs.calendar_list_events,
    "calendar_create_event": gs.calendar_create_event,
    "drive_list_files": gs.drive_list_files,
    "drive_read_file": gs.drive_read_file,
    "drive_upload_file": gs.drive_upload_file,
    "schedule_task": t.schedule_task,
    "run_background": t.run_background,
    "read_process_output": t.read_process_output,
    "list_processes": t.list_processes,
    "stop_process": t.stop_process,
}

tools = types.Tool(
    function_declarations=[
        types.FunctionDeclaration.from_callable(client=client, callable=fn)
        for fn in tool_dict.values()
    ]
)

#Test to make sure everything is working
async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text("Hello! I'm your Google AI assistant.")
def build_system_instruction(memory: str, browser_url: str, now: str, persist_mode: bool = False, tool_log: str = "") -> str:
    cwd = os.getcwd()
    instruction = f"""You are a personal AI assistant. Be helpful and concise.

System info:
- OS: {os_name}
- Current date/time: {now}
- Bot working directory: {cwd} (this is where the bot itself lives — NOT where user files should go)

Saved memory about the user:
{memory}

Browser state:
- Current browser page: {browser_url}
- This reflects reality right now, even if earlier conversation mentions a different page. Trust this over anything you previously said about the browser.

Tool rules:
- Use save_memory for important user facts, delete_memory when outdated, read_memory to recall facts
- Use write_file, read_file, list_directory for file operations. Only use run_shell when explicitly asked
- File paths: always use absolute paths (e.g. C:\\Users\\orier\\Desktop\\project). Never use relative paths or write files into the bot working directory unless the user explicitly asks to
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
    if persist_mode:
        instruction += "\n- PERSISTENT MODE IS ON: do not give up, ask the user for help, or stop early. Keep trying different approaches until the task is fully complete. Only stop if you hit an unrecoverable API error."
    if tool_log:
        instruction += f"\n\nRecent tool calls in this conversation:\n{tool_log}"
    return instruction
#Function to handle messages. Used the most often.

screenshot_tools = {"browser_navigate", "browser_screenshot", "browser_click", "browser_type", "browser_scroll", "browser_click_element", "browser_go_back"}
#Tools where repeating the exact same call is legitimate - observing state again (the page
#or inbox may have changed) or paging through content (scroll). These skip the duplicate
#check; the iteration cap still limits them. Action tools (write_file, gmail_send_email,
#browser_click...) keep the strict check - repeating those identically means a stuck loop.
duplicate_exempt_tools = {"browser_screenshot", "browser_get_elements", "browser_current_url", "browser_scroll", "read_memory", "read_file", "list_directory", "gmail_list_messages", "gmail_read_message", "calendar_list_events", "drive_list_files", "drive_read_file"}
MAX_TOOL_ITERATIONS = 20
PERSIST_MAX_TOOL_ITERATIONS = 100
TELEGRAM_MAX_MESSAGE_CHARS = 4000 #Telegram rejects messages over 4096 chars - leave headroom
KEEP_RECENT_SCREENSHOTS = 2
PERSIST_MODE = False
CHECKIN_INTERVAL_MINUTES = 60
CHECKIN_PROMPT = (
    "[Automated periodic check-in] Use gmail_list_messages with query 'is:unread' to check for "
    "important new emails, and calendar_list_events to check for events starting soon. Compare "
    "against what you've already told the user in the recent conversation above - do not repeat "
    "something you already flagged unless there's new or materially changed information (e.g. "
    "an event is now starting much sooner, or a new reply came in). If there's something worth "
    "telling the user, reply with a short message for them, and call gmail_mark_as_read on each "
    "email you report. If there's nothing new and noteworthy, reply with exactly: "
    "NOTHING_TO_REPORT"
)
SCHEDULED_TASK_PROMPT = (
    "[Scheduled task] The user previously asked you to do the following at this exact time. "
    "It is pre-approved - complete it now using your tools without asking for confirmation, "
    "then briefly tell the user what you did.\n\nTask: {task}"
)
SCHEDULED_TASK_POLL_SECONDS = 30
# Matches raw element-map lines (e.g. "[12] a: 'text' at (100, 200)") or pasted-HTML fragments
INVALID_REPLY_PATTERN = re.compile(r"^\[\d+\]\s+\w+:|target=\"_blank\"|utm_source=")

def _validate_tool_registrations() -> None:
    #Declarations are generated from tool_dict, so they can't drift apart anymore - the
    #one desync still possible is a dict key not matching its function's actual name
    #(the model calls tools by declaration name, which from_callable takes from __name__)
    mismatched = {name for name, fn in tool_dict.items() if fn.__name__ != name}
    if mismatched:
        raise RuntimeError(f"tool_dict keys don't match their function names: {mismatched}")
    registered = set(tool_dict)
    if not screenshot_tools <= registered:
        raise RuntimeError(f"screenshot_tools has unknown tools: {screenshot_tools - registered}")
    if not duplicate_exempt_tools <= registered:
        raise RuntimeError(f"duplicate_exempt_tools has unknown tools: {duplicate_exempt_tools - registered}")

_validate_tool_registrations()

async def _execute_tool(tool_name: str, args: dict) -> Any:
    """Looks up and runs a tool by name, returning its result (or an error string)."""
    if tool_name not in tool_dict:
        return f'Tool: {tool_name} not found'
    try:
        if inspect.iscoroutinefunction(tool_dict[tool_name]):
            return await tool_dict[tool_name](**args)
        return await asyncio.to_thread(tool_dict[tool_name], **args) #Sync tools run in a worker thread so they don't block the event loop
    except Exception as e:
        result = f"Error executing {tool_name}: {e}"
        logger.warning(result)
        return result

def _tool_result_parts(func: Any, tool_name: str, result: Any) -> list:
    """Builds the message parts for one tool's result, attaching an image part if the
    result includes a screenshot. Sending happens once per batch in _run_tool_loop."""
    if isinstance(result, tuple):
        # Has both image and element map
        image_b64, element_map = result
        image_bytes = base64.b64decode(image_b64)
        return [
            types.Part(
                function_response=types.FunctionResponse(
                    name=tool_name,
                    id=func.id,
                    response={"result": element_map}
                )
            ),
            types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        ]
    if tool_name in screenshot_tools and not result.startswith("Error"):
        image_bytes = base64.b64decode(result)
        return [
            types.Part(
                function_response=types.FunctionResponse(
                    name=tool_name,
                    id=func.id,
                    response={"result": "Screenshot taken successfully"}
                )
            ),
            types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        ]
    return [types.Part(
        function_response=types.FunctionResponse(
            name=tool_name,
            id=func.id,
            response={"result": result}
        )
    )]

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

_TOOL_STATUS: dict[str, str] = {
    "run_shell":             "Running a command...",
    "run_background":        "Starting a background process...",
    "read_process_output":   "Reading process output...",
    "stop_process":          "Stopping a process...",
    "list_processes":        "Listing processes...",
    "write_file":            "Writing a file...",
    "read_file":             "Reading a file...",
    "list_directory":        "Listing files...",
    "find_file":             "Searching for a file...",
    "move_file":             "Moving a file...",
    "web_search":            "Searching the web...",
    "browser_navigate":      "Browsing the web...",
    "browser_screenshot":    "Taking a screenshot...",
    "browser_click":         "Clicking...",
    "browser_click_element": "Clicking...",
    "browser_type":          "Typing in browser...",
    "browser_scroll":        "Scrolling...",
    "browser_get_elements":  "Reading the page...",
    "browser_go_back":       "Going back...",
    "gmail_list_messages":   "Checking email...",
    "gmail_read_message":    "Reading an email...",
    "gmail_send_email":      "Sending an email...",
    "gmail_mark_as_read":    "Marking email as read...",
    "calendar_list_events":  "Checking calendar...",
    "calendar_create_event": "Creating a calendar event...",
    "drive_list_files":      "Listing Drive files...",
    "drive_read_file":       "Reading a Drive file...",
    "drive_upload_file":     "Uploading to Drive...",
    "save_memory":           "Saving to memory...",
    "read_memory":           "Reading memory...",
    "schedule_task":         "Scheduling a task...",
}

async def _keep_typing(bot: Any, chat_id: int, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            pass

async def _run_tool_loop(chat: Any, response: Any, persist_mode: bool = False, status_callback: Any = None, conversation_id: int = 0) -> tuple[Any, bool]:
    """Repeatedly executes tool calls requested by the model until it stops calling tools,
    a duplicate call is detected, or the iteration cap is exceeded. Returns the final
    response and whether the loop gave up early.

    In persist_mode, duplicate calls no longer trigger a give-up - the model is told to try a
    different approach and keeps going - and the iteration cap is raised to
    PERSIST_MAX_TOOL_ITERATIONS as a safety net instead of MAX_TOOL_ITERATIONS."""
    seen_calls = set()
    give_up = False
    iteration_count = 0
    max_iterations = PERSIST_MAX_TOOL_ITERATIONS if persist_mode else MAX_TOOL_ITERATIONS
    while response.function_calls and not give_up: #Checks if the AI called any tools in its response
        #Execute every call in this response first, collect all the results, then answer
        #them in ONE message - the API requires a response for each call in the turn, and
        #sending mid-batch would generate a new model response while we're still iterating
        #over the old one
        parts = []
        stop_executing = False #Set when the cap/duplicate check trips mid-batch; the rest get a skip message
        for func in response.function_calls:
            call_key = f"{func.name}_{func.args}"
            tool_name = func.name
            logger.debug("Tool call: %s", tool_name)

            iteration_count += 1
            if stop_executing:
                result = "Skipped - stopping tool use now."
            elif iteration_count > max_iterations:
                result = "You've taken too many actions on this task. Stop here and respond to the user now, summarizing what you've done so far and what's left."
                give_up = True
                stop_executing = True
            elif call_key in seen_calls and tool_name not in duplicate_exempt_tools:
                if persist_mode:
                    result = "You've already tried that exact call. Try a different approach instead of repeating it."
                else:
                    result = "This approach isn't working. Tell the user you're unable to complete the task and ask them for more information."
                    give_up = True
                    stop_executing = True
            else:
                seen_calls.add(call_key)
                if status_callback:
                    try:
                        await status_callback(_TOOL_STATUS.get(tool_name, f"Using {tool_name}..."))
                    except Exception:
                        pass
                result = await _execute_tool(tool_name, func.args)
                if conversation_id:
                    args_summary = str(dict(func.args))[:150]
                    result_text = result[1] if isinstance(result, tuple) else str(result)
                    add_to_conversation("tool", f"{tool_name}({args_summary}) → {result_text[:200]}", conversation_id)
            parts.extend(_tool_result_parts(func, tool_name, result))
        response = await chat.send_message(parts)
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

async def _generate_response(prompt: str, persist_mode: bool = False, status_callback: Any = None) -> tuple[str, bool]:
    """Builds a chat from the stored conversation history, sends `prompt` to the model, runs the
    tool loop, and returns (final_text, give_up). Does not touch the conversation history table -
    callers decide what (if anything) to record."""
    memory = read_memory() #Reads the bot's memory. This memory stores important information only.
    conversation_id = database.get_active_conversation_id()
    conversation = read_conversation(30, conversation_id) #Reads the recent conversation history to provide context for the AI's response
    contents=[types.Content(role=msg["role"], parts=[types.Part(text=msg["parts"][0])]) for msg in conversation] #Converts the conversation history into the correct format for Gemini API
    browser_url = t.browser_current_url() #Grounds the model in the browser's actual current page, regardless of what past conversation text says
    now = datetime.now().astimezone().isoformat() #Grounds the model in the current date/time for resolving relative dates (e.g. calendar events)
    logs = database.get_tool_logs(conversation_id)
    tool_log = "\n".join(f"- {entry}" for entry in logs)
    chat = client.aio.chats.create( #The async client - same API, but send_message can be awaited so it doesn't block the event loop
            model="gemini-3.1-flash-lite",
            history=contents, #type: ignore
            config=types.GenerateContentConfig(tools=[tools],
                system_instruction=build_system_instruction(memory, browser_url, now, persist_mode, tool_log)
        ),)
    response = await chat.send_message(prompt)
    response, give_up = await _run_tool_loop(chat, response, persist_mode, status_callback, conversation_id) #Executes any tool calls the model requested
    return _finalize_reply(response, give_up), give_up

def _describe_error(e: Exception) -> str:
    """Turns an exception into a friendly user-facing message, using the API's real
    error codes instead of string-matching the error text."""
    if isinstance(e, errors.APIError):
        if e.code == 429:
            return "I've hit my API rate limit. Please wait a moment and try again."
        if e.code == 503:
            return "Gemini is currently unavailable. Please try again in a few minutes."
        if e.code == 400 and "token" in str(e).lower():
            return "The conversation is too long. Try /clear and start fresh."
    return f"Something went wrong: {e}"

def _chunk_message(text: str) -> list:
    """Splits a reply into pieces under Telegram's message length limit - sending one
    oversized message raises BadRequest and the user would get nothing at all."""
    return [text[i:i + TELEGRAM_MAX_MESSAGE_CHARS] for i in range(0, len(text), TELEGRAM_MAX_MESSAGE_CHARS)] or [text]

async def respond(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    #Edited messages, channel posts, reactions etc. arrive with message=None - nothing to respond to
    if update.message is None or update.message.text is None or update.effective_chat is None:
        return
    int_chat_id = update.effective_chat.id
    status_msg = await context.bot.send_message(chat_id=int_chat_id, text="Thinking...")
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(context.bot, int_chat_id, stop_typing))

    async def on_status(text: str) -> None:
        try:
            await status_msg.edit_text(text)
        except Exception:
            pass

    try:
        user_message = update.message.text
        chat_id = str(int_chat_id) #Captures where to send proactive/unprompted messages later
        if database.get_setting("chat_id") != chat_id:
            database.set_setting("chat_id", chat_id)
        conversation_id = database.get_active_conversation_id()
        add_to_conversation("user", user_message, conversation_id) #Saves the user's message to the conversation history in the database
        final_text, _ = await _generate_response(user_message, PERSIST_MODE, on_status)
        add_to_conversation("model", final_text, conversation_id) #Saves the AI's response to the conversation history in the database
        for chunk in _chunk_message(final_text): #Sends the AI's response back to the user on Telegram
            await update.message.reply_text(chunk)
    except Exception as e:
        logger.exception("Failed to handle message") #Keep a full traceback in the console, not just the Telegram reply
        await update.message.reply_text(_describe_error(e))
    finally:
        stop_typing.set()
        typing_task.cancel()
        try:
            await status_msg.delete()
        except Exception:
            pass
   

   
    
   
async def clear(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    database.clear_conversation(database.get_active_conversation_id())
    await update.message.reply_text("Conversation cleared!")

async def toggle_persist(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    global PERSIST_MODE
    PERSIST_MODE = not PERSIST_MODE
    if PERSIST_MODE:
        status = "ON - I won't give up on a task until it's done or I hit an API error."
    else:
        status = "OFF."
    await update.message.reply_text(f"Persistent mode is now {status}")

async def new_conversation(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    conv_id = database.create_conversation()
    database.set_active_conversation_id(conv_id)
    await update.message.reply_text(f"Started Conversation {conv_id}. This is now active.")

async def list_conversations_cmd(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    active_id = database.get_active_conversation_id()
    lines = [
        f"{'-> ' if c['id'] == active_id else '   '}{c['id']}. {c['title']}"
        for c in database.list_conversations()
    ]
    await update.message.reply_text("\n".join(lines))

async def switch_conversation(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /switch <number>")
        return
    conv_id = int(context.args[0])
    if not database.conversation_exists(conv_id):
        await update.message.reply_text(f"No Conversation {conv_id}. Use /list to see all conversations.")
        return
    database.set_active_conversation_id(conv_id)
    await update.message.reply_text(f"Switched to Conversation {conv_id}.")

async def rename_conversation_cmd(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if not context.args:
        await update.message.reply_text("Usage: /rename <name>")
        return
    name = " ".join(context.args)
    active_id = database.get_active_conversation_id()
    database.rename_conversation(active_id, name)
    await update.message.reply_text(f"Renamed Conversation {active_id} to '{name}'.")

async def proactive_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodically asks the model to check for anything noteworthy (emails, calendar events,
    etc.) and messages the user unprompted if it finds something worth flagging."""
    chat_id = database.get_setting("chat_id")
    if not chat_id:
        return
    int_chat_id = int(chat_id)
    status_msg = await context.bot.send_message(chat_id=int_chat_id, text="Checking in...")
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(context.bot, int_chat_id, stop_typing))
    try:
        final_text, give_up = await _generate_response(CHECKIN_PROMPT)
    except Exception:
        logger.exception("Proactive check-in failed")
        stop_typing.set()
        typing_task.cancel()
        try:
            await status_msg.delete()
        except Exception:
            pass
        return
    finally:
        stop_typing.set()
        typing_task.cancel()
        try:
            await status_msg.delete()
        except Exception:
            pass
    if give_up or final_text.strip().upper() == "NOTHING_TO_REPORT":
        return
    for chunk in _chunk_message(final_text):
        await context.bot.send_message(chat_id=int_chat_id, text=chunk)
    add_to_conversation("model", final_text, database.get_active_conversation_id())

async def check_scheduled_tasks(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs and clears any scheduled tasks whose due time has passed, using the full tool loop
    so the model can actually act (send emails, create files, etc.), then reports back to the
    user."""
    now_ts = datetime.now().timestamp()
    for task in database.get_due_tasks(now_ts):
        #Mark running instead of deleting up front - if the bot crashes mid-task, the row
        #survives and gets re-queued on the next startup instead of silently vanishing
        database.mark_task_running(task["id"])
        int_chat_id = int(task["chat_id"])
        status_msg = await context.bot.send_message(chat_id=int_chat_id, text="Running scheduled task...")
        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(_keep_typing(context.bot, int_chat_id, stop_typing))
        try:
            final_text, _ = await _generate_response(SCHEDULED_TASK_PROMPT.format(task=task["task"]))
        except Exception:
            logger.exception("Scheduled task failed")
            final_text = f"I tried to run a scheduled task but hit an error: {task['task']}"
        finally:
            stop_typing.set()
            typing_task.cancel()
            try:
                await status_msg.delete()
            except Exception:
                pass
        database.delete_scheduled_task(task["id"])
        for chunk in _chunk_message(final_text):
            await context.bot.send_message(chat_id=int_chat_id, text=chunk)
        add_to_conversation("model", final_text, database.get_active_conversation_id())


async def _post_init(application: Any) -> None:
    await application.bot.set_my_commands([
        telegram.BotCommand("start", "Greet the bot"),
        telegram.BotCommand("clear", "Clear the active conversation's history"),
        telegram.BotCommand("persist", "Toggle persistent mode (don't give up until the task is done)"),
        telegram.BotCommand("new", "Start a new conversation"),
        telegram.BotCommand("list", "List all conversations"),
        telegram.BotCommand("switch", "Switch to a conversation by number"),
        telegram.BotCommand("rename", "Rename the active conversation"),
    ])

def main() -> None:
    requeued = database.reset_running_tasks()
    if requeued:
        logger.warning("Re-queued %d scheduled task(s) interrupted by a previous shutdown", requeued)
    #Only respond to the owner - the bot has shell/email access, so ignore everyone else
    user_filter = filters.User(user_id=ALLOWED_USER_ID)
    application = ApplicationBuilder().token(telegram_key).post_init(_post_init).build() # type: ignore
    application.add_handler(CommandHandler("start", start, filters=user_filter))
    application.add_handler(CommandHandler("clear", clear, filters=user_filter))
    application.add_handler(CommandHandler("persist", toggle_persist, filters=user_filter))
    application.add_handler(CommandHandler("new", new_conversation, filters=user_filter))
    application.add_handler(CommandHandler("list", list_conversations_cmd, filters=user_filter))
    application.add_handler(CommandHandler("switch", switch_conversation, filters=user_filter))
    application.add_handler(CommandHandler("rename", rename_conversation_cmd, filters=user_filter))
    application.job_queue.run_repeating( #type: ignore
        proactive_check,
        interval=CHECKIN_INTERVAL_MINUTES * 60,
        first=CHECKIN_INTERVAL_MINUTES * 60,
    )
    application.job_queue.run_repeating( #type: ignore
        check_scheduled_tasks,
        interval=SCHEDULED_TASK_POLL_SECONDS,
        first=SCHEDULED_TASK_POLL_SECONDS,
    )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & user_filter, respond))
    application.run_polling(allowed_updates=telegram.Update.ALL_TYPES)

if __name__ == "__main__":
    main()