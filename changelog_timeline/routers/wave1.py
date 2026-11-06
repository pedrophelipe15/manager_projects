import sqlite3
import sys
from fastapi import HTTPException
from metrics.wave1_bottleneck.aging_wip import get_aging_wip
from core.db import BASE_DIR, DB_PATH, get_db_connection
from kernel.jobs import JobRunner
from fastapi import APIRouter

router = APIRouter()


# --- Wave 1: Metrics Endpoints ---


sys.path.insert(0, BASE_DIR)


@router.get("/api/metrics/wave1/time-per-status")
def api_time_per_status(project_key: str):
    """Retorna tempo médio e percentis por status para issues Done do projeto.
    Exclui status de espera/backlog que não representam trabalho ativo."""
    import math

    # Status excluídos da análise de gargalo (não representam etapa de fluxo ativo)
    EXCLUDED_STATUSES = {"Open", "Backlog", "To do", "Canceled", "Reject", "Removed", "Done"}

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT status, duration_ms
        FROM metrics_per_status
        WHERE project_key = ? AND issue_key IN (
            SELECT key FROM issues WHERE project_key = ? AND status = 'Done'
        )
        ORDER BY status
    """, (project_key, project_key))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {"project_key": project_key, "statuses": [], "total_issues": 0}

    # Agrupa durações por status, excluindo os não-relevantes
    by_status: dict[str, list[int]] = {}
    for row in rows:
        status = row["status"]
        if status in EXCLUDED_STATUSES:
            continue
        by_status.setdefault(status, []).append(row["duration_ms"])

    def percentile(values: list[int], pct: float) -> int:
        s = sorted(values)
        idx = max(0, min(int(math.ceil(pct / 100.0 * len(s))) - 1, len(s) - 1))
        return s[idx]

    statuses = []
    for status, durations in by_status.items():
        statuses.append({
            "status": status,
            "count": len(durations),
            "avg_ms": int(sum(durations) / len(durations)),
            "p50_ms": percentile(durations, 50),
            "p70_ms": percentile(durations, 70),
            "p85_ms": percentile(durations, 85),
            "p95_ms": percentile(durations, 95),
        })

    # Ordena por p85 descendente (gargalo no topo)
    statuses.sort(key=lambda x: x["p85_ms"], reverse=True)

    # Total de issues Done analisadas
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT issue_key) FROM metrics_per_status WHERE project_key = ? AND issue_key IN (SELECT key FROM issues WHERE project_key = ? AND status = 'Done')", (project_key, project_key))
    total = cursor.fetchone()[0]
    conn.close()

    return {"project_key": project_key, "statuses": statuses, "total_issues": total}


@router.get("/api/metrics/wave1/percentiles")
def api_percentiles(project_key: str):
    """Retorna percentis de lead time e cycle time do projeto."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT metric_type, p50_ms, p70_ms, p85_ms, p95_ms, avg_ms, count FROM metrics_percentiles WHERE project_key = ?", (project_key,))
    rows = cursor.fetchall()
    conn.close()

    result = {}
    for row in rows:
        result[row["metric_type"]] = {
            "p50_ms": row["p50_ms"],
            "p70_ms": row["p70_ms"],
            "p85_ms": row["p85_ms"],
            "p95_ms": row["p95_ms"],
            "avg_ms": row["avg_ms"],
            "count": row["count"],
        }

    return {"project_key": project_key, "percentiles": result}


