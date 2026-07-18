"""
Gestor del navegador Playwright con anti-detección máxima.
Usa el Google Chrome real del sistema para evitar fingerprinting.
"""
import os
import sys
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page
from playwright_stealth import Stealth

# Instancia global de stealth
_stealth = Stealth()

# Directorio base donde se guardan los perfiles de cada bot
PROFILES_DIR = Path.home() / ".tabasco" / "profiles"

# User-Agent actualizado a Chrome 136 (julio 2026)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

# sec-ch-ua para Chrome 136
SEC_CH_UA = '"Chromium";v="136", "Google Chrome";v="136", "Not-A.Brand";v="99"'


def find_chrome_executable() -> str | None:
    """
    Busca el ejecutable de Google Chrome real instalado en el sistema.
    Si lo encuentra, Playwright lo usará en lugar del Chromium propio
    (evita el fingerprint de automatización).
    """
    if sys.platform == "win32":
        candidates = [
            Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
            Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
            # Chrome Beta/Dev/Canary como fallback
            Path("C:/Program Files/Google/Chrome Beta/Application/chrome.exe"),
            Path("C:/Program Files/Google/Chrome Dev/Application/chrome.exe"),
        ]
    elif sys.platform == "darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"),
        ]
    else:  # Linux
        candidates = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/google-chrome-stable"),
            Path("/usr/bin/chromium-browser"),
            Path("/usr/bin/chromium"),
            Path("/snap/bin/chromium"),
        ]

    for path in candidates:
        if path.exists():
            print(f"[Browser] Chrome real encontrado: {path}", flush=True)
            return str(path)

    print("[Browser] Chrome real no encontrado, usando Chromium de Playwright", flush=True)
    return None


def get_profile_path(bot_name: str) -> Path:
    """Devuelve la ruta del directorio de perfil para un bot dado."""
    path = PROFILES_DIR / bot_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def profile_exists(bot_name: str) -> bool:
    """Comprueba si existe un perfil guardado para el bot."""
    path = get_profile_path(bot_name)
    return any(path.iterdir()) if path.exists() else False


def clear_profile(bot_name: str):
    """Elimina el perfil guardado de un bot (cierra sesión)."""
    import shutil
    path = get_profile_path(bot_name)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


# Script JS de anti-detección inyectado en cada página
_ANTI_DETECTION_SCRIPT = """
// ── Ocultar webdriver ──────────────────────────────────────────────────────
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// ── Plugins reales ─────────────────────────────────────────────────────────
const _plugins = [
    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
];
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const arr = _plugins.map(p => {
            const plugin = Object.create(Plugin.prototype);
            Object.defineProperty(plugin, 'name', { get: () => p.name });
            Object.defineProperty(plugin, 'filename', { get: () => p.filename });
            Object.defineProperty(plugin, 'description', { get: () => p.description });
            Object.defineProperty(plugin, 'length', { get: () => 0 });
            return plugin;
        });
        arr.item = i => arr[i];
        arr.namedItem = name => arr.find(p => p.name === name) || null;
        arr.refresh = () => {};
        Object.defineProperty(arr, 'length', { get: () => _plugins.length });
        return arr;
    }
});

// ── Idiomas ────────────────────────────────────────────────────────────────
Object.defineProperty(navigator, 'languages', { get: () => ['es-ES', 'es', 'en-US', 'en'] });
Object.defineProperty(navigator, 'language', { get: () => 'es-ES' });

// ── Plataforma ─────────────────────────────────────────────────────────────
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'vendor', { get: () => 'Google Inc.' });
Object.defineProperty(navigator, 'vendorSub', { get: () => '' });
Object.defineProperty(navigator, 'productSub', { get: () => '20030107' });
Object.defineProperty(navigator, 'appVersion', { get: () => '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36' });

// ── Chrome runtime ─────────────────────────────────────────────────────────
if (!window.chrome) {
    window.chrome = {};
}
if (!window.chrome.runtime) {
    window.chrome.runtime = {
        PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
        PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformNaclArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
        RequestUpdateCheckStatus: { THROTTLED: 'throttled', NO_UPDATE: 'no_update', UPDATE_AVAILABLE: 'update_available' },
        OnInstalledReason: { INSTALL: 'install', UPDATE: 'update', CHROME_UPDATE: 'chrome_update', SHARED_MODULE_UPDATE: 'shared_module_update' },
        OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
        connect: () => {},
        sendMessage: () => {},
        id: undefined,
    };
}

// ── Permisos ───────────────────────────────────────────────────────────────
const _originalQuery = window.navigator.permissions ? window.navigator.permissions.query : null;
if (_originalQuery) {
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : _originalQuery(parameters);
}

// ── Screen dimensions coherentes ──────────────────────────────────────────
Object.defineProperty(screen, 'width', { get: () => 1920 });
Object.defineProperty(screen, 'height', { get: () => 1080 });
Object.defineProperty(screen, 'availWidth', { get: () => 1920 });
Object.defineProperty(screen, 'availHeight', { get: () => 1040 });
Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });

// ── WebGL vendor/renderer realistas ───────────────────────────────────────
const _getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return _getParameter.call(this, parameter);
};
try {
    const _getParameter2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
        return _getParameter2.call(this, parameter);
    };
} catch(e) {}

// ── Ocultar automatización en iframes ─────────────────────────────────────
Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
    get: function() {
        const win = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow').get.call(this);
        if (win) {
            try {
                Object.defineProperty(win.navigator, 'webdriver', { get: () => undefined });
            } catch(e) {}
        }
        return win;
    }
});

// ── Ocultar toString de funciones modificadas ──────────────────────────────
const _nativeToString = Function.prototype.toString;
Function.prototype.toString = function() {
    const result = _nativeToString.call(this);
    if (result.includes('native code')) return result;
    return result;
};
"""


