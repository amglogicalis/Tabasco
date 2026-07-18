"""
Módulo de historial de conversaciones locales.
Guarda y carga chats por bot en: data/history/<bot_name>/
Formato: JSON con lista de mensajes {role, text, timestamp}
"""
import json
from pathlib import Path
from datetime import datetime

# Directorio base de historiales
_BASE = Path(__file__).parent.parent / "data" / "history"


def _bot_dir(bot_name: str) -> Path:
    d = _BASE / bot_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_file(bot_name: str, session_id: str) -> Path:
    return _bot_dir(bot_name) / f"{session_id}.json"


# ─── API pública ────────────────────────────────────────────────────────────

def new_session_id() -> str:
    """Genera un ID de sesión basado en la fecha y hora actuales."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_session(bot_name: str, session_id: str, messages: list[dict], url: str = ""):
    """
    Guarda la sesión en disco.
    messages: lista de dicts {role: 'user'|'bot'|'error', text: str, timestamp: str}
    Solo guarda si hay al menos un mensaje de usuario o bot real.
    """
    if not any(m["role"] in ("user", "bot") for m in messages):
        return
    data = {
        "bot": bot_name,
        "session_id": session_id,
        "saved_at": datetime.now().isoformat(),
        "url": url,
        "messages": messages,
    }
    try:
        _session_file(bot_name, session_id).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        print(f"[History] Error al guardar sesión: {e}", flush=True)


def load_session(bot_name: str, session_id: str) -> list[dict]:
    """Carga los mensajes de una sesión guardada."""
    f = _session_file(bot_name, session_id)
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data.get("messages", [])
    except Exception as e:
        print(f"[History] Error al cargar sesión {session_id}: {e}", flush=True)
        return []


def load_session_full(bot_name: str, session_id: str) -> dict:
    """Carga todos los datos de una sesión guardada en JSON."""
    f = _session_file(bot_name, session_id)
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[History] Error al cargar sesión completa {session_id}: {e}", flush=True)
        return {}


def list_sessions(bot_name: str) -> list[dict]:
    """
    Lista todas las sesiones guardadas para un bot, ordenadas de más reciente a más antigua.
    Devuelve lista de dicts: {session_id, saved_at, preview (primer mensaje de usuario), count}
    """
    d = _bot_dir(bot_name)
    sessions = []
    for f in sorted(d.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            msgs = data.get("messages", [])
            # Preview: primer mensaje del usuario
            preview = next(
                (m["text"][:60] for m in msgs if m["role"] == "user"),
                "(sin mensajes)"
            )
            sessions.append({
                "session_id": data.get("session_id", f.stem),
                "saved_at": data.get("saved_at", ""),
                "preview": preview,
                "count": len([m for m in msgs if m["role"] in ("user", "bot")]),
            })
        except Exception:
            pass
    return sessions


def delete_session(bot_name: str, session_id: str):
    """Elimina una sesión del historial."""
    f = _session_file(bot_name, session_id)
    if f.exists():
        f.unlink()


def delete_all_sessions(bot_name: str):
    """Elimina todo el historial de un bot."""
    import shutil
    d = _bot_dir(bot_name)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
