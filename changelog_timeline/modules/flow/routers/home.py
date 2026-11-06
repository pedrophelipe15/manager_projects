from modules.flow.metrics.wave5_commitment import get_commitment_summary_all
from modules.flow.db import get_db_connection
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/home/overview")
def api_home_overview(project_keys: str | None = None):
    """Visão consolidada da home 'Minha Visão'.

    Para cada projeto (todos, ou apenas os informados em project_keys separados
    por vírgula), retorna: commitment score, contagem por classificação, WIP,
    bloqueadas, sem responsável, paradas >14 dias e as issues acionáveis
    ('precisa de você hoje').
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Escopo de projetos
    if project_keys:
        wanted = [k.strip() for k in project_keys.split(",") if k.strip()]
    else:
        cursor.execute("SELECT DISTINCT project_key FROM issues WHERE project_key IS NOT NULL")
        wanted = [r["project_key"] for r in cursor.fetchall()]

    # Commitment por projeto (dict para lookup)
    commitment = {c["project_key"]: c for c in get_commitment_summary_all(conn).get("projects", [])}

    from datetime import datetime, timedelta, date
    now = datetime.now()
    stale_cutoff = now - timedelta(days=14)
    overdue_cutoff = date.today() - timedelta(days=7)  # due date vencido ha mais de 7 dias
    active_states = ("In Progress", "Blocked", "Test", "Waiting for Delivery")
    active_ph = ",".join(["?"] * len(active_states))

    def parse_due(due):
        """Converte due_date (YYYY-MM-DD ou ISO) para date; None se invalido/vazio."""
        if not due:
            return None
        try:
            return datetime.fromisoformat(str(due).split("T")[0]).date()
        except (ValueError, TypeError):
            return None

    projects = []
    for pk in sorted(wanted):
        # Contagens de status ativo
        cursor.execute(
            f"SELECT status, assignee_name, key, summary, updated_at FROM issues "
            f"WHERE project_key = ? AND status IN ({active_ph})",
            [pk, *active_states],
        )
        active_rows = cursor.fetchall()

        # Vencidas > 7 dias: apenas status ativos, com due date no passado.
        cursor.execute(
            f"SELECT due_date FROM issues WHERE project_key = ? AND status IN ({active_ph}) "
            f"AND due_date IS NOT NULL AND due_date != ''",
            [pk, *active_states],
        )
        overdue = 0
        for r in cursor.fetchall():
            dd = parse_due(r["due_date"])
            if dd is not None and dd < overdue_cutoff:
                overdue += 1

        in_flight = sum(1 for r in active_rows if r["status"] in ("In Progress", "Test", "Waiting for Delivery"))
        blocked = sum(1 for r in active_rows if r["status"] == "Blocked")
        no_assignee = sum(1 for r in active_rows if not (r["assignee_name"] or "").strip())

        stale = 0
        for r in active_rows:
            if not r["updated_at"]:
                continue
            try:
                upd = datetime.fromisoformat(str(r["updated_at"]).replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, TypeError):
                continue
            if upd < stale_cutoff:
                stale += 1

        c = commitment.get(pk, {})
        counts = c.get("counts", {})
        projects.append({
            "project_key": pk,
            "commitment_score": c.get("commitment_score"),
            "commitment_total": c.get("total_issues", 0),
            "commitment_counts": {
                "kept": counts.get("kept", 0),
                "replanned": counts.get("replanned", 0),
                "attention": counts.get("attention", 0),
                "pushing": counts.get("pushing", 0),
            },
            "pushing": counts.get("pushing", 0),
            "attention": counts.get("attention", 0),
            "in_flight": in_flight,
            "blocked": blocked,
            "no_assignee": no_assignee,
            "stale": stale,
            "overdue": overdue,
        })

    conn.close()
    # As issues por indicador sao carregadas sob demanda via /api/home/detail
    # (modal ao clicar no indicador do card). A home so devolve os agregados.
    return {"projects": projects}


@router.get("/api/home/detail")
def api_home_detail(project_key: str, metric: str):
    """Lista as issues reais por tras de um indicador da home 'Minha Visão'.

    metric: pushing | attention | blocked | no_assignee | in_flight | stale
    Alimenta o modal que abre ao clicar num indicador do card de projeto.
    """
    from datetime import datetime, timedelta

    valid = {"pushing", "attention", "blocked", "no_assignee", "in_flight", "stale", "overdue"}
    if metric not in valid:
        return {"error": f"metric invalido. Use um de: {sorted(valid)}", "issues": []}

    conn = get_db_connection()
    cursor = conn.cursor()
    JIRA = "https://jiraps.atlassian.net/browse/"

    meta = {
        "pushing": {
            "title": "Prazo empurrado (3x+)",
            "desc": "Issues com due date reprogramado 3 ou mais vezes.",
        },
        "attention": {
            "title": "Prazo em atencao (2x)",
            "desc": "Issues com due date reprogramado 2 vezes.",
        },
        "blocked": {"title": "Bloqueado", "desc": "Issues em status Blocked."},
        "no_assignee": {"title": "Sem responsavel", "desc": "Issues ativas sem responsavel atribuido."},
        "in_flight": {"title": "Em andamento", "desc": "Issues em In Progress, Test ou Waiting for Delivery."},
        "stale": {"title": "Paradas > 14 dias", "desc": "Issues ativas sem atualizacao ha mais de 14 dias."},
        "overdue": {"title": "Vencidas > 7 dias", "desc": "Issues ativas (In Progress, Blocked, Test, Waiting for Delivery) com due date vencido ha mais de 7 dias."},
    }

    issues = []

    if metric == "overdue":
        from datetime import date, timedelta
        overdue_cutoff = date.today() - timedelta(days=7)
        today = date.today()
        active_states_ov = ("In Progress", "Blocked", "Test", "Waiting for Delivery")
        active_ph_ov = ",".join(["?"] * len(active_states_ov))
        cursor.execute(
            f"SELECT key, summary, status, assignee_name, due_date FROM issues "
            f"WHERE project_key = ? AND status IN ({active_ph_ov}) "
            f"AND due_date IS NOT NULL AND due_date != ''",
            [project_key, *active_states_ov],
        )
        for r in cursor.fetchall():
            due = r["due_date"]
            try:
                dd = datetime.fromisoformat(str(due).split("T")[0]).date()
            except (ValueError, TypeError):
                continue
            if dd >= overdue_cutoff:
                continue
            days_late = (today - dd).days
            issues.append({
                "key": r["key"],
                "url": JIRA + r["key"],
                "summary": r["summary"] or "",
                "assignee": r["assignee_name"] or "Sem responsavel",
                "status": r["status"] or "",
                "due_date": due,
                "detail": f"vencida ha {days_late}d",
                "days_late": days_late,
            })
        # Mais atrasadas primeiro.
        issues.sort(key=lambda x: x["days_late"], reverse=True)
    elif metric in ("pushing", "attention"):
        classification = "pushing" if metric == "pushing" else "attention"
        cursor.execute(
            """
            SELECT s.issue_key, s.assignee_name, s.reschedules, s.total_days_pushed,
                   s.original_due, s.current_due, i.summary, i.status
            FROM metrics_due_date_slippage s
            LEFT JOIN issues i ON i.key = s.issue_key
            WHERE s.project_key = ? AND s.classification = ?
            ORDER BY s.reschedules DESC, s.total_days_pushed DESC
            """,
            (project_key, classification),
        )
        for r in cursor.fetchall():
            issues.append({
                "key": r["issue_key"],
                "url": JIRA + r["issue_key"],
                "summary": r["summary"] or "",
                "assignee": r["assignee_name"] or "Sem responsavel",
                "status": r["status"] or "",
                "due_date": r["current_due"],
                "detail": f"{r['reschedules']} reprogramacoes · +{r['total_days_pushed']}d",
                "original_due": r["original_due"],
                "current_due": r["current_due"],
            })

        # Somente para "pushing": reconstroi o historico de due dates (array de todos
        # os prazos que a issue teve) a partir dos changelogs do campo 'duedate'.
        if metric == "pushing" and issues:
            def _due_only(v):
                if not v:
                    return ""
                return str(v).replace("T", " ").split(" ")[0].strip()

            keys = [it["key"] for it in issues]
            kph = ",".join(["?"] * len(keys))
            cursor.execute(
                f"""
                SELECT issue_key, from_value, to_value, event_date
                FROM parsed_changelogs
                WHERE field = 'duedate' AND issue_key IN ({kph})
                ORDER BY issue_key, event_date ASC
                """,
                keys,
            )
            hist = {}
            for c in cursor.fetchall():
                seq = hist.setdefault(c["issue_key"], [])
                frm = _due_only(c["from_value"])
                to = _due_only(c["to_value"])
                # Primeiro evento: inclui o valor de origem (prazo original).
                if not seq and frm:
                    seq.append(frm)
                if to:
                    seq.append(to)
            for it in issues:
                seq = hist.get(it["key"], [])
                # Garante que o original_due apareca primeiro, se o changelog nao capturou.
                if it.get("original_due") and (not seq or seq[0] != _due_only(it["original_due"])):
                    od = _due_only(it["original_due"])
                    if od and od not in seq:
                        seq = [od] + seq
                it["due_history"] = seq
    else:
        active_states = ("In Progress", "Blocked", "Test", "Waiting for Delivery")
        active_ph = ",".join(["?"] * len(active_states))
        cursor.execute(
            f"SELECT key, summary, status, assignee_name, updated_at, due_date FROM issues "
            f"WHERE project_key = ? AND status IN ({active_ph})",
            [project_key, *active_states],
        )
        rows = cursor.fetchall()
        now = datetime.now()
        stale_cutoff = now - timedelta(days=14)

        def days_since(updated):
            if not updated:
                return None
            try:
                upd = datetime.fromisoformat(str(updated).replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, TypeError):
                return None
            return (now - upd).days

        for r in rows:
            status = r["status"]
            has_assignee = bool((r["assignee_name"] or "").strip())
            d = days_since(r["updated_at"])
            keep = False
            detail = ""
            if metric == "blocked" and status == "Blocked":
                keep = True
                detail = f"parado ha {d}d" if d is not None else "Bloqueado"
            elif metric == "no_assignee" and not has_assignee:
                keep = True
                detail = status
            elif metric == "in_flight" and status in ("In Progress", "Test", "Waiting for Delivery"):
                keep = True
                detail = status
            elif metric == "stale":
                upd_dt = None
                if r["updated_at"]:
                    try:
                        upd_dt = datetime.fromisoformat(str(r["updated_at"]).replace("Z", "+00:00")).replace(tzinfo=None)
                    except (ValueError, TypeError):
                        upd_dt = None
                if upd_dt is not None and upd_dt < stale_cutoff:
                    keep = True
                    detail = f"sem atualizacao ha {d}d"
            if keep:
                issues.append({
                    "key": r["key"],
                    "url": JIRA + r["key"],
                    "summary": r["summary"] or "",
                    "assignee": r["assignee_name"] or "Sem responsavel",
                    "status": status,
                    "due_date": r["due_date"],
                    "detail": detail,
                })

        # Ordena os "parados" pelos mais antigos primeiro; demais por status.
        if metric == "stale":
            issues.sort(key=lambda x: x["detail"], reverse=True)

    conn.close()
    m = meta[metric]
    return {
        "project_key": project_key,
        "metric": metric,
        "title": m["title"],
        "description": m["desc"],
        "count": len(issues),
        "issues": issues,
    }
