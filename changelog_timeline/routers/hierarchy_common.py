import threading
from modules.hierarchy.config import load_entries
from fastapi import APIRouter

router = APIRouter()


# =============================================================================
# --- Hierarchy API (pipeline isolada — hierarchy.db) ---
# =============================================================================


# Estado global de sync hierárquica
hierarchy_sync_state = {
    "running": False,
    "progress": [],
    "error": None,
}


hierarchy_sync_lock = threading.Lock()


def _load_hierarchy_config() -> list[dict]:
    """Carrega a configuração de hierarquias (chave `hierarchy` do projects.yaml) via ConfigStore."""
    return load_entries()