class BrowserManager:
    """
    Gestiona instancias de Playwright con:
    - Uso del Chrome real del sistema (máxima anti-detección)
    - playwright-stealth aplicado
    - User Data Directory por bot (sesiones persistentes)
    - User-Agent actualizado a Chrome 136
    - Script JS de anti-detección completo
    """

    def __init__(self, bot_name: str, headless: bool = True):
        self.bot_name = bot_name
        self.headless = headless
        self._playwright = None
        self._browser: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self) -> Page:
        """Inicia el navegador y devuelve la página activa."""
        self._playwright = await async_playwright().start()

        profile_path = get_profile_path(self.bot_name)
        chrome_exe = find_chrome_executable()

        # Args anti-detección máxima (sin --no-sandbox: Chrome real lo rechaza en Windows)
        args = [
            "--disable-blink-features=AutomationControlled",
            "--exclude-switches=enable-automation,enable-logging",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1280,900",
            "--disable-ipc-flooding-protection",
            "--disable-prompt-on-repost",
            "--disable-hang-monitor",
            "--password-store=basic",
            "--use-mock-keychain",
        ]

        # SIEMPRE headless=False — el headless real de Chromium tiene un fingerprint
        # claramente detectable por Cloudflare/OpenAI/Anthropic/etc.
        # Cuando queremos modo "invisible" ocultamos la ventana con Win32 API.
        launch_kwargs = dict(
            user_data_dir=str(profile_path),
            headless=False,
            args=args,
            viewport={"width": 1280, "height": 900},
            user_agent=USER_AGENT,
            locale="es-ES",
            timezone_id="Europe/Madrid",
            ignore_https_errors=True,
            extra_http_headers={
                "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
                "sec-ch-ua": SEC_CH_UA,
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            },
        )

        # Si encontramos Chrome real, usarlo como ejecutable
        if chrome_exe:
            launch_kwargs["executable_path"] = chrome_exe

        self._browser = await self._playwright.chromium.launch_persistent_context(
            **launch_kwargs
        )

        # Obtener o crear la primera página
        pages = self._browser.pages
        self._page = pages[0] if pages else await self._browser.new_page()

        # Aplicar stealth
        await _stealth.apply_stealth_async(self._page)

        # Inyectar script anti-detección
        await self._page.add_init_script(_ANTI_DETECTION_SCRIPT)

        return self._page

    async def new_page(self) -> Page:
        """Abre una nueva pestaña en el contexto actual."""
        if not self._browser:
            raise RuntimeError("El navegador no está iniciado.")
        page = await self._browser.new_page()
        await _stealth.apply_stealth_async(page)
        await page.add_init_script(_ANTI_DETECTION_SCRIPT)
        return page

    async def stop(self):
        """Cierra el navegador y Playwright."""
        try:
            if self._browser:
                await self._browser.close()
                self._browser = None
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
        except Exception:
            pass

    @property
    def page(self) -> Page | None:
        return self._page

    @property
    def context(self) -> BrowserContext | None:
        return self._browser

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()
