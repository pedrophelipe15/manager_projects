import os
import sqlite3
import subprocess
import sys
import threading
from fastapi import HTTPException
from pydantic import BaseModel
from core.db import BASE_DIR, DB_PATH, get_db_connection
from kernel.config_store import default_path
from modules.flow.config import load_projects, update_projects
from fastapi import APIRouter

router = APIRouter()


# --- Projects Sync ---


# Caminho do projects.yaml (MANAGER_PROJECTS_YAML sobrescreve). O acesso ao conteúdo é
# feito SEMPRE pelo ConfigStore (modules/flow/config.py), nunca abrindo o arquivo direto.
PROJECTS_YAML = default_path()


EXPORTER_DIR = os.path.join(BASE_DIR, "exporter_jira")


# Estado global de sincronização
sync_state = {
    "running": False,
    "current_project": None,
    "progress": [],  # lista de mensagens de log
    "completed": [],  # projetos finalizados
    "error": None,
    "cancel_requested": False,
}


sync_lock = threading.Lock()


sync_process: subprocess.Popen | None = None


def _load_projects() -> list[dict]:
    """Carrega projetos habilitados (campo 'enabled', default True) via ConfigStore."""
    return load_projects(only_enabled=True)


def _configured_project_keys() -> list[str]:
    """Retorna os project_keys CADASTRADOS (habilitados) em projects.yaml.

    Usado para restringir visoes cross-project (ex.: Portfolio/Wave 4) aos projetos
    atualmente configurados, ignorando dados antigos de projetos ja removidos do cadastro.
    """
    return [str(p.get("key")).strip() for p in _load_projects() if p.get("key")]


def _finish_sync_record(sync_id: int, start_time: float, inserted: int, updated: int, changelogs: int, status: str, error_msg):
    """Finaliza registro de sync no banco."""
    import time as time_mod
    from datetime import datetime as dt

    duration = time_mod.time() - start_time
    finished_at = dt.now().isoformat()

    conn = sqlite3.connect(DB_PATH, timeout=30)
    cur = conn.cursor()
    cur.execute('''
        UPDATE sync_history 
        SET finished_at = ?, duration_seconds = ?, issues_inserted = ?, issues_updated = ?,
            changelogs_count = ?, status = ?, error_message = ?
        WHERE id = ?
    ''', (finished_at, round(duration, 1), inserted, updated, changelogs, status, error_msg, sync_id))
    conn.commit()
    conn.close()


def _run_extraction(jql: str, output_dir: str, key: str) -> dict:
    """Executa extração de uma pipeline. Retorna dict com resultado."""
    import sys

    os.makedirs(output_dir, exist_ok=True)

    jql_file = os.path.join(EXPORTER_DIR, f"_sync_{key}_{os.getpid()}.txt")
    with open(jql_file, "w", encoding="utf-8") as f:
        f.write(jql)

    cmd = [
        sys.executable,
        os.path.join(EXPORTER_DIR, "export_jira.py"),
        "--jql", jql_file,
        "--output-dir", output_dir,
        "--with-changelog",
        "--db-cache", DB_PATH,
        "--skip-test",
    ]

    try:
        result = subprocess.run(cmd, cwd=EXPORTER_DIR, capture_output=True, text=True, timeout=1800)
        os.remove(jql_file)

        if result.returncode != 0:
            return {"ok": False, "error": result.stderr[:300]}

        # Extrai informações do output
        info_lines = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if "Issues retornadas" in line or "Arquivo gerado" in line or "eventos" in line or "Cache:" in line or "cache-miss" in line or "overflow" in line:
                info_lines.append(line)

        return {"ok": True, "info": info_lines}

    except subprocess.TimeoutExpired:
        try:
            os.remove(jql_file)
        except OSError:
            pass
        return {"ok": False, "error": "Timeout (>30min)"}
    except Exception as e:
        try:
            os.remove(jql_file)
        except OSError:
            pass
        return {"ok": False, "error": str(e)[:300]}


