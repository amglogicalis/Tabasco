"""
Bot para ChatGPT (chatgpt.com)
Con manejo de Cloudflare Turnstile y selectores actualizados.
"""
import asyncio
import random
from core.base_bot import BaseBot


def _dbg(msg: str):
    print(f"[ChatGPT] {msg}", flush=True)


class ChatGPTBot(BaseBot):
    BOT_NAME     = "chatgpt"
    DISPLAY_NAME = "ChatGPT"
    URL          = "https://chatgpt.com/"
    LOGIN_URL    = "https://chatgpt.com/"
    ICON         = "chatgpt.png"
    COLOR        = "#e07a5a"
    MODELS = {
        "GPT-4o":      "gpt-4o",
        "GPT-4o mini": "gpt-4o-mini",
        "o3":          "o3",
        "o4-mini":     "o4-mini",
    }

    # ── Detección de login ────────────────────────────────────────────────────

    async def _is_logged_in(self) -> bool:
        """
        True si estamos en chatgpt.com autenticados y con la UI de chat visible.
        Estrategia basada en URL + presencia de elemento de input.
        """
        try:
            if self._page is None:
                return False

            url = self._page.url
            _dbg(f"URL actual: {url}")

            # Páginas de autenticación o bloqueo → no logado
            not_logged_patterns = [
                "auth.openai.com",
                "/login",
                "/signup",
                "challenge",
                "cdn-cgi",   # Cloudflare challenge
            ]
            for p in not_logged_patterns:
                if p in url:
                    _dbg(f"No logado → patrón '{p}' en URL")
                    return False

            # Si no está en chatgpt.com → no logado
            if "chatgpt.com" not in url:
                _dbg(f"URL fuera de chatgpt.com: {url}")
                return False

            # Verificar que hay UI de chat (input visible)
            input_sels = [
                '#prompt-textarea',
                'div[contenteditable="true"]',
                'textarea',
                '[data-testid="send-button"]',
            ]
            for sel in input_sels:
                try:
                    el = await self._page.query_selector(sel)
                    if el and await el.is_visible():
                        _dbg(f"Logado (input visible: {sel})")
                        return True
                except Exception:
                    pass

            # También logado si hay la sidebar/nav de ChatGPT
            nav_sels = [
                'nav',
                '[data-testid="profile-button"]',
                'a[href="/"]',
            ]
            for sel in nav_sels:
                try:
                    el = await self._page.query_selector(sel)
                    if el:
                        _dbg(f"Logado (nav: {sel})")
                        return True
                except Exception:
                    pass

            _dbg("No se encontró UI de chat")
            return False

        except Exception as e:
            _dbg(f"Excepción: {e}")
            return False

    # ── Preparación del chat ──────────────────────────────────────────────────

    async def _prepare_chat(self):
        """Cierra modales de bienvenida y asegura que estamos en el chat principal."""
        try:
            await asyncio.sleep(1.5)

            # Cerrar modales de bienvenida / onboarding
            for sel in [
                'button[data-testid="close-button"]',
                'button[aria-label="Close"]',
                '[data-radix-dialog-close]',
                'button.close',
            ]:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

            _dbg("Chat preparado")
        except Exception as e:
            _dbg(f"_prepare_chat error (no crítico): {e}")

    async def select_model(self, model_name: str) -> bool:
        """Selecciona un modelo en ChatGPT."""
        self._current_model = model_name
        if self._page is None:
            return False
        try:
            # El selector de modelo en ChatGPT suele estar en un dropdown
            model_btn_sels = [
                '[data-testid="model-switcher"]',
                'button[aria-label*="model" i]',
                'button[aria-haspopup="listbox"]',
                'div[aria-haspopup="menu"]:has-text("GPT")',
                'div[aria-haspopup="menu"]:has-text("o3")',
                'div[aria-haspopup="menu"]:has-text("o4")',
                '.model-picker',
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
                    f'[role="menuitemradio"]:has-text("{model_name}")',
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

            _dbg(f"Modelo guardado localmente: {model_name}")
            return True
        except Exception as e:
            _dbg(f"Error al seleccionar modelo: {e}")
            return True

    # ── Envío de mensaje ──────────────────────────────────────────────────────

    async def send_message(self, message: str, file_path: str | None = None) -> str:
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

            # Selectores para el input (orden de preferencia, julio 2026)
            input_sels = [
                '#prompt-textarea',
                'div[contenteditable="true"][data-lexical-editor]',
                'div[contenteditable="true"]',
                'textarea',
            ]

            input_el = None
            for sel in input_sels:
                try:
                    el = await self._page.wait_for_selector(sel, timeout=7000, state="visible")
                    if el:
                        input_el = el
                        _dbg(f"Input encontrado: {sel}")
                        break
                except Exception:
                    continue

            if not input_el:
                raise RuntimeError("No se encontró el área de texto de ChatGPT.")

            # Click + limpiar
            await input_el.click()
            await asyncio.sleep(random.uniform(0.3, 0.6))
            await self._page.keyboard.press("Control+a")
            await asyncio.sleep(0.1)
            await self._page.keyboard.press("Delete")
            await asyncio.sleep(0.2)

            # Escribir con delays humanos
            for char in message:
                await self._page.keyboard.type(char, delay=random.randint(30, 80))

            await asyncio.sleep(random.uniform(0.4, 0.8))

            # Intentar botón de envío
            sent = False
            for sel in [
                'button[data-testid="send-button"]',
                'button[aria-label="Send message"]',
                'button[aria-label="Send prompt"]',
                'button[type="submit"]',
                '[data-testid="fruitjuice-send-button"]',
            ]:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_enabled():
                        await btn.click()
                        sent = True
                        _dbg(f"Enviado via botón: {sel}")
                        break
                except Exception:
                    pass

            if not sent:
                await self._page.keyboard.press("Enter")
                _dbg("Enviado via Enter")

            self._emit_status("Esperando respuesta de ChatGPT...")
            response = await self._wait_for_response()
            self._emit_message(response)
            self._emit_status("Listo")
            return response

        except Exception as e:
            err = f"Error al enviar mensaje a ChatGPT: {e}"
            _dbg(err)
            self._emit_error(err)
            raise RuntimeError(err)

    # ── Esperar respuesta ─────────────────────────────────────────────────────

    async def _wait_for_response(self) -> str:
        """Espera a que ChatGPT genere la respuesta completa."""
        stop_sels = [
            'button[aria-label="Stop generating"]',
            'button[data-testid="stop-button"]',
            'button[aria-label="Stop streaming"]',
        ]

        # Esperar a que aparezca el botón de stop (señal de que empezó a generar)
        for _ in range(20):
            await asyncio.sleep(0.3)
            found_stop = False
            for sel in stop_sels:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        found_stop = True
                        break
                except Exception:
                    pass
            if found_stop:
                break

        # Esperar hasta 90s a que termine de generar
        for attempt in range(180):
            await asyncio.sleep(0.5)
            still_generating = False
            for sel in stop_sels:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        still_generating = True
                        break
                except Exception:
                    pass
            if not still_generating and attempt >= 3:
                break

        await asyncio.sleep(1.5)

        # ── Extracción con JS robusto ──────────────────────────────────────────
        # Estrategia: JS que prueba múltiples selectores y devuelve el último con texto
        js_result = await self._page.evaluate("""() => {
            const candidates = [
                // Julio 2026: estructura basada en data-message-author-role
                '[data-message-author-role="assistant"]',
                // Estructura clásica article/turn
                'article[data-testid*="conversation-turn"]:not([data-testid*="user"])',
                // Clase markdown dentro de turno asistente
                '.agent-turn .markdown',
                '.agent-turn',
                // Genérico: buscar divs con contenido de respuesta
                '[class*="assistant"] [class*="markdown"]',
                '[class*="assistant"]',
                // Último recurso: cualquier article del chat
                'main article',
            ];
            for (const sel of candidates) {
                try {
                    const els = document.querySelectorAll(sel);
                    if (els.length === 0) continue;
                    // Tomar el último elemento con texto significativo
                    for (let i = els.length - 1; i >= 0; i--) {
                        const t = els[i].innerText || els[i].textContent || '';
                        const trimmed = t.trim();
                        if (trimmed.length > 5) {
                            return JSON.stringify({sel: sel, text: trimmed});
                        }
                    }
                } catch(e) {}
            }
            // Último recurso absoluto: todo el texto del main
            try {
                const main = document.querySelector('main');
                if (main) return JSON.stringify({sel: 'main', text: main.innerText.trim()});
            } catch(e) {}
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

        # ── Fallback: selectores directos Python ──────────────────────────────
        for sel in [
            '[data-message-author-role="assistant"]',
            '.agent-turn',
            'article',
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
        return "(No se pudo extraer la respuesta de ChatGPT)"
