from kernel.jobs import JobRunner
from modules.hierarchy.config import load_entries
from fastapi import APIRouter

router = APIRouter()


# =============================================================================
# --- Hierarchy API (pipeline isolada — hierarchy.db) ---
# =============================================================================


# Job da sync hierárquica (estado/log/thread geridos pelo kernel.jobs)
hierarchy_sync_job = JobRunner("hierarchy_sync")


def _load_hierarchy_config() -> list[dict]:
    """Carrega a configuração de hierarquias (chave `hierarchy` do projects.yaml) via ConfigStore."""
    return load_entries()
