"""Arbo MCP is cut off from all links.

These tests fail the build if anything in the code, the data or the skin
could reach, load or point at something outside this folder.
"""

import ast
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKED_DIRS = ("arbo_mcp", "data", "skin")


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def checked_files():
    for folder in CHECKED_DIRS:
        for dirpath, _, names in os.walk(os.path.join(ROOT, folder)):
            if "__pycache__" in dirpath:
                continue
            for name in names:
                yield os.path.join(dirpath, name)


class NoLinksAnywhere(unittest.TestCase):
    PATTERNS = {
        "web address": re.compile(r"(?:https?|ftp|wss?|file)://|//[a-z0-9-]+\.|\bwww\.", re.I),
        "domain name": re.compile(r"\b[a-z0-9-]+\.(?:com|net|org|io|app|ai|dev|co|gov|us|biz|info|cloud|site)\b", re.I),
        "email address": re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I),
        "IP address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    }

    def test_no_links_in_code_data_or_skin(self):
        for path in checked_files():
            text = read_text(path)
            for label, pattern in self.PATTERNS.items():
                match = pattern.search(text)
                self.assertIsNone(match, f"{label} in {os.path.relpath(path, ROOT)}: {match and match.group(0)}")


class NothingFromOutside(unittest.TestCase):
    def test_python_imports_only_the_standard_library_and_itself(self):
        allowed = set(sys.stdlib_module_names) | {"arbo_mcp"}
        for name in os.listdir(os.path.join(ROOT, "arbo_mcp")):
            if not name.endswith(".py"):
                continue
            tree = ast.parse(read_text(os.path.join(ROOT, "arbo_mcp", name)))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module or ""] if node.level == 0 else []
                else:
                    continue
                for mod in mods:
                    self.assertIn(mod.split(".")[0], allowed, f"{name} imports {mod}")

    def test_skin_loads_only_its_own_files(self):
        skin = os.path.join(ROOT, "skin")
        for name in os.listdir(skin):
            text = read_text(os.path.join(skin, name))
            for ref in re.findall(r'(?:href|src)\s*=\s*"([^"]*)"', text):
                if ref.startswith("#"):
                    continue
                self.assertNotIn("/", ref, f"{name}: {ref} must be a file in this folder")
                self.assertTrue(os.path.exists(os.path.join(skin, ref)), f"{name}: {ref} does not exist")
            for forbidden in ("@import", "url(", "<iframe", "<img", "<object", "<embed", "<form",
                              "fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon",
                              "import(", "localStorage", "sessionStorage", "indexedDB", "navigator."):
                self.assertNotIn(forbidden, text, f"{name} contains {forbidden}")


class SkinWording(unittest.TestCase):
    """The skin follows the brief's language rules."""

    BANNED = [
        r"\bclear\b", r"\bhealthy\b", r"no disease found", r"no hazards", r"\b0 (?:findings|flags|hazards)\b",
        r"someone will call you back", r"\bsuffolk\b", r"\btcia\b", r"looks good", r"\bsafe to (?:climb|fell)\b",
    ]

    def test_no_banned_phrases(self):
        # The screens themselves (HTML and CSS). skin/README.md lists the
        # banned words on purpose, so it is not scanned here.
        skin = os.path.join(ROOT, "skin")
        for name in os.listdir(skin):
            if not name.endswith((".html", ".css")):
                continue
            text = read_text(os.path.join(skin, name))
            for pattern in self.BANNED:
                self.assertIsNone(re.search(pattern, text, re.I), f"{name}: banned phrase {pattern}")

    def test_no_real_names_in_data_or_skin(self):
        for folder in ("data", "skin"):
            for dirpath, _, names in os.walk(os.path.join(ROOT, folder)):
                for name in names:
                    text = read_text(os.path.join(dirpath, name))
                    for real in (r"art-is-tree", r"\bmike\b", r"campbell"):
                        self.assertIsNone(re.search(real, text, re.I), f"{name}: {real}")

    def test_required_safety_wording_is_present(self):
        text = read_text(os.path.join(ROOT, "skin", "template.html"))
        # Jack's required crew banner (brief DB-35), word for word.
        self.assertIn("Arbo paused, hand work allowed, fixed limits still apply "
                      "(power-line distance, aloft rules), log it afterward.", text)
        self.assertIn("Call 911 now", text)
        self.assertIn("Can't confirm, don't dig.", text)
        self.assertIn("Unknown: counts as aloft", text)
        # No time limits on the owner's decisions (Mike, Sep 26, 2026).
        self.assertIn("No time limit", text)
        for timer in ("countdown", "counts as no", "expires"):
            self.assertNotIn(timer, text.lower())
        self.assertIsNone(re.search(r">\s*\d{1,2}:\d{2}\s*left", text))
        # The 911 banner comes before every other banner.
        self.assertLess(text.index("banner-emergency\""), text.index("banner-paused\""))