@router.get("/api/metrics/wave1/percentiles-weekly")
def api_percentiles_weekly(project_key: str, weeks: int = 26):
    """Retorna evolução semanal dos percentis de lead time e cycle time.
    
    Agrupa issues Done por semana de resolução e calcula P50/P85 para cada semana.
    """
    import math
    from collections import defaultdict
    from datetime import datetime as dt

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT i.resolved_at, m.lead_time_ms, m.cycle_time_ms
        FROM issues i
        INNER JOIN metrics m ON i.key = m.issue_key
        WHERE i.status = 'Done' AND i.resolved_at IS NOT NULL AND i.resolved_at != ''
          AND m.lead_time_ms > 0
          AND i.project_key = ?
        ORDER BY i.resolved_at
    ''', (project_key,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {"project_key": project_key, "weeks": []}

    # Agrupa por semana ISO
    by_week: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for resolved_at, lead_ms, cycle_ms in rows:
        try:
            resolved_dt = dt.fromisoformat(resolved_at.replace("Z", "+00:00"))
            iso = resolved_dt.isocalendar()
            week_key = f"{iso[0]}-W{iso[1]:02d}"
            by_week[week_key].append((lead_ms, cycle_ms))
        except (ValueError, TypeError):
            continue

    def percentile(values: list[int], pct: float) -> int:
        s = sorted(values)
        idx = max(0, min(int(math.ceil(pct / 100.0 * len(s))) - 1, len(s) - 1))
        return s[idx]

    # Gera resultado ordenado, limitado às últimas N semanas
    sorted_weeks = sorted(by_week.keys())
    sorted_weeks = sorted_weeks[-weeks:]  # últimas N semanas

    result = []
    for week_key in sorted_weeks:
        items = by_week[week_key]
        leads = [x[0] for x in items]
        cycles = [x[1] for x in items if x[1] > 0]

        entry = {
            "week": week_key,
            "count": len(items),
            "lead_time": {
                "p50_ms": percentile(leads, 50),
                "p85_ms": percentile(leads, 85),
            },
        }
        if cycles:
            entry["cycle_time"] = {
                "p50_ms": percentile(cycles, 50),
                "p85_ms": percentile(cycles, 85),
            }
        else:
            entry["cycle_time"] = {"p50_ms": 0, "p85_ms": 0}

        result.append(entry)

    return {"project_key": project_key, "weeks": result}


@router.get("/api/metrics/wave1/flow-efficiency-weekly")
def api_flow_efficiency_weekly(project_key: str, weeks: int = 26):
    """Retorna evolução semanal da Flow Efficiency (Opção A).

    Agrupa issues Done por semana ISO de resolução e calcula a média de
    flow_efficiency (%) daquela semana, junto com a contagem de issues.
    Reaproveita o flow_efficiency já persistido por issue em metrics_flow.
    """
    from collections import defaultdict
    from datetime import datetime as dt

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT i.resolved_at, mf.flow_efficiency
        FROM issues i
        INNER JOIN metrics_flow mf ON i.key = mf.issue_key
        WHERE i.status = 'Done' AND i.resolved_at IS NOT NULL AND i.resolved_at != ''
          AND i.project_key = ?
        ORDER BY i.resolved_at
    ''', (project_key,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {"project_key": project_key, "weeks": []}

    by_week: dict[str, list[float]] = defaultdict(list)
    for resolved_at, flow_eff in rows:
        try:
            resolved_dt = dt.fromisoformat(resolved_at.replace("Z", "+00:00"))
            iso = resolved_dt.isocalendar()
            week_key = f"{iso[0]}-W{iso[1]:02d}"
            by_week[week_key].append(flow_eff or 0.0)
        except (ValueError, TypeError):
            continue

    sorted_weeks = sorted(by_week.keys())[-weeks:]

    result = []
    for week_key in sorted_weeks:
        effs = by_week[week_key]
        avg_eff = round(sum(effs) / len(effs), 1) if effs else 0.0
        result.append({
            "week": week_key,
            "count": len(effs),
            "avg_efficiency": avg_eff,
        })

    return {"project_key": project_key, "weeks": result}


@router.get("/api/metrics/wave1/flow-efficiency")
def api_flow_efficiency(project_key: str):
    """Retorna flow efficiency agregado e por issue do projeto."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT issue_key, work_time_ms, wait_time_ms, lead_time_ms, flow_efficiency
        FROM metrics_flow
        WHERE project_key = ?
        ORDER BY flow_efficiency ASC
    """, (project_key,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {"project_key": project_key, "avg_efficiency": 0, "count": 0, "issues": []}

    efficiencies = [r["flow_efficiency"] for r in rows]
    avg_eff = sum(efficiencies) / len(efficiencies)

    return {
        "project_key": project_key,
        "avg_efficiency": round(avg_eff, 2),
        "count": len(rows),
        "issues": [dict(r) for r in rows],
    }


@router.get("/api/metrics/wave1/cfd")
def api_cfd(project_key: str):
    """Retorna dados do Cumulative Flow Diagram (snapshots diários por status)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT snapshot_date, status, count
        FROM metrics_cfd
        WHERE project_key = ?
        ORDER BY snapshot_date ASC, status
    """, (project_key,))
    rows = cursor.fetchall()
    conn.close()

    # Agrupa por data
    by_date: dict[str, dict[str, int]] = {}
    all_statuses = set()
    for row in rows:
        date = row["snapshot_date"]
        status = row["status"]
        by_date.setdefault(date, {})[status] = row["count"]
        all_statuses.add(status)

    return {
        "project_key": project_key,
        "statuses": sorted(all_statuses),
        "data": [{"date": d, "counts": counts} for d, counts in by_date.items()],
    }


@router.get("/api/metrics/wave1/aging-wip")
def api_aging_wip(project_key: str):
    """Retorna issues ativas com cycle time acima do P85 histórico."""
    conn = get_db_connection()
    result = get_aging_wip(conn, project_key)
    conn.close()
    return result


@router.post("/api/metrics/wave1/recalculate")
def api_recalculate_wave1(project_key: str):
    """Recalcula métricas Wave 1 para um projeto (sem rodar pipeline/sync).
    
    Validação: só permite se a última sync do projeto foi há menos de 1 dia.
    Executa em background com progresso via polling.
    """
    from datetime import datetime, timedelta

    conn = get_db_connection()
    cursor = conn.cursor()

    # Valida freshness: última sync < 1 dia
    cursor.execute('''
        SELECT started_at FROM sync_history 
        WHERE project_key = ? AND status = 'success'
        ORDER BY id DESC LIMIT 1
    ''', (project_key,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail="Nenhuma sincronização anterior encontrada. Execute a pipeline completa em Configurações primeiro.")

    try:
        last_dt = datetime.fromisoformat(row["started_at"])
        if (datetime.now() - last_dt) > timedelta(days=1):
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"Última sincronização foi em {last_dt.strftime('%d/%m/%Y %H:%M')} (mais de 1 dia atrás). Atualize os dados em Configurações antes de recalcular métricas."
            )
    except (ValueError, TypeError):
        conn.close()
        raise HTTPException(status_code=400, detail="Erro ao verificar data da última sync.")

    conn.close()

    # Inicia em background (início atômico: 409 se já estiver rodando)
    if not wave1_job.start(_run_wave1_recalculate, args=(project_key,), init={"project_key": project_key}):
        raise HTTPException(status_code=409, detail="Recálculo já em andamento")

    return {"message": "Recálculo iniciado", "project_key": project_key}


# Job do recálculo Wave 1 (estado/log/thread geridos pelo kernel.jobs)
wave1_job = JobRunner("wave1_recalc", extras={"project_key": None})


def _run_wave1_recalculate(job: JobRunner, project_key: str):
    """Recalcula métricas em background com progresso detalhado."""
    import time as time_mod
    import sys
    sys.path.insert(0, BASE_DIR)
    from metrics.base import calculate_metrics as calc_base
    from metrics.wave1_bottleneck.time_per_status import calculate_time_per_status, setup_table as setup_tps
    from metrics.wave1_bottleneck.percentiles import calculate_percentiles, setup_table as setup_perc
    from metrics.wave1_bottleneck.flow_efficiency import calculate_flow_efficiency, setup_table as setup_flow
    from metrics.wave1_bottleneck.cfd import calculate_cfd, setup_table as setup_cfd

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")

    # Busca keys
    cursor = conn.cursor()
    cursor.execute("SELECT key FROM issues WHERE project_key = ?", (project_key,))
    keys = [r[0] for r in cursor.fetchall()]

    job.log(f"Projeto: {project_key} ({len(keys)} issues)")

    steps = [
        ("Métricas base (lead/cycle time)", lambda: calc_base(conn, keys)),
        ("Limpeza de órfãos", lambda: _cleanup_orphans(conn)),
        ("Tempo por status", lambda: (setup_tps(conn), calculate_time_per_status(conn, keys))[1]),
        ("Percentis (P50/P70/P85/P95)", lambda: (setup_perc(conn), calculate_percentiles(conn, keys))[1]),
        ("Flow Efficiency", lambda: (setup_flow(conn), calculate_flow_efficiency(conn, keys))[1]),
        ("Cumulative Flow Diagram", lambda: (setup_cfd(conn), calculate_cfd(conn, keys))[1]),
    ]

    total = len(steps)
    for idx, (name, fn) in enumerate(steps, 1):
        job.log(f"[{idx}/{total}] {name}...")

        t0 = time_mod.time()
        try:
            result = fn()
            elapsed = round(time_mod.time() - t0, 1)
            job.log(f"  ✓ Concluído ({elapsed}s) — {result} registros")
        except Exception as e:
            elapsed = round(time_mod.time() - t0, 1)
            job.log(f"  ✗ Erro ({elapsed}s): {str(e)[:150]}")

    conn.close()

    # Registra data de execução
    from datetime import datetime as dt
    total_elapsed = time_mod.time() - sum(1 for _ in [])  # usa tempo real
    conn3 = sqlite3.connect(DB_PATH, timeout=30)
    conn3.execute("""
        INSERT OR REPLACE INTO wave_recalc_history (project_key, wave, executed_at, duration_seconds)
        VALUES (?, 'wave1', ?, NULL)
    """, (project_key, dt.now().isoformat()))
    conn3.commit()
    conn3.close()

    job.log("Recálculo finalizado!")


def _cleanup_orphans(conn):
    """Remove registros de métricas órfãos."""
    cursor = conn.cursor()
    c1 = cursor.execute("DELETE FROM metrics_per_status WHERE issue_key NOT IN (SELECT key FROM issues)").rowcount
    c2 = cursor.execute("DELETE FROM metrics_flow WHERE issue_key NOT IN (SELECT key FROM issues)").rowcount
    conn.commit()
    return c1 + c2


@router.get("/api/metrics/wave1/recalculate/status")
def api_recalculate_status():
    """Status do recálculo Wave 1 em andamento."""
    return wave1_job.snapshot("running", "project_key", "progress")


@router.get("/api/metrics/wave1/last-update")
def api_wave1_last_update(project_key: str):
    """Retorna data da última atualização de métricas Wave1 para o projeto."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT executed_at FROM wave_recalc_history WHERE project_key = ? AND wave = 'wave1'", (project_key,))
    row = cursor.fetchone()
    conn.close()
    return {"project_key": project_key, "last_wave1_update": row["executed_at"] if row else None}
