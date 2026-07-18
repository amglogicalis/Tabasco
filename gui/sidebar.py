"""
Barra lateral con gestión dinámica de bots (el usuario añade los que quiere).
"""
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QDialog,
    QComboBox, QDialogButtonBox, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap

# Bots disponibles para añadir
AVAILABLE_BOTS = {
    "gemini":   {"display": "Gemini",   "color": "#e05a5a", "emoji": "✦", "desc": "Google Gemini"},
    "chatgpt":  {"display": "ChatGPT",  "color": "#e07a5a", "emoji": "◈", "desc": "OpenAI ChatGPT"},
    "claude":   {"display": "Claude",   "color": "#D97757", "emoji": "◆", "desc": "Anthropic Claude"},
    "copilot":  {"display": "Copilot",  "color": "#4D8FD4", "emoji": "◇", "desc": "Microsoft Copilot"},
    "deepseek": {"display": "DeepSeek", "color": "#4D6BFE", "emoji": "⬡", "desc": "DeepSeek AI"},
}

STATUS_COLORS = {
    "disconnected": "#6a3535",
    "loading":      "#c0832b",
    "connected":    "#4a8b4a",
    "error":        "#8b2a2a",
}
STATUS_LABELS = {
    "disconnected": "Sin sesión",
    "loading":      "Conectando...",
    "connected":    "Conectado",
    "error":        "Error",
}


