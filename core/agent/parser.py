"""
Parser de acciones XML para el agente Tabasco Code.

El agente usa tags XML especiales en sus respuestas para indicar
qué operaciones realizar. Este módulo extrae y estructura esas acciones.

Formato reconocido:
    <tabasco:read path="ruta/relativa/archivo.py"/>
    <tabasco:write path="ruta/relativa/archivo.py">contenido</tabasco:write>
    <tabasco:shell>comando</tabasco:shell>
    <tabasco:done>resumen de lo realizado</tabasco:done>
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Action:
    """Una acción extraída de la respuesta del LLM."""
    type: str             # 'read' | 'write' | 'shell' | 'done'
    path: Optional[str] = None   # para read/write
    content: str = ""            # para write/shell/done
    # Posición en el texto original (para mantener orden)
    _pos: int = field(default=0, repr=False, compare=False)


def parse_actions(text: str) -> list[Action]:
    """
    Extrae todas las acciones XML de la respuesta del LLM.

    El parser es tolerante: maneja variaciones de espaciado y también
    detecta tags que estén dentro de bloques de código markdown.

    Returns:
        Lista de Action ordenada por posición de aparición en el texto.
    """
    # Desenvuelve bloques de código markdown (```xml ... ```) para poder parsear
    clean = re.sub(
        r'```(?:xml|tabasco|bash|sh)?\n?(.*?)\n?```',
        r'\1',
        text,
        flags=re.DOTALL,
    )

    actions: list[Action] = []

    # ── read: <tabasco:read path="..."/>  ─────────────────────────────────────
    for m in re.finditer(
        r'<tabasco:read\s+path="([^"]+)"\s*(?:/>|></tabasco:read>)',
        clean,
    ):
        actions.append(Action(type="read", path=m.group(1).strip(), _pos=m.start()))

    # ── write: <tabasco:write path="...">content</tabasco:write> ─────────────
    for m in re.finditer(
        r'<tabasco:write\s+path="([^"]+)">\n?(.*?)\n?</tabasco:write>',
        clean,
        re.DOTALL,
    ):
        actions.append(Action(
            type="write",
            path=m.group(1).strip(),
            content=m.group(2),
            _pos=m.start(),
        ))

    # ── shell: <tabasco:shell>command</tabasco:shell> ─────────────────────────
    for m in re.finditer(
        r'<tabasco:shell>\n?(.*?)\n?</tabasco:shell>',
        clean,
        re.DOTALL,
    ):
        actions.append(Action(type="shell", content=m.group(1).strip(), _pos=m.start()))

    # ── done: <tabasco:done>summary</tabasco:done> ────────────────────────────
    for m in re.finditer(
        r'<tabasco:done>\n?(.*?)\n?</tabasco:done>',
        clean,
        re.DOTALL,
    ):
        actions.append(Action(type="done", content=m.group(1).strip(), _pos=m.start()))

    # Ordenar por posición de aparición en el texto
    actions.sort(key=lambda a: a._pos)
    return actions


def extract_text_parts(text: str) -> list[str]:
    """
    Extrae las partes de texto del LLM que no son tags de acción.
    Útil para mostrar el razonamiento del agente entre acciones.
    """
    # Eliminar todos los tags conocidos y devolver lo que queda
    cleaned = re.sub(
        r'<tabasco:(?:read|write|shell|done)[^>]*>.*?</tabasco:\w+>|'
        r'<tabasco:read[^/]*/>\s*',
        '',
        text,
        flags=re.DOTALL,
    )
    # También limpiar bloques de código markdown que contienen acciones
    cleaned = re.sub(r'```(?:xml|tabasco)?\n?.*?\n?```', '', cleaned, flags=re.DOTALL)
    return [part.strip() for part in cleaned.split('\n') if part.strip()]
