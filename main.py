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


def main():
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
    sys.exit(ret)


if __name__ == "__main__":
    main()
