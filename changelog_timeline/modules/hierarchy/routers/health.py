import json as _json
from fastapi import HTTPException
from modules.hierarchy.db import get_hierarchy_connection
from modules.hierarchy.metrics import get_all_epics_health
from modules.hierarchy.metrics import get_all_initiatives_health
from modules.hierarchy.metrics import get_dashboard_v2_data
from modules.hierarchy.metrics import get_epic_health_data
from modules.hierarchy.metrics import get_excluded_projects
from modules.hierarchy.metrics import get_initiative_health_data
from fastapi import APIRouter

router = APIRouter()




# --- Hierarchy: Epic Health Endpoint ---


@router.get("/api/hierarchy/epic-health")
def api_hierarchy_epic_health(key: str | None = None):
    """Retorna dados de saúde de um épico específico ou de todos os épicos.
    
    Parâmetros (query string):
      - key: key do épico (ex: PSADB-1434). Se omitido, retorna todos.
    """
    conn = get_hierarchy_connection()

    if key:
        data = get_epic_health_data(conn, key)
        conn.close()
        if not data:
            raise HTTPException(status_code=404, detail=f"Épico '{key}' não encontrado no hierarchy.db")
        return data
    else:
        data = get_all_epics_health(conn)
        conn.close()
        return data


@router.get("/api/hierarchy/initiative-health")
def api_hierarchy_initiative_health(key: str | None = None):
    """Retorna dados de saúde de uma iniciativa específica ou de todas.
    
    Parâmetros (query string):
      - key: key da iniciativa (ex: GPPGI-325). Se omitido, retorna todas.
    """
    conn = get_hierarchy_connection()

    if key:
        data = get_initiative_health_data(conn, key)
        conn.close()
        if not data:
            raise HTTPException(status_code=404, detail=f"Iniciativa '{key}' não encontrada no hierarchy.db")
        return data
    else:
        data = get_all_initiatives_health(conn)
        conn.close()
        return data


@router.get("/api/hierarchy/dashboard-v2")
def api_hierarchy_dashboard_v2():
    """Retorna dados consolidados do Dashboard V2.
    
    Inclui: big numbers, initiatives health, e épicos órfãos (sem iniciativa).
    """
    conn = get_hierarchy_connection()
    data = get_dashboard_v2_data(conn)
    conn.close()
    return data


@router.get("/api/hierarchy/roadmap")
def api_hierarchy_roadmap():
    """Retorna dados para o Roadmap: stories agrupadas por hierarquia (initiative→epic) + órfãos.
    
    Retorna todas as stories com due_date ou resolved_at, organizadas hierarquicamente.
    """
    conn = get_hierarchy_connection()
    cursor = conn.cursor()

    # Projetos excluídos: não consolidados nem exibidos
    excluded = set(get_excluded_projects())

    def _pk(issue_key):
        """Deriva project_key do prefixo da issue key (antes do último hífen)."""
        if not issue_key:
            return ""
        return issue_key.rsplit("-", 1)[0].upper() if "-" in issue_key else str(issue_key).upper()

    def _fetch_stories(parent_key):
        cursor.execute("""
            SELECT key, summary, status, project_key, assignee_name, due_date, resolved_at
            FROM h_stories WHERE parent_key = ?
        """, (parent_key,))
        stories = []
        for r in cursor.fetchall():
            d = dict(r)
            pk = (d.get("project_key") or _pk(d.get("key"))).upper()
            if pk in excluded:
                continue
            stories.append(d)
        return stories

    # Busca todas as iniciativas com seus épicos e stories
    cursor.execute("SELECT key, summary, project_key FROM h_initiatives")
    initiatives_rows = cursor.fetchall()

    initiatives = []
    for ini_row in initiatives_rows:
        ini = dict(ini_row)
        # Pula iniciativas de projetos excluídos
        if (ini.get("project_key") or _pk(ini.get("key"))).upper() in excluded:
            continue
        # Busca épicos da iniciativa
        children_keys = _json.loads(ini.get("children_keys") or "[]") if "children_keys" in ini.keys() else []
        if not children_keys:
            cursor.execute("SELECT children_keys FROM h_initiatives WHERE key = ?", (ini["key"],))
            ck_row = cursor.fetchone()
            children_keys = _json.loads(ck_row["children_keys"] or "[]") if ck_row else []

        if not children_keys:
            cursor.execute("SELECT key FROM h_epics WHERE parent_key = ?", (ini["key"],))
            children_keys = [r["key"] for r in cursor.fetchall()]

        epics = []
        for ek in children_keys:
            cursor.execute("SELECT key, summary, project_key FROM h_epics WHERE key = ?", (ek,))
            epic_row = cursor.fetchone()
            if not epic_row:
                continue
            epic = dict(epic_row)
            # Pula épicos de projetos excluídos
            if (epic.get("project_key") or _pk(epic.get("key"))).upper() in excluded:
                continue

            epic["stories"] = _fetch_stories(ek)
            epics.append(epic)

        ini["epics"] = epics
        initiatives.append(ini)

    # Busca épicos órfãos (sem parent_key ou parent_key não é uma initiative)
    cursor.execute("SELECT key, summary, parent_key, project_key FROM h_epics")
    all_epics = cursor.fetchall()

    linked_epic_keys = set()
    for ini in initiatives:
        for ep in ini["epics"]:
            linked_epic_keys.add(ep["key"])

    orphan_epics = []
    for ep_row in all_epics:
        # Pula épicos de projetos excluídos
        if (ep_row["project_key"] or _pk(ep_row["key"])).upper() in excluded:
            continue
        if ep_row["key"] not in linked_epic_keys:
            epic = {"key": ep_row["key"], "summary": ep_row["summary"]}
            epic["stories"] = _fetch_stories(ep_row["key"])
            if epic["stories"]:
                orphan_epics.append(epic)

    conn.close()
    return {"initiatives": initiatives, "orphan_epics": orphan_epics}