def _run_sync(project_keys: list[str], mode: str = "delta"):
    """Executa 1 extração unificada por projeto (JQLs combinadas)."""
    import sys
    import time as time_mod
    from datetime import datetime as dt

    global sync_state

    with sync_lock:
        sync_state["running"] = True
        sync_state["progress"] = []
        sync_state["completed"] = []
        sync_state["error"] = None
        sync_state["current_project"] = None
        sync_state["cancel_requested"] = False

    projects = _load_projects()
    if project_keys:
        projects = [p for p in projects if p.get("key") in project_keys]

    with sync_lock:
        sync_state["progress"].append(f"Iniciando sincronização de {len(projects)} projeto(s)...")

    for idx, project in enumerate(projects):
        # Verifica cancelamento
        with sync_lock:
            if sync_state["cancel_requested"]:
                sync_state["progress"].append("Sincronização cancelada pelo usuário.")
                break

        key = project.get("key", "unknown")
        name = project.get("name", key)
        pipelines = project.get("pipelines", {})

        with sync_lock:
            sync_state["current_project"] = key
            sync_state["progress"].append(f"\n[{idx+1}/{len(projects)}] {name} ({key})")

        if not pipelines:
            with sync_lock:
                sync_state["progress"].append(f"  AVISO: {key} sem pipelines definidas. Pulando.")
            continue

        # Registra início no banco
        start_time = time_mod.time()
        started_at = dt.now().isoformat()
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cur = conn.cursor()
        cur.execute("INSERT INTO sync_history (project_key, mode, started_at, status) VALUES (?, ?, ?, 'running')", (key, mode, started_at))
        sync_id = cur.lastrowid
        conn.commit()
        conn.close()

        # Conta issues antes
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM issues WHERE project_key = ?", (key,))
        issues_before = cur.fetchone()[0]
        conn.close()

        # Output para este projeto
        project_output_dir = os.path.join(BASE_DIR, "output", key)

        # Monta JQL unificada combinando as pipelines com OR
        jql_parts = []
        pipeline_names = []
        for pipe_key in ["active", "done", "delta"]:
            pipe = pipelines.get(pipe_key)
            if not pipe:
                continue
            pipe_jql = pipe.get("jql", "").strip()
            if pipe_jql:
                jql_parts.append(f"({pipe_jql})")
                pipeline_names.append(pipe.get("name", pipe_key))

        if not jql_parts:
            with sync_lock:
                sync_state["progress"].append(f"  AVISO: {key} sem JQLs válidas. Pulando.")
            _finish_sync_record(sync_id, start_time, 0, 0, 0, "error", "Nenhuma JQL válida")
            continue

        merged_jql = " OR ".join(jql_parts)

        with sync_lock:
            sync_state["progress"].append(f"  ├─ Extração unificada ({len(jql_parts)} pipelines: {', '.join(pipeline_names)})")
            sync_state["progress"].append(f"  │    Extraindo issues...")

        # Verifica cancelamento antes da extração
        with sync_lock:
            if sync_state["cancel_requested"]:
                sync_state["progress"].append("  Sincronização cancelada pelo usuário.")
                _finish_sync_record(sync_id, start_time, 0, 0, 0, "cancelled", "Cancelado pelo usuário")
                break

        # Uma única extração com JQL combinada — elimina duplicatas automaticamente
        result = _run_extraction(merged_jql, project_output_dir, key)

        if not result["ok"]:
            with sync_lock:
                sync_state["progress"].append(f"  │    ERRO: {result['error'][:150]}")
            _finish_sync_record(sync_id, start_time, 0, 0, 0, "error", result["error"][:200])
            continue

        # Mostra info
        for line in result.get("info", []):
            with sync_lock:
                sync_state["progress"].append(f"  │    {line}")

        with sync_lock:
            sync_state["progress"].append(f"  │    ✓ Extração concluída")

        # Fase de Ingestão (arquivos já estão no project_output_dir, sem necessidade de combinar)
        with sync_lock:
            if sync_state["cancel_requested"]:
                sync_state["progress"].append("  Sincronização cancelada pelo usuário.")
                _finish_sync_record(sync_id, start_time, 0, 0, 0, "cancelled", "Cancelado pelo usuário")
                break
            sync_state["progress"].append(f"  └─ Ingestão no banco...")

        # Executa ingestão
        exclude_statuses = project.get("exclude_statuses", [])
        cmd_ingest = [
            sys.executable,
            os.path.join(BASE_DIR, "ingest_to_db.py"),
            "--input-dir", project_output_dir,
            "--db-path", DB_PATH,
        ]
        if exclude_statuses:
            cmd_ingest.extend(["--exclude-statuses", ",".join(exclude_statuses)])

        try:
            result = subprocess.run(cmd_ingest, cwd=BASE_DIR, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                with sync_lock:
                    sync_state["progress"].append(f"  ERRO na ingestão: {result.stderr[:200]}")
                _finish_sync_record(sync_id, start_time, 0, 0, 0, "error", result.stderr[:200])
                continue

            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if "inseridas" in line or "inseridos" in line or "calculadas" in line:
                    with sync_lock:
                        sync_state["progress"].append(f"     {line}")

        except Exception as e:
            with sync_lock:
                sync_state["progress"].append(f"  ERRO ingestão: {str(e)[:200]}")
            _finish_sync_record(sync_id, start_time, 0, 0, 0, "error", str(e)[:200])
            continue

        # Calcula métricas pós-ingestão
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM issues WHERE project_key = ?", (key,))
        issues_after = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM parsed_changelogs WHERE project_key = ?", (key,))
        changelogs_count = cur.fetchone()[0]
        conn.close()

        if issues_before == 0:
            issues_inserted = issues_after
            issues_updated = 0
        else:
            issues_inserted = max(0, issues_after - issues_before)
            issues_updated = min(issues_before, issues_after)

        _finish_sync_record(sync_id, start_time, issues_inserted, max(0, issues_updated), changelogs_count, "success", None)

        elapsed = round(time_mod.time() - start_time, 1)
        with sync_lock:
            sync_state["completed"].append(key)
            sync_state["progress"].append(f"  ✓ {key} concluído! ({elapsed}s) — {issues_inserted} novos, {issues_updated} atualizados")

    with sync_lock:
        sync_state["running"] = False
        sync_state["current_project"] = None
        sync_state["progress"].append("\nPipeline finalizada.")


@router.get("/api/settings/projects")
def get_projects():
    """Lista projetos configurados com pipelines e última execução."""
    projects = _load_projects()

    conn = get_db_connection()
    cursor = conn.cursor()

    enriched = []
    for p in projects:
        key = p.get("key")
        item = dict(p)

        # Última sync (qualquer modo)
        cursor.execute('''
            SELECT started_at, duration_seconds, issues_inserted, issues_updated, changelogs_count, status, mode
            FROM sync_history 
            WHERE project_key = ? AND status = 'success'
            ORDER BY id DESC LIMIT 1
        ''', (key,))
        row = cursor.fetchone()
        if row:
            item["last_sync"] = {
                "date": row["started_at"],
                "duration_seconds": row["duration_seconds"],
                "issues_inserted": row["issues_inserted"],
                "issues_updated": row["issues_updated"],
                "changelogs_count": row["changelogs_count"],
                "status": row["status"],
                "mode": row["mode"],
            }
        else:
            item["last_sync"] = None

        enriched.append(item)

    conn.close()
    return enriched


# --- Adicionar / remover projeto (escreve no projects.yaml) ---

# Status padrão considerados "trabalho ativo" na pipeline 'active'.
# Espelha o padrão usado pelos projetos existentes no projects.yaml.
DEFAULT_ACTIVE_STATUSES = ["In Progress", "Blocked", "Test", "Waiting for Delivery"]


# Status padrão a excluir na ingestão (issues nesses status são removidas).
DEFAULT_EXCLUDE_STATUSES = ["Canceled", "Reject", "Open", "To do", "Backlog", "Refinement"]


class ProjectCreate(BaseModel):
    key: str                                   # ex: "BL"
    name: str                                  # ex: "PS - Belize"
    jql_project: str                           # cláusula de projeto na JQL, ex: 'project = "PS - Belize"' ou 'project in (13146)'
    active_statuses: list[str] | None = None   # default: DEFAULT_ACTIVE_STATUSES
    exclude_statuses: list[str] | None = None  # default: DEFAULT_EXCLUDE_STATUSES


def _build_pipelines(jql_project: str, active_statuses: list[str]) -> dict:
    """Gera as 3 pipelines (active/done/delta) no MESMO padrão dos projetos atuais.

    Só varia a cláusula de projeto e a lista de status ativos; o restante do
    template (done 26w, delta 10d) é idêntico ao usado pelo processo de coleta.
    """
    jql_project = jql_project.strip()
    status_list = ", ".join(f'"{s}"' for s in active_statuses)
    return {
        "active": {
            "name": "Trabalho ativo",
            # Inclui tambem subtasks ativas (pai nao-ativo). O extrator traz o pai (parent inclusion).
            "jql": f'{jql_project} AND (status in ({status_list}) OR (issuetype in subTaskIssueTypes() AND status in ({status_list})))',
        },
        "done": {
            "name": "Done (6 meses)",
            "jql": f"{jql_project} AND status = Done AND resolved >= -26w",
        },
        "delta": {
            "name": "Delta (10 dias)",
            "jql": f"{jql_project} AND updated >= -10d",
        },
    }


@router.post("/api/settings/projects", status_code=201)
def add_project(entry: ProjectCreate):
    """Adiciona um novo projeto ao projects.yaml, gerando as 3 pipelines padrão.

    Mantém consistência com o processo de coleta: as JQLs active/done/delta são
    geradas a partir da cláusula de projeto e da lista de status ativos.
    """
    key = entry.key.strip()
    name = entry.name.strip()
    jql_project = entry.jql_project.strip()

    if not key:
        raise HTTPException(status_code=400, detail="key não pode ser vazio")
    if not name:
        raise HTTPException(status_code=400, detail="name não pode ser vazio")
    if not jql_project:
        raise HTTPException(status_code=400, detail="jql_project não pode ser vazio (ex: 'project = \"PS - Belize\"')")

    active_statuses = entry.active_statuses if entry.active_statuses else DEFAULT_ACTIVE_STATUSES
    exclude_statuses = entry.exclude_statuses if entry.exclude_statuses is not None else DEFAULT_EXCLUDE_STATUSES

    new_project = {
        "key": key,
        "name": name,
        "exclude_statuses": exclude_statuses,
        "pipelines": _build_pipelines(jql_project, active_statuses),
    }

    def _add(all_projects: list):
        # Checa duplicata contra TODOS os projetos (inclusive desabilitados), sob lock
        if any(str(p.get("key", "")).strip().upper() == key.upper() for p in all_projects):
            raise HTTPException(status_code=409, detail=f"Projeto com key '{key}' já existe")
        all_projects.append(new_project)

    update_projects(_add)
    return new_project


@router.delete("/api/settings/projects/{key}")
def delete_project(key: str):
    """Remove um projeto do projects.yaml.

    Observação: NÃO remove os dados já ingeridos no banco (issues/métricas).
    A remoção afeta apenas a configuração de coleta.
    """
    def _remove(all_projects: list):
        kept = [p for p in all_projects if str(p.get("key", "")).strip().upper() != key.strip().upper()]
        if len(kept) == len(all_projects):
            raise HTTPException(status_code=404, detail=f"Projeto '{key}' não encontrado")
        all_projects[:] = kept

    update_projects(_remove)
    return {"message": f"Projeto '{key}' removido da configuração", "key": key}


# --- Remover DADOS de um projeto do banco (ação destrutiva, separada da config) ---

# Tabelas de dados/métricas que possuem coluna project_key.
# Ordem importa: filhas antes, issues por último.
_PROJECT_DATA_TABLES = [
    "parsed_changelogs",
    "metrics_per_status",
    "metrics_flow",
    "metrics_cfd",
    "metrics_percentiles",
    "metrics",
]


@router.get("/api/settings/projects/{key}/data-stats")
def get_project_data_stats(key: str):
    """Retorna a contagem de registros no banco para um project_key (preview do que seria removido)."""
    pk = key.strip().upper()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM issues WHERE UPPER(project_key) = ?", (pk,))
    issues_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM parsed_changelogs WHERE UPPER(project_key) = ?", (pk,))
    changelogs_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM metrics WHERE UPPER(project_key) = ?", (pk,))
    metrics_count = cursor.fetchone()[0]

    conn.close()
    return {
        "project_key": pk,
        "issues": issues_count,
        "changelogs": changelogs_count,
        "metrics": metrics_count,
        "has_data": (issues_count + changelogs_count + metrics_count) > 0,
    }


@router.delete("/api/settings/projects/{key}/data")
def delete_project_data(key: str):
    """Remove TODOS os dados de um projeto do banco (issues, changelogs e métricas).

    Ação DESTRUTIVA e irreversível. NÃO altera o projects.yaml (a configuração
    permanece). Use quando quiser limpar os dados coletados de um projeto.
    """
    pk = key.strip().upper()
    if not pk:
        raise HTTPException(status_code=400, detail="key não pode ser vazio")

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    # Contagem antes (para o relatório de retorno)
    cur.execute("SELECT COUNT(*) FROM issues WHERE UPPER(project_key) = ?", (pk,))
    issues_before = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM parsed_changelogs WHERE UPPER(project_key) = ?", (pk,))
    changelogs_before = cur.fetchone()[0]

    if issues_before == 0 and changelogs_before == 0:
        conn.close()
        return {
            "message": f"Nenhum dado encontrado para o projeto '{pk}'",
            "project_key": pk,
            "issues_removed": 0,
            "changelogs_removed": 0,
        }

    # Remove das tabelas de dados/métricas e por fim das issues
    for table in _PROJECT_DATA_TABLES:
        cur.execute(f"DELETE FROM {table} WHERE UPPER(project_key) = ?", (pk,))
    cur.execute("DELETE FROM issues WHERE UPPER(project_key) = ?", (pk,))

    conn.commit()
    conn.close()

    return {
        "message": f"Dados do projeto '{pk}' removidos do banco",
        "project_key": pk,
        "issues_removed": issues_before,
        "changelogs_removed": changelogs_before,
    }


class SyncRequest(BaseModel):
    project_keys: list[str] | None = None  # None = todos
    mode: str = "delta"  # "delta" ou "full"


@router.post("/api/settings/projects/sync")
def start_sync(req: SyncRequest):
    """Inicia sincronização em background."""
    if sync_state["running"]:
        raise HTTPException(status_code=409, detail="Sincronização já em andamento")

    keys = req.project_keys or []
    mode = req.mode if req.mode in ("full", "delta") else "delta"
    thread = threading.Thread(target=_run_sync, args=(keys, mode), daemon=True)
    thread.start()

    return {"message": "Sincronização iniciada", "project_keys": keys or "todos", "mode": mode}


@router.get("/api/settings/projects/sync/status")
def get_sync_status():
    """Retorna status da sincronização em andamento."""
    with sync_lock:
        return {
            "running": sync_state["running"],
            "current_project": sync_state["current_project"],
            "progress": list(sync_state["progress"]),
            "completed": list(sync_state["completed"]),
        }


@router.post("/api/settings/projects/sync/cancel")
def cancel_sync():
    """Solicita cancelamento da sincronização em andamento."""
    with sync_lock:
        if not sync_state["running"]:
            raise HTTPException(status_code=400, detail="Nenhuma sincronização em andamento")
        sync_state["cancel_requested"] = True
        sync_state["progress"].append("Cancelamento solicitado. Aguardando finalização da etapa atual...")
    return {"message": "Cancelamento solicitado"}
