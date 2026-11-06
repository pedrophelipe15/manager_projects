from modules.flow.db import get_db_connection
from fastapi import APIRouter

router = APIRouter()


# --- Due Date: contador de postergações ---

# Deslocamento mínimo (em dias) para uma alteração de due date ser considerada
# uma postergação relevante. Mudanças de <= este valor (ida/volta, ajuste fino)
# são ignoradas para não inflar a contagem com ruído (ex: "3 vezes, 0 dias").
DUE_DATE_SIGNIFICANT_DAYS = 7


@router.get("/api/metrics/due-date-changes")
def api_due_date_changes(project_key: str, min_changes: int = 2):
    """Conta postergações RELEVANTES de due date por issue ativa.

    Só conta alterações onde havia data anterior (from_value não nulo) E o
    deslocamento individual (|to - from|) é superior a DUE_DATE_SIGNIFICANT_DAYS
    dias. Ajustes finos ou ida/volta que somam pouco são ignorados.
    Retorna apenas issues com contagem de alterações relevantes >= min_changes.
    """
    from datetime import date

    def _parse_due(v):
        """Converte um valor de due date do changelog em date. Aceita ISO ou 'YYYY-MM-DD ...'."""
        if not v:
            return None
        s = str(v).strip()
        if not s:
            return None
        s = s.replace("T", " ").split(" ")[0]  # pega só a parte da data
        try:
            y, m, d = s.split("-")
            return date(int(y), int(m), int(d))
        except (ValueError, TypeError):
            return None

    conn = get_db_connection()
    cursor = conn.cursor()

    # Candidatas: issues ativas com pelo menos 1 mudança de duedate com valor anterior
    cursor.execute("""
        SELECT DISTINCT pc.issue_key
        FROM parsed_changelogs pc
        INNER JOIN issues i ON pc.issue_key = i.key
        WHERE pc.field = 'duedate'
          AND pc.from_value IS NOT NULL AND TRIM(pc.from_value) != ''
          AND i.project_key = ?
          AND i.status NOT IN ('Done', 'Canceled', 'Reject', 'Removed')
    """, (project_key,))
    candidate_keys = [r["issue_key"] for r in cursor.fetchall()]

    result = []
    for key in candidate_keys:
        # Todas as mudanças de duedate da issue, em ordem cronológica
        cursor.execute("""
            SELECT from_value, to_value, event_date
            FROM parsed_changelogs
            WHERE issue_key = ? AND field = 'duedate'
            ORDER BY event_date ASC
        """, (key,))
        due_rows = cursor.fetchall()

        first_due = None
        last_due = None
        significant_changes = 0
        for dr in due_rows:
            fv = _parse_due(dr["from_value"])
            tv = _parse_due(dr["to_value"])
            if first_due is None and fv is not None:
                first_due = fv
            if tv is not None:
                last_due = tv
            # Conta só deslocamentos relevantes (> limite, em qualquer direção)
            if fv is not None and tv is not None and abs((tv - fv).days) > DUE_DATE_SIGNIFICANT_DAYS:
                significant_changes += 1

        if significant_changes < min_changes:
            continue

        days_postponed = None
        if first_due is not None and last_due is not None:
            days_postponed = (last_due - first_due).days

        # Ignora se a postergação líquida acumulada for <= limite (ex: foi e voltou = 0 dias)
        if days_postponed is None or abs(days_postponed) <= DUE_DATE_SIGNIFICANT_DAYS:
            continue

        cursor.execute(
            "SELECT key, summary, status, assignee_name, due_date FROM issues WHERE key = ?",
            (key,),
        )
        info = cursor.fetchone()
        if not info:
            continue

        result.append({
            "key": info["key"],
            "summary": info["summary"],
            "status": info["status"],
            "assignee": info["assignee_name"],
            "due_date": info["due_date"],
            "changes": significant_changes,
            "first_due_date": first_due.isoformat() if first_due else None,
            "last_due_date": last_due.isoformat() if last_due else None,
            "days_postponed": days_postponed,
        })

    # Ordena por dias de postergação desc (mais crítico primeiro)
    result.sort(key=lambda x: (x["days_postponed"] or 0), reverse=True)

    conn.close()
    return {
        "project_key": project_key,
        "min_changes": min_changes,
        "significant_threshold_days": DUE_DATE_SIGNIFICANT_DAYS,
        "issues": result,
    }


# --- Inconsistencies ---

