"""
gui/code_widget.py — Panel de Tabasco Code

Interfaz gráfica para el agente de codificación autónomo.
Muestra el workspace, la conversación del agente y las acciones
(lecturas, escrituras, comandos) en tiempo real conforme se ejecutan.
"""

from __future__ import annotations

import html
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QTextCursor, QColor, QPalette, QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QTextEdit, QFileDialog, QSizePolicy,
    QTextBrowser, QSpacerItem,
)

from core.agent.orchestrator import TabascoAgent
from core.agent.parser import Action


# ── Paleta de colores ──────────────────────────────────────────────────────────

_C = {
    "bg":          "#080202",
    "bg_card":     "#0e0404",
    "bg_input":    "#100404",
    "border":      "#1e0808",
    "border_hi":   "#3a1212",
    "read_bg":     "#080e18",
    "read_border": "#1a3355",
    "read_icon":   "📖",
    "write_bg":    "#080e0a",
    "write_border":"#1a4022",
    "write_icon":  "✏️",
    "shell_bg":    "#0e0c04",
    "shell_border":"#3a2e08",
    "shell_icon":  "🖥️",
    "done_bg":     "#040e06",
    "done_border": "#1a5528",
    "done_icon":   "✅",
    "err_bg":      "#0e0404",
    "err_border":  "#5a1a1a",
    "err_icon":    "❌",
    "text":        "#c8b4b4",
    "text_dim":    "#6a4444",
    "text_code":   "#a8c8a8",
    "accent":      "#c0392b",
    "accent_dim":  "#7a1a1a",
    "user_bg":     "#140606",
    "user_border": "#2e1010",
    "agent_bg":    "#0c0c0c",
    "agent_border":"#1a1a1a",
}


# ── Worker QThread ─────────────────────────────────────────────────────────────

