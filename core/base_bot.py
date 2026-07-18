"""
Clase base abstracta para todos los bots de chatbot.
Cada bot mantiene su propio ProactorEventLoop persistente para que
Playwright siempre opere en el mismo loop donde creó el browser/page.
"""
import asyncio
import sys
import threading
from abc import ABC, abstractmethod
from typing import Callable, Optional
from playwright.async_api import Page
from core.browser import BrowserManager, profile_exists, clear_profile


def _minimize_chrome_window():
    """
    Minimiza todas las ventanas de Chrome/Chromium visibles en Windows.
    Usa ctypes (sin dependencias extra).
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        import ctypes.wintypes

        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        SW_HIDE = 0  # Oculta completamente: no aparece en barra de tareas ni Alt+Tab
        windows_to_minimize = []

        def enum_callback(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            if cls_buf.value == "Chrome_WidgetWin_1":
                windows_to_minimize.append(hwnd)
            return True

        cb = WNDENUMPROC(enum_callback)
        user32.EnumWindows(cb, 0)
        for hwnd in windows_to_minimize:
            user32.ShowWindow(hwnd, SW_HIDE)
            print(f"[Browser] Ventana Chrome ocultada (hwnd={hwnd})", flush=True)
    except Exception as e:
        print(f"[Browser] No se pudo minimizar Chrome: {e}", flush=True)


class BaseBot(ABC):
    """
    Clase abstracta base para todos los bots.

    IMPORTANTE — Loop persistente:
    Cada instancia mantiene su propio asyncio event loop (ProactorEventLoop en Windows).
    Todos los métodos async DEBEN ejecutarse en self._loop mediante self.run(coro).
    Esto garantiza que Playwright siempre opera en el mismo loop donde creó el browser.
    """

    BOT_NAME: str = ""
    DISPLAY_NAME: str = ""
    URL: str = ""
    LOGIN_URL: str = ""
    ICON: str = ""
    COLOR: str = "#FFFFFF"
    MODELS: dict = {}  # {"Nombre visible": "id_interno"}

    def __init__(self):
        self._browser_manager: Optional[BrowserManager] = None
        self._page: Optional[Page] = None
        self._is_ready: bool = False
        self._current_model: str | None = None
        self._on_message_callback: Optional[Callable[[str], None]] = None
        self._on_error_callback: Optional[Callable[[str], None]] = None
        self._on_status_callback: Optional[Callable[[str], None]] = None
        self._lock = threading.Lock()

        # Crear loop persistente para este bot
        if sys.platform == "win32":
            self._loop = asyncio.ProactorEventLoop()
        else:
            self._loop = asyncio.new_event_loop()

    # ─── Runner ──────────────────────────────────────────────────────────────

    def run(self, coro):
        """
        Ejecuta una coroutine en el loop persistente del bot.
        Thread-safe via lock para evitar llamadas concurrentes.
        """
        with self._lock:
            return self._loop.run_until_complete(coro)

    # ─── Callbacks ───────────────────────────────────────────────────────────

    def set_on_message(self, callback: Callable[[str], None]):
        self._on_message_callback = callback

    def set_on_error(self, callback: Callable[[str], None]):
        self._on_error_callback = callback

    def set_on_status(self, callback: Callable[[str], None]):
        self._on_status_callback = callback

    def _emit_message(self, message: str):
        if self._on_message_callback:
            self._on_message_callback(message)

    def _emit_error(self, error: str):
        if self._on_error_callback:
            self._on_error_callback(error)

    def _emit_status(self, status: str):
        if self._on_status_callback:
            self._on_status_callback(status)

    # ─── Gestión de sesión ────────────────────────────────────────────────────

    def has_session(self) -> bool:
        return profile_exists(self.BOT_NAME)

    def clear_session(self):
        clear_profile(self.BOT_NAME)
        self._is_ready = False

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    def get_current_url(self) -> str:
        """Obtiene la URL actual del navegador de forma síncrona."""
        if not self._page:
            return ""
        try:
            return self.run(self._get_current_url_coro())
        except Exception:
            return ""

    async def _get_current_url_coro(self) -> str:
        return self._page.url if self._page else ""

    async def load_session_url(self, url: str) -> bool:
        """Navega a una URL de chat específica del historial."""
        if not self._page or not url:
            return False
        try:
            if self._page.url == url:
                return True
            self._emit_status("Cargando chat...")
            print(f"[{self.DISPLAY_NAME}] Navegando a URL de historial: {url}", flush=True)
            await self._page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(2)
            self._emit_status("Listo")
            return True
        except Exception as e:
            print(f"[{self.DISPLAY_NAME}] Error al navegar a la URL del historial: {e}", flush=True)
            return False

    # ── Modelos ─────────────────────────────────────────────────────────────────

    def get_models(self) -> dict:
        """Retorna el diccionario de modelos disponibles del bot."""
        return self.MODELS

    def get_current_model(self) -> str | None:
        """Retorna el nombre del modelo actualmente seleccionado."""
        return self._current_model

    async def select_model(self, model_name: str) -> bool:
        """
        Selecciona un modelo en la plataforma web.
        Subclases deben sobreescribir para interactuar con el DOM.
        Por defecto solo actualiza el estado local.
        """
        self._current_model = model_name
        print(f"[{self.DISPLAY_NAME}] Modelo seleccionado (base): {model_name}", flush=True)
        return True

    # ── Adjuntar archivos ───────────────────────────────────────────────────────────

    async def _attach_file(self, file_path: str) -> bool:
        """
        Adjunta un archivo al input del chat usando Playwright.
        Intenta múltiples estrategias para encontrar el input de archivo.
        Subclases pueden sobreescribir para implementaciones específicas.
        """
        from pathlib import Path as _Path
        if not _Path(file_path).exists():
            print(f"[{self.DISPLAY_NAME}] Archivo no encontrado: {file_path}", flush=True)
            return False

        try:
            # Estrategia 1: input[type="file"] directo (funciona en muchas plataformas)
            file_inputs = await self._page.query_selector_all('input[type="file"]')
            for fi in file_inputs:
                try:
                    await fi.set_input_files(file_path)
                    print(f"[{self.DISPLAY_NAME}] Archivo adjuntado (input directo): {file_path}", flush=True)
                    await asyncio.sleep(1.5)
                    return True
                except Exception:
                    continue

            # Estrategia 2: buscar botón de adjuntar y esperar file chooser (soporte multilenguaje)
            attach_sels = [
                'button[aria-label*="attach" i]',
                'button[aria-label*="upload" i]',
                'button[aria-label*="file" i]',
                'button[aria-label*="image" i]',
                'button[aria-label*="adjuntar" i]',
                'button[aria-label*="subir" i]',
                'button[aria-label*="archivo" i]',
                'button[aria-label*="imagen" i]',
                'button[title*="attach" i]',
                'button[title*="upload" i]',
                'button[title*="subir" i]',
                'button[title*="adjuntar" i]',
                '[data-tooltip*="attach" i]',
                '[data-tooltip*="upload" i]',
                '[data-tooltip*="subir" i]',
                '[data-tooltip*="adjuntar" i]',
                'label[for*="file"]',
            ]
            for sel in attach_sels:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        async with self._page.expect_file_chooser(timeout=3000) as fc_info:
                            await btn.click()
                        fc = await fc_info.value
                        await fc.set_files(file_path)
                        print(f"[{self.DISPLAY_NAME}] Archivo adjuntado (chooser): {sel}", flush=True)
                        await asyncio.sleep(1.5)
                        return True
                except Exception:
                    continue

            print(f"[{self.DISPLAY_NAME}] No se pudo adjuntar el archivo", flush=True)
            return False
        except Exception as e:
            print(f"[{self.DISPLAY_NAME}] Error al adjuntar archivo: {e}", flush=True)
            return False

    # ─── Ciclo de vida ────────────────────────────────────────────────────────

    async def start_headless(self) -> bool:
        """
        Inicia el bot con sesión guardada en modo invisible.
        Siempre usa headless=False (Chrome real) y oculta la ventana con Win32 API.
        """
        try:
            self._emit_status(f"Iniciando {self.DISPLAY_NAME}...")
            # headless=False siempre — ocultar ventana manualmente tras lanzar
            self._browser_manager = BrowserManager(self.BOT_NAME, headless=False)
            self._page = await self._browser_manager.start()

            # Ocultar ventana de Chrome inmediatamente (modo invisible)
            await asyncio.sleep(0.8)
            _minimize_chrome_window()

            await self._page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            if await self._is_logged_in():
                await self._prepare_chat()
                self._is_ready = True
                self._emit_status("Listo")
                return True
            else:
                await self._browser_manager.stop()
                self._browser_manager = None
                self._is_ready = False
                self._emit_status("Sesión expirada")
                return False
        except Exception as e:
            self._emit_error(f"Error al iniciar {self.DISPLAY_NAME}: {e}")
            self._is_ready = False
            return False

    async def start_headful_for_login(self) -> Page:
        """Inicia en modo visible para login manual."""
        self._browser_manager = BrowserManager(self.BOT_NAME, headless=False)
        self._page = await self._browser_manager.start()
        try:
            await self._page.goto(
                self.LOGIN_URL,
                wait_until="domcontentloaded",
                timeout=30000
            )
            await asyncio.sleep(3)
        except Exception as e:
            print(f"[{self.DISPLAY_NAME}] Error al navegar a login URL: {e}", flush=True)
        return self._page

    async def wait_for_login(self, timeout: int = 180) -> bool:
        """Espera a que el usuario complete el login (máx. `timeout` segundos)."""
        for _ in range(timeout * 2):
            try:
                if self._page is None:
                    return False
                if await self._is_logged_in():
                    print(f"[{self.DISPLAY_NAME}] Login detectado, esperando flush de cookies...", flush=True)
                    await asyncio.sleep(5)
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return False

    async def prepare_after_login(self) -> bool:
        """
        Prepara el chat sobre el browser YA ABIERTO (post-login).
        No cierra ni reinicia el browser. Minimiza Chrome al acabar.
        """
        try:
            if self._page is None:
                return False
            self._emit_status(f"Preparando {self.DISPLAY_NAME}...")
            await self._prepare_chat()
            self._is_ready = True
            await asyncio.sleep(0.5)
            _minimize_chrome_window()
            self._emit_status("Listo")
            return True
        except Exception as e:
            self._emit_error(f"Error preparando chat: {e}")
            self._is_ready = False
            return False

    async def stop(self):
        """Detiene el navegador y libera recursos."""
        self._is_ready = False
        if self._browser_manager:
            await self._browser_manager.stop()
            self._browser_manager = None
            self._page = None

    def destroy(self):
        """Cierra el loop persistente del bot definitivamente."""
        try:
            if not self._loop.is_closed():
                self._loop.close()
        except Exception:
            pass

    # ─── Métodos abstractos ───────────────────────────────────────────────────

    @abstractmethod
    async def _is_logged_in(self) -> bool:
        pass

    @abstractmethod
    async def _prepare_chat(self):
        pass

    @abstractmethod
    async def send_message(self, message: str, file_path: str | None = None) -> str:
        """Envía mensaje con archivo adjunto opcional."""
        pass
