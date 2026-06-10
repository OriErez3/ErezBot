import logging
import subprocess
from database import add_to_memory
from database import read_memory as read_memory_db
import sqlite3
import os
import shutil
from dotenv import load_dotenv
from tavily import TavilyClient
from playwright.async_api import (
    async_playwright,
    Browser,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
)
import base64
from PIL import Image, ImageDraw
import io
from typing import Optional, Union

load_dotenv()
logger = logging.getLogger(__name__)
tav_key = os.getenv("TAVILY_KEY")
conn = sqlite3.connect("memory.db")
cursor = conn.cursor()
tav_client = TavilyClient(tav_key)

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

def save_memory(key: str, value: str) -> str:
    add_to_memory(key, value)
    return f"Memory saved: {key} = {value}"

def delete_memory(key: str) -> str:
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
        logger.debug("Listing: %s (exists: %s)", path, os.path.exists(path))
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


# Browser things

def _normalize_url(url: str) -> str:
    return url.strip().rstrip('/')

class BrowserSession:
    """Encapsulates a single Playwright browser/page and the element index cache for it."""

    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.elements_cache: dict[int, dict] = {}

    async def _ensure_page(self) -> Page:
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self.page = await self._browser.new_page(viewport={"width": 1280, "height": 720})
        assert self.page is not None
        return self.page

    def _invalidate_elements_cache(self) -> None:
        # The DOM/layout may have changed, so cached element positions can no longer be trusted.
        self.elements_cache.clear()

    async def _screenshot_b64(self) -> str:
        assert self.page is not None
        screenshot = await self.page.screenshot()
        return base64.b64encode(screenshot).decode("utf-8")

    async def _settle(self) -> None:
        # Give navigations triggered by the action time to finish, plus a short
        # grace period for JS-driven UI updates, before screenshotting.
        assert self.page is not None
        try:
            await self.page.wait_for_load_state("load", timeout=3000)
        except PlaywrightTimeoutError:
            pass
        await self.page.wait_for_timeout(300)

    async def navigate(self, url: str) -> Union[str, tuple[str, str]]:
        try:
            page = await self._ensure_page()
            if _normalize_url(url) == _normalize_url(page.url):
                return await self._screenshot_b64(), "Already on this page - navigation skipped to avoid losing progress."
            await page.goto(url)
            self._invalidate_elements_cache()
            await self._settle()
            return await self._screenshot_b64()
        except Exception as e:
            return f"Error: {e}"

    def get_current_url(self) -> str:
        return self.page.url if self.page else "No page open"

    async def screenshot(self) -> str:
        if self.page is None:
            return "Error: No browser open. Use browser_navigate first."
        try:
            return await self._screenshot_b64()
        except Exception as e:
            return f"Error: {e}"

    async def get_elements(self, screenshot: bool = False) -> Union[str, tuple[str, str]]:
        if self.page is None:
            return "Error: No browser open. Use browser_navigate first."
        try:
            # Query DOM
            elements = await self.page.evaluate("""
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
            self.elements_cache.clear()
            for el in elements:
                self.elements_cache[el['index']] = el
            # Build element map
            element_map = "\n".join([
                f"[{el['index']}] {el['tag']}: '{el['text']}' at ({el['x']:.0f}, {el['y']:.0f})"
                for el in elements
            ])

            if not screenshot:
                return element_map

            # Take and annotate screenshot
            shot = await self.page.screenshot()
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

    async def click_element(self, index: int) -> str:
        if self.page is None:
            return "Error: No browser open."
        try:
            el = self.elements_cache.get(index)
            logger.debug("Clicking element %s: %s", index, el)
            if el is None:
                return "Error: Element not found. Run browser_get_elements first."

            x = el['x'] + el['width'] / 2
            y = el['y'] + el['height'] / 2
            await self.page.mouse.click(x, y)
            self._invalidate_elements_cache()
            await self._settle()
            return await self._screenshot_b64()
        except Exception as e:
            return f"Error: {e}"

    async def click(self, x: int, y: int) -> str:
        if self.page is None:
            return "Error: no browser is open. Use browser_navigate to open it."
        try:
            await self.page.mouse.click(x, y)
            self._invalidate_elements_cache()
            await self._settle()
            return await self._screenshot_b64()
        except Exception as e:
            return f"Error: {e}"

    async def type_text(self, text: str, press_enter: bool = False) -> str:
        if self.page is None:
            return "Error: no browser is open. Use browser_navigate to open it."
        try:
            await self.page.keyboard.type(text)
            if press_enter:
                await self.page.keyboard.press("Enter")
            self._invalidate_elements_cache()
            await self._settle()
            return await self._screenshot_b64()
        except Exception as e:
            return f"Error: {e}"

    async def scroll(self, direction: str, amount: int = 300) -> str:
        if self.page is None:
            return "Error: No browser open. Use browser_navigate first."
        try:
            if direction == "down":
                await self.page.mouse.wheel(0, amount)
            elif direction == "up":
                await self.page.mouse.wheel(0, -amount)
            self._invalidate_elements_cache()
            await self._settle()
            return await self._screenshot_b64()
        except Exception as e:
            return f"Error: {e}"

    async def go_back(self) -> str:
        if self.page is None:
            return "Error: No browser open."
        try:
            await self.page.go_back()
            self._invalidate_elements_cache()
            await self._settle()
            return await self._screenshot_b64()
        except Exception as e:
            return f"Error: {e}"


_browser_session = BrowserSession()

async def browser_navigate(url: str) -> Union[str, tuple[str, str]]:
    return await _browser_session.navigate(url)

def browser_current_url() -> str:
    return _browser_session.get_current_url()

async def browser_screenshot() -> str:
    return await _browser_session.screenshot()

async def browser_get_elements(screenshot: bool = False) -> Union[str, tuple[str, str]]:
    return await _browser_session.get_elements(screenshot)

async def browser_click_element(index: int) -> str:
    return await _browser_session.click_element(index)

async def browser_click(x: int, y: int) -> str:
    return await _browser_session.click(x, y)

async def browser_type(text: str, press_enter: bool = False) -> str:
    return await _browser_session.type_text(text, press_enter)

async def browser_scroll(direction: str, amount: int = 300) -> str:
    return await _browser_session.scroll(direction, amount)

async def browser_go_back() -> str:
    return await _browser_session.go_back()