@router.get("/api/hierarchy/issue-links")
def api_hierarchy_issue_links(issue_key: str | None = None):
    """Retorna issue links da hierarquia.
    
    Parâmetros:
      - issue_key (opcional): filtra links de uma issue específica.
        Se omitido, retorna todos os links.
    
    Retorna lista de links com issue_key, linked_key, direction e relation.
    """
    conn = get_hierarchy_connection()
    cursor = conn.cursor()

    if issue_key:
        # Links onde a issue é origem OU destino
        cursor.execute("""
            SELECT issue_key, linked_key, direction, relation
            FROM h_issue_links
            WHERE issue_key = ? OR linked_key = ?
        """, (issue_key, issue_key))
    else:
        cursor.execute("SELECT issue_key, linked_key, direction, relation FROM h_issue_links")

    rows = cursor.fetchall()
    conn.close()

    return {"issue_links": [dict(r) for r in rows]}


@router.get("/api/hierarchy/pending")
def api_hierarchy_pending():
    """Lista as atividades (stories) PENDENTES da hierarquia, para a aba Pendencias.

    Pendente = status que NAO e concluido. "Resolved" e tratado como concluido
    (= Done), portanto NAO entra. Done/Canceled/Reject tambem ficam de fora.
    Inclui lead_time_ms e cycle_time_ms (calculados, de h_metrics) para cada issue.
    Projetos excluidos (projects.yaml) nao sao retornados.
    """
    conn = get_hierarchy_connection()
    cursor = conn.cursor()

    # Status considerados concluidos (nao-pendentes). Resolved = Done.
    done_states = ("Done", "Resolved", "Canceled", "Reject")
    ph = ",".join(["?"] * len(done_states))

    cursor.execute(f"""
        SELECT s.key, s.summary, s.status, s.issuetype_name, s.project_key,
               s.assignee_name, s.due_date, s.created_at, s.updated_at, s.parent_key,
               COALESCE(m.lead_time_ms, 0)  AS lead_time_ms,
               COALESCE(m.cycle_time_ms, 0) AS cycle_time_ms
        FROM h_stories s
        LEFT JOIN h_metrics m ON m.issue_key = s.key
        WHERE s.status NOT IN ({ph})
    """, done_states)

    excluded = set(get_excluded_projects())

    def _pk(issue_key):
        if not issue_key:
            return ""
        return issue_key.rsplit("-", 1)[0].upper() if "-" in issue_key else str(issue_key).upper()

    issues = []
    for r in cursor.fetchall():
        d = dict(r)
        pk = (d.get("project_key") or _pk(d.get("key"))).upper()
        if pk in excluded:
            continue
        issues.append({
            "key": d["key"],
            "summary": d["summary"] or "",
            "status": d["status"] or "",
            "project_key": d["project_key"] or _pk(d["key"]),
            "assignee": d["assignee_name"] or "",
            "due_date": d["due_date"],
            "created_at": d["created_at"],
            "updated_at": d["updated_at"],
            "parent_key": d["parent_key"] or "",
            "lead_time_ms": d["lead_time_ms"],
            "cycle_time_ms": d["cycle_time_ms"],
        })

    conn.close()
    return {"issues": issues, "count": len(issues)}
