"""
Bot para Google Gemini (gemini.google.com)
Selectores actualizados julio 2026 + Shadow DOM handling.
"""
import asyncio
import random
from core.base_bot import BaseBot


def _dbg(msg: str):
    print(f"[Gemini] {msg}", flush=True)


class GeminiBot(BaseBot):
    BOT_NAME     = "gemini"
    DISPLAY_NAME = "Gemini"
    URL          = "https://gemini.google.com/app"
    LOGIN_URL    = "https://gemini.google.com/"
    ICON         = "gemini.png"
    COLOR        = "#e05a5a"
    MODELS = {
        "3.5 Flash": "3.5 Flash",
        "3.1 Pro": "3.1 Pro",
        "3.1 Flash-Lite": "3.1 Flash-Lite",
        "Razonamiento ampliado": "Razonamiento ampliado",
    }

    # ── Detección de login ────────────────────────────────────────────────────

    async def _is_logged_in(self) -> bool:
        """
        True si estamos en Gemini autenticados (URL-based).
        """
        try:
            if self._page is None:
                return False

            url = self._page.url
            _dbg(f"URL actual: {url}")

            # Rechazar páginas de error/CAPTCHA de Google
            # (gemini.google.com puede aparecer en el parámetro ?continue= de la sorry page)
            no_login_patterns = [
                "accounts.google.com",
                "myaccount.google.com",
                "/signin",
                "/login",
                "challenge",
                "ServiceLogin",
                "identifier",
                "google.com/sorry",    # CAPTCHA / bot-detection page
                "google.com/recaptcha",
            ]
            for pattern in no_login_patterns:
                if pattern in url:
                    _dbg(f"No logado → patrón '{pattern}' en URL")
                    return False

            # La URL base debe ser gemini.google.com (no solo en parámetros)
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if "gemini.google.com" in parsed.netloc:
                _dbg("Logado (URL gemini sin login)")
                return True

            if url in ("", "about:blank", "chrome://newtab/"):
                _dbg("Página en blanco/cargando")
                return False

            _dbg(f"URL desconocida: {url}")
            return False

        except Exception as e:
            _dbg(f"Excepción en _is_logged_in: {e}")
            return False

    # ── Preparación del chat ──────────────────────────────────────────────────

    async def _prepare_chat(self):
        """Navega a /app y cierra posibles modales."""
        try:
            current = self._page.url
            if "/app" not in current:
                _dbg("Navegando a /app...")
                await self._page.goto(self.URL, wait_until="domcontentloaded", timeout=25000)
                await asyncio.sleep(3)

            # Cerrar posibles modales de bienvenida
            for sel in [
                'button[aria-label="Close"]',
                'button[aria-label="Dismiss"]',
                'button[aria-label="Got it"]',
                'mat-dialog-container button:first-of-type',
            ]:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.4)
                except Exception:
                    pass

            _dbg("Chat preparado")
        except Exception as e:
            _dbg(f"_prepare_chat error (no crítico): {e}")

    async def select_model(self, model_name: str) -> bool:
        """Selecciona un modelo en Gemini usando el desplegable de modelos."""
        self._current_model = model_name
        if self._page is None:
            return False
        try:
            # 1. Encontrar y hacer clic en el botón del selector de modelos
            model_btn_sels = [
                'button[data-test-id="bard-mode-menu-button"]',
                'button[aria-label*="selector de modo" i]',
                'button[aria-label*="model" i]',
                'button[aria-label*="Model" i]',
            ]
            clicked = False
            for sel in model_btn_sels:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.8)
                        clicked = True
                        break
                except Exception:
                    pass

            if clicked:
                # 2. Buscar la opción del modelo por su texto en gem-menu-item u otros elementos
                option_sels = [
                    f'gem-menu-item:has-text("{model_name}")',
                    f'[role="menuitem"]:has-text("{model_name}")',
                    f'[role="option"]:has-text("{model_name}")',
                    f'button:has-text("{model_name}")',
                ]
                for opt_sel in option_sels:
                    try:
                        opt = await self._page.query_selector(opt_sel)
                        if opt and await opt.is_visible():
                            await opt.click()
                            await asyncio.sleep(1.0)
                            _dbg(f"Modelo seleccionado con éxito: {model_name}")
                            return True
                    except Exception:
                        pass
                
                # Si no pudo hacer clic, cerrar el menú presionando Escape
                _dbg(f"No se pudo hacer clic en la opción del modelo {model_name}, cerrando menú...")
                await self._page.keyboard.press('Escape')

            _dbg(f"Modelo guardado localmente (sin cambios en UI): {model_name}")
            return True
        except Exception as e:
            _dbg(f"Error al seleccionar modelo: {e}")
            return True

    async def _attach_file(self, file_path: str) -> bool:
        """Adjunta un archivo en la interfaz de Gemini con trazado detallado."""
        from pathlib import Path as _Path
        if not _Path(file_path).exists():
            _dbg(f"[Paso 0] Archivo no encontrado: {file_path}")
            return False

        try:
            # 1. Encontrar y hacer clic en el botón de subidas/añadir (+)
            _dbg("[Paso 1/3] Buscando el botón de subidas (+)...")
            upload_btn = None
            
            # Buscar el icono de suma directamente (pierce shadow DOMs)
            icon = await self._page.query_selector('mat-icon[fonticon="plus"], mat-icon[data-mat-icon-name="plus"]')
            if icon:
                _dbg("  Icono '+' encontrado. Obteniendo botón superior...")
                try:
                    upload_btn = await self._page.evaluate_handle('(el) => el.closest("button")', icon)
                except Exception as e:
                    _dbg(f"  Fallo al resolver botón contenedor del icono: {e}")

            # Fallback a selectores directos
            if not upload_btn:
                _dbg("  Buscando por selectores alternativos del botón...")
                upload_btn_sels = [
                    'button[aria-label*="Subidas" i]',
                    'button[aria-label*="Upload" i]',
                    'button:has(mat-icon[fonticon="plus"])',
                    'button:has(mat-icon[data-mat-icon-name="plus"])',
                ]
                for sel in upload_btn_sels:
                    try:
                        btn = await self._page.query_selector(sel)
                        if btn and await btn.is_visible():
                            upload_btn = btn
                            _dbg(f"  Botón encontrado con selector: {sel}")
                            break
                    except Exception:
                        pass

            if not upload_btn:
                _dbg("ERROR: No se pudo localizar el botón '+' de subidas.")
                return False

            _dbg("  Haciendo clic en el botón '+'...")
            await upload_btn.click()
            await asyncio.sleep(0.8)

            # 2. Buscar la opción 'Subir archivos' / 'Upload' en el menú flotante
            _dbg("[Paso 2/3] Buscando opción de subir en el menú flotante con locators específicos...")
            import re as _re
            subir_item = self._page.locator('gem-menu-item, [role="menuitem"], .mat-mdc-menu-item, button[role="menuitem"]').filter(has_text=_re.compile("subir|upload", _re.IGNORECASE)).first

            # 3. Interceptar el File Chooser y cargar el archivo
            _dbg("[Paso 3/3] Abriendo cargador de archivos del sistema...")
            async with self._page.expect_file_chooser(timeout=5000) as fc_info:
                await subir_item.click()
            fc = await fc_info.value
            await fc.set_files(file_path)
            _dbg(f"¡ARCHIVO ADJUNTADO CON ÉXITO! Ruta: {file_path}")
            await asyncio.sleep(1.5)
            return True

        except Exception as e:
            _dbg(f"EXCEPCIÓN al adjuntar archivo en Gemini: {e}")
            return False

    # ── Buscar input de Gemini ────────────────────────────────────────────────

    async def _find_input(self):
        """
        Busca el área de texto de Gemini probando múltiples estrategias.
        Gemini usa Shadow DOM y custom elements (rich-textarea).
        """
        # Estrategia 1: selectores directos (julio 2026)
        direct_sels = [
            'rich-textarea div[contenteditable="true"]',
            'rich-textarea .ql-editor',
            '.input-area-container div[contenteditable="true"]',
            '.text-input-field div[contenteditable="true"]',
            'div[contenteditable="true"].ql-editor',
            'div[contenteditable="true"][data-placeholder]',
            'div[contenteditable="true"]',
            'textarea[aria-label]',
            'textarea',
        ]
        for sel in direct_sels:
            try:
                el = await self._page.wait_for_selector(sel, timeout=4000, state="visible")
                if el:
                    _dbg(f"Input encontrado (directo): {sel}")
                    return el
            except Exception:
                pass

        # Estrategia 2: via JavaScript evaluando el DOM completo
        try:
            el = await self._page.evaluate_handle("""() => {
                // Buscar en el DOM plano primero
                const selectors = [
                    'rich-textarea div[contenteditable="true"]',
                    'div[contenteditable="true"]',
                    'textarea'
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) return el;
                }
                // Buscar en Shadow DOM de rich-textarea
                const richTextarea = document.querySelector('rich-textarea');
                if (richTextarea && richTextarea.shadowRoot) {
                    const inner = richTextarea.shadowRoot.querySelector('div[contenteditable="true"], .ql-editor');
                    if (inner) return inner;
                }
                return null;
            }""")
            if el and await el.evaluate("el => el !== null"):
                _dbg("Input encontrado (JS evaluate)")
                return el
        except Exception as e:
            _dbg(f"JS evaluate fallido: {e}")

        return None

    # ── Envío de mensaje ──────────────────────────────────────────────────────

    async def send_message(self, message: str, file_path: str | None = None) -> str:
        if not self._is_ready or not self._page:
            raise RuntimeError("El bot no está listo. Inicia sesión primero.")

        try:
            self._emit_status("Enviando mensaje...")
            _dbg(f"Enviando: {message[:60]}...")

            # Asegurar que la página de Gemini está activa
            await self._page.bring_to_front()
            await asyncio.sleep(0.5)

            if file_path:
                await self._attach_file(file_path)
                await asyncio.sleep(0.5)

            input_el = await self._find_input()

            if not input_el:
                # Último recurso: navegar de nuevo a /app y reintentar
                _dbg("Input no encontrado, recargando /app...")
                await self._page.goto(self.URL, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(3)
                input_el = await self._find_input()

            if not input_el:
                raise RuntimeError("No se encontró el área de texto de Gemini.")

            # Click en el input
            try:
                await input_el.click()
            except Exception:
                await self._page.evaluate("el => el.focus()", input_el)
            await asyncio.sleep(random.uniform(0.3, 0.5))

            # Limpiar contenido previo
            await self._page.keyboard.press("Control+a")
            await asyncio.sleep(0.1)
            await self._page.keyboard.press("Delete")
            await asyncio.sleep(0.2)

            # Escribir el mensaje
            if len(message) > 300:
                # Mensajes largos: usar execCommand('insertText') para disparar
                # correctamente los eventos de input del editor rico de Gemini (QuillJS).
                # keyboard.type(delay=0) es demasiado rápido y los omite.
                inserted = await self._page.evaluate("""
                    (text) => {
                        const sels = [
                            'rich-textarea div[contenteditable="true"]',
                            'div[contenteditable="true"].ql-editor',
                            'div[contenteditable="true"]',
                        ];
                        let el = null;
                        for (const s of sels) { el = document.querySelector(s); if (el) break; }
                        if (!el) return false;
                        el.focus();
                        document.execCommand('selectAll', false, null);
                        document.execCommand('insertText', false, text);
                        return true;
                    }
                """, message)
                await asyncio.sleep(0.5)
                if inserted:
                    _dbg(f"Mensaje insertado via execCommand ({len(message)} chars)")
                else:
                    _dbg("execCommand fallo, usando typing rapido")
                    await self._page.keyboard.type(message, delay=0)
                    await asyncio.sleep(0.3)
            else:
                # Typing humano para mensajes cortos del chat normal
                for char in message:
                    await self._page.keyboard.type(char, delay=random.randint(25, 65))

            await asyncio.sleep(random.uniform(0.3, 0.6))

            # Intentar botón de envío
            sent = False
            send_sels = [
                'button.send-button',
                'button[aria-label="Send message"]',
                'button[aria-label="Enviar mensaje"]',
                'button[data-mat-icon-name="send"]',
                '[aria-label*="Send" i]',
                'button[type="submit"]',
            ]
            for sel in send_sels:
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

            self._emit_status("Esperando respuesta de Gemini...")
            response = await self._wait_for_response()
            self._emit_message(response)
            self._emit_status("Listo")
            return response

        except Exception as e:
            err = f"Error al enviar mensaje a Gemini: {e}"
            _dbg(err)
            self._emit_error(err)
            raise RuntimeError(err)

    # ── Esperar y extraer respuesta ───────────────────────────────────────────

    async def _wait_for_response(self) -> str:
        """Espera a que Gemini genere la respuesta completa y la extrae."""
        loading_sels = [
            'button[aria-label="Stop response"]',
            'button[aria-label="Detener respuesta"]',
            '[aria-label*="Generating" i]',
            '[aria-label*="Generando" i]',
            '.loading-indicator',
            'response-loading-indicator',
        ]

        # Espera inicial para que Gemini empiece a procesar
        await asyncio.sleep(3)

        # Esperar hasta 120s a que termine de generar
        for attempt in range(240):
            await asyncio.sleep(0.5)
            still_loading = False
            for sel in loading_sels:
                try:
                    el = await self._page.query_selector(sel)
                    if el and await el.is_visible():
                        still_loading = True
                        break
                except Exception:
                    pass
            if not still_loading and attempt >= 5:
                break

        await asyncio.sleep(2)

        # Selectores de respuesta - de más específico a más genérico
        response_sels = [
            'model-response .markdown-main-panel',
            'model-response .response-content',
            'model-response',
            '.response-container-content',
            '.model-response-text',
            '.markdown-main-panel',
            '[data-response-index]',
            '.response-content',
            'message-content',
            '.message-content',
            '.ng-star-inserted p',
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

        # Fallback JS: buscar cualquier contenedor con texto relevante
        try:
            text = await self._page.evaluate("""() => {
                const containers = document.querySelectorAll(
                    'model-response, .response-container, .model-response-text, message-content'
                );
                if (containers.length > 0) {
                    return containers[containers.length - 1].innerText;
                }
                return '';
            }""")
            if text and text.strip():
                _dbg("Respuesta extraída via JS fallback")
                return text.strip()
        except Exception:
            pass

        # Fallback JS agresivo: buscar el último bloque de texto largo en la página
        try:
            text = await self._page.evaluate("""() => {
                // Buscar todos los párrafos y divs con contenido sustancial
                const els = [...document.querySelectorAll('p, div[class], span[class]')];
                const candidates = els.filter(el => {
                    const t = (el.innerText || '').trim();
                    return t.length > 20 && el.children.length < 5;
                });
                if (candidates.length > 0) {
                    return candidates[candidates.length - 1].innerText.trim();
                }
                return '';
            }""")
            if text and text.strip() and len(text.strip()) > 20:
                _dbg("Respuesta extraída via JS agresivo")
                return text.strip()
        except Exception:
            pass

        # Último recurso: guardar el HTML de la página para diagnóstico
        try:
            from pathlib import Path as _Path
            html = await self._page.content()
            dump_path = _Path(__file__).parent.parent.parent / "debug_gemini_page.html"
            dump_path.write_text(html, encoding="utf-8")
            _dbg(f"HTML de la página guardado en: {dump_path}")
        except Exception as e:
            _dbg(f"No se pudo guardar el HTML: {e}")

        _dbg("No se pudo extraer respuesta")
        return ""
