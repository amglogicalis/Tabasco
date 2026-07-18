"""
Panel lateral de historial de conversaciones.
Se muestra a la derecha del chat cuando el usuario lo abre.
"""
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from core import history as hist


def _fmt_date(iso: str) -> str:
    """Convierte ISO timestamp a cadena legible."""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d/%m  %H:%M")
    except Exception:
        return iso[:16] if iso else ""


class SessionItem(QWidget):
    """Fila de una sesión en el panel de historial."""
    clicked  = pyqtSignal(str)   # session_id
    deleted  = pyqtSignal(str)   # session_id

    def __init__(self, session: dict, parent=None):
        super().__init__(parent)
        self.session_id = session["session_id"]
        self._setup_ui(session)

    def _setup_ui(self, s: dict):
        self.setFixedHeight(60)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        row = QWidget()
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setStyleSheet(
            "QWidget { background: transparent; border-radius: 8px; }"
            "QWidget:hover { background: #1a0808; }"
        )
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(10, 6, 8, 6)
        row_lay.setSpacing(8)

        # Columna texto
        text_col = QWidget()
        text_col.setStyleSheet("background:transparent;")
        tc = QVBoxLayout(text_col)
        tc.setContentsMargins(0, 0, 0, 0)
        tc.setSpacing(2)

        date_lbl = QLabel(_fmt_date(s.get("saved_at", "")))
        date_lbl.setStyleSheet("color:#4a2828; font-size:10px; background:transparent;")

        preview = s.get("preview", "")[:52]
        preview_lbl = QLabel(preview + "…" if len(s.get("preview", "")) > 52 else preview)
        preview_lbl.setStyleSheet("color:#9c7070; font-size:11px; background:transparent;")
        preview_lbl.setWordWrap(False)

        count_lbl = QLabel(f"{s.get('count', 0)} mensajes")
        count_lbl.setStyleSheet("color:#3a1818; font-size:10px; background:transparent;")

        tc.addWidget(date_lbl)
        tc.addWidget(preview_lbl)
        tc.addWidget(count_lbl)
        row_lay.addWidget(text_col)
        row_lay.addStretch()

        # Botón eliminar
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(20, 20)
        del_btn.setToolTip("Borrar esta conversación de la app")
        del_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; "
            "color: #8a3535; font-size: 11px; border-radius: 4px; }"
            "QPushButton:hover { background: #3a1010; color: #ff5555; }"
        )
        del_btn.clicked.connect(lambda: self.deleted.emit(self.session_id))
        row_lay.addWidget(del_btn)

        row.mousePressEvent = lambda e: self.clicked.emit(self.session_id)
        layout.addWidget(row)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background:#160606; max-height:1px; border:none;")
        layout.addWidget(sep)


class HistoryPanel(QWidget):
    """
    Panel deslizable de historial de chats.
    Señales:
      session_selected(bot_name, session_id) -> cargar conversación
      session_deleted(bot_name, session_id)  -> notificar borrado
      panel_closed                           -> ocultar el panel
    """
    session_selected = pyqtSignal(str, str)   # bot_name, session_id
    session_deleted  = pyqtSignal(str, str)   # bot_name, session_id
    panel_closed     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("history_panel")
        self.setFixedWidth(240)
        self.setStyleSheet(
            "#history_panel {"
            "  background: #080202;"
            "  border-left: 1px solid #1e0808;"
            "}"
        )
        self._bot_name: str = ""
        self._setup_ui()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Cabecera
        hdr = QWidget()
        hdr.setFixedHeight(48)
        hdr.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #060101, stop:1 #0a0303);"
            "border-bottom: 1px solid #1a0606;"
        )
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(14, 0, 10, 0)

        self._title_lbl = QLabel("Historial")
        self._title_lbl.setStyleSheet(
            "color: #9c7070; font-size: 11px; font-weight: bold; "
            "letter-spacing: 2px; background:transparent;"
        )
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; "
            "color: #4a2828; font-size: 12px; }"
            "QPushButton:hover { color: #e05050; background: #1a0808; "
            "border-radius: 4px; }"
        )
        close_btn.clicked.connect(self.panel_closed.emit)
        hdr_lay.addWidget(self._title_lbl)
        hdr_lay.addStretch()
        hdr_lay.addWidget(close_btn)
        lay.addWidget(hdr)

        # Scroll de sesiones
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._list_lay = QVBoxLayout(self._container)
        self._list_lay.setContentsMargins(8, 8, 8, 8)
        self._list_lay.setSpacing(2)
        self._list_lay.addStretch()

        self._scroll.setWidget(self._container)
        lay.addWidget(self._scroll)

        # Footer: vaciar todo
        ftr = QWidget()
        ftr.setFixedHeight(44)
        ftr.setStyleSheet(
            "background: #060101; border-top: 1px solid #160606;"
        )
        ftr_lay = QHBoxLayout(ftr)
        ftr_lay.setContentsMargins(10, 0, 10, 0)

        clear_btn = QPushButton("Vaciar historial")
        clear_btn.setFixedHeight(28)
        clear_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #2a1010; "
            "border-radius: 6px; color: #4a2020; font-size: 11px; padding: 0 10px; }"
            "QPushButton:hover { border-color: #8b1a1a; color: #e05050; "
            "background: #1a0808; }"
        )
        clear_btn.clicked.connect(self._clear_all)
        ftr_lay.addWidget(clear_btn)
        lay.addWidget(ftr)

        # Label "sin historial"
        self._empty_lbl = QLabel("Sin conversaciones\nguardadas")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(
            "color: #2a1010; font-size: 12px; background:transparent;"
        )
        self._empty_lbl.setWordWrap(True)

    def load_for_bot(self, bot_name: str, display_name: str = ""):
        """Carga y muestra las sesiones del bot indicado."""
        self._bot_name = bot_name
        self._title_lbl.setText(f"Historial · {display_name or bot_name}")
        self._refresh()

    def _refresh(self):
        # Limpiar lista visual
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sessions = hist.list_sessions(self._bot_name)
        if not sessions:
            # Mostrar label vacío
            idx = self._list_lay.count() - 1
            self._list_lay.insertWidget(idx, self._empty_lbl)
            self._empty_lbl.setVisible(True)
            return

        self._empty_lbl.setVisible(False)
        for s in sessions:
            item = SessionItem(s)
            item.clicked.connect(self._on_session_click)
            item.deleted.connect(self._on_session_delete)
            idx = self._list_lay.count() - 1
            self._list_lay.insertWidget(idx, item)

    def _on_session_click(self, session_id: str):
        self.session_selected.emit(self._bot_name, session_id)

    def _on_session_delete(self, session_id: str):
        hist.delete_session(self._bot_name, session_id)
        self._refresh()
        self.session_deleted.emit(self._bot_name, session_id)

    def _clear_all(self):
        if self._bot_name:
            hist.delete_all_sessions(self._bot_name)
            self._refresh()
            self.session_deleted.emit(self._bot_name, "")