class AgentWorker(QThread):
    """
    Ejecuta el loop del agente en un hilo separado para no bloquear la GUI.
    Emite señales por cada evento del agente.
    """
    # Texto de razonamiento del agente (respuesta completa del bot)
    agent_message  = pyqtSignal(str)
    # Una acción fue ejecutada (Action, resultado)
    action_done    = pyqtSignal(object, str)
    # Tarea completada (mensaje de resumen)
    task_done      = pyqtSignal(str)
    # Error crítico
    task_error     = pyqtSignal(str)
    # Progreso de iteración (actual, máximo)
    iteration      = pyqtSignal(int, int)

    def __init__(self, workspace: str, bot, task: str, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.bot = bot
        self.task = task

    def run(self):
        agent = TabascoAgent(
            workspace=self.workspace,
            bot=self.bot,
            on_message=lambda m: self.agent_message.emit(m),
            on_action=lambda a, r: self.action_done.emit(a, r),
            on_done=lambda s: self.task_done.emit(s),
            on_error=lambda e: self.task_error.emit(e),
            on_iteration=lambda i, m: self.iteration.emit(i, m),
        )
        agent.run(self.task)


# ── Widgets de la conversación ─────────────────────────────────────────────────

class UserBubble(QFrame):
    """Burbuja del mensaje del usuario."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: {_C['user_bg']}; border: 1px solid {_C['user_border']};"
            f"border-radius: 12px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(4)

        role = QLabel("👤  Tú")
        role.setStyleSheet(
            f"color: {_C['accent_dim']}; font-size: 10px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(role)

        msg = QLabel(text)
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg.setStyleSheet(
            f"color: {_C['text']}; font-size: 13px; background: transparent; border: none;"
        )
        lay.addWidget(msg)


class AgentBubble(QFrame):
    """Burbuja del razonamiento/texto del agente (filtrado de XML)."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: {_C['agent_bg']}; border: 1px solid {_C['agent_border']};"
            f"border-radius: 12px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(4)

        role = QLabel("Tabasco Code")
        role.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: 10px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(role)

        # Filtrar tags XML para mostrar sólo el razonamiento en texto plano
        import re
        clean = re.sub(
            r'<tabasco:(?:read|write|shell|done)[^>]*>.*?</tabasco:\w+>|'
            r'<tabasco:read[^/]*/>\s*',
            '',
            text,
            flags=re.DOTALL,
        ).strip()

        if clean:
            msg = QLabel(clean)
            msg.setWordWrap(True)
            msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            msg.setStyleSheet(
                f"color: {_C['text_dim']}; font-size: 12px; "
                f"background: transparent; border: none; font-style: italic;"
            )
            lay.addWidget(msg)
        else:
            msg = QLabel("(ejecutando acciones…)")
            msg.setStyleSheet(
                f"color: {_C['text_dim']}; font-size: 11px; "
                f"background: transparent; border: none; font-style: italic;"
            )
            lay.addWidget(msg)


class ActionCard(QFrame):
    """
    Tarjeta visual para mostrar una acción del agente y su resultado.
    El estilo varía según el tipo de acción (read/write/shell/done/error).
    """

    def __init__(self, action: Action, result: str, parent=None):
        super().__init__(parent)
        self._action = action
        self._result = result
        self._setup(action.type, action, result)

    def _setup(self, kind: str, action: Action, result: str):
        # Elegir estilo según tipo
        styles = {
            "read":  (_C["read_bg"],   _C["read_border"],  _C["read_icon"]),
            "write": (_C["write_bg"],  _C["write_border"], _C["write_icon"]),
            "shell": (_C["shell_bg"],  _C["shell_border"], _C["shell_icon"]),
            "done":  (_C["done_bg"],   _C["done_border"],  _C["done_icon"]),
            "error": (_C["err_bg"],    _C["err_border"],   _C["err_icon"]),
        }
        bg, border, icon = styles.get(kind, styles["error"])

        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; "
            f"border-radius: 10px; }}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)

        # ── Cabecera de la tarjeta ─────────────────────────────────────────────
        head_row = QWidget()
        head_row.setStyleSheet("background: transparent;")
        head_lay = QHBoxLayout(head_row)
        head_lay.setContentsMargins(0, 0, 0, 0)
        head_lay.setSpacing(6)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"font-size: 14px; background: transparent; border: none;"
        )
        head_lay.addWidget(icon_lbl)

        # Título descriptivo
        title = self._build_title(kind, action)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {border}; font-size: 11px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        head_lay.addWidget(title_lbl)
        head_lay.addStretch()

        # Botón para expandir/contraer contenido
        self._expand_btn = QPushButton("▼")
        self._expand_btn.setFixedSize(22, 22)
        self._expand_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; "
            f"color: {_C['text_dim']}; font-size: 10px; }}"
            f"QPushButton:hover {{ color: {_C['text']}; }}"
        )
        self._expand_btn.setCheckable(True)
        self._expand_btn.setChecked(True)
        self._expand_btn.clicked.connect(self._toggle_content)
        head_lay.addWidget(self._expand_btn)

        lay.addWidget(head_row)

        # ── Contenido expandible ───────────────────────────────────────────────
        self._content_widget = QWidget()
        self._content_widget.setStyleSheet("background: transparent;")
        content_lay = QVBoxLayout(self._content_widget)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(4)

        # Mostrar el código/contenido de la acción si aplica
        if kind == "write" and action.content:
            preview = self._make_code_box(action.content, border, max_lines=12)
            content_lay.addWidget(preview)
        elif kind == "shell" and action.content:
            cmd_lbl = QLabel(f"$ {action.content}")
            cmd_lbl.setWordWrap(True)
            cmd_lbl.setStyleSheet(
                f"color: {_C['shell_border']}; font-family: 'Consolas', monospace; "
                f"font-size: 11px; background: transparent; border: none;"
            )
            content_lay.addWidget(cmd_lbl)

        # Resultado
        if result:
            result_box = self._make_result_box(result, border)
            content_lay.addWidget(result_box)

        lay.addWidget(self._content_widget)

    def _build_title(self, kind: str, action: Action) -> str:
        if kind == "read":
            return f"Leyendo: {action.path}"
        elif kind == "write":
            return f"Escribiendo: {action.path}"
        elif kind == "shell":
            cmd = (action.content or "")[:60].replace('\n', ' ')
            return f"Ejecutando: {cmd}{'…' if len(action.content or '') > 60 else ''}"
        elif kind == "done":
            return "Tarea completada"
        else:
            return "Acción desconocida"

    def _make_code_box(self, content: str, border_color: str, max_lines: int = 15) -> QTextBrowser:
        box = QTextBrowser()
        box.setStyleSheet(
            f"QTextBrowser {{ background: #050505; border: 1px solid {border_color}44; "
            f"border-radius: 6px; color: {_C['text_code']}; "
            f"font-family: 'Consolas', 'Courier New', monospace; font-size: 11px; "
            f"padding: 6px; }}"
        )
        lines = content.split('\n')
        if len(lines) > max_lines:
            preview = '\n'.join(lines[:max_lines]) + f"\n... ({len(lines)-max_lines} líneas más)"
        else:
            preview = content
        box.setPlainText(preview)
        line_count = min(len(lines), max_lines) + 1
        box.setFixedHeight(min(line_count * 17 + 16, 260))
        box.setReadOnly(True)
        box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        return box

    def _make_result_box(self, result: str, border_color: str) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        cly = QVBoxLayout(container)
        cly.setContentsMargins(0, 2, 0, 0)
        cly.setSpacing(2)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: {border_color}33; max-height: 1px; border: none;")
        cly.addWidget(sep)

        result_lbl = QLabel(result)
        result_lbl.setWordWrap(True)
        result_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # Si el resultado es código/multi-línea, usar fuente mono
        is_multiline = '\n' in result or len(result) > 120
        if is_multiline:
            result_lbl.setStyleSheet(
                f"color: {_C['text_dim']}; font-family: 'Consolas', monospace; "
                f"font-size: 10px; background: transparent; border: none;"
            )
        else:
            result_lbl.setStyleSheet(
                f"color: {_C['text_dim']}; font-size: 11px; "
                f"background: transparent; border: none;"
            )
        cly.addWidget(result_lbl)
        return container

    def _toggle_content(self):
        visible = self._expand_btn.isChecked()
        self._content_widget.setVisible(visible)
        self._expand_btn.setText("▼" if visible else "▶")