class AddBotDialog(QDialog):
    """Diálogo para añadir un nuevo bot."""

    def __init__(self, already_added: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Añadir agente")
        self.setFixedSize(360, 220)
        self.setModal(True)
        self._selected = None
        self._setup_ui(already_added)

    def _setup_ui(self, already_added):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(14)

        title = QLabel("Añadir agente de IA")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #e8d5d5;")
        layout.addWidget(title)

        subtitle = QLabel("Selecciona el chatbot que quieres usar.\nDeberás iniciar sesión con tu cuenta.")
        subtitle.setStyleSheet("color: #a07070; font-size: 12px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self._combo = QComboBox()
        self._combo.setFixedHeight(38)
        for name, info in AVAILABLE_BOTS.items():
            if name not in already_added:
                self._combo.addItem(f"{info['emoji']}  {info['display']} — {info['desc']}", name)

        if self._combo.count() == 0:
            self._combo.addItem("Ya tienes todos los agentes añadidos", "")
            self._combo.setEnabled(False)

        layout.addWidget(self._combo)
        layout.addStretch()

        buttons = QHBoxLayout()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setFixedHeight(36)
        cancel_btn.clicked.connect(self.reject)

        self._ok_btn = QPushButton("Añadir agente →")
        self._ok_btn.setFixedHeight(36)
        self._ok_btn.setStyleSheet(
            "QPushButton { background: #8b1a1a; border: none; border-radius: 8px; "
            "color: white; font-weight: bold; padding: 0 16px; }"
            "QPushButton:hover { background: #c0392b; }"
            "QPushButton:disabled { background: #3a1010; color: #6a3535; }"
        )
        self._ok_btn.setEnabled(self._combo.isEnabled())
        self._ok_btn.clicked.connect(self.accept)

        buttons.addWidget(cancel_btn)
        buttons.addStretch()
        buttons.addWidget(self._ok_btn)
        layout.addLayout(buttons)

    def selected_bot(self) -> str:
        return self._combo.currentData() or ""


class BotItem(QWidget):
    """
    Fila de un bot en la sidebar con indicador de estado y botones de acción.
    """
    clicked      = pyqtSignal(str)   # bot_name
    remove_req   = pyqtSignal(str)   # bot_name
    logout_req   = pyqtSignal(str)   # bot_name

    def __init__(self, bot_name: str, parent=None):
        super().__init__(parent)
        self.bot_name = bot_name
        info = AVAILABLE_BOTS.get(bot_name, {})
        self.display_name = info.get("display", bot_name)
        self.color = info.get("color", "#e05a5a")
        self.emoji = info.get("emoji", "●")
        self._active = False
        self._status = "disconnected"
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(0)

        # ── Fila principal ──
        self._row = QWidget()
        self._row.setCursor(Qt.CursorShape.PointingHandCursor)
        row_layout = QHBoxLayout(self._row)
        row_layout.setContentsMargins(10, 9, 10, 9)
        row_layout.setSpacing(10)

        # Emoji/color del bot
        emoji_lbl = QLabel(self.emoji)
        emoji_lbl.setFixedWidth(18)
        emoji_lbl.setStyleSheet(f"color: {self.color}; font-size: 14px; font-weight: bold;")
        row_layout.addWidget(emoji_lbl)

        # Nombre + estado
        text_col = QWidget()
        text_layout = QVBoxLayout(text_col)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        self._name_lbl = QLabel(self.display_name)
        self._name_lbl.setStyleSheet("color: #e8d5d5; font-size: 13px; font-weight: 600;")

        self._status_lbl = QLabel("Sin sesión")
        self._status_lbl.setStyleSheet(f"color: {STATUS_COLORS['disconnected']}; font-size: 10px;")

        text_layout.addWidget(self._name_lbl)
        text_layout.addWidget(self._status_lbl)
        row_layout.addWidget(text_col)
        row_layout.addStretch()

        # Punto de estado
        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color: {STATUS_COLORS['disconnected']}; font-size: 9px;")
        row_layout.addWidget(self._dot)

        layout.addWidget(self._row)
        self._row.mousePressEvent = lambda e: self.clicked.emit(self.bot_name)

        # ── Fila de acciones (visible solo cuando está activo) ──
        self._actions_row = QWidget()
        actions_layout = QHBoxLayout(self._actions_row)
        actions_layout.setContentsMargins(12, 0, 12, 6)
        actions_layout.setSpacing(6)
        actions_layout.addStretch()

        self._logout_btn = QPushButton("Cerrar sesión")
        self._logout_btn.setFixedHeight(20)
        self._logout_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #5a2020; "
            "border-radius: 4px; color: #8a4040; padding: 0 8px; font-size: 10px; }"
            "QPushButton:hover { border-color: #c0392b; color: #e05050; background: #2a0a0a; }"
        )
        self._logout_btn.clicked.connect(lambda: self.logout_req.emit(self.bot_name))

        self._remove_btn = QPushButton("✕")
        self._remove_btn.setFixedSize(20, 20)
        self._remove_btn.setToolTip("Eliminar agente")
        self._remove_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #4a1a1a; "
            "border-radius: 4px; color: #6a3535; font-size: 10px; }"
            "QPushButton:hover { border-color: #8b2a2a; color: #e05050; background: #2a0a0a; }"
        )
        self._remove_btn.clicked.connect(lambda: self.remove_req.emit(self.bot_name))

        actions_layout.addWidget(self._logout_btn)
        actions_layout.addWidget(self._remove_btn)

        self._actions_row.setVisible(False)
        layout.addWidget(self._actions_row)

    def set_active(self, active: bool):
        self._active = active
        if active:
            self._row.setStyleSheet(
                "QWidget { background-color: #2f0f0f; border-left: 3px solid #c0392b; border-radius: 8px; }"
            )
            self._name_lbl.setStyleSheet(f"color: {self.color}; font-size: 13px; font-weight: bold;")
        else:
            self._row.setStyleSheet("")
            self._name_lbl.setStyleSheet("color: #e8d5d5; font-size: 13px; font-weight: 600;")
        self._actions_row.setVisible(active)

    def set_status(self, status: str, custom_text: str = ""):
        self._status = status
        color = STATUS_COLORS.get(status, STATUS_COLORS["disconnected"])
        label = custom_text if custom_text else STATUS_LABELS.get(status, status)
        self._dot.setStyleSheet(f"color: {color}; font-size: 9px;")
        self._status_lbl.setText(label)
        self._status_lbl.setStyleSheet(f"color: {color}; font-size: 10px;")


