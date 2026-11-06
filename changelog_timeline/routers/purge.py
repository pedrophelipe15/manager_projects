import sqlite3
from fastapi import HTTPException
from pydantic import BaseModel
from core.db import DB_PATH, get_db_connection
from fastapi import APIRouter

router = APIRouter()


# --- Purge (Expurgo) ---

@router.get("/api/settings/purge/status")
def get_purge_status():
    """Retorna status do expurgo: último executado, estimativa de registros a remover, se está pendente."""
    from datetime import datetime, timedelta

    conn = get_db_connection()
    cursor = conn.cursor()

    # Último expurgo
    cursor.execute("SELECT executed_at, issues_removed, changelogs_removed FROM purge_history ORDER BY id DESC LIMIT 1")
    last = cursor.fetchone()

    last_purge = None
    days_since = None
    if last:
        last_purge = {
            "date": last["executed_at"],
            "issues_removed": last["issues_removed"],
            "changelogs_removed": last["changelogs_removed"],
        }
        try:
            last_dt = datetime.fromisoformat(last["executed_at"])
            days_since = (datetime.now() - last_dt).days
        except (ValueError, TypeError):
            days_since = None

    # Estimativa: mesmo criterio do expurgo (Done + >6 meses E sem parent vivo).
    cutoff = (datetime.now() - timedelta(weeks=26)).isoformat()
    _eligible_cte = """
        WITH eligible AS (
            SELECT key FROM issues
            WHERE status = 'Done' AND resolved_at IS NOT NULL AND resolved_at < ?
        ),
        to_purge AS (
            SELECT key FROM issues
            WHERE key IN (SELECT key FROM eligible)
              AND (parent_key IS NULL OR parent_key = '' OR parent_key IN (SELECT key FROM eligible))
        )
    """
    cursor.execute(_eligible_cte + "SELECT COUNT(*) FROM to_purge", (cutoff,))
    estimated_issues = cursor.fetchone()[0]

    cursor.execute(
        _eligible_cte + "SELECT COUNT(*) FROM parsed_changelogs WHERE issue_key IN (SELECT key FROM to_purge)",
        (cutoff,),
    )
    estimated_changelogs = cursor.fetchone()[0]

    conn.close()

    recommended = estimated_issues > 0 and (days_since is None or days_since >= 7)

    return {
        "last_purge": last_purge,
        "days_since": days_since,
        "recommended": recommended,
        "estimated": {
            "issues": estimated_issues,
            "changelogs": estimated_changelogs,
        }
    }