class DoneCard(QFrame):
    """Tarjeta especial para cuando el agente termina la tarea."""

    def __init__(self, summary: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: {_C['done_bg']}; border: 2px solid {_C['done_border']}; "
            f"border-radius: 12px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)

        head = QLabel("✅  Tarea Completada")
        head.setStyleSheet(
            f"color: #4aaa66; font-size: 13px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(head)

        if summary:
            msg = QLabel(summary)
            msg.setWordWrap(True)
            msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            msg.setStyleSheet(
                f"color: {_C['text']}; font-size: 12px; "
                f"background: transparent; border: none;"
            )
            lay.addWidget(msg)


class ErrorCard(QFrame):
    """Tarjeta para errores críticos del agente."""

    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: {_C['err_bg']}; border: 1px solid {_C['err_border']}; "
            f"border-radius: 10px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(4)

        head = QLabel("❌  Error del agente")
        head.setStyleSheet(
            f"color: #cc3333; font-size: 11px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(head)

        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(msg)


class IterationBadge(QLabel):
    """Pequeña etiqueta que muestra el progreso de iteraciones del agente."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: 10px; "
            f"background: transparent; padding: 2px;"
        )

    def update_iteration(self, current: int, maximum: int):
        self.setText(f"↻ Iteración {current}/{maximum}")


class ThinkingIndicator(QWidget):
    """Indicador animado de 'pensando...' mientras el agente procesa."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._dots = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._idx = 0

        self._spinner = QLabel(self._dots[0])
        self._spinner.setStyleSheet(
            f"color: {_C['accent_dim']}; font-size: 16px; background: transparent;"
        )
        lay.addWidget(self._spinner)

        self._lbl = QLabel("Tabasco Code está pensando…")
        self._lbl.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: 12px; "
            f"font-style: italic; background: transparent;"
        )
        lay.addWidget(self._lbl)

        self._iter_lbl = QLabel("")
        self._iter_lbl.setStyleSheet(
            f"color: {_C['accent_dim']}; font-size: 10px; background: transparent;"
        )
        lay.addWidget(self._iter_lbl)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(100)

    def _tick(self):
        self._idx = (self._idx + 1) % len(self._dots)
        self._spinner.setText(self._dots[self._idx])

    def set_iteration(self, current: int, maximum: int):
        self._iter_lbl.setText(f"  ↻ {current}/{maximum}")

    def set_status(self, msg: str):
        self._lbl.setText(msg)


# ── Widget principal ───────────────────────────────────────────────────────────

class CodeWidget(QWidget):
    """
    Panel principal de Tabasco Code.

    Muestra:
      - Barra de workspace (selector de carpeta)
      - Área de conversación con burbujas de usuario, tarjetas de acción
      - Barra de entrada para nuevas tareas
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bot = None
        self._workspace: str = ""
        self._worker: AgentWorker | None = None
        self._thinking: ThinkingIndicator | None = None
        self._setup_ui()

    # ── Configuración pública ──────────────────────────────────────────────────

    def set_bot(self, bot):
        """Conecta el widget con el bot activo (Playwright)."""
        self._bot = bot
        self._update_send_state()

    def set_workspace(self, path: str):
        """Establece el directorio de trabajo del agente."""
        self._workspace = path
        if path:
            display = Path(path).name or path
            self._ws_lbl.setText(f"📁  {display}")
            self._ws_lbl.setToolTip(path)
        else:
            self._ws_lbl.setText("Sin carpeta seleccionada")
        self._update_send_state()

    def get_workspace(self) -> str:
        return self._workspace

    # ── Setup de UI ───────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setStyleSheet(f"background: {_C['bg']};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Barra de workspace ─────────────────────────────────────────────────
        ws_bar = self._make_workspace_bar()
        root.addWidget(ws_bar)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet(f"background: {_C['border']}; max-height: 1px; border: none;")
        root.addWidget(sep1)

        # ── Área de scroll de conversación ─────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: {_C['bg']}; }}"
            f"QScrollBar:vertical {{ background: {_C['bg']}; width: 6px; }}"
            f"QScrollBar::handle:vertical {{ background: {_C['border_hi']}; border-radius: 3px; }}"
        )

        self._conv_container = QWidget()
        self._conv_container.setStyleSheet(f"background: {_C['bg']};")
        self._conv_layout = QVBoxLayout(self._conv_container)
        self._conv_layout.setContentsMargins(16, 16, 16, 16)
        self._conv_layout.setSpacing(10)
        self._conv_layout.addStretch()   # empuja contenido hacia abajo

        self._scroll.setWidget(self._conv_container)
        root.addWidget(self._scroll)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"background: {_C['border']}; max-height: 1px; border: none;")
        root.addWidget(sep2)

        # ── Barra de entrada ───────────────────────────────────────────────────
        input_area = self._make_input_bar()
        root.addWidget(input_area)

        self._show_welcome()

    def _make_workspace_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet(
            f"QWidget {{ background: {_C['bg_card']}; border-bottom: 1px solid {_C['border']}; }}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(10)

        code_lbl = QLabel("💻  Tabasco Code")
        code_lbl.setStyleSheet(
            f"color: {_C['accent']}; font-size: 13px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(code_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"background: {_C['border']}; max-width: 1px; border: none;")
        lay.addWidget(sep)

        self._ws_lbl = QLabel("Sin carpeta seleccionada")
        self._ws_lbl.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(self._ws_lbl)
        lay.addStretch()

        btn_ws = QPushButton("📂  Cambiar carpeta")
        btn_ws.setFixedHeight(28)
        btn_ws.setStyleSheet(
            f"QPushButton {{ background: {_C['bg']}; border: 1px solid {_C['border_hi']}; "
            f"border-radius: 6px; color: {_C['text_dim']}; padding: 0 12px; font-size: 11px; }}"
            f"QPushButton:hover {{ border-color: {_C['accent_dim']}; color: {_C['accent']}; }}"
        )
        btn_ws.clicked.connect(self._on_choose_workspace)
        lay.addWidget(btn_ws)

        btn_clear = QPushButton("🗑  Limpiar")
        btn_clear.setFixedHeight(28)
        btn_clear.setStyleSheet(
            f"QPushButton {{ background: {_C['bg']}; border: 1px solid {_C['border']}; "
            f"border-radius: 6px; color: {_C['text_dim']}; padding: 0 12px; font-size: 11px; }}"
            f"QPushButton:hover {{ border-color: #5a1a1a; color: #cc3333; }}"
        )
        btn_clear.clicked.connect(self._on_clear)
        lay.addWidget(btn_clear)

        return bar

    def _make_input_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(
            f"QWidget {{ background: {_C['bg_input']}; }}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 10, 16, 12)
        lay.setSpacing(10)

        self._input = QTextEdit()
        self._input.setPlaceholderText(
            "Describe la tarea… (p.ej. 'Crea un servidor HTTP en Python')"
            "  ·  Enter para enviar  ·  Shift+Enter para nueva línea"
        )
        self._input.setFixedHeight(52)
        self._input.setStyleSheet(
            f"QTextEdit {{ background: {_C['bg_card']}; border: 1px solid {_C['border_hi']}; "
            f"border-radius: 10px; color: {_C['text']}; padding: 8px 12px; font-size: 13px; }}"
            f"QTextEdit:focus {{ border-color: {_C['accent_dim']}; }}"
        )
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._input.installEventFilter(self)
        self._input.textChanged.connect(self._update_send_state)
        lay.addWidget(self._input)

        self._send_btn = QPushButton("▶  Ejecutar")
        self._send_btn.setFixedSize(110, 52)
        self._send_btn.setEnabled(False)
        self._send_btn.setStyleSheet(
            f"QPushButton {{ background: {_C['accent_dim']}; border: none; border-radius: 10px; "
            f"color: #fff; font-size: 13px; font-weight: bold; }}"
            f"QPushButton:hover:enabled {{ background: {_C['accent']}; }}"
            f"QPushButton:disabled {{ background: #1a0606; color: #3a1010; }}"
        )
        self._send_btn.clicked.connect(self._on_send)
        lay.addWidget(self._send_btn)

        return bar

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            key_event = event
            if key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not (key_event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self._on_send()
                    return True
        return super().eventFilter(obj, event)

    # ── Pantalla de bienvenida ─────────────────────────────────────────────────

    def _show_welcome(self):
        welcome = QWidget()
        welcome.setStyleSheet("background: transparent;")
        wlay = QVBoxLayout(welcome)
        wlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wlay.setSpacing(12)

        icon_lbl = QLabel("💻")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 48px; background: transparent;")
        wlay.addWidget(icon_lbl)

        title = QLabel("Tabasco Code")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {_C['accent']}; font-size: 22px; font-weight: bold; "
            f"letter-spacing: 2px; background: transparent;"
        )
        wlay.addWidget(title)

        sub = QLabel("Agente autónomo de programación")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            f"color: {_C['text_dim']}; font-size: 12px; background: transparent;"
        )
        wlay.addWidget(sub)

        tips = [
            "✦  Selecciona una carpeta de workspace",
            "✦  Describe la tarea en lenguaje natural",
            "✦  El agente crea, edita y ejecuta código automáticamente",
            "✦  Usa el bot activo (Gemini, ChatGPT, Claude…) como motor",
        ]
        for tip in tips:
            tip_lbl = QLabel(tip)
            tip_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tip_lbl.setStyleSheet(
                f"color: {_C['accent_dim']}; font-size: 11px; background: transparent;"
            )
            wlay.addWidget(tip_lbl)

        self._add_widget(welcome)

    # ── Manejo de conversación ─────────────────────────────────────────────────

    def _add_widget(self, widget: QWidget):
        """Inserta un widget ANTES del stretch final."""
        # El stretch está en la última posición
        idx = self._conv_layout.count() - 1
        self._conv_layout.insertWidget(idx, widget)
        # Scroll al final
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_send(self):
        task = self._input.toPlainText().strip()
        if not task or not self._bot or not self._workspace:
            return
        if self._worker and self._worker.isRunning():
            return  # ya hay un agente corriendo

        self._input.clear()

        # Mostrar burbuja de usuario
        self._add_widget(UserBubble(task))

        # Mostrar indicador de pensando
        self._thinking = ThinkingIndicator()
        self._add_widget(self._thinking)

        # Lanzar worker
        self._worker = AgentWorker(self._workspace, self._bot, task)
        self._worker.agent_message.connect(self._on_agent_message)
        self._worker.action_done.connect(self._on_action_done)
        self._worker.task_done.connect(self._on_task_done)
        self._worker.task_error.connect(self._on_task_error)
        self._worker.iteration.connect(self._on_iteration)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

        self._send_btn.setEnabled(False)
        self._input.setEnabled(False)

    def _remove_thinking(self):
        if self._thinking:
            self._thinking.setParent(None)
            self._thinking.deleteLater()
            self._thinking = None

    def _on_agent_message(self, text: str):
        self._remove_thinking()
        bubble = AgentBubble(text)
        self._add_widget(bubble)

    def _on_action_done(self, action: Action, result: str):
        card = ActionCard(action, result)
        self._add_widget(card)

    def _on_task_done(self, summary: str):
        self._remove_thinking()
        self._add_widget(DoneCard(summary))

    def _on_task_error(self, message: str):
        self._remove_thinking()
        self._add_widget(ErrorCard(message))

    def _on_iteration(self, current: int, maximum: int):
        if self._thinking:
            self._thinking.set_iteration(current, maximum)

    def _on_worker_finished(self):
        self._remove_thinking()
        self._send_btn.setEnabled(bool(self._workspace and self._bot))
        self._input.setEnabled(True)
        self._input.setFocus()

    # ── Acciones de la barra de workspace ─────────────────────────────────────

    def _on_choose_workspace(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta de workspace",
            self._workspace or "",
        )
        if path:
            self.set_workspace(path)

    def _on_clear(self):
        """Limpia la conversación del panel."""
        # Quitar todos los widgets excepto el stretch final
        while self._conv_layout.count() > 1:
            item = self._conv_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._show_welcome()

    # ── Estado del botón de envío ──────────────────────────────────────────────

    def _update_send_state(self):
        has_text = bool(self._input.toPlainText().strip())
        ready = has_text and bool(self._bot) and bool(self._workspace)
        if not (self._worker and self._worker.isRunning()):
            self._send_btn.setEnabled(ready)
