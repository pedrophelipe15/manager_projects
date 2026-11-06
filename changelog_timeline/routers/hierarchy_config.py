import json as _json
from fastapi import HTTPException
from modules.hierarchy.db import get_hierarchy_connection
from pydantic import BaseModel
from routers.hierarchy_common import _load_hierarchy_config
from modules.hierarchy.config import load_excluded_raw, update_entries, update_excluded
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/hierarchy/config")
def get_hierarchy_config():
    """Retorna configurações de hierarquias do projects.yaml."""
    return _load_hierarchy_config()


class HierarchyConfigEntry(BaseModel):
    key: str
    name: str
    type: str  # "initiative" ou "epic"


@router.post("/api/hierarchy/config", status_code=201)
def add_hierarchy_config(entry: HierarchyConfigEntry):
    """Adiciona uma nova entrada de hierarquia ao projects.yaml."""
    if entry.type not in ("initiative", "epic"):
        raise HTTPException(status_code=400, detail="type deve ser 'initiative' ou 'epic'")
    if not entry.key.strip():
        raise HTTPException(status_code=400, detail="key não pode ser vazio")

    new_entry = {"key": entry.key.strip(), "name": entry.name.strip(), "type": entry.type}

    def _add(entries: list):
        # Verifica duplicata sob lock (sem corrida entre duas requisições)
        if any(e["key"] == new_entry["key"] for e in entries):
            raise HTTPException(status_code=409, detail=f"Key '{entry.key}' já existe na configuração")
        entries.append(new_entry)

    update_entries(_add)
    return new_entry


@router.put("/api/hierarchy/config/{key}")
def update_hierarchy_config(key: str, entry: HierarchyConfigEntry):
    """Atualiza uma entrada de hierarquia no projects.yaml."""
    updated = {"key": entry.key.strip(), "name": entry.name.strip(), "type": entry.type}

    def _update(entries: list):
        idx = next((i for i, e in enumerate(entries) if e["key"] == key), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"Key '{key}' não encontrada")
        entries[idx] = updated

    update_entries(_update)
    return updated


@router.delete("/api/hierarchy/config/{key}")
def delete_hierarchy_config(key: str):
    """Remove uma entrada de hierarquia do projects.yaml."""
    def _remove(entries: list):
        kept = [e for e in entries if e["key"] != key]
        if len(kept) == len(entries):
            raise HTTPException(status_code=404, detail=f"Key '{key}' não encontrada")
        entries[:] = kept

    update_entries(_remove)
    return {"message": f"Hierarquia '{key}' removida"}


# --- Limpar DADOS de uma hierarquia do hierarchy.db (destrutivo, separado da config) ---

def _collect_hierarchy_keys(cur, key: str) -> dict:
    """Resolve a subárvore de uma key (initiative ou epic) e retorna as keys por nível.

    initiative -> seus epics -> stories -> subtasks. epic -> stories -> subtasks.
    """
    import json as _json
    initiatives, epics, stories, subtasks = [], [], [], []

    cur.execute("SELECT children_keys FROM h_initiatives WHERE key = ?", (key,))
    ini = cur.fetchone()
    if ini is not None:
        initiatives = [key]
        epic_keys = _json.loads(ini["children_keys"] or "[]") if ini["children_keys"] else []
        if not epic_keys:
            cur.execute("SELECT key FROM h_epics WHERE parent_key = ?", (key,))
            epic_keys = [r["key"] for r in cur.fetchall()]
        epics = epic_keys
    else:
        cur.execute("SELECT key FROM h_epics WHERE key = ?", (key,))
        if cur.fetchone() is None:
            return {}  # key não é initiative nem epic
        epics = [key]

    # Stories dos epics
    for ek in epics:
        cur.execute("SELECT key FROM h_stories WHERE parent_key = ?", (ek,))
        stories.extend([r["key"] for r in cur.fetchall()])
    # Subtasks das stories
    for sk in stories:
        cur.execute("SELECT key FROM h_subtasks WHERE parent_key = ?", (sk,))
        subtasks.extend([r["key"] for r in cur.fetchall()])

    return {"initiatives": initiatives, "epics": epics, "stories": stories, "subtasks": subtasks}


@router.get("/api/hierarchy/config/{key}/data-stats")
def get_hierarchy_data_stats(key: str):
    """Preview: contagem do que seria removido do hierarchy.db para uma key."""
    conn = get_hierarchy_connection()
    cur = conn.cursor()
    scope = _collect_hierarchy_keys(cur, key)
    if not scope:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Key '{key}' não encontrada no hierarchy.db")

    all_keys = scope["initiatives"] + scope["epics"] + scope["stories"] + scope["subtasks"]
    changelogs = metrics = 0
    if all_keys:
        ph = ",".join(["?"] * len(all_keys))
        changelogs = cur.execute(f"SELECT COUNT(*) FROM h_changelogs WHERE issue_key IN ({ph})", all_keys).fetchone()[0]
        metrics = cur.execute(f"SELECT COUNT(*) FROM h_metrics WHERE issue_key IN ({ph})", all_keys).fetchone()[0]
    conn.close()
    return {
        "key": key,
        "initiatives": len(scope["initiatives"]),
        "epics": len(scope["epics"]),
        "stories": len(scope["stories"]),
        "subtasks": len(scope["subtasks"]),
        "changelogs": changelogs,
        "metrics": metrics,
        "has_data": bool(all_keys),
    }


