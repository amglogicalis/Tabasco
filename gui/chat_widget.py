"""
Widget del área de chat con burbujas de mensajes con soporte Markdown
y botón "Copiar" en bloques de código.
"""
import re
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QTextBrowser, QFrame, QSizePolicy,
    QPushButton, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
import markdown as md


def markdown_to_html(text: str) -> str:
    """Convierte texto Markdown a HTML con estilos inline para el chat."""
    html = md.markdown(
        text,
        extensions=["fenced_code", "codehilite", "tables", "nl2br"],
    )
    # Estilos para bloques de código inline
    html = html.replace(
        '<code>',
        '<code style="background:#1a1a3a;color:#e0e0ff;padding:2px 6px;border-radius:4px;'
        'font-family:Consolas,monospace;font-size:12px;">'
    )
    # Estilos para bloques pre/code
    html = html.replace(
        '<pre>',
        '<pre style="background:#0d0d2e;color:#e0e0ff;padding:12px 16px;border-radius:8px;'
        'border:1px solid #2a2a5a;font-family:Consolas,monospace;font-size:12px;'
        'overflow-x:auto;margin:8px 0;">'
    )
    return html


def extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """
    Extrae bloques de código del texto Markdown.
    Devuelve lista de (language, code).
    """
    blocks = []
    # Bloques cercados con lenguaje: ```python ... ```
    pattern = re.compile(r'```(\w*)\n?(.*?)```', re.DOTALL)
    for match in pattern.finditer(text):
        lang = match.group(1) or "code"
        code = match.group(2).strip()
        if code:
            blocks.append((lang, code))
    return blocks


