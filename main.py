"""
Tabasco - Terminal AI Bridge
Punto de entrada principal de la aplicación.
"""
import sys
import os
import asyncio
import warnings
from pathlib import Path

# Suprimir ResourceWarning al cerrar (normal en Windows con Playwright)
warnings.filterwarnings("ignore", category=ResourceWarning)
# NOTA: En Windows Playwright requiere ProactorEventLoop (defecto) para lanzar subprocesos.
# NO cambiar la política del event loop o Playwright fallará con NotImplementedError.

# Asegurar que el directorio raíz del proyecto esté en el path
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtCore import Qt

from gui.main_window import MainWindow


def limpiar_procesos_huerfanos():
    """
    Cierra cualquier proceso Chromium residual de Playwright sin ventana activa
    y borra los archivos temporales SingletonLock para evitar bloqueos del perfil.
    """
    if sys.platform != "win32":
        return
    try:
        import subprocess
        # Cerrar procesos Chromium huérfanos en segundo plano (sin ventana interactiva)
        subprocess.run(
            'taskkill /f /im chrome.exe /fi "WINDOWTITLE eq "" "',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        
        # Eliminar archivos SingletonLock de los perfiles de los bots
        profile_root = Path(os.environ.get('USERPROFILE', '')) / '.tabasco' / 'profiles'
        if profile_root.exists():
            for bot_dir in profile_root.iterdir():
                if bot_dir.is_dir():
                    lock_file = bot_dir / 'SingletonLock'
                    if lock_file.exists():
                        try:
                            lock_file.unlink(missing_ok=True)
                            print(f"[GarbageCollector] SingletonLock eliminado en: {bot_dir.name}", flush=True)
                        except Exception:
                            pass
    except Exception:
        pass


def main():
    # Limpiar procesos huérfanos antes del arranque
    limpiar_procesos_huerfanos()

    # Habilitar escalado de alta resolución
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Tabasco")
    app.setApplicationDisplayName("Tabasco — Terminal AI Bridge")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Tabasco")

    # Fuente por defecto
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Icono de la aplicación — usar logo PNG si no hay .ico
    icon_path = ROOT_DIR / "assets" / "icons" / "tabasco.ico"
    if not icon_path.exists():
        icon_path = ROOT_DIR / "assets" / "icons" / "tabasco_logo_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Crear y mostrar la ventana principal
    window = MainWindow()
    window.show()

    ret = app.exec()
    
    # Limpieza final al cerrar la app
    limpiar_procesos_huerfanos()
    sys.exit(ret)


if __name__ == "__main__":
    main()