@router.get("/api/settings/purge/history")
def get_purge_history():
    """Historico (changelog) dos expurgos executados — ultimas 20 execucoes."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, executed_at, issues_removed, changelogs_removed, cutoff_date, scope, sample_keys
        FROM purge_history
        ORDER BY id DESC LIMIT 20
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{
        "id": r["id"],
        "executed_at": r["executed_at"],
        "issues_removed": r["issues_removed"],
        "changelogs_removed": r["changelogs_removed"],
        "cutoff_date": r["cutoff_date"],
        "scope": r["scope"] if "scope" in r.keys() else "all",
        "sample_keys": (r["sample_keys"] if "sample_keys" in r.keys() else "") or "",
    } for r in rows]


@router.get("/api/settings/purge/preview")
def get_purge_preview():
    """Lista as issues que SERAO removidas pelo expurgo (Done resolvidas ha > 6 meses).

    Mesmo criterio do execute_purge, mas apenas leitura — alimenta o painel de
    detalhamento (tabela + filtros) antes de o usuario confirmar o expurgo.
    """
    from datetime import datetime, timedelta

    cutoff = (datetime.now() - timedelta(weeks=26)).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    # Elegivel = Done + resolvido ha >6 meses E (sem parent OU parent tambem elegivel).
    # Evita expurgar um filho cujo pai permanece no banco (preserva a arvore e as metricas).
    cursor.execute("""
        WITH eligible AS (
            SELECT key FROM issues
            WHERE status = 'Done' AND resolved_at IS NOT NULL AND resolved_at < ?
        )
        SELECT i.key, i.parent_key, i.summary, i.status, i.assignee_name, i.project_key,
               i.created_at, i.due_date, i.updated_at, i.resolved_at,
               p.status AS parent_status
        FROM issues i
        LEFT JOIN issues p ON p.key = i.parent_key
        WHERE i.key IN (SELECT key FROM eligible)
          AND (
                i.parent_key IS NULL OR i.parent_key = ''
                OR i.parent_key IN (SELECT key FROM eligible)
          )
        ORDER BY i.resolved_at ASC
    """, (cutoff,))
    rows = cursor.fetchall()
    conn.close()

    issues = [{
        "key": r["key"],
        "parent_key": r["parent_key"] or "",
        "parent_status": r["parent_status"] or "",
        "summary": r["summary"] or "",
        "status": r["status"] or "",
        "assignee": r["assignee_name"] or "",
        "project_key": r["project_key"] or "",
        "created_at": r["created_at"],
        "due_date": r["due_date"],
        "updated_at": r["updated_at"],
        "resolved_at": r["resolved_at"],
    } for r in rows]

    return {"issues": issues, "count": len(issues), "cutoff_date": cutoff}


class PurgeKeysPayload(BaseModel):
    keys: list[str]


@router.post("/api/settings/purge/selected")
def execute_purge_selected(payload: PurgeKeysPayload):
    """Expurga APENAS as issues informadas (ex.: resultado filtrado do preview).

    Por seguranca, cada key so e removida se for realmente elegivel pelo mesmo
    criterio do expurgo (Done + resolvido ha >6 meses E sem parent vivo). Keys
    inelegiveis sao ignoradas (reportadas em 'skipped').
    """
    from datetime import datetime, timedelta

    req_keys = [k.strip() for k in (payload.keys or []) if k and k.strip()]
    if not req_keys:
        raise HTTPException(status_code=400, detail="Nenhuma issue informada")

    cutoff = (datetime.now() - timedelta(weeks=26)).isoformat()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    # Conjunto elegivel global (para validar parent vivo), mesmo criterio dos demais.
    cur.execute("""
        WITH eligible AS (
            SELECT key FROM issues
            WHERE status = 'Done' AND resolved_at IS NOT NULL AND resolved_at < ?
        )
        SELECT key FROM issues
        WHERE key IN (SELECT key FROM eligible)
          AND (parent_key IS NULL OR parent_key = '' OR parent_key IN (SELECT key FROM eligible))
    """, (cutoff,))
    purgeable = {r[0] for r in cur.fetchall()}

    keys = [k for k in req_keys if k in purgeable]
    skipped = [k for k in req_keys if k not in purgeable]

    if not keys:
        conn.close()
        return {"message": "Nenhuma das issues informadas e elegivel", "issues_removed": 0, "changelogs_removed": 0, "skipped": skipped}

    total_changelogs = 0
    batch_size = 500
    for i in range(0, len(keys), batch_size):
        batch = keys[i:i+batch_size]
        ph = ",".join(["?" for _ in batch])
        cur.execute(f"SELECT COUNT(*) FROM parsed_changelogs WHERE issue_key IN ({ph})", batch)
        total_changelogs += cur.fetchone()[0]
        cur.execute(f"DELETE FROM parsed_changelogs WHERE issue_key IN ({ph})", batch)
        cur.execute(f"DELETE FROM metrics WHERE issue_key IN ({ph})", batch)
        cur.execute(f"DELETE FROM issues WHERE key IN ({ph})", batch)

    sample = ",".join(keys[:20])
    cur.execute("""
        INSERT INTO purge_history (executed_at, issues_removed, changelogs_removed, cutoff_date, scope, sample_keys)
        VALUES (?, ?, ?, ?, 'filtered', ?)
    """, (datetime.now().isoformat(), len(keys), total_changelogs, cutoff, sample))

    conn.commit()
    conn.close()

    return {
        "message": "Expurgo (selecao) concluido",
        "issues_removed": len(keys),
        "changelogs_removed": total_changelogs,
        "skipped": skipped,
    }


@router.post("/api/settings/purge")
def execute_purge():
    """Executa expurgo de issues Done com resolved_at > 6 meses."""
    from datetime import datetime, timedelta

    cutoff = (datetime.now() - timedelta(weeks=26)).isoformat()

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    # Identifica issues a remover. Mesmo criterio do preview: Done + resolvido ha >6 meses
    # E (sem parent OU parent tambem elegivel) — nunca apaga um filho cujo pai permanece.
    cur.execute("""
        WITH eligible AS (
            SELECT key FROM issues
            WHERE status = 'Done' AND resolved_at IS NOT NULL AND resolved_at < ?
        )
        SELECT key FROM issues
        WHERE key IN (SELECT key FROM eligible)
          AND (
                parent_key IS NULL OR parent_key = ''
                OR parent_key IN (SELECT key FROM eligible)
          )
    """, (cutoff,))
    keys = [r[0] for r in cur.fetchall()]

    if not keys:
        conn.close()
        return {"message": "Nenhum registro para expurgar", "issues_removed": 0, "changelogs_removed": 0}

    # Remove em batches
    total_changelogs = 0
    batch_size = 500
    for i in range(0, len(keys), batch_size):
        batch = keys[i:i+batch_size]
        placeholders = ",".join(["?" for _ in batch])
        cur.execute(f"SELECT COUNT(*) FROM parsed_changelogs WHERE issue_key IN ({placeholders})", batch)
        total_changelogs += cur.fetchone()[0]
        cur.execute(f"DELETE FROM parsed_changelogs WHERE issue_key IN ({placeholders})", batch)
        cur.execute(f"DELETE FROM metrics WHERE issue_key IN ({placeholders})", batch)
        cur.execute(f"DELETE FROM issues WHERE key IN ({placeholders})", batch)

    # Registra no histórico (scope 'all' = expurgou tudo que era elegivel).
    sample = ",".join(keys[:20])
    cur.execute("""
        INSERT INTO purge_history (executed_at, issues_removed, changelogs_removed, cutoff_date, scope, sample_keys)
        VALUES (?, ?, ?, ?, 'all', ?)
    """, (datetime.now().isoformat(), len(keys), total_changelogs, cutoff, sample))

    conn.commit()
    conn.close()

    return {
        "message": "Expurgo concluído",
        "issues_removed": len(keys),
        "changelogs_removed": total_changelogs,
        "cutoff_date": cutoff,
    }
