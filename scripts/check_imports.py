import sys
print(f"Python: {sys.version}")

errors = []

try:
    import PyQt6
    from PyQt6.QtWidgets import QApplication
    print("OK: PyQt6")
except Exception as e:
    errors.append(f"PyQt6: {e}")

try:
    import playwright
    from playwright.async_api import async_playwright
    print("OK: playwright")
except Exception as e:
    errors.append(f"playwright: {e}")

try:
    from playwright_stealth import Stealth
    _s = Stealth()
    print("OK: playwright_stealth")
except Exception as e:
    errors.append(f"playwright_stealth: {e}")

try:
    import markdown
    print("OK: markdown")
except Exception as e:
    errors.append(f"markdown: {e}")

try:
    import qasync
    print("OK: qasync")
except Exception as e:
    errors.append(f"qasync: {e}")

# Test core imports
try:
    from core.browser import BrowserManager, get_profile_path
    print("OK: core.browser")
except Exception as e:
    errors.append(f"core.browser: {e}")

try:
    from core.base_bot import BaseBot
    print("OK: core.base_bot")
except Exception as e:
    errors.append(f"core.base_bot: {e}")

try:
    from core.bots.gemini import GeminiBot
    from core.bots.chatgpt import ChatGPTBot
    from core.bots.claude import ClaudeBot
    from core.bots.copilot import CopilotBot
    print("OK: all bots")
except Exception as e:
    errors.append(f"bots: {e}")

try:
    from gui.chat_widget import ChatWidget
    from gui.sidebar import Sidebar
    from gui.login_window import LoginWindow
    from gui.main_window import MainWindow
    print("OK: all GUI modules")
except Exception as e:
    errors.append(f"gui: {e}")

print()
if errors:
    print("ERRORS:")
    for err in errors:
        print(f"  - {err}")
    sys.exit(1)
else:
    print("All checks passed! Run: python main.py")
