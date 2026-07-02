"""Unit tests for the pure helper functions - the command guardrails in tools.py and the
reply-handling helpers in main.py. Run from the project root with:

    python -m unittest test_helpers -v

Importing main requires the .env to be present (the bot refuses to start without its keys).
No network calls are made and no Telegram/Gemini traffic is generated.
"""
import unittest

from tools import _is_blocked, _download_command_redirect
from main import _chunk_message, INVALID_REPLY_PATTERN, TELEGRAM_MAX_MESSAGE_CHARS


class TestBlockedCommands(unittest.TestCase):
    def test_blocks_destructive_commands(self):
        for cmd in [
            "format c:",
            "FORMAT D:",
            "diskpart",
            "mkfs.ext4 /dev/sda1",
            "rm -rf /",
            "sudo rm -rf / --no-preserve-root",
            "shutdown /s /t 0",
            "reboot",
            "reg delete HKLM\\SYSTEM /f",
            ":(){ :|:& };:",  # fork bomb
        ]:
            self.assertIsNotNone(_is_blocked(cmd), f"should be blocked: {cmd}")

    def test_allows_normal_commands(self):
        for cmd in [
            "pip install requests",
            "npm run build",
            "npm run restart",          # regression: bare 'restart' used to false-positive
            "docker restart mycontainer",
            "systemctl restart nginx",
            "rm -rf ./build",           # deleting a local folder is not wiping root
            "echo hello",
            "python main.py",
        ]:
            self.assertIsNone(_is_blocked(cmd), f"should be allowed: {cmd}")


class TestDownloadRedirect(unittest.TestCase):
    def test_redirects_download_commands(self):
        for cmd in [
            "curl -o server.jar https://example.com/server.jar",
            "curl --output file.zip https://example.com/f.zip",
            "curl -O https://example.com/f.zip --remote-name",
            "wget https://example.com/file.tar.gz",
            'Invoke-WebRequest -Uri "https://x.com/f.exe" -OutFile "f.exe"',
            "iwr https://x.com/f.msi -OutFile f.msi",
        ]:
            self.assertIsNotNone(_download_command_redirect(cmd), f"should redirect: {cmd}")

    def test_leaves_non_download_commands_alone(self):
        for cmd in [
            "curl https://api.github.com/repos/x/y/releases/latest",  # API call, no output flag
            "git clone https://github.com/x/y.git",
            "pip install requests",
            "echo wget-like behavior",  # mentions wget but isn't the command
            "pip install wget",         # installing the wget *package* is not a download
        ]:
            self.assertIsNone(_download_command_redirect(cmd), f"should be left alone: {cmd}")


class TestChunkMessage(unittest.TestCase):
    def test_empty_and_short(self):
        self.assertEqual(_chunk_message(""), [""])
        self.assertEqual(_chunk_message("hi"), ["hi"])

    def test_exact_limit_is_one_chunk(self):
        text = "a" * TELEGRAM_MAX_MESSAGE_CHARS
        self.assertEqual(_chunk_message(text), [text])

    def test_over_limit_splits_and_reassembles(self):
        text = "a" * (TELEGRAM_MAX_MESSAGE_CHARS + 1)
        chunks = _chunk_message(text)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(len(c) <= TELEGRAM_MAX_MESSAGE_CHARS for c in chunks))
        self.assertEqual("".join(chunks), text)


class TestInvalidReplyPattern(unittest.TestCase):
    def test_flags_raw_tool_output(self):
        for text in [
            "[12] a: 'Click here' at (100, 200)",     # raw element-map line
            'Click <a href="x" target="_blank">here</a>',  # pasted HTML
            "Read more: https://news.site/story?utm_source=newsletter",  # tracking URL
        ]:
            self.assertIsNotNone(INVALID_REPLY_PATTERN.search(text), f"should be flagged: {text!r}")

    def test_allows_normal_replies(self):
        for text in [
            "Done! I downloaded the file to your Desktop.",
            "The price is [1] dollars according to the site.",  # brackets without the map format
            "Here's the link: https://example.com/page",        # clean URL, no tracking params
        ]:
            self.assertIsNone(INVALID_REPLY_PATTERN.search(text), f"should be allowed: {text!r}")


if __name__ == "__main__":
    unittest.main()