@router.delete("/api/hierarchy/config/{key}/data")
def delete_hierarchy_data(key: str):
    """Remove os DADOS de uma hierarquia (initiative/epic + filhos) do hierarchy.db.

    Ação DESTRUTIVA e irreversível. NÃO altera o projects.yaml (a config permanece).
    """
    conn = get_hierarchy_connection()
    cur = conn.cursor()
    scope = _collect_hierarchy_keys(cur, key)
    if not scope:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Key '{key}' não encontrada no hierarchy.db")

    all_keys = scope["initiatives"] + scope["epics"] + scope["stories"] + scope["subtasks"]
    if not all_keys:
        conn.close()
        return {"message": f"Nenhum dado para '{key}'", "key": key, "removed": 0}

    ph = ",".join(["?"] * len(all_keys))
    # Changelogs, métricas e links das keys da subárvore
    cur.execute(f"DELETE FROM h_changelogs WHERE issue_key IN ({ph})", all_keys)
    cur.execute(f"DELETE FROM h_metrics WHERE issue_key IN ({ph})", all_keys)
    cur.execute(f"DELETE FROM h_issue_links WHERE issue_key IN ({ph})", all_keys)
    # Registros de cada nível
    if scope["subtasks"]:
        cur.execute(f"DELETE FROM h_subtasks WHERE key IN ({','.join(['?']*len(scope['subtasks']))})", scope["subtasks"])
    if scope["stories"]:
        cur.execute(f"DELETE FROM h_stories WHERE key IN ({','.join(['?']*len(scope['stories']))})", scope["stories"])
    if scope["epics"]:
        cur.execute(f"DELETE FROM h_epics WHERE key IN ({','.join(['?']*len(scope['epics']))})", scope["epics"])
    if scope["initiatives"]:
        cur.execute(f"DELETE FROM h_initiatives WHERE key IN ({','.join(['?']*len(scope['initiatives']))})", scope["initiatives"])

    conn.commit()
    conn.close()
    return {
        "message": f"Dados da hierarquia '{key}' removidos do hierarchy.db",
        "key": key,
        "initiatives_removed": len(scope["initiatives"]),
        "epics_removed": len(scope["epics"]),
        "stories_removed": len(scope["stories"]),
        "subtasks_removed": len(scope["subtasks"]),
    }


# =============================================================================
# Projetos excluídos (não consolidados nem exibidos)
# =============================================================================


def _load_excluded_projects() -> list[str]:
    """Carrega a lista de project_keys excluídos do projects.yaml.

    Projetos excluídos NÃO são consolidados nos cálculos nem exibidos nos
    dashboards de hierarquia. A comparação é feita contra o project_key
    (prefixo da issue key antes do último hífen, ex: 'PSDC' em 'PSDC-1404').
    """
    raw = load_excluded_raw()
    # Normaliza: deriva project_key, uppercase, sem duplicatas, preservando ordem
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        key = _normalize_project_key(item)
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _normalize_project_key(value) -> str:
    """Deriva o project_key a partir de um valor informado.

    Aceita tanto o project_key puro ('PSDC') quanto a issue key completa
    ('PSDC-1404'), retornando sempre o prefixo em uppercase ('PSDC').
    """
    raw = str(value or "").strip().upper()
    if not raw:
        return ""
    # Se for uma issue key (PREFIXO-NUMERO), pega só o prefixo
    if "-" in raw:
        prefix, suffix = raw.rsplit("-", 1)
        if suffix.isdigit() and prefix:
            return prefix
    return raw


def _normalized_unique(raw: list) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        k = _normalize_project_key(item)
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


class ExcludedProjectEntry(BaseModel):
    key: str


# Rotas canônicas em /api/hierarchy/excluded-projects (pertencem ao módulo hierarchy).
# As rotas antigas em /api/settings/excluded-projects continuam funcionando (deprecated).

@router.get("/api/hierarchy/excluded-projects")
@router.get("/api/settings/excluded-projects", deprecated=True)
def api_get_excluded_projects():
    """Retorna a lista de project_keys atualmente excluídos."""
    return {"excluded_projects": _load_excluded_projects()}


@router.post("/api/hierarchy/excluded-projects", status_code=201)
@router.post("/api/settings/excluded-projects", status_code=201, deprecated=True)
def add_excluded_project(entry: ExcludedProjectEntry):
    """Adiciona um project_key à lista de exclusão.

    Aceita tanto o project_key ('PSDC') quanto a issue key ('PSDC-1404'),
    derivando sempre o prefixo do projeto.
    """
    key = _normalize_project_key(entry.key)
    if not key:
        raise HTTPException(status_code=400, detail="key não pode ser vazio")

    def _add(raw: list):
        keys = _normalized_unique(raw)
        if key in keys:
            raise HTTPException(status_code=409, detail=f"Projeto '{key}' já está excluído")
        keys.append(key)
        raw[:] = keys
        return keys

    return {"excluded_projects": update_excluded(_add)}


@router.delete("/api/hierarchy/excluded-projects/{key}")
@router.delete("/api/settings/excluded-projects/{key}", deprecated=True)
def delete_excluded_project(key: str):
    """Remove um project_key da lista de exclusão."""
    key = _normalize_project_key(key)

    def _remove(raw: list):
        keys = _normalized_unique(raw)
        kept = [k for k in keys if k != key]
        if len(kept) == len(keys):
            raise HTTPException(status_code=404, detail=f"Projeto '{key}' não encontrado")
        raw[:] = kept
        return kept

    return {"excluded_projects": update_excluded(_remove)}