class Sidebar(QWidget):
    """
    Barra lateral con gestión dinámica de bots.
    """
    bot_selected  = pyqtSignal(str)
    bot_logout    = pyqtSignal(str)
    bot_removed   = pyqtSignal(str)
    bot_added     = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._items: dict[str, BotItem] = {}
        self._active: str | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Cabecera con logo ──
        header = QWidget()
        header.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #060101, stop:1 #0a0303);"
            "border-bottom: 1px solid #1a0606;"
        )
        header.setFixedHeight(88)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(14, 14, 14, 14)
        h_layout.setSpacing(12)

        # Logo imagen
        logo_path = Path(__file__).parent.parent / "assets" / "icons" / "tabasco_logo_icon.png"
        if logo_path.exists():
            logo_lbl = QLabel()
            pixmap = QPixmap(str(logo_path)).scaled(
                46, 46,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            logo_lbl.setPixmap(pixmap)
            logo_lbl.setFixedSize(46, 46)
            logo_lbl.setStyleSheet("background: transparent; border: none;")
            h_layout.addWidget(logo_lbl)

        # Texto título + subtítulo
        text_col = QWidget()
        text_col.setStyleSheet("background:transparent;")
        tc_lay = QVBoxLayout(text_col)
        tc_lay.setContentsMargins(0, 0, 0, 0)
        tc_lay.setSpacing(3)

        title = QLabel("TABASCO")
        title.setStyleSheet(
            "color: #d9d0d0; font-size: 14px; font-weight: bold; "
            "letter-spacing: 4px; background:transparent;"
        )
        subtitle = QLabel("Terminal AI Bridge")
        subtitle.setStyleSheet(
            "color: #3a1818; font-size: 10px; letter-spacing: 1px; background:transparent;"
        )

        tc_lay.addWidget(title)
        tc_lay.addWidget(subtitle)
        h_layout.addWidget(text_col)
        h_layout.addStretch()

        layout.addWidget(header)

        # ── Sección agentes ──
        agents_header = QWidget()
        agents_header.setFixedHeight(34)
        ah_layout = QHBoxLayout(agents_header)
        ah_layout.setContentsMargins(16, 0, 12, 0)

        agents_lbl = QLabel("AGENTES")
        agents_lbl.setStyleSheet(
            "color: #3a1515; font-size: 9px; font-weight: bold; letter-spacing: 2px;"
        )
        ah_layout.addWidget(agents_lbl)
        ah_layout.addStretch()
        layout.addWidget(agents_header)

        # ── Lista de bots (scroll) ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(6, 6, 6, 6)
        self._list_layout.setSpacing(3)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_container)
        layout.addWidget(self._scroll)

        # ── Pie: botón añadir ──
        footer = QWidget()
        footer.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #080202, stop:1 #060101);"
            "border-top: 1px solid #160606;"
        )
        f_layout = QVBoxLayout(footer)
        f_layout.setContentsMargins(10, 10, 10, 14)
        f_layout.setSpacing(8)

        self._add_btn = QPushButton("＋  Añadir agente")
        self._add_btn.setFixedHeight(38)
        self._add_btn.setStyleSheet(
            "QPushButton { background: #100404; border: 1px dashed #3a1010; border-radius: 10px; "
            "color: #6a3535; font-size: 12px; font-weight: 500; }"
            "QPushButton:hover { background: #1a0808; border-color: #c0392b; color: #e8d5d5; "
            "border-style: solid; }"
        )
        self._add_btn.clicked.connect(self._on_add_bot)
        f_layout.addWidget(self._add_btn)

        version_lbl = QLabel("v1.0  ·  Sin API Key requerida")
        version_lbl.setStyleSheet(
            "color: #2a0c0c; font-size: 10px; letter-spacing: 0.5px;"
        )
        version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f_layout.addWidget(version_lbl)

        layout.addWidget(footer)

    def _on_add_bot(self):
        already = list(self._items.keys())
        dlg = AddBotDialog(already, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            bot_name = dlg.selected_bot()
            if bot_name:
                self.add_bot(bot_name)
                self.bot_added.emit(bot_name)

    def add_bot(self, bot_name: str):
        """Añade un bot a la sidebar."""
        if bot_name in self._items:
            return
        item = BotItem(bot_name)
        item.clicked.connect(self._on_item_clicked)
        item.logout_req.connect(self.bot_logout.emit)
        item.remove_req.connect(self._on_remove_bot)
        self._items[bot_name] = item
        # Insertar antes del stretch
        count = self._list_layout.count()
        self._list_layout.insertWidget(count - 1, item)

    def _on_item_clicked(self, bot_name: str):
        self._set_active(bot_name)
        self.bot_selected.emit(bot_name)

    def _on_remove_bot(self, bot_name: str):
        """Elimina un bot de la sidebar."""
        if bot_name not in self._items:
            return
        item = self._items.pop(bot_name)
        self._list_layout.removeWidget(item)
        item.deleteLater()
        if self._active == bot_name:
            self._active = None
        self.bot_removed.emit(bot_name)

    def _set_active(self, bot_name: str):
        if self._active and self._active in self._items:
            self._items[self._active].set_active(False)
        self._active = bot_name
        if bot_name in self._items:
            self._items[bot_name].set_active(True)

    def set_bot_status(self, bot_name: str, status: str, text: str = ""):
        if bot_name in self._items:
            self._items[bot_name].set_status(status, text)

    def has_bot(self, bot_name: str) -> bool:
        return bot_name in self._items
