"""
Orquestador principal del agente Tabasco Code.

Gestiona el loop agente completo:
  1. Construye el contexto (sistema + árbol de archivos + tarea)
  2. Envía el mensaje al bot activo (vía Playwright, igual que el chat normal)
  3. Parsea la respuesta buscando acciones XML
  4. Ejecuta las acciones y recopila resultados
  5. Si no ha terminado, construye el siguiente mensaje y repite (goto 2)
  6. Notifica a la GUI via callbacks en cada evento

El historial de conversación vive de forma natural en el navegador del bot
(igual que un chat normal), por lo que no necesitamos gestionar tokens.
"""

from pathlib import Path
from typing import Callable
from .parser import parse_actions, Action
from .executor import Executor


# ── Prompt de sistema ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are Tabasco Code, an autonomous AI coding agent.
You have full control over the user workspace. You can read/write files and run shell commands.

=== AVAILABLE ACTIONS (use XML tags in your responses) ===

Read a file:
<tabasco:read path="relative/path/to/file.py"/>

Create or overwrite a file:
<tabasco:write path="relative/path/to/file.py">
exact file content here
</tabasco:write>

Run a shell command:
<tabasco:shell>
command here
</tabasco:shell>

Signal task completion:
<tabasco:done>
Brief summary of what was accomplished.
</tabasco:done>

=== RULES ===
1. Use ONLY relative paths from the workspace root.
2. Read a file before modifying it.
3. You can chain multiple actions in one response.
4. Analyze command output before continuing.
5. If an error occurs, diagnose and fix it.
6. When the task is 100% complete, use <tabasco:done>.

=== WORKSPACE ===
Path: {workspace}

File tree:
{file_tree}
=================
"""


class TabascoAgent:
    """
    Agente de codificación autónomo.
    Se instancia por tarea y se ejecuta en un QThread (AgentWorker).
    """

    MAX_ITERATIONS = 10  # Número máximo de turnos agente↔bot

    def __init__(
        self,
        workspace: str,
        bot,
        on_message:  Callable[[str], None],        # texto del agente (razonamiento)
        on_action:   Callable[[Action, str], None], # (acción, resultado)
        on_done:     Callable[[str], None],         # tarea completada
        on_error:    Callable[[str], None],         # error crítico
        on_iteration: Callable[[int, int], None] = None,  # (actual, máximo)
    ):
        self.workspace = Path(workspace)
        self.bot = bot
        self.executor = Executor(workspace)
        self.on_message   = on_message
        self.on_action    = on_action
        self.on_done      = on_done
        self.on_error     = on_error
        self.on_iteration = on_iteration or (lambda i, m: None)

    # ── API pública ────────────────────────────────────────────────────────────

    def run(self, user_task: str) -> None:
        """
        Ejecuta el loop del agente de forma síncrona (debe llamarse en un QThread).
        Envía mensajes al bot, parsea y ejecuta acciones, itera hasta completar.
        """
        # Escape curly braces in file tree to avoid .format() errors
        file_tree_safe = self.executor.file_tree().replace("{", "{{").replace("}", "}}")
        workspace_safe = str(self.workspace).replace("{", "{{").replace("}", "}}")
        system = _SYSTEM_PROMPT.format(
            workspace=workspace_safe,
            file_tree=file_tree_safe,
        )
        # Primer mensaje: sistema + tarea
        current_msg = f"{system}\n\nUSER TASK:\n{user_task}"

        for iteration in range(self.MAX_ITERATIONS):
            self.on_iteration(iteration + 1, self.MAX_ITERATIONS)

            # ── Enviar al bot ──────────────────────────────────────────────────
            try:
                response = self.bot.run(self.bot.send_message(current_msg))
            except Exception as exc:
                self.on_error(f"Error al comunicarse con el bot: {exc}")
                return

            if not response or not response.strip():
                self.on_error(
                    f"El bot devolvio una respuesta vacia o None. "
                    f"Valor recibido: {response!r}"
                )
                return

            # ── Notificar el texto de razonamiento ────────────────────────────
            self.on_message(response)

            # ── Parsear acciones ───────────────────────────────────────────────
            actions = parse_actions(response)

            results: list[tuple[Action, str]] = []
            done = False

            for action in actions:
                if action.type == "done":
                    done = True
                    self.on_done(action.content or "Tarea completada.")
                    break

                # Ejecutar y notificar
                result = self.executor.execute(action)
                self.on_action(action, result)
                results.append((action, result))

            if done:
                return

            # ── Si no hay acciones, asumir que terminó ─────────────────────────
            if not results:
                self.on_done("El agente completó la respuesta sin acciones adicionales.")
                return

            # ── Construir mensaje de seguimiento con los resultados ───────────
            current_msg = self._build_followup(results)

        # Límite de iteraciones alcanzado
        self.on_error(
            f"El agente alcanzó el límite de {self.MAX_ITERATIONS} iteraciones "
            f"sin completar la tarea. Puedes continuar enviando un nuevo mensaje."
        )

    # ── Helpers internos ───────────────────────────────────────────────────────

    def _build_followup(self, results: list[tuple[Action, str]]) -> str:
        """Construye el mensaje de seguimiento con los resultados de las acciones."""
        parts = ["Resultados de las acciones ejecutadas:\n"]
        for action, result in results:
            if action.type == "read":
                parts.append(
                    f'<resultado_read path="{action.path}">\n{result}\n</resultado_read>'
                )
            elif action.type == "write":
                parts.append(
                    f'<resultado_write path="{action.path}">\n{result}\n</resultado_write>'
                )
            elif action.type == "shell":
                cmd_preview = action.content[:80].replace('\n', ' ')
                parts.append(
                    f'<resultado_shell cmd="{cmd_preview}">\n{result}\n</resultado_shell>'
                )
        parts.append(
            "\nContinúa con la tarea. Si ya terminaste todo, usa <tabasco:done>."
        )
        return "\n\n".join(parts)