class CodeBlock(QWidget):
    """
    Widget que muestra un bloque de código con cabecera (lenguaje + botón copiar)
    y el contenido del código.
    """

    def __init__(self, language: str, code: str, parent=None):
        super().__init__(parent)
        self._code = code
        self._setup_ui(language, code)

    def _setup_ui(self, language: str, code: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(0)

        # ── Cabecera del bloque ──
        header = QWidget()
        header.setStyleSheet(
            "background:#0d0d2e; border-radius:8px 8px 0 0; "
            "border:1px solid #2a2a5a; border-bottom:none;"
        )
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(12, 6, 8, 6)
        h_lay.setSpacing(8)

        lang_lbl = QLabel(language.lower() if language else "code")
        lang_lbl.setStyleSheet(
            "color:#7878c8; font-size:11px; font-family:Consolas,monospace; "
            "font-weight:bold; background:transparent;"
        )
        h_lay.addWidget(lang_lbl)
        h_lay.addStretch()

        self._copy_btn = QPushButton("📋 Copiar")
        self._copy_btn.setFixedHeight(22)
        self._copy_btn.setStyleSheet(
            "QPushButton { background:#1a1a4a; border:1px solid #3a3a7a; border-radius:4px; "
            "color:#9090d0; font-size:10px; padding:0 8px; }"
            "QPushButton:hover { background:#2a2a6a; border-color:#6060c0; color:#c0c0ff; }"
            "QPushButton:pressed { background:#0d0d3a; }"
        )
        self._copy_btn.clicked.connect(self._copy_code)
        h_lay.addWidget(self._copy_btn)

        layout.addWidget(header)

        # ── Contenido del código ──
        code_display = QTextBrowser()
        code_display.setObjectName("code_block")
        code_display.setReadOnly(True)
        code_display.setFrameShape(QFrame.Shape.NoFrame)
        code_display.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        code_display.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        code_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        code_display.setStyleSheet(
            "QTextBrowser { background:#0d0d2e; color:#e0e0ff; "
            "font-family:Consolas,monospace; font-size:12px; "
            "border:1px solid #2a2a5a; border-top:none; "
            "border-radius:0 0 8px 8px; padding:10px 14px; }"
        )
        code_display.setPlainText(code)
        code_display.document().adjustSize()
        h = int(code_display.document().size().height()) + 20
        code_display.setFixedHeight(min(h, 400))  # máx 400px

        layout.addWidget(code_display)

    def _copy_code(self):
        """Copia el código al portapapeles y cambia el botón temporalmente."""
        QApplication.clipboard().setText(self._code)
        self._copy_btn.setText("✓ Copiado")
        self._copy_btn.setStyleSheet(
            "QPushButton { background:#1a3a1a; border:1px solid #3a7a3a; border-radius:4px; "
            "color:#70c070; font-size:10px; padding:0 8px; }"
        )
        QTimer.singleShot(2000, self._reset_copy_btn)

    def _reset_copy_btn(self):
        self._copy_btn.setText("📋 Copiar")
        self._copy_btn.setStyleSheet(
            "QPushButton { background:#1a1a4a; border:1px solid #3a3a7a; border-radius:4px; "
            "color:#9090d0; font-size:10px; padding:0 8px; }"
            "QPushButton:hover { background:#2a2a6a; border-color:#6060c0; color:#c0c0ff; }"
            "QPushButton:pressed { background:#0d0d3a; }"
        )


class AutoHeightTextBrowser(QTextBrowser):
    """
    Subclase de QTextBrowser que se ajusta automáticamente en altura
    según el ancho y la cantidad de texto del mensaje.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.document().documentLayout().documentSizeChanged.connect(self._adjust_height)

    def _adjust_height(self):
        self.document().setTextWidth(self.viewport().width())
        h = int(self.document().size().height()) + 8
        self.setFixedHeight(max(h, 24))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._adjust_height)


class MessageBubble(QWidget):
    """
    Widget que representa una burbuja de mensaje en el chat.
    Soporta mensajes de usuario y de bot, con Markdown, bloques de código
    con botón copiar, y timestamp.
    """

    def __init__(self, text: str, is_user: bool, sender_name: str = "", parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.sender_name = sender_name
        self._raw_text = text
        self._setup_ui(text)

    def _setup_ui(self, text: str):
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(16, 4, 16, 4)
        outer_layout.setSpacing(0)

        # Columna de la burbuja
        bubble_col = QWidget()
        bubble_col_layout = QVBoxLayout(bubble_col)
        bubble_col_layout.setContentsMargins(0, 0, 0, 0)
        bubble_col_layout.setSpacing(2)

        # Nombre del remitente
        if self.sender_name:
            sender_lbl = QLabel(self.sender_name)
            sender_lbl.setObjectName("sender_label")
            if self.is_user:
                sender_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            bubble_col_layout.addWidget(sender_lbl)

        # La burbuja en sí
        bubble = QWidget()
        bubble.setObjectName("bubble_user" if self.is_user else "bubble_bot")

        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)
        bubble_layout.setSpacing(6)

        if self.is_user:
            # Mensajes de usuario: texto plano
            text_browser = self._make_text_browser()
            text_browser.setPlainText(text)
            bubble_layout.addWidget(text_browser)
        else:
            # Mensajes del bot: Markdown + bloques de código especiales
            code_blocks = extract_code_blocks(text)

            if code_blocks:
                # Separar texto y bloques de código
                parts = self._split_text_and_code(text)
                for part_type, part_content in parts:
                    if part_type == "text" and part_content.strip():
                        # Texto normal con markdown
                        clean = re.sub(r'```(\w*)\n?.*?```', '', part_content, flags=re.DOTALL).strip()
                        if clean:
                            tb = self._make_text_browser()
                            html = markdown_to_html(clean)
                            tb.setHtml(f'<div style="{self._get_text_style()}">{html}</div>')
                            bubble_layout.addWidget(tb)
                    elif part_type == "code":
                        lang, code = part_content
                        code_widget = CodeBlock(lang, code)
                        bubble_layout.addWidget(code_widget)
            else:
                # Sin bloques de código: renderizar todo como markdown
                tb = self._make_text_browser()
                html = markdown_to_html(text)
                tb.setHtml(f'<div style="{self._get_text_style()}">{html}</div>')
                bubble_layout.addWidget(tb)

        # Timestamp
        ts = QLabel(datetime.now().strftime("%H:%M"))
        ts.setObjectName("timestamp_label")
        ts.setAlignment(Qt.AlignmentFlag.AlignRight if self.is_user else Qt.AlignmentFlag.AlignLeft)
        bubble_layout.addWidget(ts)

        bubble_col_layout.addWidget(bubble)

        # Alineación: usuario a la derecha, bot a la izquierda
        if self.is_user:
            outer_layout.addStretch()
            outer_layout.addWidget(bubble_col)
        else:
            outer_layout.addWidget(bubble_col)
            outer_layout.addStretch()

        # Limitar ancho de la burbuja
        bubble.setMaximumWidth(620)
        bubble_col.setMaximumWidth(640)

    def _make_text_browser(self) -> AutoHeightTextBrowser:
        tb = AutoHeightTextBrowser()
        tb.setObjectName("message_text")
        tb.setOpenExternalLinks(True)
        tb.setReadOnly(True)
        tb.document().setDefaultStyleSheet(self._get_text_style())
        return tb

    def _split_text_and_code(self, text: str) -> list:
        """
        Divide el texto en partes: texto plano y bloques de código.
        Devuelve lista de ("text", str) o ("code", (lang, code)).
        """
        parts = []
        pattern = re.compile(r'```(\w*)\n?(.*?)```', re.DOTALL)
        last_end = 0
        for match in pattern.finditer(text):
            # Texto antes del bloque
            before = text[last_end:match.start()]
            if before:
                parts.append(("text", before))
            # Bloque de código
            lang = match.group(1) or "code"
            code = match.group(2).strip()
            parts.append(("code", (lang, code)))
            last_end = match.end()
        # Texto después del último bloque
        after = text[last_end:]
        if after:
            parts.append(("text", after))
        return parts

    def _get_text_style(self) -> str:
        color = "#ffffff" if self.is_user else "#e0e0e0"
        return (
            f"color:{color};font-family:'Segoe UI',Arial,sans-serif;"
            f"font-size:13px;line-height:1.5;background:transparent;"
        )


class TypingIndicator(QWidget):
    """Indicador de 'escribiendo...' animado."""

    def __init__(self, bot_name: str, parent=None):
        super().__init__(parent)
        self.bot_name = bot_name
        self._dots = 0
        self._setup_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(500)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 4)

        self._label = QLabel(f"{self.bot_name} está escribiendo...")
        self._label.setObjectName("typing_indicator")
        layout.addWidget(self._label)
        layout.addStretch()

    def _animate(self):
        self._dots = (self._dots + 1) % 4
        dots = "." * self._dots
        self._label.setText(f"{self.bot_name} está escribiendo{dots}")

    def stop(self):
        self._timer.stop()


class ChatWidget(QWidget):
    """
    Widget principal del área de chat.
    Muestra las burbujas de mensajes con scroll automático.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("chat_area")
        self._messages: list[dict] = []   # [{role, text, timestamp}]
        self._setup_ui()
        self._typing_indicator: TypingIndicator | None = None

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scroll area para los mensajes
        self._scroll = QScrollArea()
        self._scroll.setObjectName("chat_scroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        # Contenedor de mensajes
        self._messages_container = QWidget()
        self._messages_container.setObjectName("chat_area")
        self._messages_layout = QVBoxLayout(self._messages_container)
        self._messages_layout.setContentsMargins(0, 16, 0, 16)
        self._messages_layout.setSpacing(6)
        self._messages_layout.addStretch()  # Empuja mensajes hacia abajo

        self._scroll.setWidget(self._messages_container)
        main_layout.addWidget(self._scroll)

    def add_user_message(self, text: str):
        """Añade una burbuja de mensaje del usuario."""
        self._remove_typing_indicator()
        self._messages.append({
            "role": "user",
            "text": text,
            "timestamp": datetime.now().strftime("%H:%M"),
        })
        bubble = MessageBubble(text, is_user=True, sender_name="Tú")
        count = self._messages_layout.count()
        self._messages_layout.insertWidget(count - 1, bubble)
        self._scroll_to_bottom()

    def add_bot_message(self, text: str, bot_name: str = "Bot"):
        """Añade una burbuja de mensaje del bot."""
        self._remove_typing_indicator()
        self._messages.append({
            "role": "bot",
            "text": text,
            "bot_name": bot_name,
            "timestamp": datetime.now().strftime("%H:%M"),
        })
        bubble = MessageBubble(text, is_user=False, sender_name=bot_name)
        count = self._messages_layout.count()
        self._messages_layout.insertWidget(count - 1, bubble)
        self._scroll_to_bottom()

    def add_error_message(self, text: str):
        """Añade un mensaje de error."""
        error_widget = QWidget()
        error_layout = QHBoxLayout(error_widget)
        error_layout.setContentsMargins(16, 4, 16, 4)
        label = QLabel(f"⚠️ {text}")
        label.setStyleSheet("color: #f44336; font-size: 12px; font-style: italic;")
        label.setWordWrap(True)
        error_layout.addWidget(label)
        error_layout.addStretch()
        count = self._messages_layout.count()
        self._messages_layout.insertWidget(count - 1, error_widget)
        self._scroll_to_bottom()

    def show_typing_indicator(self, bot_name: str):
        """Muestra el indicador de 'escribiendo...'."""
        self._remove_typing_indicator()
        self._typing_indicator = TypingIndicator(bot_name)
        count = self._messages_layout.count()
        self._messages_layout.insertWidget(count - 1, self._typing_indicator)
        self._scroll_to_bottom()

    def _remove_typing_indicator(self):
        """Elimina el indicador de typing si existe."""
        if self._typing_indicator:
            self._typing_indicator.stop()
            self._messages_layout.removeWidget(self._typing_indicator)
            self._typing_indicator.deleteLater()
            self._typing_indicator = None

    def clear_messages(self):
        """Limpia todos los mensajes del chat."""
        self._messages.clear()
        self._remove_typing_indicator()
        while self._messages_layout.count() > 1:  # Mantener el stretch
            item = self._messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def get_messages(self) -> list[dict]:
        """Devuelve la lista de mensajes actuales para guardar en historial."""
        return list(self._messages)

    def has_messages(self) -> bool:
        """True si hay al menos un mensaje de usuario o bot."""
        return any(m["role"] in ("user", "bot") for m in self._messages)

    def restore_messages(self, messages: list[dict], bot_name: str = "Bot"):
        """
        Restaura mensajes desde el historial (no los guarda de nuevo).
        Se usa al cargar una sesión guardada.
        """
        self._remove_typing_indicator()
        # Limpiar visualmente pero conservar self._messages que ya se cargó desde afuera
        while self._messages_layout.count() > 1:
            item = self._messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._messages = []
        for m in messages:
            role = m.get("role", "")
            text = m.get("text", "")
            name = m.get("bot_name", bot_name) if role == "bot" else "Tú"
            if role == "user":
                self._messages.append(m)
                bubble = MessageBubble(text, is_user=True, sender_name="Tú")
            elif role == "bot":
                self._messages.append(m)
                bubble = MessageBubble(text, is_user=False, sender_name=name)
            else:
                continue
            count = self._messages_layout.count()
            self._messages_layout.insertWidget(count - 1, bubble)
        QTimer.singleShot(80, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def _scroll_to_bottom(self):
        """Hace scroll hasta el último mensaje."""
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))
