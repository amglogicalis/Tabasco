"""
Ventana de login — abre navegador visible para que el usuario inicie sesión.
"""
import asyncio
import sys
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer


class LoginWorker(QThread):
    """Hilo que gestiona el proceso de login en background."""
    login_success = pyqtSignal()
    login_failed  = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, bot, parent=None):
        super().__init__(parent)
        self.bot = bot

    def run(self):
        # Usar el loop persistente del bot para que Playwright siempre
        # opere en el mismo loop donde fue creado el browser/page.
        try:
            self.bot.run(self._do_login())
        except Exception as e:
            self.login_failed.emit(str(e))

    async def _do_login(self):
        try:
            self.status_update.emit(f"Abriendo navegador para {self.bot.DISPLAY_NAME}…")
            await self.bot.start_headful_for_login()
            self.status_update.emit("Inicia sesión en el navegador que se ha abierto…")
            success = await self.bot.wait_for_login(timeout=180)
            if success:
                self.login_success.emit()
            else:
                self.login_failed.emit("Tiempo de espera agotado (3 min). Inténtalo de nuevo.")
        except Exception as e:
            self.login_failed.emit(str(e))


class LoginWindow(QDialog):
    """
    Diálogo que guía al usuario para hacer login en un chatbot.
    """
    login_completed = pyqtSignal(bool)

    def __init__(self, bot, parent=None):
        super().__init__(parent)
        self.bot = bot
        self._worker: LoginWorker | None = None
        self._finished = False   # Flag para evitar doble emisión de señales
        self._success = False    # Resultado final del login
        self._setup_ui()
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint
        )

    def _setup_ui(self):
        self.setWindowTitle(f"Iniciar sesión — {self.bot.DISPLAY_NAME}")
        self.setFixedSize(420, 310)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Cabecera ──
        header = QWidget()
        header.setStyleSheet("background:#0d0404; border-bottom:1px solid #3a1010;")
        h_lay = QVBoxLayout(header)
        h_lay.setContentsMargins(20, 14, 20, 12)
        h_lay.setSpacing(3)

        title = QLabel(f"Iniciar sesión en {self.bot.DISPLAY_NAME}")
        title.setStyleSheet("color:#e8d5d5; font-size:15px; font-weight:bold;")

        sub = QLabel("Se abrirá un navegador para que puedas acceder con tu cuenta")
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#7a4040; font-size:12px;")

        h_lay.addWidget(title)
        h_lay.addWidget(sub)
        layout.addWidget(header)

        # ── Cuerpo ──
        body = QWidget()
        body.setStyleSheet("background:#1a0808;")
        b_lay = QVBoxLayout(body)
        b_lay.setContentsMargins(20, 18, 20, 16)
        b_lay.setSpacing(12)

        # Pasos
        info = QWidget()
        info.setStyleSheet(
            "background:#200a0a; border:1px solid #4a1a1a; border-radius:8px;"
        )
        i_lay = QVBoxLayout(info)
        i_lay.setContentsMargins(14, 10, 14, 10)
        i_lay.setSpacing(5)

        for step in [
            "1. Haz clic en  Abrir navegador",
            f"2. Inicia sesión con tu cuenta de {self.bot.DISPLAY_NAME}",
            "3. Tabasco detectará el login automáticamente",
            "4. El navegador se cerrará solo y el chat estará listo",
        ]:
            lbl = QLabel(step)
            lbl.setStyleSheet("color:#8a5050; font-size:12px;")
            i_lay.addWidget(lbl)

        b_lay.addWidget(info)

        # Estado
        self._status_lbl = QLabel("Listo para iniciar sesión")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setStyleSheet("color:#6a3535; font-size:12px;")
        b_lay.addWidget(self._status_lbl)

        # Barra de progreso
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setFixedHeight(4)
        b_lay.addWidget(self._progress)

        # Botones
        btn_row = QWidget()
        btn_row.setStyleSheet("background:transparent;")
        br_lay = QHBoxLayout(btn_row)
        br_lay.setContentsMargins(0, 0, 0, 0)
        br_lay.setSpacing(10)

        self._cancel_btn = QPushButton("Cancelar")
        self._cancel_btn.setFixedHeight(36)
        self._cancel_btn.setStyleSheet(
            "QPushButton{background:#2a1010;border:1px solid #5a2020;border-radius:8px;"
            "color:#b08080;padding:0 16px;font-size:13px;}"
            "QPushButton:hover{background:#3a1515;border-color:#8b2a2a;}"
        )
        self._cancel_btn.clicked.connect(self._on_cancel)

        self._start_btn = QPushButton("Abrir navegador →")
        self._start_btn.setFixedHeight(36)
        self._start_btn.setStyleSheet(
            "QPushButton{background:#8b1a1a;border:none;border-radius:8px;"
            "color:white;padding:0 20px;font-size:13px;font-weight:bold;}"
            "QPushButton:hover{background:#c0392b;}"
            "QPushButton:disabled{background:#2a1010;color:#6a3535;}"
        )
        self._start_btn.clicked.connect(self._on_start)

        br_lay.addWidget(self._cancel_btn)
        br_lay.addStretch()
        br_lay.addWidget(self._start_btn)
        b_lay.addWidget(btn_row)

        layout.addWidget(body)

    # ── Lógica ────────────────────────────────────────────────────────────────

    def _on_start(self):
        self._start_btn.setEnabled(False)
        self._start_btn.setText("Esperando…")
        self._progress.setVisible(True)
        self._status_lbl.setText("Abriendo navegador…")
        self._status_lbl.setStyleSheet("color:#c0832b; font-size:12px;")

        self._worker = LoginWorker(self.bot)
        self._worker.status_update.connect(self._status_lbl.setText)
        self._worker.login_success.connect(self._on_success)
        self._worker.login_failed.connect(self._on_failed)
        self._worker.start()

    def _on_success(self):
        if self._finished:
            return
        self._progress.setVisible(False)
        self._status_lbl.setText("✅ ¡Sesión iniciada correctamente!")
        self._status_lbl.setStyleSheet("color:#4a8b4a; font-size:12px;")
        self._start_btn.setText("Cerrando navegador…")
        self._start_btn.setEnabled(False)
        # Cerrar automáticamente tras 1.2s — solo una vez via QTimer
        QTimer.singleShot(1200, lambda: self._finish(True))

    def _on_failed(self, error: str):
        self._progress.setVisible(False)
        self._status_lbl.setText(f"❌ {error}")
        self._status_lbl.setStyleSheet("color:#c0392b; font-size:12px;")
        self._start_btn.setEnabled(True)
        self._start_btn.setText("Reintentar")

    def _on_cancel(self):
        if self._finished:
            return
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(1000)
        self._finish(False)

    def _finish(self, success: bool):
        """Emite el resultado UNA sola vez y cierra el diálogo."""
        if self._finished:
            return
        self._finished = True
        self._success = success
        self.login_completed.emit(success)
        # Cerrar sin disparar closeEvent de nuevo (usamos hide en lugar de accept/reject)
        self.hide()
        if success:
            self.accept()
        else:
            self.reject()

    def closeEvent(self, event):
        """Sólo emite False si el login NO se completó con éxito."""
        if not self._finished:
            # Usuario cerró la ventana manualmente sin completar el login
            if self._worker and self._worker.isRunning():
                self._worker.terminate()
            self._finished = True
            self._success = False
            self.login_completed.emit(False)
        super().closeEvent(event)