@router.get("/api/inconsistencies")
def get_inconsistencies(project_key: str | None = None):
    """Retorna inconsistências detectadas no banco, respeitando regras habilitadas."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Carrega regras de validação
    cursor.execute("SELECT id, enabled, statuses FROM validation_rules")
    rules = {r["id"]: {"enabled": r["enabled"], "statuses": r["statuses"].split(",")} for r in cursor.fetchall()}

    results = {
        "due_date_parent_vs_subtask": [],
        "due_date_empty": [],
        "done_without_metrics": [],
        "active_without_cycle": [],
        "active_without_assignee": [],
        "story_stale_active_subtask": [],
    }

    project_filter = ""
    params = []
    if project_key:
        project_filter = "AND i.project_key = ?"
        params = [project_key]

    # 1. Due date de Story/parent menor que due date das subtasks
    if rules.get("due_date_parent_vs_subtask", {}).get("enabled"):
        statuses = rules["due_date_parent_vs_subtask"]["statuses"]
        status_ph = ",".join([f"'{s.strip()}'" for s in statuses])
        cursor.execute(f"""
            SELECT 
                parent.key as parent_key,
                parent.summary as parent_summary,
                parent.due_date as parent_due_date,
                parent.status as parent_status,
                child.key as child_key,
                child.summary as child_summary,
                child.due_date as child_due_date,
                child.status as child_status,
                child.assignee_name as child_assignee,
                child.created_at as child_created_at,
                child.updated_at as child_updated_at,
                parent.project_key
            FROM issues child
            INNER JOIN issues parent ON child.parent_key = parent.key
            WHERE child.status IN ({status_ph})
                AND parent.due_date IS NOT NULL
                AND child.due_date IS NOT NULL
                AND parent.due_date < child.due_date
                {'AND child.project_key = ?' if project_key else ''}
        """, params)
        for row in cursor.fetchall():
            results["due_date_parent_vs_subtask"].append(dict(row))

    # 2. Due date sem preenchimento
    if rules.get("due_date_empty", {}).get("enabled"):
        statuses = rules["due_date_empty"]["statuses"]
        status_ph = ",".join([f"'{s.strip()}'" for s in statuses])
        cursor.execute(f"""
            SELECT 
                i.key, i.summary, i.status, i.assignee_name as assignee, i.project_key, i.parent_key,
                i.created_at, i.updated_at, i.due_date
            FROM issues i
            WHERE i.status IN ({status_ph})
                AND (i.due_date IS NULL OR i.due_date = '')
                {project_filter}
        """, params)
        for row in cursor.fetchall():
            results["due_date_empty"].append(dict(row))

    # 3. Done sem cycle time E lead time
    if rules.get("done_without_metrics", {}).get("enabled"):
        cursor.execute(f"""
            SELECT 
                i.key, i.summary, i.status, i.assignee_name as assignee, i.project_key, i.resolved_at,
                i.parent_key, i.created_at, i.updated_at, i.due_date,
                m.lead_time_ms, m.cycle_time_ms
            FROM issues i
            LEFT JOIN metrics m ON i.key = m.issue_key
            WHERE i.status = 'Done'
                AND (m.lead_time_ms IS NULL OR m.lead_time_ms = 0)
                AND (m.cycle_time_ms IS NULL OR m.cycle_time_ms = 0)
                {project_filter}
        """, params)
        for row in cursor.fetchall():
            results["done_without_metrics"].append(dict(row))

    # 4. In Progress / Blocked sem cycle time
    if rules.get("active_without_cycle", {}).get("enabled"):
        statuses = rules["active_without_cycle"]["statuses"]
        status_ph = ",".join([f"'{s.strip()}'" for s in statuses])
        cursor.execute(f"""
            SELECT 
                i.key, i.summary, i.status, i.assignee_name as assignee, i.project_key, i.created_at,
                i.parent_key, i.updated_at, i.due_date,
                m.cycle_time_ms
            FROM issues i
            LEFT JOIN metrics m ON i.key = m.issue_key
            WHERE i.status IN ({status_ph})
                AND (m.cycle_time_ms IS NULL OR m.cycle_time_ms = 0)
                {project_filter}
        """, params)
        for row in cursor.fetchall():
            results["active_without_cycle"].append(dict(row))

    # 5. In Progress / Blocked sem assignee
    if rules.get("active_without_assignee", {}).get("enabled"):
        statuses = rules["active_without_assignee"]["statuses"]
        status_ph = ",".join([f"'{s.strip()}'" for s in statuses])
        cursor.execute(f"""
            SELECT 
                i.key, i.summary, i.status, i.project_key, i.created_at,
                i.parent_key, i.assignee_name as assignee, i.updated_at, i.due_date
            FROM issues i
            WHERE i.status IN ({status_ph})
                AND (i.assignee_name IS NULL OR i.assignee_name = '')
                {project_filter}
        """, params)
        for row in cursor.fetchall():
            results["active_without_assignee"].append(dict(row))

    # 6. Story parada (status nao-ativo) com subtask ativa.
    #    O 'statuses' da regra define o que conta como "ativo" para a subtask.
    #    Status nao-ativos da story: tudo que NAO e ativo e NAO e concluido.
    if rules.get("story_stale_active_subtask", {}).get("enabled"):
        active_statuses = [s.strip() for s in rules["story_stale_active_subtask"]["statuses"]]
        active_ph = ",".join([f"'{s}'" for s in active_statuses])
        # Story (parent) nao pode estar ativa nem concluida/cancelada.
        done_like = ["Done", "Resolved", "Canceled", "Reject", "Removed"]
        parent_exclude = active_statuses + done_like
        parent_excl_ph = ",".join([f"'{s}'" for s in parent_exclude])
        q = f"""
            SELECT
                parent.key AS parent_key,
                parent.summary AS parent_summary,
                parent.status AS parent_status,
                parent.assignee_name AS parent_assignee,
                parent.due_date AS parent_due_date,
                parent.project_key AS project_key,
                child.key AS child_key,
                child.summary AS child_summary,
                child.status AS child_status,
                child.assignee_name AS child_assignee,
                child.updated_at AS child_updated_at
            FROM issues child
            INNER JOIN issues parent ON child.parent_key = parent.key
            WHERE child.status IN ({active_ph})
              AND parent.status NOT IN ({parent_excl_ph})
              {'AND parent.project_key = ?' if project_key else ''}
            ORDER BY parent.key, child.key
        """
        cursor.execute(q, params)
        for row in cursor.fetchall():
            results["story_stale_active_subtask"].append(dict(row))

    conn.close()

    return {
        "project_key": project_key,
        "inconsistencies": results,
        "totals": {
            "due_date_parent_vs_subtask": len(results["due_date_parent_vs_subtask"]),
            "due_date_empty": len(results["due_date_empty"]),
            "done_without_metrics": len(results["done_without_metrics"]),
            "active_without_cycle": len(results["active_without_cycle"]),
            "active_without_assignee": len(results["active_without_assignee"]),
            "story_stale_active_subtask": len(results["story_stale_active_subtask"]),
            "total": sum(len(v) for v in results.values()),
        }
    }
