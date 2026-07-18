"""
scripts/run_monitor_test.py

Script automatizado de monitoreo continuo para Gemini.
Se ejecuta en GitHub Actions. Carga cookies de sesion desde variables de entorno,
envia un mensaje de prueba y verifica que la respuesta se extraiga correctamente.
Saliendo con exit code 1 en caso de fallo para disparar la alerta por correo.
"""

import asyncio
import os
import sys
import json
import tempfile
from pathlib import Path
from playwright.async_api import async_playwright

# Forzar imports locales de core
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.bots.gemini import GeminiBot


async def run_test():
    print("[Monitor] Iniciando test de robustez de Gemini...")
    
    # 1. Recuperar sesion desde secreto en GitHub Actions
    session_json = os.environ.get("GEMINI_SESSION_COOKIE")
    if not session_json:
        print("[Monitor] ERROR: Variable GEMINI_SESSION_COOKIE no configurada.")
        sys.exit(1)
        
    try:
        cookies = json.loads(session_json)
    except Exception as e:
        print(f"[Monitor] ERROR: El formato de cookies no es JSON valido: {e}")
        sys.exit(1)

    # 2. Inyectar cookies en un perfil de usuario temporal
    temp_dir = tempfile.TemporaryDirectory()
    profile_path = Path(temp_dir.name)
    
    # Estructura del profile de Playwright para cookies
    # Playwright guarda el estado de almacenamiento (auth) en un json
    state_file = profile_path / "state.json"
    state_data = {
        "cookies": cookies,
        "origins": []
    }
    state_file.write_text(json.dumps(state_data), encoding="utf-8")

    # 3. Lanzar Playwright en modo headless completo
    bot = GeminiBot()
    # Sobreescribimos internals para que use nuestro perfil temporal con las cookies inyectadas
    bot._browser_manager = None
    
    print("[Monitor] Lanzando Chromium headless...")
    async with async_playwright() as p:
        # Lanzar contexto con estado inyectado
        browser_context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        
        # Enlazar la pagina al bot
        page = browser_context.pages[0]
        bot._page = page
        bot._is_ready = True  # Asumimos que esta listo gracias a las cookies
        
        try:
            print("[Monitor] Navegando a Gemini app...")
            await page.goto(bot.URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            
            # Verificar si redirecciono a sorry page o login
            current_url = page.url
            print(f"[Monitor] URL tras carga: {current_url}")
            
            if "google.com/sorry" in current_url:
                print("[Monitor] ERROR: Google bloqueo la peticion (CAPTCHA Sorry page).")
                sys.exit(1)
                
            if "gemini.google.com" not in current_url or "signin" in current_url:
                print("[Monitor] ERROR: Sesion expirada o redireccion a login.")
                sys.exit(1)

            # Enviar mensaje de prueba
            test_msg = "Hello, respond with exactly: OK_TEST"
            print(f"[Monitor] Enviando mensaje de prueba: {test_msg!r}")
            
            response = await bot.send_message(test_msg)
            print(f"[Monitor] Respuesta extraida: {response!r}")
            
            if not response or not response.strip():
                print("[Monitor] ERROR: La respuesta de Gemini esta vacia o no pudo extraerse.")
                sys.exit(1)
                
            print("[Monitor] TEST PASADO CON EXITO. La infraestructura de Gemini sigue operativa.")
            
        except Exception as e:
            print(f"[Monitor] EXCEPCION DURANTE EL TEST: {e}")
            sys.exit(1)
        finally:
            await browser_context.close()
            temp_dir.cleanup()

if __name__ == "__main__":
    asyncio.run(run_test())
