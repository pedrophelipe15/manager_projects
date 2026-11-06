from modules.flow.db import get_db_connection, resolve_key
from fastapi import APIRouter

router = APIRouter()


# --- Issues & Timeline ---

@router.get("/api/issues")
def get_issues():
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT 
            i.key,
            i.parent_key,
            i.project_key,
            i.assignee_name as assignee,
            i.summary,
            i.status,
            i.created_at,
            i.updated_at,
            i.due_date,
            i.resolved_at,
            m.lead_time_ms,
            m.cycle_time_ms
        FROM issues i
        LEFT JOIN metrics m ON i.key = m.issue_key
        ORDER BY i.updated_at DESC
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


@router.get("/api/issues/{key}/timeline")
def get_issue_timeline(key: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Normaliza key antiga (issue migrada de projeto) para a key atual
    key = resolve_key(conn, key)

    # Busca regras de blacklist ativas
    cursor.execute("SELECT type, value FROM blacklist_rules WHERE enabled = 1")
    rules = cursor.fetchall()
    blocked_authors = [r['value'] for r in rules if r['type'] == 'author']
    blocked_fields = [r['value'] for r in rules if r['type'] == 'field']

    query = """
        SELECT 
            author_name,
            author_avatar_url,
            event_date,
            field,
            from_value,
            to_value,
            is_cycle_time_interval
        FROM parsed_changelogs
        WHERE issue_key = ?
        ORDER BY event_date ASC
    """
    cursor.execute(query, (key,))
    rows = cursor.fetchall()

    # Aplica blacklist
    events = []
    for row in rows:
        r = dict(row)
        if r['author_name'] in blocked_authors:
            continue
        if r['field'] in blocked_fields:
            continue
        events.append(r)

    # Busca métricas pré-calculadas do banco
    cursor.execute("SELECT lead_time_ms, cycle_time_ms FROM metrics WHERE issue_key = ?", (key,))
    metrics_row = cursor.fetchone()

    conn.close()

    return {
        "events": events,
        "metrics": {
            "lead_time_ms": metrics_row['lead_time_ms'] if metrics_row else 0,
            "cycle_time_ms": metrics_row['cycle_time_ms'] if metrics_row else 0,
        }
    }
