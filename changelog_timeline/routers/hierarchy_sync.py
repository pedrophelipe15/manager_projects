import os
import subprocess
import sys
from fastapi import HTTPException
from modules.hierarchy.db import get_hierarchy_connection
from metrics.hierarchy_metrics import calculate_hierarchy_metrics
from routers.hierarchy_common import _load_hierarchy_config, hierarchy_sync_job
from kernel.jobs import JobRunner
from kernel.paths import EXPORTER_DIR
from fastapi import APIRouter

router = APIRouter()


# --- Hierarchy Sync ---

@router.post("/api/hierarchy/sync")
def start_hierarchy_sync(initiative_key: str | None = None, epic_keys: str | None = None):
    """Dispara sincronização hierárquica em background.
    
    Parâmetros (query string):
      - initiative_key: key de uma iniciativa (ex: GPPGI-325)
      - epic_keys: keys de épicos separados por vírgula (ex: PSADB-1457,PSADB-1500)
    
    Se nenhum parâmetro for passado, usa a configuração do projects.yaml.
    """
    if hierarchy_sync_job.running:  # resposta rápida; o início atômico (abaixo) é a garantia real
        raise HTTPException(status_code=409, detail="Sincronização hierárquica já em andamento")

    # Determina o que sincronizar
    if not initiative_key and not epic_keys:
        # Usa config do projects.yaml
        config = _load_hierarchy_config()
        if not config:
            raise HTTPException(status_code=400, detail="Nenhuma hierarquia configurada em projects.yaml e nenhum parâmetro fornecido")

    if not hierarchy_sync_job.start(_run_hierarchy_sync, args=(initiative_key, epic_keys)):
        raise HTTPException(status_code=409, detail="Sincronização hierárquica já em andamento")

    return {
        "message": "Sincronização hierárquica iniciada",
        "initiative_key": initiative_key,
        "epic_keys": epic_keys,
    }


@router.get("/api/hierarchy/sync/status")
def get_hierarchy_sync_status():
    """Retorna status da sincronização hierárquica em andamento."""
    return hierarchy_sync_job.snapshot("running", "progress", "error")


@router.get("/api/hierarchy/last-sync")
def get_hierarchy_last_sync():
    """Retorna informações da última sincronização hierárquica."""
    conn = get_hierarchy_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM h_sync_history 
        WHERE status = 'success'
        ORDER BY id DESC LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"last_sync": None}

    return {"last_sync": dict(row)}


def _run_hierarchy_sync(job: JobRunner, initiative_key: str | None, epic_keys: str | None):
    """Executa a sincronização hierárquica em background."""
    import sys
    import time as time_mod
    from datetime import datetime as dt

    start_time = time_mod.time()

    try:
        # Monta argumentos para o export_hierarchy.py
        cmd = [sys.executable, os.path.join(EXPORTER_DIR, "export_hierarchy.py")]

        if initiative_key:
            cmd.extend(["--initiative", initiative_key])
            job.log(f"Iniciando extração para iniciativa: {initiative_key}")
        elif epic_keys:
            cmd.extend(["--epics", epic_keys])
            job.log(f"Iniciando extração para épicos: {epic_keys}")
        else:
            # Usa configuração do projects.yaml
            config = _load_hierarchy_config()
            # Agrupa por tipo
            initiatives = [c["key"] for c in config if c.get("type") == "initiative"]
            epics = [c["key"] for c in config if c.get("type") == "epic"]

            if initiatives:
                # Executa para cada iniciativa
                for ini_key in initiatives:
                    job.log(f"Extraindo iniciativa: {ini_key}")
                    _exec_hierarchy_extraction(["--initiative", ini_key])

                # Se também tem épicos avulsos, executa em batch
                if epics:
                    job.log(f"Extraindo épicos: {','.join(epics)}")
                    _exec_hierarchy_extraction(["--epics", ",".join(epics)])

                # Calcula métricas
                job.log("Calculando métricas (lead/cycle time)...")
                conn = get_hierarchy_connection()
                count = calculate_hierarchy_metrics(conn)
                conn.close()
                job.log(f"  ✓ {count} métricas calculadas")

                # Registra sucesso
                _record_hierarchy_sync(start_time, "success", None)

                elapsed = round(time_mod.time() - start_time, 1)
                job.log(f"Sincronização hierárquica concluída ({elapsed}s)")
                return

            elif epics:
                cmd.extend(["--epics", ",".join(epics)])
                job.log(f"Extraindo épicos do config: {','.join(epics)}")
            else:
                job.set(error="Nenhuma hierarquia configurada")
                return

        # Execução direta (initiative_key ou epic_keys fornecidos como parâmetro)
        job.log("Executando extrator hierárquico...")

        result = subprocess.run(cmd, cwd=EXPORTER_DIR, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            job.log(f"ERRO: {result.stderr[:300]}")
            job.set(error=result.stderr[:300])
            _record_hierarchy_sync(start_time, "error", result.stderr[:200])
            return

        # Log do output
        for line in result.stdout.strip().split("\n")[-15:]:
            job.log(f"  {line.strip()}")

        # Calcula métricas
        job.log("Calculando métricas (lead/cycle time)...")
        conn = get_hierarchy_connection()
        count = calculate_hierarchy_metrics(conn)
        conn.close()
        job.log(f"  ✓ {count} métricas calculadas")

        _record_hierarchy_sync(start_time, "success", None)

        elapsed = round(time_mod.time() - start_time, 1)
        job.log(f"Sincronização hierárquica concluída ({elapsed}s)")

    except subprocess.TimeoutExpired:
        job.log("ERRO: Timeout (>10min)")
        job.set(error="Timeout")
        _record_hierarchy_sync(start_time, "error", "Timeout")

    except Exception as e:
        job.log(f"ERRO: {str(e)[:300]}")
        job.set(error=str(e)[:200])
        _record_hierarchy_sync(start_time, "error", str(e)[:200])


def _exec_hierarchy_extraction(extra_args: list[str]):
    """Executa export_hierarchy.py com argumentos extras."""
    import sys
    cmd = [sys.executable, os.path.join(EXPORTER_DIR, "export_hierarchy.py")] + extra_args
    result = subprocess.run(cmd, cwd=EXPORTER_DIR, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"Extração falhou: {result.stderr[:200]}")
    return result


def _record_hierarchy_sync(start_time: float, status: str, error_msg: str | None):
    """Registra resultado da sync na h_sync_history."""
    import time as time_mod
    from datetime import datetime as dt

    duration = round(time_mod.time() - start_time, 1)
    conn = get_hierarchy_connection()
    cursor = conn.cursor()

    # Conta registros atuais
    cursor.execute("SELECT COUNT(*) as c FROM h_initiatives")
    ini_count = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM h_epics")
    epic_count = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM h_stories")
    story_count = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM h_subtasks")
    subtask_count = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM h_changelogs")
    changelog_count = cursor.fetchone()["c"]

    cursor.execute('''
        INSERT INTO h_sync_history 
        (initiative_key, started_at, finished_at, duration_seconds,
         initiatives_count, epics_count, stories_count, subtasks_count, changelogs_count,
         status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        "", dt.now().isoformat(), dt.now().isoformat(), duration,
        ini_count, epic_count, story_count, subtask_count, changelog_count,
        status, error_msg,
    ))
    conn.commit()
    conn.close()
