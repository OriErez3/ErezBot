import string
import subprocess
from database import add_to_memory
from database import read_memory as read_memory_db
import sqlite3
import os 
import shutil
from dotenv import load_dotenv
from tavily import TavilyClient
from playwright.async_api import async_playwright
import base64
from PIL import Image, ImageDraw, ImageFont
import io
load_dotenv()
tav_key = os.getenv("TAVILY_KEY")
conn = sqlite3.connect("memory.db")
cursor = conn.cursor()
tav_client = TavilyClient(tav_key)
elements_cache = {}
def run_shell(command: str) -> str:
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True,
            encoding="utf-8",
            errors="replace"  # replaces undecodable characters instead of crashing
        )
        return result.stdout + result.stderr
    except Exception as e:
        return f"Error: {e}"

def save_memory(key: str, value: str):
    add_to_memory(key, value)
    return f"Memory saved: {key} = {value}"

def delete_memory(key: str):
    cursor.execute('''SELECT key FROM memory WHERE key = ?''', (key,))
    if cursor.fetchone():
        cursor.execute('''DELETE FROM memory WHERE key = ?''', (key,))
        conn.commit()
        return f"Memory deleted: {key}"
    return f"Memory not found: {key}"
def read_memory() -> str:
    try:
        memory = read_memory_db()  # your existing db function
        if not memory:
            return "No memories saved."
        return memory
    except Exception as e:
        return f"Error: {e}"


def list_directory(path: str = ".") -> str:
    try:
        # normalize the path so forward and back slashes both work
        path = os.path.normpath(path)
        print(f"Listing: {path}")
        print(f"Exists: {os.path.exists(path)}")
        if not os.path.exists(path):
            return f"Path does not exist: {path}"
        if not os.path.isdir(path):
            return f"{path} is a file, not a directory"
        files = os.listdir(path)
        if not files:
            return f"Directory is empty: {path}"
        return "\n".join(files)
    except Exception as e:
        return f"Error: {e}"

