import json as _json
from fastapi import HTTPException
from modules.hierarchy.db import get_hierarchy_connection
from kernel.shared.constants import ACTIVE_STATES
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/hierarchy/sync/history")
def get_hierarchy_sync_history():
    """Retorna histórico completo de sincronizações hierárquicas."""
    conn = get_hierarchy_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM h_sync_history ORDER BY id DESC LIMIT 20")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/api/hierarchy/tree")
def get_hierarchy_tree(key: str):
    """Retorna árvore completa a partir de uma initiative ou epic key.
    
    Se key for uma initiative: retorna initiative → epics → stories → subtasks
    Se key for um epic: retorna epic → stories → subtasks
    Inclui métricas (lead/cycle time) para stories e subtasks.
    """
    conn = get_hierarchy_connection()
    cursor = conn.cursor()

    # Tenta como initiative
    cursor.execute("SELECT * FROM h_initiatives WHERE key = ?", (key,))
    initiative = cursor.fetchone()

    if initiative:
        # Busca épicos filhos
        initiative_dict = dict(initiative)
        children_keys = _json.loads(initiative_dict.get("children_keys") or "[]")

        epics = []
        if children_keys:
            placeholders = ",".join(["?" for _ in children_keys])
            cursor.execute(f"SELECT * FROM h_epics WHERE key IN ({placeholders})", children_keys)
            epics_rows = cursor.fetchall()
        else:
            # Fallback: busca por parent_key
            cursor.execute("SELECT * FROM h_epics WHERE parent_key = ?", (key,))
            epics_rows = cursor.fetchall()

        for epic_row in epics_rows:
            epic = dict(epic_row)
            epic["stories"] = _get_stories_for_epic(cursor, epic["key"])
            epics.append(epic)

        conn.close()
        return {
            "type": "initiative",
            "initiative": initiative_dict,
            "epics": epics,
            "summary_metrics": _aggregate_metrics_for_epics(epics),
        }

    # Tenta como epic
    cursor.execute("SELECT * FROM h_epics WHERE key = ?", (key,))
    epic = cursor.fetchone()

    if epic:
        epic_dict = dict(epic)
        epic_dict["stories"] = _get_stories_for_epic(cursor, key)

        conn.close()
        return {
            "type": "epic",
            "epic": epic_dict,
            "summary_metrics": _aggregate_metrics_for_stories(epic_dict["stories"]),
        }

    conn.close()
    raise HTTPException(status_code=404, detail=f"Key '{key}' não encontrada em h_initiatives nem h_epics")


def _get_stories_for_epic(cursor, epic_key: str) -> list[dict]:
    """Busca stories de um epic com métricas e subtasks."""
    cursor.execute("SELECT * FROM h_stories WHERE parent_key = ?", (epic_key,))
    stories_rows = cursor.fetchall()

    stories = []
    for story_row in stories_rows:
        story = dict(story_row)

        # Métricas da story
        cursor.execute("SELECT lead_time_ms, cycle_time_ms FROM h_metrics WHERE issue_key = ?", (story["key"],))
        metrics = cursor.fetchone()
        story["lead_time_ms"] = metrics["lead_time_ms"] if metrics else 0
        story["cycle_time_ms"] = metrics["cycle_time_ms"] if metrics else 0

        # Issue links da story
        cursor.execute("SELECT linked_key, direction, relation FROM h_issue_links WHERE issue_key = ?", (story["key"],))
        links_rows = cursor.fetchall()
        story["issue_links"] = [dict(r) for r in links_rows]

        # Subtasks
        cursor.execute("SELECT * FROM h_subtasks WHERE parent_key = ?", (story["key"],))
        subtasks_rows = cursor.fetchall()
        subtasks = []
        for sub_row in subtasks_rows:
            sub = dict(sub_row)
            cursor.execute("SELECT lead_time_ms, cycle_time_ms FROM h_metrics WHERE issue_key = ?", (sub["key"],))
            sub_metrics = cursor.fetchone()
            sub["lead_time_ms"] = sub_metrics["lead_time_ms"] if sub_metrics else 0
            sub["cycle_time_ms"] = sub_metrics["cycle_time_ms"] if sub_metrics else 0
            subtasks.append(sub)

        story["subtasks"] = subtasks
        stories.append(story)

    return stories


def _aggregate_metrics_for_stories(stories: list[dict]) -> dict:
    """Calcula métricas agregadas para uma lista de stories."""
    total = len(stories)
    done = sum(1 for s in stories if s.get("status") in ("Done", "Resolved", "Canceled"))
    in_progress = sum(1 for s in stories if s.get("status") in ACTIVE_STATES)

    lead_times = [s["lead_time_ms"] for s in stories if s.get("lead_time_ms", 0) > 0]
    cycle_times = [s["cycle_time_ms"] for s in stories if s.get("cycle_time_ms", 0) > 0]

    return {
        "total_stories": total,
        "done": done,
        "in_progress": in_progress,
        "progress_pct": round((done / total * 100) if total > 0 else 0, 1),
        "avg_lead_time_ms": int(sum(lead_times) / len(lead_times)) if lead_times else 0,
        "avg_cycle_time_ms": int(sum(cycle_times) / len(cycle_times)) if cycle_times else 0,
        "p85_lead_time_ms": _percentile(lead_times, 85),
        "p85_cycle_time_ms": _percentile(cycle_times, 85),
    }


def _aggregate_metrics_for_epics(epics: list[dict]) -> dict:
    """Calcula métricas agregadas para uma lista de epics (agrupa stories de todos eles)."""
    all_stories = []
    for epic in epics:
        all_stories.extend(epic.get("stories", []))
    metrics = _aggregate_metrics_for_stories(all_stories)
    metrics["total_epics"] = len(epics)
    return metrics


def _percentile(data: list, pct: int) -> int:
    """Calcula percentil de uma lista numérica."""
    if not data:
        return 0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * pct / 100)
    idx = min(idx, len(sorted_data) - 1)
    return sorted_data[idx]
