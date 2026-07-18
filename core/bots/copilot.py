"""
Bot para Microsoft Copilot (copilot.microsoft.com)
Selectores actualizados julio 2026.
"""
import asyncio
import random
from core.base_bot import BaseBot


def _dbg(msg: str):
    print(f"[Copilot] {msg}", flush=True)


class CopilotBot(BaseBot):
    BOT_NAME     = "copilot"
    DISPLAY_NAME = "Copilot"
    URL          = "https://copilot.microsoft.com/"
    LOGIN_URL    = "https://copilot.microsoft.com/"
    ICON         = "copilot.png"
    COLOR        = "#0078D4"
    MODELS = {
        "Equilibrado": "balanced",
        "Creativo":    "creative",
        "Preciso":     "precise",
    }

    # ── Detección de login ────────────────────────────────────────────────────

    async def _is_logged_in(self) -> bool:
        """Verifica si estamos logados en Copilot."""
        try:
            if self._page is None:
                return False

            url = self._page.url
            _dbg(f"URL actual: {url}")

            # Páginas de Microsoft login → no logado
            not_logged_patterns = [
                "login.microsoftonline.com",
                "login.live.com",
                "account.microsoft.com",
                "/login",
                "signin",
            ]
            for p in not_logged_patterns:
                if p in url:
                    _dbg(f"No logado → patrón '{p}' en URL")
                    return False

            if "copilot.microsoft.com" not in url:
                _dbg(f"URL fuera de copilot.microsoft.com: {url}")
                return False

            # Verificar que hay UI de chat (input visible)
            input_sels = [
                'textarea#userInput',
                'textarea[data-testid*="input"]',
                'div[contenteditable="true"]',
                '#searchbox',
                'cib-text-input textarea',
                'textarea[placeholder]',
                '[aria-label*="message" i]',
                '[aria-label*="pregunta" i]',
            ]
            for sel in input_sels:
                try:
                    el = await self._page.query_selector(sel)
                    if el and await el.is_visible():
                        _dbg(f"Logado (input visible: {sel})")
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
        """Prepara Copilot para el chat."""
        try:
            await asyncio.sleep(1.5)

            # Cerrar modales o banners
            close_selectors = [
                'button[aria-label="Close"]',
                'button[aria-label="Cerrar"]',
                'button[title="Close"]',
                '.dismiss-button',
                '[data-testid="dismiss"]',
            ]
            for sel in close_selectors:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.3)
                except Exception:
                    pass

            # Iniciar nueva conversación si hay botón disponible
            new_chat_selectors = [
                'button[aria-label="New topic"]',
                'button[aria-label="New chat"]',
                'button[aria-label="Nueva conversación"]',
                '#new-conversation-button',
                '[data-testid="new-chat"]',
            ]
            for sel in new_chat_selectors:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(1)
                        _dbg(f"Nueva conversación iniciada: {sel}")
                        break
                except Exception:
                    pass

            _dbg("Chat preparado")
        except Exception as e:
            _dbg(f"_prepare_chat error (no crítico): {e}")

    async def select_model(self, model_name: str) -> bool:
        """Selecciona el estilo de conversación en Copilot."""
        self._current_model = model_name
        if self._page is None:
            return False
        try:
            mode_sels = [
                f'button[aria-label*="{model_name}" i]',
                f'button:has-text("{model_name}")',
                f'[role="tab"]:has-text("{model_name}")',
                f'[role="button"]:has-text("{model_name}")',
            ]
            for sel in mode_sels:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.4)
                        _dbg(f"Modo seleccionado: {model_name}")
                        return True
                except Exception:
                    pass
            _dbg(f"Modo guardado localmente: {model_name}")
            return True
        except Exception as e:
            _dbg(f"Error al seleccionar modo: {e}")
            return True

    # ── Envío de mensaje ──────────────────────────────────────────────────────

    async def send_message(self, message: str, file_path: str | None = None) -> str:
        """Envía un mensaje a Copilot y obtiene la respuesta."""
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

            # Selectores de input (julio 2026)
            input_selectors = [
                'textarea#userInput',
                'textarea[data-testid*="input"]',
                'div[contenteditable="true"]',
                'cib-text-input textarea',
                'textarea[placeholder]',
                '#searchbox',
                '[aria-label*="message" i]',
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
                raise RuntimeError("No se encontró el área de texto de Copilot.")

            await input_el.click()
            await asyncio.sleep(random.uniform(0.2, 0.4))

            # Limpiar contenido previo
            await self._page.keyboard.press("Control+a")
            await asyncio.sleep(0.1)
            await self._page.keyboard.press("Delete")
            await asyncio.sleep(0.15)

            # Escribir con delays humanos
            for char in message:
                await self._page.keyboard.type(char, delay=random.randint(25, 65))

            await asyncio.sleep(random.uniform(0.3, 0.6))

            # Intentar botones de envío (julio 2026)
            send_selectors = [
                'button[aria-label="Submit"]',
                'button[aria-label="Enviar"]',
                'button[data-testid="submit-button"]',
                'button[type="submit"]',
                'cib-action-bar button[aria-label]',
                '#submit-button',
                '[aria-label*="send" i]',
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

            self._emit_status("Esperando respuesta de Copilot...")
            response = await self._wait_for_response()
            self._emit_message(response)
            self._emit_status("Listo")
            return response

        except Exception as e:
            error_msg = f"Error al enviar mensaje a Copilot: {e}"
            _dbg(error_msg)
            self._emit_error(error_msg)
            raise RuntimeError(error_msg)

    # ── Esperar y extraer respuesta ───────────────────────────────────────────

    async def _wait_for_response(self) -> str:
        """Espera a que Copilot genere la respuesta completa."""
        await asyncio.sleep(2.5)

        # Esperar a que el indicador de carga aparezca (señal de inicio)
        loading_selectors = [
            'cib-typing-indicator',
            '.typing-indicator',
            '[aria-label="Copilot is responding"]',
            '[aria-label="Copilot está respondiendo"]',
            '.response-generating',
            '[data-testid="loading-indicator"]',
            'div[aria-busy="true"]',
        ]
        for _ in range(10):
            await asyncio.sleep(0.3)
            for sel in loading_selectors:
                try:
                    el = await self._page.query_selector(sel)
                    if el and await el.is_visible():
                        break
                except Exception:
                    pass

        # Esperar hasta 90s a que el indicador de carga desaparezca
        for attempt in range(180):
            await asyncio.sleep(0.5)
            still_generating = False
            for sel in loading_selectors:
                try:
                    el = await self._page.query_selector(sel)
                    if el and await el.is_visible():
                        still_generating = True
                        break
                except Exception:
                    pass
            if not still_generating and attempt >= 3:
                break

        await asyncio.sleep(1.5)

        # ── Extracción con JS robusto ─────────────────────────────────────────
        js_result = await self._page.evaluate("""() => {
            const candidates = [
                // Web Components de Copilot (estructura 2024-2026)
                'cib-message-group[source="bot"] cib-message',
                'cib-message[source="bot"]',
                // Estructura basada en data-testid
                '[data-testid="copilot-message"]',
                '[data-testid="message"][data-author="bot"]',
                // Adaptive cards dentro de Copilot
                'cib-message .ac-textBlock',
                'cib-message .ac-container',
                // Clases de respuesta genéricas
                '.response-message-group .message',
                '.message[data-author="bot"]',
                // Estructura moderna (React): buscar por rol
                '[data-message-author-role="assistant"]',
                // Último recurso: divs con id/class que contengan "response"
                '[class*="response"][class*="message"]',
                // Genérico amplio
                '[class*="bot"][class*="message"]',
                '[class*="assistant"]',
            ];
            for (const sel of candidates) {
                try {
                    const els = document.querySelectorAll(sel);
                    if (els.length === 0) continue;
                    for (let i = els.length - 1; i >= 0; i--) {
                        const t = els[i].innerText || els[i].textContent || '';
                        const trimmed = t.trim();
                        if (trimmed.length > 5) {
                            return JSON.stringify({sel: sel, text: trimmed});
                        }
                    }
                } catch(e) {}
            }
            // Último recurso: todo el texto visible de la zona de chat
            const chatZones = ['#chat-list', '#copilot-chat', 'main', 'body'];
            for (const z of chatZones) {
                try {
                    const el = document.querySelector(z);
                    if (el) {
                        const t = el.innerText.trim();
                        if (t.length > 10) return JSON.stringify({sel: z, text: t});
                    }
                } catch(e) {}
            }
            return null;
        }""")

        if js_result:
            try:
                import json
                data = json.loads(js_result)
                text = data.get("text", "")
                sel_used = data.get("sel", "?")
                if text:
                    _dbg(f"Respuesta extraída con JS ({sel_used}): {text[:80]}...")
                    return text
            except Exception as e:
                _dbg(f"Error parseando JS result: {e}")

        # ── Fallback directo Python ───────────────────────────────────────────
        for sel in [
            'cib-message[source="bot"]',
            '[data-testid="copilot-message"]',
            '[data-message-author-role="assistant"]',
        ]:
            try:
                els = await self._page.query_selector_all(sel)
                for el in reversed(els):
                    text = await el.inner_text()
                    if text and len(text.strip()) > 5:
                        _dbg(f"Fallback Python ({sel}): {text[:60]}...")
                        return text.strip()
            except Exception:
                pass

        _dbg("No se pudo extraer respuesta")
        return "(No se pudo extraer la respuesta de Copilot)"
