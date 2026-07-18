"""
Executor: ejecuta de forma segura las acciones del agente en el workspace.

Operaciones soportadas:
  - read:  Lee el contenido de un archivo.
  - write: Crea o sobreescribe un archivo (crea directorios intermedios).
  - shell: Ejecuta un comando de shell en la raíz del workspace.

Todas las rutas se validan para que estén dentro del workspace (sandbox).
"""

import subprocess
import sys
from pathlib import Path
from .parser import Action

# Límites de contenido para evitar contextos demasiado largos
MAX_READ_CHARS  = 12_000
MAX_SHELL_CHARS =  4_000


class Executor:
    """Ejecuta acciones del agente de forma aislada dentro del workspace."""

    def __init__(self, workspace: str):
        self.workspace = Path(workspace).resolve()

    # ── API pública ────────────────────────────────────────────────────────────

    def execute(self, action: Action) -> str:
        """
        Ejecuta una acción y devuelve el resultado como string.
        Nunca lanza excepciones; los errores se devuelven como texto.
        """
        try:
            if action.type == "read":
                return self._read(action.path)
            elif action.type == "write":
                return self._write(action.path, action.content)
            elif action.type == "shell":
                return self._shell(action.content)
            else:
                return f"[ERROR] Tipo de acción desconocido: {action.type}"
        except Exception as exc:
            return f"[ERROR] {exc}"

    # ── Operaciones internas ───────────────────────────────────────────────────

    def _safe_path(self, rel: str) -> Path:
        """Resuelve y valida que la ruta esté dentro del workspace (sandbox)."""
        resolved = (self.workspace / rel).resolve()
        if not str(resolved).startswith(str(self.workspace)):
            raise PermissionError(
                f"Ruta fuera del workspace (bloqueada por seguridad): {rel}"
            )
        return resolved

    def _read(self, path: str | None) -> str:
        if not path:
            return "[ERROR] No se especificó ruta para leer."
        p = self._safe_path(path)
        if not p.exists():
            return f"[ERROR] El archivo no existe: {path}"
        if p.is_dir():
            # Si es un directorio, listar su contenido
            entries = sorted(p.iterdir())
            lines = [f"{'📁 ' if e.is_dir() else '📄 '}{e.name}" for e in entries]
            return f"Contenido del directorio '{path}':\n" + "\n".join(lines)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"[ERROR] No se pudo leer: {e}"
        truncated = ""
        if len(text) > MAX_READ_CHARS:
            text = text[:MAX_READ_CHARS]
            truncated = f"\n\n... [TRUNCADO — el archivo tiene más de {MAX_READ_CHARS} caracteres]"
        return text + truncated

    def _write(self, path: str | None, content: str) -> str:
        if not path:
            return "[ERROR] No se especificó ruta para escribir."
        p = self._safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        lines = content.count('\n') + 1
        return f"[OK] Archivo escrito: {path} ({len(content)} bytes, {lines} lineas)"

    def _shell(self, cmd: str) -> str:
        if not cmd:
            return "[ERROR] Comando vacío."
        try:
            # Usar el Python actual para garantizar el entorno correcto
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(self.workspace),
                timeout=120,
                encoding="utf-8",
                errors="replace",
            )
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()

            parts = []
            if stdout:
                parts.append(stdout)
            if stderr:
                parts.append(f"[stderr]\n{stderr}")
            if result.returncode != 0:
                parts.append(f"[Código de salida: {result.returncode}]")

            output = "\n".join(parts).strip() or "(sin salida)"

            if len(output) > MAX_SHELL_CHARS:
                output = output[:MAX_SHELL_CHARS] + "\n... [TRUNCADO]"
            return output

        except subprocess.TimeoutExpired:
            return "[ERROR] El comando superó el tiempo límite (120s)."
        except Exception as exc:
            return f"[ERROR] {exc}"

    # ── Utilidades ─────────────────────────────────────────────────────────────

    def file_tree(self, max_items: int = 200) -> str:
        """Genera un árbol de archivos del workspace como texto."""
        IGNORE = {'.git', '__pycache__', 'node_modules', '.venv', 'venv',
                  '.idea', '.vs', 'dist', 'build', '.next', '.nuxt'}
        lines = []
        count = 0

        for p in sorted(self.workspace.rglob('*')):
            if count >= max_items:
                lines.append("  ... (demasiados archivos, truncado)")
                break
            parts = p.relative_to(self.workspace).parts
            if any(part in IGNORE or part.startswith('.') for part in parts):
                continue
            depth = len(parts) - 1
            indent = "  " * depth
            icon = "📁 " if p.is_dir() else "📄 "
            lines.append(f"{indent}{icon}{p.name}")
            count += 1

        return '\n'.join(lines) if lines else '(workspace vacío)'
