"""
Bot para Claude de Anthropic (claude.ai)
Selectores actualizados julio 2026.
"""
import asyncio
import random
from core.base_bot import BaseBot


def _dbg(msg: str):
    print(f"[Claude] {msg}", flush=True)


class ClaudeBot(BaseBot):
    BOT_NAME     = "claude"
    DISPLAY_NAME = "Claude"
    URL          = "https://claude.ai/new"
    LOGIN_URL    = "https://claude.ai/"
    ICON         = "claude.png"
    COLOR        = "#D97757"
    MODELS = {
        "Claude 4 Sonnet":   "claude-sonnet-4",
        "Claude 3.7 Sonnet": "claude-3-7-sonnet",
        "Claude 3.5 Sonnet": "claude-3-5-sonnet",
        "Claude 3.5 Haiku":  "claude-3-5-haiku",
    }

    # ── Detección de login ────────────────────────────────────────────────────

    async def _is_logged_in(self) -> bool:
        """Verifica si estamos logados en Claude."""
        try:
            if self._page is None:
                return False

            url = self._page.url
            _dbg(f"URL actual: {url}")

            # Páginas de autenticación → no logado
            no_login_patterns = ["login", "auth", "signin", "signup"]
            for p in no_login_patterns:
                if p in url:
                    _dbg(f"No logado → patrón '{p}' en URL")
                    return False

            if "claude.ai" not in url:
                _dbg(f"URL fuera de claude.ai: {url}")
                return False

            # Verificar que hay UI de chat
            chat_sels = [
                '.ProseMirror',
                'div[contenteditable="true"]',
                '[data-placeholder]',
                'div[aria-label*="Claude"]',
                'fieldset',
                '[aria-label="Write your prompt to Claude"]',
            ]
            for sel in chat_sels:
                try:
                    el = await self._page.query_selector(sel)
                    if el and await el.is_visible():
                        _dbg(f"Logado (UI visible: {sel})")
                        return True
                except Exception:
                    pass

            # Si estamos en claude.ai sin login → redirige al inicio de sesión
            _dbg("No se encontró UI de chat")
            return False

        except Exception as e:
            _dbg(f"Excepción en _is_logged_in: {e}")
            return False

    # ── Preparación del chat ──────────────────────────────────────────────────

    async def _prepare_chat(self):
        """Prepara Claude para el chat."""
        try:
            current = self._page.url
            if "/new" not in current:
                _dbg("Navegando a /new...")
                await self._page.goto(self.URL, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2.5)

            # Cerrar modales si existen
            close_selectors = [
                'button[aria-label="Close"]',
                'button[aria-label="Cerrar"]',
                '[data-testid="close-modal"]',
                'button.close',
                '[data-state="open"] button[aria-label*="close" i]',
            ]
            for sel in close_selectors:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.3)
                except Exception:
                    pass

            _dbg("Chat preparado")
        except Exception as e:
            _dbg(f"_prepare_chat error (no crítico): {e}")

    async def select_model(self, model_name: str) -> bool:
        """Selecciona un modelo en Claude.ai."""
        self._current_model = model_name
        if self._page is None:
            return False
        try:
            model_btn_sels = [
                '[aria-label*="model" i]',
                'button[aria-label*="Claude" i]',
                '.model-picker',
                'button:has-text("Claude")',
                '[data-testid*="model"]',
            ]
            clicked = False
            for sel in model_btn_sels:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.6)
                        clicked = True
                        break
                except Exception:
                    pass

            if clicked:
                option_sels = [
                    f'[role="menuitem"]:has-text("{model_name}")',
                    f'[role="option"]:has-text("{model_name}")',
                    f'button:has-text("{model_name}")',
                    f'li:has-text("{model_name}")',
                ]
                for opt_sel in option_sels:
                    try:
                        opt = await self._page.query_selector(opt_sel)
                        if opt and await opt.is_visible():
                            await opt.click()
                            await asyncio.sleep(0.5)
                            _dbg(f"Modelo seleccionado: {model_name}")
                            return True
                    except Exception:
                        pass
                await self._page.keyboard.press('Escape')

            return True
        except Exception as e:
            _dbg(f"Error al seleccionar modelo: {e}")
            return True

    # ── Envío de mensaje ──────────────────────────────────────────────────────

    async def send_message(self, message: str, file_path: str | None = None) -> str:
        """Envía un mensaje a Claude y obtiene la respuesta."""
        if not self._is_ready or not self._page:
            raise RuntimeError("El bot no está listo. Inicia sesión primero.")

        try:
            self._emit_status("Enviando mensaje...")
            _dbg(f"Enviando: {message[:60]}...")

            await self._page.bring_to_front()
            await asyncio.sleep(0.5)

            if file_path:
                await self._attach_file(file_path)
                await asyncio.sleep(0.5)

            # Selectores de input (orden de preferencia, julio 2026)
            input_selectors = [
                '.ProseMirror[contenteditable="true"]',
                'div[contenteditable="true"].ProseMirror',
                'div[aria-label="Write your prompt to Claude"]',
                '[data-placeholder][contenteditable="true"]',
                'div[contenteditable="true"]',
                'fieldset div[contenteditable="true"]',
            ]

            input_el = None
            for sel in input_selectors:
                try:
                    el = await self._page.wait_for_selector(sel, timeout=6000, state="visible")
                    if el:
                        input_el = el
                        _dbg(f"Input encontrado: {sel}")
                        break
                except Exception:
                    continue

            if not input_el:
                raise RuntimeError("No se encontró el área de texto de Claude.")

            await input_el.click()
            await asyncio.sleep(random.uniform(0.2, 0.5))

            # Seleccionar todo y borrar contenido previo
            await self._page.keyboard.press("Control+a")
            await asyncio.sleep(0.1)
            await self._page.keyboard.press("Backspace")
            await asyncio.sleep(0.15)

            # Escribir con delays humanos
            for char in message:
                await self._page.keyboard.type(char, delay=random.randint(25, 70))

            await asyncio.sleep(random.uniform(0.3, 0.6))

            # Intentar botones de envío (julio 2026)
            send_selectors = [
                'button[aria-label="Send Message"]',
                'button[aria-label="Send message"]',
                'button[data-testid="send-button"]',
                'button[aria-label*="send" i]',
                'button[type="submit"]',
                'fieldset button[type="submit"]',
            ]
            sent = False
            for sel in send_selectors:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_enabled():
                        await btn.click()
                        sent = True
                        _dbg(f"Enviado via botón: {sel}")
                        break
                except Exception:
                    continue

            if not sent:
                await self._page.keyboard.press("Enter")
                _dbg("Enviado via Enter")

            self._emit_status("Esperando respuesta de Claude...")
            response = await self._wait_for_response()
            self._emit_message(response)
            self._emit_status("Listo")
            return response

        except Exception as e:
            error_msg = f"Error al enviar mensaje a Claude: {e}"
            _dbg(error_msg)
            self._emit_error(error_msg)
            raise RuntimeError(error_msg)

    # ── Esperar y extraer respuesta ───────────────────────────────────────────

    async def _wait_for_response(self) -> str:
        """Espera a que Claude genere la respuesta completa."""
        await asyncio.sleep(2)

        # Esperar hasta 120s a que el indicador de generación desaparezca
        for attempt in range(240):
            await asyncio.sleep(0.5)
            still_generating = False
            try:
                # Botón de stop visible → todavía generando
                stop_sels = [
                    'button[aria-label="Stop"]',
                    'button[aria-label="Stop Response"]',
                    'button[data-testid="stop-button"]',
                    '[aria-label*="Stop" i]',
                ]
                for sel in stop_sels:
                    el = await self._page.query_selector(sel)
                    if el and await el.is_visible():
                        still_generating = True
                        break

                if not still_generating:
                    # También chequear streaming indicators
                    stream_sels = [
                        '.streaming-indicator',
                        '[data-is-streaming="true"]',
                        '.animate-pulse',
                        'span.cursor-blink',
                    ]
                    for sel in stream_sels:
                        el = await self._page.query_selector(sel)
                        if el and await el.is_visible():
                            still_generating = True
                            break
            except Exception:
                pass

            if not still_generating and attempt >= 2:
                break

        await asyncio.sleep(1.2)

        # Extraer la última respuesta del asistente (selectores julio 2026)
        response_sels = [
            '[data-testid="ai-message"] .prose',
            '[data-testid="assistant-message"] .prose',
            '.font-claude-message',
            '[data-is-streaming="false"] .prose',
            '.prose.max-w-none',
            '[data-testid="ai-message"]',
            '.message-content .prose',
        ]
        for sel in response_sels:
            try:
                els = await self._page.query_selector_all(sel)
                if els:
                    text = await els[-1].inner_text()
                    if text.strip():
                        _dbg(f"Respuesta extraída con: {sel}")
                        return text.strip()
            except Exception:
                pass

        # Fallback JS
        try:
            text = await self._page.evaluate("""() => {
                const sels = [
                    '[data-testid="ai-message"]',
                    '.font-claude-message',
                    '.prose'
                ];
                for (const sel of sels) {
                    const els = document.querySelectorAll(sel);
                    if (els.length > 0) {
                        return els[els.length - 1].innerText;
                    }
                }
                return '';
            }""")
            if text and text.strip():
                _dbg("Respuesta extraída via JS fallback")
                return text.strip()
        except Exception:
            pass

        _dbg("No se pudo extraer respuesta")
        return "(No se pudo extraer la respuesta de Claude)"