def read_file(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
            return content
    except Exception as e:
        return f"Error: {e}"

def write_file(path: str, content: str, binary: bool = False) -> str:
    try:
        if binary:
            with open(path, "wb") as f:
                f.write(base64.b64decode(content))
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        return "Successfully written!"
    except Exception as e:
        return f"Error: {e}"



def find_file(filename: str) -> str:
    import os
    search_paths = [
        os.path.expanduser("~"),  # home directory
        os.path.expanduser("~/Desktop"),
        os.path.expanduser("~/Documents"),
        os.path.expanduser("~/Downloads"),
    ]
    
    matches = []
    for path in search_paths:
        if os.path.exists(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    if filename.lower() in file.lower():
                        matches.append(os.path.join(root, file))
    
    return "\n".join(matches) if matches else "No files found"

def move_file(source: str, destination: str) -> str:
    try:
        shutil.move(source,destination)
        return(f"{source} moved to {destination}")
    except Exception as e:
        return f"Error: {e}"

def web_search(query: str) -> str:
    try:
        response = tav_client.search(query=query, max_results=5, include_answer=True)
        answer = response.get("answer", "")
        results = "\n\n".join(
            f"Title: {r['title']}\nURL: {r['url']}\nContent: {r['content']}"
            for r in response["results"]
        )
        if answer:
            return f"Direct answer: {answer}\n\nSources:\n{results}"
        return f"Sources:\n{results}"
    except Exception as e:
        return f"Error: {e}"
    
#Browser things
playwright_instance = None
browser_instance = None
page_instance = None
current_url = ""

async def browser_navigate(url: str) -> str:
    global playwright_instance,browser_instance, page_instance, current_url
    try:
        if browser_instance is None:
            playwright_instance = await async_playwright().start()
            browser_instance = await playwright_instance.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
            page_instance = await browser_instance.new_page(viewport={"width": 1280, "height": 720})
        await page_instance.goto(url)
        current_url = page_instance.url
        screenshot = await page_instance.screenshot()
        return base64.b64encode(screenshot).decode("utf-8")
    except Exception as e:
        return f"Error: {e}"
def browser_current_url() -> str:
    return current_url if current_url else "No page open"

async def browser_screenshot() -> str:
    global page_instance
    try:
        if page_instance is None:
            return "Error: No browser open. Use browser_navigate first."
        screenshot = await page_instance.screenshot()
        return base64.b64encode(screenshot).decode("utf-8")
    except Exception as e:
        return f"Error: {e}"

async def browser_get_elements(screenshot: bool = False):
    global page_instance
    try:
        if page_instance is None:
            return "Error: No browser open. Use browser_navigate first."
        
        # Query DOM
        elements = await page_instance.evaluate("""
            () => {
                const selectors = 'a, button, input, select, textarea, [role=button], [role=link], [onclick]';
                const els = document.querySelectorAll(selectors);
                return Array.from(els).map((el, i) => {
                    const rect = el.getBoundingClientRect();
                    return {
                        index: i + 1,
                        tag: el.tagName.toLowerCase(),
                        text: (el.innerText || el.value || el.placeholder || el.ariaLabel || '').slice(0, 30).trim(),
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    };
                }).filter(el => el.width > 0 && el.height > 0 && el.y >= 0);
            }
        """)
        elements_cache.clear()
        for el in elements:
            elements_cache[el['index']] = el
        # Build element map
        element_map = "\n".join([
            f"[{el['index']}] {el['tag']}: '{el['text']}' at ({el['x']:.0f}, {el['y']:.0f})"
            for el in elements
        ])
        
        if not screenshot:
            return element_map
        
        # Take and annotate screenshot
        shot = await page_instance.screenshot()
        img = Image.open(io.BytesIO(shot))
        draw = ImageDraw.Draw(img)
        
        for el in elements:
            x, y, w, h = el['x'], el['y'], el['width'], el['height']
            draw.rectangle([x, y, x+w, y+h], outline="red", width=2)
            draw.rectangle([x, y-15, x+25, y], fill="red")
            draw.text((x+2, y-14), str(el['index']), fill="white")
        
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        
        return image_b64, element_map
        
    except Exception as e:
        return f"Error: {e}"

async def browser_click_element(index: int) -> str:
    global page_instance, elements_cache
    try:
        if page_instance is None:
            return "Error: No browser open."
        
        el = elements_cache.get(index)
        print(f"Clicking element {index}: {el}")
        if el is None:
            return "Error: Element not found. Run browser_get_elements first."
        
        x = el['x'] + el['width'] / 2
        y = el['y'] + el['height'] / 2
        await page_instance.mouse.click(x, y)
        screenshot = await page_instance.screenshot()
        return base64.b64encode(screenshot).decode("utf-8")
    except Exception as e:
        return f"Error: {e}"

async def browser_click(x: int, y:int) -> str:
    global page_instance
    try:
        if page_instance is None:
            return "Error: no browser is open. Use browser_navigate to open it."
        await page_instance.mouse.click(x,y)
        screenshot = await page_instance.screenshot()
        return base64.b64encode(screenshot).decode("utf-8")
    except Exception as e:
        return f"Error: {e}"
     
async def browser_type(text: str, press_enter: bool = False) -> str:
    global page_instance
    try:
        if page_instance is None:
            return "Error: no browser is open. Use browser_navigate to open it."
        await page_instance.keyboard.type(text)
        if press_enter:
            await page_instance.keyboard.press("Enter")
        screenshot = await page_instance.screenshot()
        return base64.b64encode(screenshot).decode("utf-8")
    except Exception as e:
        return f"Error: {e}"

async def browser_scroll(direction: str, amount: int = 300) -> str:
    global page_instance
    try:
        if page_instance is None:
            return "Error: No browser open. Use browser_navigate first."
        if direction == "down":
            await page_instance.mouse.wheel(0, amount)
        elif direction == "up":
            await page_instance.mouse.wheel(0, -amount)
        screenshot = await page_instance.screenshot()
        return base64.b64encode(screenshot).decode("utf-8")
    except Exception as e:
        return f"Error: {e}"

async def browser_go_back():
    global page_instance
    try:
        if page_instance is None:
            return "Error: No browser open."
        await page_instance.go_back()
        screenshot = await page_instance.screenshot()
        return base64.b64encode(screenshot).decode("utf-8")
    except Exception as e:
        return f"Error: {e}"
    
