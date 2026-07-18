"""
Bot para DeepSeek (chat.deepseek.com)
Selectores julio 2026.
"""
import asyncio
import random
from core.base_bot import BaseBot


def _dbg(msg: str):
    print(f"[DeepSeek] {msg}", flush=True)


class DeepSeekBot(BaseBot):
    BOT_NAME     = "deepseek"
    DISPLAY_NAME = "DeepSeek"
    URL          = "https://chat.deepseek.com/"
    LOGIN_URL    = "https://chat.deepseek.com/"
    ICON         = "deepseek.png"
    COLOR        = "#4D6BFE"
    MODELS = {
        "DeepSeek-V3": "deepseek-v3",
        "DeepSeek-R1": "deepseek-r1",
    }

    # ── Detección de login ────────────────────────────────────────────────────

    async def _is_logged_in(self) -> bool:
        """Verifica si estamos logados en DeepSeek."""
        try:
            if self._page is None:
                return False

            url = self._page.url
            _dbg(f"URL actual: {url}")

            # Páginas de auth → no logado
            no_login_patterns = ["/sign_in", "/sign_up", "/login", "/register", "auth"]
            for p in no_login_patterns:
                if p in url:
                    _dbg(f"No logado → patrón '{p}' en URL")
                    return False

            if "chat.deepseek.com" not in url:
                _dbg(f"URL fuera de chat.deepseek.com: {url}")
                return False

            # Verificar que hay UI de chat
            chat_sels = [
                'textarea',
                '[contenteditable="true"]',
                '#chat-input',
                '.chat-input',
                'div[id*="input"]',
                '[placeholder*="message" i]',
                '[placeholder*="mensaje" i]',
                '[data-testid*="input"]',
            ]
            for sel in chat_sels:
                try:
                    el = await self._page.query_selector(sel)
                    if el and await el.is_visible():
                        _dbg(f"Logado (UI visible: {sel})")
                        return True
                except Exception:
                    pass

            _dbg("No se encontró UI de chat")
            return False

        except Exception as e:
            _dbg(f"Excepción en _is_logged_in: {e}")
            return False

    # ── Preparación del chat ──────────────────────────────────────────────────

    async def _prepare_chat(self):
        """Prepara DeepSeek para el chat."""
        try:
            current = self._page.url
            if "chat.deepseek.com" not in current:
                _dbg("Navegando a chat...")
                await self._page.goto(self.URL, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)

            # Cerrar modales si existen
            close_selectors = [
                'button[aria-label="Close"]',
                'button[aria-label="Cerrar"]',
                '[data-testid="close"]',
                'button.close',
                '[class*="close" i][role="button"]',
            ]
            for sel in close_selectors:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.3)
                except Exception:
                    pass

            # Iniciar nueva conversación
            new_chat_sels = [
                'button[aria-label*="new" i]',
                'button[aria-label*="nuevo" i]',
                '[data-testid="new-chat"]',
                'a[href="/"]',
            ]
            for sel in new_chat_sels:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.8)
                        _dbg(f"Nueva conversación: {sel}")
                        break
                except Exception:
                    pass

            _dbg("Chat preparado")
        except Exception as e:
            _dbg(f"_prepare_chat error (no crítico): {e}")

    async def select_model(self, model_name: str) -> bool:
        """Selecciona el modelo en DeepSeek (V3 o R1)."""
        self._current_model = model_name
        if self._page is None:
            return False
        try:
            model_id = self.MODELS.get(model_name, "")
            toggle_sels = [
                f'button[aria-label*="{model_name}" i]',
                f'button:has-text("{model_name}")',
                f'[data-model="{model_id}"]',
                'button[aria-pressed]',
                '[role="switch"]',
            ]
            for sel in toggle_sels:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.4)
                        _dbg(f"Modelo seleccionado: {model_name}")
                        return True
                except Exception:
                    pass
            _dbg(f"Modelo guardado localmente: {model_name}")
            return True
        except Exception as e:
            _dbg(f"Error al seleccionar modelo: {e}")
            return True

    # ── Envío de mensaje ──────────────────────────────────────────────────────

    async def send_message(self, message: str, file_path: str | None = None) -> str:
        """Envía un mensaje a DeepSeek y obtiene la respuesta."""
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

            # Selectores de input
            input_selectors = [
                'textarea#chat-input',
                'textarea.chat-input',
                'textarea[placeholder*="message" i]',
                'textarea[placeholder*="mensaje" i]',
                'textarea[data-testid*="input"]',
                '[contenteditable="true"]',
                'textarea',
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
                raise RuntimeError("No se encontró el área de texto de DeepSeek.")

            await input_el.click()
            await asyncio.sleep(random.uniform(0.2, 0.5))

            # Limpiar contenido previo
            await self._page.keyboard.press("Control+a")
            await asyncio.sleep(0.1)
            await self._page.keyboard.press("Delete")
            await asyncio.sleep(0.15)

            # Escribir con delays humanos
            for char in message:
                await self._page.keyboard.type(char, delay=random.randint(25, 65))

            await asyncio.sleep(random.uniform(0.3, 0.6))

            # Intentar botones de envío
            send_selectors = [
                'button[aria-label="Send"]',
                'button[aria-label="Enviar"]',
                'button[data-testid="send-button"]',
                'button[type="submit"]',
                '[class*="send" i][role="button"]',
                'button svg[aria-label*="send" i]',
            ]
            sent = False
            for sel in send_selectors:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn:
                        parent = await btn.evaluate_handle("el => el.closest('button') || el")
                        if await parent.evaluate("el => !el.disabled"):
                            await parent.click()
                            sent = True
                            _dbg(f"Enviado via botón: {sel}")
                            break
                except Exception:
                    continue

            if not sent:
                await self._page.keyboard.press("Enter")
                _dbg("Enviado via Enter")

            self._emit_status("Esperando respuesta de DeepSeek...")
            response = await self._wait_for_response()
            self._emit_message(response)
            self._emit_status("Listo")
            return response

        except Exception as e:
            error_msg = f"Error al enviar mensaje a DeepSeek: {e}"
            _dbg(error_msg)
            self._emit_error(error_msg)
            raise RuntimeError(error_msg)

    # ── Esperar y extraer respuesta ───────────────────────────────────────────

    async def _wait_for_response(self) -> str:
        """Espera a que DeepSeek genere la respuesta completa."""
        await asyncio.sleep(2.5)

        # Esperar hasta 90s
        for attempt in range(180):
            await asyncio.sleep(0.5)
            still_generating = False
            try:
                stop_sels = [
                    'button[aria-label="Stop"]',
                    'button[aria-label="Detener"]',
                    '[data-testid="stop-button"]',
                    '[class*="stop" i][role="button"]',
                    'div[class*="loading"]',
                    '.generating',
                ]
                for sel in stop_sels:
                    el = await self._page.query_selector(sel)
                    if el and await el.is_visible():
                        still_generating = True
                        break
            except Exception:
                pass

            if not still_generating and attempt >= 2:
                break

        await asyncio.sleep(1.2)

        # Extraer la última respuesta del asistente
        response_sels = [
            '[data-message-author-role="assistant"] .markdown',
            '[data-message-author-role="assistant"]',
            '.ds-markdown',
            '.message-content[data-role="assistant"]',
            '[class*="assistant"][class*="message"]',
            '[class*="response"] .markdown',
            '[class*="markdown"]',
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
                    '[data-message-author-role="assistant"]',
                    '.ds-markdown',
                    '[class*="assistant"]',
                    '[class*="markdown"]'
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
        return "(No se pudo extraer la respuesta de DeepSeek)"
