"""
Ventana principal de Tabasco.
Orquesta la sidebar, el chat widget y la comunicación con los bots.
Todos los workers usan bot.run() (loop persistente del bot) para garantizar
que Playwright siempre opera en el mismo loop donde creó el browser.
"""
import sys
import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QTextEdit, QPushButton, QFrame, QSizePolicy,
    QComboBox, QFileDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QKeyEvent, QFont, QPixmap, QShortcut, QKeySequence

from gui.sidebar import Sidebar, AVAILABLE_BOTS
from gui.chat_widget import ChatWidget
from gui.login_window import LoginWindow
from gui.history_panel import HistoryPanel
from gui.code_widget import CodeWidget
from core.bots.gemini import GeminiBot
from core.bots.chatgpt import ChatGPTBot
from core.bots.claude import ClaudeBot
from core.bots.copilot import CopilotBot
from core.bots.deepseek import DeepSeekBot
from core import history as hist

BOT_CLASSES = {
    "gemini":   GeminiBot,
    "chatgpt":  ChatGPTBot,
    "claude":   ClaudeBot,
    "copilot":  CopilotBot,
    "deepseek": DeepSeekBot,
}

# Ruta al archivo de configuración de agentes persistidos
_CONFIG_PATH = Path(__file__).parent.parent / "data" / "agents.json"


def _fmt_hist_date(session_id: str) -> str:
    """Formatea el ID de sesión (AAAAMMDD_HHMMSS) en una fecha legible."""
    try:
        from datetime import datetime
        dt = datetime.strptime(session_id, "%Y%m%d_%H%M%S")
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return session_id



# ─── Workers ──────────────────────────────────────────────────────────────────
# IMPORTANTE: todos usan bot.run(coro) en lugar de crear loops propios.
# bot.run() usa el loop persistente del bot (ProactorEventLoop en Windows).

class BotStartWorker(QThread):
    """Intenta iniciar el bot en modo headless (con sesión guardada)."""
    success    = pyqtSignal()
    need_login = pyqtSignal()
    error      = pyqtSignal(str)
    status     = pyqtSignal(str)

    def __init__(self, bot, parent=None):
        super().__init__(parent)
        self.bot = bot

    def run(self):
        try:
            self.bot.set_on_status(lambda s: self.status.emit(s))
            ok = self.bot.run(self.bot.start_headless())
            if ok:
                self.success.emit()
            else:
                self.need_login.emit()
        except Exception as e:
            self.error.emit(str(e))


class BotSendWorker(QThread):
    """Envía un mensaje al bot y recibe la respuesta."""
    response = pyqtSignal(str)
    error    = pyqtSignal(str)
    status   = pyqtSignal(str)

    def __init__(self, bot, message: str, file_path: str = "", parent=None):
        super().__init__(parent)
        self.bot = bot
        self.message = message
        self.file_path = file_path or None

    def run(self):
        try:
            self.bot.set_on_status(lambda s: self.status.emit(s))
            self.bot.set_on_message(lambda m: self.response.emit(m))
            self.bot.set_on_error(lambda e: self.error.emit(e))
            self.bot.run(self.bot.send_message(self.message, self.file_path))
        except Exception as e:
            self.error.emit(str(e))


class ModelSelectWorker(QThread):
    """Cambia el modelo activo en el bot (operación de Playwright)."""
    success = pyqtSignal(str)  # model_name
    error   = pyqtSignal(str)

    def __init__(self, bot, model_name: str, parent=None):
        super().__init__(parent)
        self.bot = bot
        self.model_name = model_name

    def run(self):
        try:
            ok = self.bot.run(self.bot.select_model(self.model_name))
            if ok:
                self.success.emit(self.model_name)
            else:
                self.error.emit(f"No se pudo seleccionar {self.model_name}")
        except Exception as e:
            self.error.emit(str(e))


class BotNavigateWorker(QThread):
    """Navega a una URL específica en el navegador del bot (restaurar historial)."""
    done   = pyqtSignal(bool)
    status = pyqtSignal(str)

    def __init__(self, bot, url: str, parent=None):
        super().__init__(parent)
        self.bot = bot
        self.url = url

    def run(self):
        try:
            self.bot.set_on_status(lambda s: self.status.emit(s))
            ok = self.bot.run(self.bot.load_session_url(self.url))
            self.done.emit(ok)
        except Exception:
            self.done.emit(False)


class BotPrepareWorker(QThread):
    """
    Prepara el chat usando el navegador YA ABIERTO tras el login.
    No cierra ni reinicia el browser.
    """
    success = pyqtSignal()
    error   = pyqtSignal(str)
    status  = pyqtSignal(str)

    def __init__(self, bot, parent=None):
        super().__init__(parent)
        self.bot = bot

    def run(self):
        try:
            self.bot.set_on_status(lambda s: self.status.emit(s))
            ok = self.bot.run(self.bot.prepare_after_login())
            if ok:
                self.success.emit()
            else:
                self.error.emit("No se pudo preparar el chat tras el login.")
        except Exception as e:
            self.error.emit(str(e))


class BotStopWorker(QThread):
    """Detiene el bot limpiamente."""
    done = pyqtSignal()

    def __init__(self, bot, parent=None):
        super().__init__(parent)
        self.bot = bot

    def run(self):
        try:
            self.bot.run(self.bot.stop())
        except Exception:
            pass
        finally:
            self.done.emit()


# ─── Input bar ──────────────────────────────────────────────────────────────────

class InputBar(QWidget):
    # Emite (texto, file_path) donde file_path puede ser ""
    message_sent = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("input_bar")
        self._file_path: str = ""
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 8, 16, 10)
        outer.setSpacing(4)

        # ─ Fila de preview de archivo (oculta por defecto) ─
        self._file_row = QWidget()
        self._file_row.setVisible(False)
        self._file_row.setStyleSheet("background: transparent;")
        fr_lay = QHBoxLayout(self._file_row)
        fr_lay.setContentsMargins(4, 0, 0, 0)
        fr_lay.setSpacing(6)

        self._file_lbl = QLabel()
        self._file_lbl.setStyleSheet(
            "color: #9c7070; font-size: 11px; background: transparent;"
        )
        self._file_clear_btn = QPushButton("✕")
        self._file_clear_btn.setFixedSize(16, 16)
        self._file_clear_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #5a2828; font-size: 10px; }"
            "QPushButton:hover { color: #e05050; }"
        )
        self._file_clear_btn.clicked.connect(self._clear_file)
        fr_lay.addWidget(self._file_lbl)
        fr_lay.addWidget(self._file_clear_btn)
        fr_lay.addStretch()
        outer.addWidget(self._file_row)

        # ─ Fila principal (adjuntar + input + enviar) ─
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(8)

        # Botón adjuntar
        self._attach_btn = QPushButton("📎")
        self._attach_btn.setFixedSize(42, 48)
        self._attach_btn.setToolTip("Adjuntar imagen o archivo")
        self._attach_btn.setStyleSheet(
            "QPushButton { background: #140606; border: 1px solid #2e1010; border-radius: 12px;"
            "color: #7a4040; font-size: 16px; }"
            "QPushButton:hover { background: #1e0a0a; border-color: #6b1e1e; color: #c06060; }"
            "QPushButton:disabled { color: #2a1010; border-color: #160606; }"
        )
        self._attach_btn.clicked.connect(self._on_attach)
        row_lay.addWidget(self._attach_btn)

        self._input = QTextEdit()
        self._input.setObjectName("message_input")
        self._input.setPlaceholderText(
            "Escribe un mensaje…  (↵ Enter para enviar  ·  Shift+Enter para nueva línea)"
        )
        self._input.setFixedHeight(48)
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._input.installEventFilter(self)
        self._input.textChanged.connect(self._on_text_changed)
        row_lay.addWidget(self._input)

        self._btn = QPushButton("Enviar ↑")
        self._btn.setObjectName("send_button")
        self._btn.setFixedSize(84, 48)
        self._btn.clicked.connect(self._send)
        self._btn.setEnabled(False)
        row_lay.addWidget(self._btn)

        outer.addWidget(row)

    def _on_text_changed(self):
        has_text = bool(self._input.toPlainText().strip())
        self._btn.setEnabled(has_text or bool(self._file_path))

    def eventFilter(self, obj, event):
        if obj is self._input and isinstance(event, QKeyEvent):
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self._send()
                    return True
        return super().eventFilter(obj, event)

    def _on_attach(self):
        """Abre diálogo para seleccionar un archivo."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar archivo para adjuntar",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.svg);;"
            "Documentos (*.pdf *.txt *.md *.csv *.docx *.xlsx);;"
            "Todos los archivos (*.*)"
        )
        if file_path:
            self._file_path = file_path
            name = Path(file_path).name
            display = name[:35] + "…" if len(name) > 35 else name
            self._file_lbl.setText(f"📎 {display}")
            self._file_row.setVisible(True)
            self._btn.setEnabled(True)

    def _clear_file(self):
        self._file_path = ""
        self._file_lbl.setText("")
        self._file_row.setVisible(False)
        self._on_text_changed()

    def _send(self):
        text = self._input.toPlainText().strip()
        file_path = self._file_path
        if text or file_path:
            self._input.clear()
            self._btn.setEnabled(False)
            self._clear_file()
            self.message_sent.emit(text, file_path)

    def set_enabled(self, v: bool):
        self._input.setEnabled(v)
        self._attach_btn.setEnabled(v)
        if not v:
            self._btn.setEnabled(False)
        else:
            self._on_text_changed()

    def focus(self):
        self._input.setFocus()


# ─── Placeholder ──────────────────────────────────────────────────────────────

class PlaceholderWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("placeholder_widget")
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(0)

        lay.addStretch()

        # Tarjeta central con logo
        card = QWidget()
        card.setFixedSize(300, 300)
        card.setStyleSheet(
            "QWidget { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #150606, stop:1 #0d0303);"
            "border: 1px solid #2e1010; border-radius: 20px; }"
        )
        card_lay = QVBoxLayout(card)
        card_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.setSpacing(16)
        card_lay.setContentsMargins(24, 24, 24, 24)

        # Logo
        logo_path = Path(__file__).parent.parent / "assets" / "icons" / "tabasco_logo_icon.png"
        if logo_path.exists():
            logo_lbl = QLabel()
            pixmap = QPixmap(str(logo_path)).scaled(
                110, 110,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            logo_lbl.setPixmap(pixmap)
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo_lbl.setStyleSheet("background:transparent; border:none;")
        else:
            logo_lbl = QLabel("[T]")
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo_lbl.setStyleSheet("font-size: 40px; color:#c0392b; font-weight:bold; background:transparent; border:none;")
        card_lay.addWidget(logo_lbl)

        title_lbl = QLabel("TABASCO")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            "color: #c0392b; font-size: 20px; font-weight: bold; "
            "letter-spacing: 6px; background:transparent; border:none;"
        )
        card_lay.addWidget(title_lbl)

        sub_lbl = QLabel("Terminal AI Bridge")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setStyleSheet(
            "color: #5a2525; font-size: 11px; letter-spacing: 1px; "
            "background:transparent; border:none;"
        )
        card_lay.addWidget(sub_lbl)

        lay.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(24)

        hint_lbl = QLabel("Selecciona  ＋ Añadir agente  en la barra lateral para comenzar")
        hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_lbl.setStyleSheet(
            "color: #3a1818; font-size: 12px; background:transparent;"
        )
        lay.addWidget(hint_lbl)

        bots_lbl = QLabel("Gemini  ·  ChatGPT  ·  Claude  ·  Copilot  ·  DeepSeek")
        bots_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bots_lbl.setStyleSheet(
            "color: #281010; font-size: 10px; letter-spacing: 1px; background:transparent;"
        )
        lay.addSpacing(6)
        lay.addWidget(bots_lbl)
        lay.addStretch()


# ─── Status bar ───────────────────────────────────────────────────────────────

class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("status_bar")
        self.setFixedHeight(24)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)

        self._lbl = QLabel("Listo")
        self._lbl.setStyleSheet("color: #4a1a1a; font-size: 11px;")
        lay.addWidget(self._lbl)
        lay.addStretch()

        self._bot_lbl = QLabel("")
        self._bot_lbl.setStyleSheet("color: #4a1a1a; font-size: 11px;")
        lay.addWidget(self._bot_lbl)

    def set_status(self, t: str):  self._lbl.setText(t)
    def set_bot(self, t: str):     self._bot_lbl.setText(t)


# ─── Main window ──────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._bots: dict[str, object] = {}
        self._workers: list = []
        self._active: str | None = None
        self._sending = False
        self._current_session_id: str | None = None   # ID de la sesión activa
        self._setup_ui()
        self._load_styles()
        self._restore_agents()   # ← cargar agentes persistidos al arrancar

    def _setup_ui(self):
        self.setWindowTitle("Tabasco — Terminal AI Bridge")
        self.setMinimumSize(900, 580)
        self.resize(1100, 720)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.bot_added.connect(self._on_bot_added)
        self._sidebar.bot_selected.connect(self._on_bot_selected)
        self._sidebar.bot_logout.connect(self._on_bot_logout)
        self._sidebar.bot_removed.connect(self._on_bot_removed)
        root.addWidget(self._sidebar)

        # ─ Zona central (header + chat + input) ─
        right = QWidget()
        r_lay = QVBoxLayout(right)
        r_lay.setContentsMargins(0, 0, 0, 0)
        r_lay.setSpacing(0)

        self._header = self._make_header()
        r_lay.addWidget(self._header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background:#1e0808; max-height:1px; border:none;")
        r_lay.addWidget(sep)

        self._placeholder = PlaceholderWidget()
        self._chat = ChatWidget()
        self._chat.setVisible(False)
        r_lay.addWidget(self._placeholder)
        r_lay.addWidget(self._chat)

        # ─ Panel de Tabasco Code (modo agente) ─
        self._code_widget = CodeWidget()
        self._code_widget.setVisible(False)
        r_lay.addWidget(self._code_widget)

        self._input_bar = InputBar()
        self._input_bar.message_sent.connect(self._on_send)
        self._input_bar.set_enabled(False)
        r_lay.addWidget(self._input_bar)

        self._status_bar = StatusBar()
        r_lay.addWidget(self._status_bar)

        root.addWidget(right)

        # ─ Panel de historial (se añade a la derecha del chat) ─
        self._history_panel = HistoryPanel()
        self._history_panel.setVisible(False)
        self._history_panel.panel_closed.connect(self._close_history)
        self._history_panel.session_selected.connect(self._on_session_load)
        self._history_panel.session_deleted.connect(self._on_session_deleted)
        root.addWidget(self._history_panel)

        # ─ Atajos de teclado ─
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self._on_new_conv)
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(self._toggle_history)

    def _make_header(self) -> QWidget:
        h = QWidget()
        h.setFixedHeight(52)
        h.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #0a0202, stop:1 #0d0404);"
            "border-bottom: 1px solid #1e0808;"
        )
        lay = QHBoxLayout(h)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(10)

        self._h_dot = QLabel("●")
        self._h_dot.setStyleSheet("color:#1e0606; font-size:12px;")

        name_col = QWidget()
        name_col.setStyleSheet("background:transparent;")
        name_lay = QVBoxLayout(name_col)
        name_lay.setContentsMargins(0, 0, 0, 0)
        name_lay.setSpacing(1)

        self._h_name = QLabel("Sin agente seleccionado")
        self._h_name.setStyleSheet(
            "color:#3a1515; font-size:14px; font-weight:bold; background:transparent;"
        )
        self._h_state = QLabel("")
        self._h_state.setStyleSheet(
            "color:#3a1515; font-size:10px; background:transparent;"
        )
        name_lay.addWidget(self._h_name)
        name_lay.addWidget(self._h_state)

        btn_new = QPushButton("✦  Nueva conversación")
        btn_new.setStyleSheet(
            "QPushButton { background: #140606; border: 1px solid #2e1010; border-radius: 8px;"
            "color: #5a2828; padding: 5px 14px; font-size: 11px; font-weight: 500; }"
            "QPushButton:hover { border-color: #7a1e1e; color: #c06060;"
            "background: #1e0a0a; }"
        )
        btn_new.clicked.connect(self._on_new_conv)

        # Combo de modelos (oculto hasta que el bot conecte)
        self._model_combo = QComboBox()
        self._model_combo.setFixedHeight(28)
        self._model_combo.setMinimumWidth(150)
        self._model_combo.setVisible(False)
        self._model_combo.setStyleSheet(
            "QComboBox { background: #140606; border: 1px solid #2e1010; border-radius: 6px;"
            "color: #7a5050; padding: 0 10px; font-size: 11px; }"
            "QComboBox:hover { border-color: #6b1e1e; color: #c06060; }"
            "QComboBox QAbstractItemView { background: #160808; border: 1px solid #3a1212;"
            "color: #e8d5d5; selection-background-color: #4a1515; }"
        )
        self._model_combo.currentTextChanged.connect(self._on_model_changed)

        self._btn_history = QPushButton("⦿  Historial")
        self._btn_history.setStyleSheet(
            "QPushButton { background: #140606; border: 1px solid #2e1010; border-radius: 8px;"
            "color: #5a2828; padding: 5px 14px; font-size: 11px; font-weight: 500; }"
            "QPushButton:hover { border-color: #7a1e1e; color: #c06060;"
            "background: #1e0a0a; }"
            "QPushButton:checked { background: #1e0808; border-color: #9b2424;"
            "color: #e05050; }"
        )
        self._btn_history.setCheckable(True)
        self._btn_history.setChecked(False)
        self._btn_history.clicked.connect(self._toggle_history)

        self._btn_delete = QPushButton("🗑  Borrar chat")
        self._btn_delete.setToolTip("Borrar esta conversación del historial local")
        self._btn_delete.setVisible(False)
        self._btn_delete.setStyleSheet(
            "QPushButton { background: #140606; border: 1px solid #2e1010; border-radius: 8px;"
            "color: #8a3535; padding: 5px 14px; font-size: 11px; font-weight: 500; }"
            "QPushButton:hover { border-color: #8b1a1a; color: #ff5555;"
            "background: #1e0a0a; }"
        )
        self._btn_delete.clicked.connect(self._on_delete_current_session)

        # Botón modo Tabasco Code
        self._btn_code = QPushButton("💻  Código")
        self._btn_code.setCheckable(True)
        self._btn_code.setChecked(False)
        self._btn_code.setStyleSheet(
            "QPushButton { background: #140606; border: 1px solid #2e1010; border-radius: 8px;"
            "color: #5a2828; padding: 5px 14px; font-size: 11px; font-weight: 500; }"
            "QPushButton:hover { border-color: #7a1e1e; color: #c06060; background: #1e0a0a; }"
            "QPushButton:checked { background: #0a1e0a; border-color: #1a6b1a; color: #66cc66; }"
        )
        self._btn_code.clicked.connect(self._toggle_code_mode)

        lay.addWidget(self._h_dot)
        lay.addWidget(name_col)
        lay.addStretch()
        lay.addWidget(self._model_combo)
        lay.addWidget(self._btn_code)
        lay.addWidget(self._btn_history)
        lay.addWidget(self._btn_delete)
        lay.addWidget(btn_new)
        return h

    def _load_styles(self):
        p = Path(__file__).parent / "styles.qss"
        if p.exists():
            self.setStyleSheet(p.read_text(encoding="utf-8"))

    # ── Persistencia de agentes ────────────────────────────────────────────────

    def _save_agents(self):
        """Guarda la lista de agentes añadidos en disco."""
        try:
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {"agents": list(self._bots.keys())}
            _CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(f"[Config] Agentes guardados: {data['agents']}", flush=True)
        except Exception as e:
            print(f"[Config] Error al guardar agentes: {e}", flush=True)

    def _restore_agents(self):
        """
        Carga los agentes guardados al arrancar.
        Solo añade los bots a la sidebar — NO intenta conectar ni abrir el navegador.
        El usuario tendrá que hacer clic en cada agente para conectar.
        """
        try:
            if not _CONFIG_PATH.exists():
                return
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            agents = data.get("agents", [])
            print(f"[Config] Restaurando agentes: {agents}", flush=True)
            for bot_name in agents:
                if bot_name not in BOT_CLASSES:
                    continue
                # Crear instancia del bot
                cls = BOT_CLASSES[bot_name]
                self._bots[bot_name] = cls()
                # Añadir a la sidebar sin disparar bot_added (para no hacer login)
                self._sidebar.add_bot(bot_name)
                # Marcar estado: si tiene sesión → "Sin conectar", si no → "Sin sesión"
                bot = self._bots[bot_name]
                if bot.has_session():
                    self._sidebar.set_bot_status(bot_name, "disconnected", "Clic para conectar")
                else:
                    self._sidebar.set_bot_status(bot_name, "disconnected", "Sin sesión")
            if agents:
                self._status_bar.set_status(f"{len(agents)} agente(s) restaurado(s) — haz clic para conectar")
        except Exception as e:
            print(f"[Config] Error al restaurar agentes: {e}", flush=True)

    # ── Bot lifecycle ──────────────────────────────────────────────────────────

    def _on_bot_added(self, bot_name: str):
        if bot_name not in self._bots:
            cls = BOT_CLASSES.get(bot_name)
            if cls:
                self._bots[bot_name] = cls()

        self._save_agents()  # ← persistir lista actualizada

        self._sidebar._set_active(bot_name)
        self._active = bot_name
        self._switch_to_chat(bot_name)

        # Si ya hay sesión guardada → intentar reconectar directo (sin login)
        bot = self._bots.get(bot_name)
        if bot and bot.has_session():
            self._try_headless(bot_name, bot)
        else:
            self._do_login(bot_name)

    def _on_bot_selected(self, bot_name: str):
        if bot_name == self._active and self._bots.get(bot_name) and self._bots[bot_name].is_ready:
            return

        self._active = bot_name
        bot = self._bots.get(bot_name)
        if not bot:
            return

        self._switch_to_chat(bot_name)

        if bot.is_ready:
            self._set_header_connected(bot_name)
            self._input_bar.set_enabled(True)
            self._input_bar.focus()
            self._populate_model_combo(bot)
            self._reset_bot_url(bot)
        elif bot.has_session():
            self._try_headless(bot_name, bot)
        else:
            self._do_login(bot_name)

    def _switch_to_chat(self, bot_name: str):
        info = AVAILABLE_BOTS.get(bot_name, {})
        name = info.get("display", bot_name)
        color = info.get("color", "#e05a5a")

        # Guardar sesión actual antes de cambiar
        self._save_current_session()

        # Si estamos en modo código, salir del modo código
        if self._btn_code.isChecked():
            self._btn_code.setChecked(False)

        self._placeholder.setVisible(False)
        self._chat.setVisible(True)
        self._code_widget.setVisible(False)
        self._chat.clear_messages()
        self._btn_delete.setVisible(True)
        self._input_bar.setVisible(True)

        # Nueva sesión de historial
        self._current_session_id = hist.new_session_id()

        # Punto de color del bot en el header
        self._h_dot.setStyleSheet(f"color:{color}; font-size:12px;")
        self._h_name.setText(name)
        self._h_name.setStyleSheet(
            f"color:#e8d5d5; font-size:14px; font-weight:bold; background:transparent;"
        )
        self._h_state.setStyleSheet("color:#4a2828; font-size:10px; background:transparent;")
        self._status_bar.set_bot(name)
        # Ocultar combo de modelos al cambiar (se vuelve a mostrar cuando conecte)
        self._model_combo.setVisible(False)

    def _try_headless(self, bot_name: str, bot):
        self._sidebar.set_bot_status(bot_name, "loading")
        self._input_bar.set_enabled(False)
        self._h_state.setText("Conectando...")
        self._h_state.setStyleSheet("color:#c0832b; font-size:11px;")
        self._status_bar.set_status("Conectando...")

        w = BotStartWorker(bot)
        w.success.connect(lambda: self._on_headless_ok(bot_name))
        w.need_login.connect(lambda: self._do_login(bot_name))
        w.error.connect(lambda e: self._on_bot_error(bot_name, e))
        w.status.connect(lambda s: self._status_bar.set_status(s))
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(w)
        w.start()

    def _on_headless_ok(self, bot_name: str):
        if bot_name != self._active:
            return
        self._sidebar.set_bot_status(bot_name, "connected")
        self._set_header_connected(bot_name)
        self._input_bar.set_enabled(True)
        self._input_bar.focus()
        self._status_bar.set_status("Listo")
        # Poblar combo de modelos
        bot = self._bots.get(bot_name)
        if bot:
            self._populate_model_combo(bot)
            # Propagar bot activo al widget de código
            self._code_widget.set_bot(bot)

    def _toggle_code_mode(self):
        """Alterna entre el chat normal y el modo Tabasco Code."""
        code_active = self._btn_code.isChecked()
        if code_active:
            # Entrar en modo código: ocultar chat e input_bar, mostrar CodeWidget
            self._chat.setVisible(False)
            self._placeholder.setVisible(False)
            self._input_bar.setVisible(False)
            self._btn_history.setVisible(False)
            self._btn_delete.setVisible(False)
            self._code_widget.setVisible(True)
            # Sincronizar el bot activo si está conectado
            bot = self._bots.get(self._active) if self._active else None
            if bot and bot.is_ready:
                self._code_widget.set_bot(bot)
            self._status_bar.set_status("💻 Tabasco Code activo")
        else:
            # Volver al modo chat
            self._code_widget.setVisible(False)
            self._input_bar.setVisible(True)
            self._btn_history.setVisible(True)
            if self._active and self._bots.get(self._active):
                self._chat.setVisible(True)
                self._btn_delete.setVisible(True)
            else:
                self._placeholder.setVisible(True)
            self._status_bar.set_status("Listo")

    def _do_login(self, bot_name: str):
        bot = self._bots.get(bot_name)
        if not bot:
            return

        self._sidebar.set_bot_status(bot_name, "loading", "Esperando login")
        self._input_bar.set_enabled(False)
        self._h_state.setText("Sesión requerida")
        self._h_state.setStyleSheet("color:#c0832b; font-size:11px;")

        dlg = LoginWindow(bot, self)
        dlg.login_completed.connect(lambda ok: self._on_login_done(bot_name, bot, ok))
        dlg.exec()

    def _on_login_done(self, bot_name: str, bot, success: bool):
        if success:
            self._sidebar.set_bot_status(bot_name, "loading")
            self._h_state.setText("Preparando chat...")
            self._h_state.setStyleSheet("color:#c0832b; font-size:11px;")
            self._status_bar.set_status("Preparando chat...")

            w = BotPrepareWorker(bot)
            w.success.connect(lambda: self._on_headless_ok(bot_name))
            w.error.connect(lambda e: self._on_bot_error(bot_name, e))
            w.status.connect(lambda s: self._status_bar.set_status(s))
            w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
            self._workers.append(w)
            w.start()
        else:
            self._sidebar.set_bot_status(bot_name, "disconnected")
            self._h_state.setText("Sin sesión")
            self._h_state.setStyleSheet("color:#6a3535; font-size:11px;")
            if bot_name == self._active:
                self._chat.add_error_message("Login cancelado. Haz clic en el agente para intentarlo de nuevo.")

    def _on_bot_error(self, bot_name: str, error: str):
        self._sidebar.set_bot_status(bot_name, "error")
        self._h_state.setText("Error")
        self._h_state.setStyleSheet("color:#8b2a2a; font-size:11px;")
        self._sending = False
        self._input_bar.set_enabled(True)
        if bot_name == self._active:
            self._chat.add_error_message(error)
        self._status_bar.set_status("Error")

    def _on_bot_logout(self, bot_name: str):
        bot = self._bots.get(bot_name)
        if not bot:
            return
        stop_w = BotStopWorker(bot)
        def after_stop():
            bot.clear_session()
            self._sidebar.set_bot_status(bot_name, "disconnected")
            if bot_name == self._active:
                self._input_bar.set_enabled(False)
                self._h_state.setText("Sesión cerrada")
                self._h_state.setStyleSheet("color:#6a3535; font-size:11px;")
                self._model_combo.setVisible(False)
                self._chat.add_error_message("Sesión cerrada. Haz clic en el agente para iniciar sesión de nuevo.")
        stop_w.done.connect(after_stop)
        stop_w.finished.connect(lambda: self._workers.remove(stop_w) if stop_w in self._workers else None)
        self._workers.append(stop_w)
        stop_w.start()

    def _on_bot_removed(self, bot_name: str):
        bot = self._bots.pop(bot_name, None)
        self._save_agents()  # ← persistir lista actualizada
        if bot:
            stop_w = BotStopWorker(bot)
            stop_w.done.connect(lambda: bot.destroy())
            stop_w.finished.connect(lambda: self._workers.remove(stop_w) if stop_w in self._workers else None)
            self._workers.append(stop_w)
            stop_w.start()
        if self._active == bot_name:
            self._active = None
            self._placeholder.setVisible(True)
            self._chat.setVisible(False)
            self._h_name.setText("Sin agente seleccionado")
            self._h_name.setStyleSheet("color:#4a1a1a; font-size:14px; font-weight:bold;")
            self._h_state.setText("")
            self._h_dot.setStyleSheet("color:#2a0808; font-size:10px;")
            self._input_bar.set_enabled(False)
            self._model_combo.setVisible(False)
            self._btn_delete.setVisible(False)
            self._status_bar.set_bot("")

    # ── Mensajes ───────────────────────────────────────────────────────────────

    def _on_send(self, text: str, file_path: str = ""):
        if not self._active or self._sending:
            return
        bot = self._bots.get(self._active)
        if not bot or not bot.is_ready:
            self._chat.add_error_message("El agente no está listo. Espera a que conecte o inicia sesión.")
            return

        self._sending = True
        self._input_bar.set_enabled(False)
        bot_name = self._active

        info = AVAILABLE_BOTS.get(bot_name, {})
        display = info.get("display", bot_name)

        # Mostrar mensaje de usuario (con indicador de archivo si hay)
        display_text = text
        if file_path and not text:
            display_text = f"📎 {Path(file_path).name}"
        elif file_path:
            display_text = f"{text}\n📎 {Path(file_path).name}"

        self._chat.add_user_message(display_text)
        self._chat.show_typing_indicator(display)
        self._status_bar.set_status("Enviando...")

        w = BotSendWorker(bot, text, file_path)
        w.response.connect(lambda msg: self._on_response(bot_name, msg, display))
        w.error.connect(lambda e: self._on_send_error(bot_name, e))
        w.status.connect(lambda s: self._status_bar.set_status(s))
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(w)
        w.start()

    def _on_response(self, bot_name: str, msg: str, display: str):
        self._sending = False
        self._chat.add_bot_message(msg, display)
        self._input_bar.set_enabled(True)
        self._input_bar.focus()
        self._status_bar.set_status("Listo")
        self._save_current_session()

    def _on_send_error(self, bot_name: str, error: str):
        self._sending = False
        self._chat.add_error_message(f"Error: {error}")
        self._input_bar.set_enabled(True)
        self._status_bar.set_status("Error al enviar")

    def _on_delete_current_session(self):
        """Borra la conversación activa del historial local de Tabasco."""
        if self._active and self._current_session_id:
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "Borrar conversación",
                "¿Estás seguro de que deseas borrar esta conversación de la app?\nEsto no afectará al navegador.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                hist.delete_session(self._active, self._current_session_id)
                self._chat.clear_messages()
                self._current_session_id = hist.new_session_id()
                self._status_bar.set_status("Conversación borrada")
                
                # Resetear navegador
                bot = self._bots.get(self._active)
                if bot and bot.is_ready:
                    self._reset_bot_url(bot)
                    
                # Refrescar historial si está visible
                if self._history_panel.isVisible():
                    info = AVAILABLE_BOTS.get(self._active, {})
                    self._history_panel.load_for_bot(self._active, info.get("display", self._active))

    def _reset_bot_url(self, bot):
        """Navega al bot a su URL base de nueva conversación en segundo plano."""
        if not bot or not bot.is_ready:
            return
        self._status_bar.set_status("Reseteando conversación en el navegador...")
        w = BotNavigateWorker(bot, bot.URL)
        w.status.connect(lambda s: self._status_bar.set_status(s))
        w.done.connect(
            lambda ok: self._status_bar.set_status(
                "Listo" if ok else "Nueva conversación (Solo visual)"
            )
        )
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(w)
        w.start()

    def _on_new_conv(self):
        if self._active:
            # Guardar sesión actual antes de limpiar
            self._save_current_session()
            self._chat.clear_messages()
            self._current_session_id = hist.new_session_id()
            self._status_bar.set_status("Nueva conversación")

            bot = self._bots.get(self._active)
            if bot and bot.is_ready:
                self._reset_bot_url(bot)

            # Refrescar historial si el panel está abierto
            if self._history_panel.isVisible() and self._active:
                info = AVAILABLE_BOTS.get(self._active, {})
                self._history_panel.load_for_bot(self._active, info.get("display", self._active))

    # ── Historial ──────────────────────────────────────────────────────────────────

    def _save_current_session(self):
        """Guarda la sesión activa en el historial si hay mensajes."""
        if self._active and self._current_session_id and self._chat.has_messages():
            try:
                bot = self._bots.get(self._active)
                url = bot.get_current_url() if bot else ""
                hist.save_session(
                    self._active,
                    self._current_session_id,
                    self._chat.get_messages(),
                    url=url
                )
                print(f"[History] Sesión guardada: {self._current_session_id} con URL: {url}", flush=True)
            except Exception as e:
                print(f"[History] Error al guardar: {e}", flush=True)

    def _toggle_history(self):
        """Abre/cierra el panel de historial."""
        visible = self._history_panel.isVisible()
        if not visible and self._active:
            info = AVAILABLE_BOTS.get(self._active, {})
            self._history_panel.load_for_bot(self._active, info.get("display", self._active))
            self._history_panel.setVisible(True)
            self._btn_history.setChecked(True)
        else:
            self._close_history()

    def _close_history(self):
        self._history_panel.setVisible(False)
        self._btn_history.setChecked(False)

    def _on_session_load(self, bot_name: str, session_id: str):
        """
        Carga una sesión del historial en el chat.
        Guarda la sesión actual primero, luego restaura la guardada.
        """
        # Buscar el bot_name interno (clave de AVAILABLE_BOTS) por display name
        internal_name = next(
            (k for k, v in AVAILABLE_BOTS.items() if v.get("display") == bot_name),
            self._active
        )
        if not internal_name:
            return
        # Guardar sesión actual
        self._save_current_session()
        
        # Cargar datos de la sesión seleccionada
        session_data = hist.load_session_full(internal_name, session_id)
        messages = session_data.get("messages", [])
        url = session_data.get("url", "")
        
        if messages:
            info = AVAILABLE_BOTS.get(internal_name, {})
            display = info.get("display", internal_name)
            self._chat.restore_messages(messages, bot_name=display)
            # Marcar como sesión actual (para no sobreescribirla si el usuario continua)
            self._current_session_id = session_id
            
            # Restaurar la conversación en el navegador de fondo si el bot está listo
            bot = self._bots.get(internal_name)
            if bot and bot.is_ready and url:
                self._status_bar.set_status("Restaurando conversación en el navegador...")
                w = BotNavigateWorker(bot, url)
                w.status.connect(lambda s: self._status_bar.set_status(s))
                w.done.connect(
                    lambda ok: self._status_bar.set_status(
                        f"Sesión del {_fmt_hist_date(session_id)} cargada (Activa)" if ok
                        else f"Sesión del {_fmt_hist_date(session_id)} cargada (Solo visual)"
                    )
                )
                w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
                self._workers.append(w)
                w.start()
            else:
                self._status_bar.set_status(f"Sesión del {_fmt_hist_date(session_id)} cargada (Solo visual)")

    def _on_session_deleted(self, internal_name: str, session_id: str):
        """Llamado cuando el usuario borra una sesión del panel de historial."""
        if not session_id:  # Significa que se vació todo el historial de este bot
            if self._active == internal_name:
                self._chat.clear_messages()
                self._current_session_id = hist.new_session_id()
        elif self._active == internal_name and self._current_session_id == session_id:
            self._chat.clear_messages()
            self._current_session_id = hist.new_session_id()

    # ── Modelo ──────────────────────────────────────────────────────────────────

    def _populate_model_combo(self, bot):
        """Rellena el combo de modelos con los del bot activo."""
        models = bot.get_models()
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        if models:
            self._model_combo.addItems(list(models.keys()))
            current = bot.get_current_model()
            if current and current in models:
                self._model_combo.setCurrentText(current)
            self._model_combo.setVisible(True)
        else:
            self._model_combo.setVisible(False)
        self._model_combo.blockSignals(False)

    def _on_model_changed(self, model_name: str):
        """Llamado cuando el usuario cambia el modelo en el combo."""
        if not model_name or not self._active:
            return
        bot = self._bots.get(self._active)
        if not bot or not bot.is_ready:
            return
        self._status_bar.set_status(f"Cambiando a {model_name}...")
        w = ModelSelectWorker(bot, model_name)
        w.success.connect(lambda m: self._status_bar.set_status(f"Modelo: {m}"))
        w.error.connect(lambda e: self._status_bar.set_status(f"Error al cambiar modelo"))
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(w)
        w.start()

    # ── Helpers ──────────────────────────────────────────────────────────────────

    def _set_header_connected(self, bot_name: str):
        self._h_state.setText("● Conectado")
        self._h_state.setStyleSheet(
            "color:#4a8b4a; font-size:10px; background:transparent;"
        )

    def closeEvent(self, event):
        self._save_current_session()
        for w in list(self._workers):
            try:
                if w.isRunning():
                    w.terminate()
                    w.wait(500)
            except Exception:
                pass
        for bot in self._bots.values():
            try:
                bot._is_ready = False
                bot.destroy()
            except Exception:
                pass
        super().closeEvent(event)
