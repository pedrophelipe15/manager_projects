from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from pydantic import BaseModel
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "issues.db")

app = FastAPI(title="Manager Projects API")


# Middleware para desabilitar cache em arquivos estáticos (dev)
class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheMiddleware)


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def resolve_key(conn: sqlite3.Connection, key: str) -> str:
    """Normaliza uma key possivelmente antiga (issue migrada de projeto) para a key atual.

    Issues movidas entre projetos mudam de key (ex.: STN-3065 -> BKA-6703). A
    tabela key_aliases mapeia keys antigas para a atual. Se a key não for um
    alias conhecido, é retornada inalterada.
    """
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT current_key FROM key_aliases WHERE old_key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else key
    except sqlite3.OperationalError:
        # Tabela ainda não criada (banco anterior à migração): usa a key como está.
        return key


def init_settings_tables():
    """Cria tabelas de configuração se não existirem."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blacklist_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ('author', 'field')),
            value TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
    ''')
    # Insere regras padrão se a tabela estiver vazia
    cursor.execute("SELECT COUNT(*) FROM blacklist_rules")
    if cursor.fetchone()[0] == 0:
        defaults = [
            ('author', 'Checklists for Jira (Pro) by HeroCoders'),
            ('field', 'Attachment'),
            ('field', 'labels'),
            ('field', 'IssueParentAssociation'),
            ('field', 'Checklist Text'),
            ('field', 'Checklist Completed'),
            ('field', 'Checklist Text (view only)'),
        ]
        cursor.executemany(
            "INSERT INTO blacklist_rules (type, value, enabled) VALUES (?, ?, 1)",
            defaults
        )
    conn.commit()
    conn.close()


def init_sync_tables():
    """Cria tabela de histórico de sincronização."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sync_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_key TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'full',
            started_at TEXT NOT NULL,
            finished_at TEXT,
            duration_seconds REAL,
            issues_inserted INTEGER DEFAULT 0,
            issues_updated INTEGER DEFAULT 0,
            changelogs_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running',
            error_message TEXT
        )
    ''')
    # Adiciona coluna mode se não existir (migração)
    try:
        cursor.execute("ALTER TABLE sync_history ADD COLUMN mode TEXT NOT NULL DEFAULT 'full'")
    except Exception:
        pass  # coluna já existe
    conn.commit()
    conn.close()


init_settings_tables()
init_sync_tables()


def init_purge_table():
    """Cria tabela para controle de expurgos."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purge_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executed_at TEXT NOT NULL,
            issues_removed INTEGER DEFAULT 0,
            changelogs_removed INTEGER DEFAULT 0,
            cutoff_date TEXT
        )
    ''')
    conn.commit()
    conn.close()


init_purge_table()


def init_wave_recalc_table():
    """Cria tabela para controle de recálculos de waves."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wave_recalc_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_key TEXT NOT NULL,
            wave TEXT NOT NULL,
            executed_at TEXT NOT NULL,
            duration_seconds REAL,
            UNIQUE(project_key, wave)
        )
    ''')
    conn.commit()
    conn.close()


init_wave_recalc_table()


# --- Pydantic Models ---

class BlacklistRuleCreate(BaseModel):
    type: str  # 'author' ou 'field'
    value: str


class BlacklistRuleUpdate(BaseModel):
    value: str | None = None
    enabled: bool | None = None


# --- Issues & Timeline ---

@app.get("/api/issues")
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


@app.get("/api/issues/{key}/timeline")
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


# --- Blacklist CRUD ---

@app.get("/api/settings/blacklist")
def get_blacklist_rules():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, type, value, enabled, created_at FROM blacklist_rules ORDER BY type, value")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/api/settings/blacklist", status_code=201)
def create_blacklist_rule(rule: BlacklistRuleCreate):
    if rule.type not in ('author', 'field'):
        raise HTTPException(status_code=400, detail="type deve ser 'author' ou 'field'")
    if not rule.value.strip():
        raise HTTPException(status_code=400, detail="value não pode ser vazio")

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verifica duplicata
    cursor.execute(
        "SELECT id FROM blacklist_rules WHERE type = ? AND value = ?",
        (rule.type, rule.value.strip())
    )
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Regra já existe")

    cursor.execute(
        "INSERT INTO blacklist_rules (type, value, enabled) VALUES (?, ?, 1)",
        (rule.type, rule.value.strip())
    )
    conn.commit()
    new_id = cursor.lastrowid
    cursor.execute("SELECT id, type, value, enabled, created_at FROM blacklist_rules WHERE id = ?", (new_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)


@app.put("/api/settings/blacklist/{rule_id}")
def update_blacklist_rule(rule_id: int, update: BlacklistRuleUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM blacklist_rules WHERE id = ?", (rule_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    if update.value is not None:
        cursor.execute("UPDATE blacklist_rules SET value = ? WHERE id = ?", (update.value.strip(), rule_id))
    if update.enabled is not None:
        cursor.execute("UPDATE blacklist_rules SET enabled = ? WHERE id = ?", (1 if update.enabled else 0, rule_id))

    conn.commit()
    cursor.execute("SELECT id, type, value, enabled, created_at FROM blacklist_rules WHERE id = ?", (rule_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)


@app.delete("/api/settings/blacklist/{rule_id}")
def delete_blacklist_rule(rule_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM blacklist_rules WHERE id = ?", (rule_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    cursor.execute("DELETE FROM blacklist_rules WHERE id = ?", (rule_id,))
    conn.commit()
    conn.close()
    return {"message": "Regra removida com sucesso"}


# --- Projects Sync ---

import yaml
import subprocess
import threading
from typing import Optional

PROJECTS_YAML = os.path.join(BASE_DIR, "projects.yaml")
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
    """Carrega projetos do YAML (novo formato com pipelines)."""
    if not os.path.exists(PROJECTS_YAML):
        return []
    with open(PROJECTS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    projects = data.get("projects", [])
    # Suporta campo 'enabled' (default True)
    return [p for p in projects if p.get("enabled", True)]


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


@app.get("/api/settings/projects")
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
            "jql": f'{jql_project} AND status in ({status_list})',
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


def _save_projects(projects: list[dict]):
    """Salva a lista de projetos de volta no projects.yaml, preservando o resto."""
    with open(PROJECTS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data["projects"] = projects
    with open(PROJECTS_YAML, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


@app.post("/api/settings/projects", status_code=201)
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

    # Carrega TODOS os projetos (inclusive desabilitados) para checar duplicata
    with open(PROJECTS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    all_projects = data.get("projects", []) or []

    if any(str(p.get("key", "")).strip().upper() == key.upper() for p in all_projects):
        raise HTTPException(status_code=409, detail=f"Projeto com key '{key}' já existe")

    active_statuses = entry.active_statuses if entry.active_statuses else DEFAULT_ACTIVE_STATUSES
    exclude_statuses = entry.exclude_statuses if entry.exclude_statuses is not None else DEFAULT_EXCLUDE_STATUSES

    new_project = {
        "key": key,
        "name": name,
        "exclude_statuses": exclude_statuses,
        "pipelines": _build_pipelines(jql_project, active_statuses),
    }

    all_projects.append(new_project)
    _save_projects(all_projects)

    return new_project


@app.delete("/api/settings/projects/{key}")
def delete_project(key: str):
    """Remove um projeto do projects.yaml.

    Observação: NÃO remove os dados já ingeridos no banco (issues/métricas).
    A remoção afeta apenas a configuração de coleta.
    """
    with open(PROJECTS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    all_projects = data.get("projects", []) or []

    new_projects = [p for p in all_projects if str(p.get("key", "")).strip().upper() != key.strip().upper()]
    if len(new_projects) == len(all_projects):
        raise HTTPException(status_code=404, detail=f"Projeto '{key}' não encontrado")

    _save_projects(new_projects)
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


@app.get("/api/settings/projects/{key}/data-stats")
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


@app.delete("/api/settings/projects/{key}/data")
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


@app.post("/api/settings/projects/sync")
def start_sync(req: SyncRequest):
    """Inicia sincronização em background."""
    if sync_state["running"]:
        raise HTTPException(status_code=409, detail="Sincronização já em andamento")

    keys = req.project_keys or []
    mode = req.mode if req.mode in ("full", "delta") else "delta"
    thread = threading.Thread(target=_run_sync, args=(keys, mode), daemon=True)
    thread.start()

    return {"message": "Sincronização iniciada", "project_keys": keys or "todos", "mode": mode}


@app.get("/api/settings/projects/sync/status")
def get_sync_status():
    """Retorna status da sincronização em andamento."""
    with sync_lock:
        return {
            "running": sync_state["running"],
            "current_project": sync_state["current_project"],
            "progress": list(sync_state["progress"]),
            "completed": list(sync_state["completed"]),
        }


@app.post("/api/settings/projects/sync/cancel")
def cancel_sync():
    """Solicita cancelamento da sincronização em andamento."""
    with sync_lock:
        if not sync_state["running"]:
            raise HTTPException(status_code=400, detail="Nenhuma sincronização em andamento")
        sync_state["cancel_requested"] = True
        sync_state["progress"].append("Cancelamento solicitado. Aguardando finalização da etapa atual...")
    return {"message": "Cancelamento solicitado"}


# --- Purge (Expurgo) ---

@app.get("/api/settings/purge/status")
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

    # Estimativa: quantas issues Done > 6 meses existem
    cutoff = (datetime.now() - timedelta(weeks=26)).isoformat()
    cursor.execute("""
        SELECT COUNT(*) FROM issues 
        WHERE status = 'Done' AND resolved_at IS NOT NULL AND resolved_at < ?
    """, (cutoff,))
    estimated_issues = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM parsed_changelogs 
        WHERE issue_key IN (
            SELECT key FROM issues WHERE status = 'Done' AND resolved_at IS NOT NULL AND resolved_at < ?
        )
    """, (cutoff,))
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


@app.post("/api/settings/purge")
def execute_purge():
    """Executa expurgo de issues Done com resolved_at > 6 meses."""
    from datetime import datetime, timedelta

    cutoff = (datetime.now() - timedelta(weeks=26)).isoformat()

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    # Identifica issues a remover
    cur.execute("""
        SELECT key FROM issues 
        WHERE status = 'Done' AND resolved_at IS NOT NULL AND resolved_at < ?
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

    # Registra no histórico
    cur.execute("""
        INSERT INTO purge_history (executed_at, issues_removed, changelogs_removed, cutoff_date)
        VALUES (?, ?, ?, ?)
    """, (datetime.now().isoformat(), len(keys), total_changelogs, cutoff))

    conn.commit()
    conn.close()

    return {
        "message": "Expurgo concluído",
        "issues_removed": len(keys),
        "changelogs_removed": total_changelogs,
        "cutoff_date": cutoff,
    }


# --- Validation Rules ---

def init_validation_rules_table():
    """Cria tabela de regras de validação e popula com defaults."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS validation_rules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            statuses TEXT NOT NULL,
            query_type TEXT NOT NULL
        )
    ''')
    # Insere defaults se tabela estiver vazia
    cursor.execute("SELECT COUNT(*) FROM validation_rules")
    if cursor.fetchone()[0] == 0:
        defaults = [
            ("due_date_parent_vs_subtask", "Due Date: Story anterior às Subtasks",
             "Issues onde a due date da Story/parent é anterior à due date de subtasks em andamento.",
             "In Progress,Blocked,Waiting for Delivery", "due_date_parent"),
            ("due_date_empty", "Due Date: Sem preenchimento",
             "Issues ativas sem due date definida.",
             "In Progress,Blocked", "due_date_empty"),
            ("done_without_metrics", "Done: Sem Lead Time e Cycle Time",
             "Issues Done sem métricas calculadas.",
             "Done", "done_no_metrics"),
            ("active_without_cycle", "In Progress/Blocked: Sem Cycle Time",
             "Issues ativas sem cycle time calculado.",
             "In Progress,Blocked", "active_no_cycle"),
            ("active_without_assignee", "In Progress/Blocked: Sem Assignee",
             "Issues ativas sem responsável atribuído.",
             "In Progress,Blocked", "active_no_assignee"),
        ]
        cursor.executemany(
            "INSERT INTO validation_rules (id, name, description, statuses, query_type) VALUES (?, ?, ?, ?, ?)",
            defaults
        )
    conn.commit()
    conn.close()


init_validation_rules_table()


class ValidationRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    statuses: str | None = None


@app.get("/api/settings/validations")
def get_validation_rules():
    """Lista regras de validação."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, description, enabled, statuses, query_type FROM validation_rules ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.put("/api/settings/validations/{rule_id}")
def update_validation_rule(rule_id: str, update: ValidationRuleUpdate):
    """Atualiza uma regra de validação."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM validation_rules WHERE id = ?", (rule_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    if update.name is not None:
        cursor.execute("UPDATE validation_rules SET name = ? WHERE id = ?", (update.name, rule_id))
    if update.description is not None:
        cursor.execute("UPDATE validation_rules SET description = ? WHERE id = ?", (update.description, rule_id))
    if update.enabled is not None:
        cursor.execute("UPDATE validation_rules SET enabled = ? WHERE id = ?", (1 if update.enabled else 0, rule_id))
    if update.statuses is not None:
        cursor.execute("UPDATE validation_rules SET statuses = ? WHERE id = ?", (update.statuses, rule_id))

    conn.commit()
    cursor.execute("SELECT id, name, description, enabled, statuses, query_type FROM validation_rules WHERE id = ?", (rule_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)


# --- Due Date: contador de postergações ---

# Deslocamento mínimo (em dias) para uma alteração de due date ser considerada
# uma postergação relevante. Mudanças de <= este valor (ida/volta, ajuste fino)
# são ignoradas para não inflar a contagem com ruído (ex: "3 vezes, 0 dias").
DUE_DATE_SIGNIFICANT_DAYS = 7


@app.get("/api/metrics/due-date-changes")
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

@app.get("/api/inconsistencies")
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
            "total": sum(len(v) for v in results.values()),
        }
    }


# --- Wave 1: Metrics Endpoints ---

import sys
sys.path.insert(0, BASE_DIR)
from metrics.wave1_bottleneck.aging_wip import get_aging_wip


@app.get("/api/metrics/wave1/time-per-status")
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


@app.get("/api/metrics/wave1/percentiles")
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


@app.get("/api/metrics/wave1/percentiles-weekly")
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


@app.get("/api/metrics/wave1/flow-efficiency")
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


@app.get("/api/metrics/wave1/cfd")
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


@app.get("/api/metrics/wave1/aging-wip")
def api_aging_wip(project_key: str):
    """Retorna issues ativas com cycle time acima do P85 histórico."""
    conn = get_db_connection()
    result = get_aging_wip(conn, project_key)
    conn.close()
    return result


# --- Insights ---

from metrics.insights import run_insights


@app.get("/api/insights")
def api_insights(project_key: str):
    """Retorna análise automática de métricas — insights categorizados por severidade."""
    conn = get_db_connection()
    result = run_insights(conn, project_key)
    conn.close()
    return result


@app.get("/api/insights/alert-count")
def api_alert_count():
    """Retorna contagem total de alertas proativos de todos os projetos (para badge na nav)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT project_key FROM issues WHERE project_key IS NOT NULL")
    projects = [row[0] for row in cursor.fetchall()]

    total_alerts = 0
    critical_alerts = 0
    for pk in projects:
        result = run_insights(conn, pk)
        for insight in result.get("insights", []):
            if insight.get("category") == "alert":
                total_alerts += 1
                if insight.get("severity") == "critical":
                    critical_alerts += 1

    conn.close()
    return {"total": total_alerts, "critical": critical_alerts}


# --- Wave 2: Previsibilidade ---

from metrics.wave2_predictability import get_throughput_weekly, monte_carlo_forecast, get_aging_backlog
from metrics.wave2_predictability.forecast import get_open_epics


@app.get("/api/metrics/wave2/throughput")
def api_throughput(project_key: str, weeks: int = 26):
    """Retorna throughput semanal (issues Done por semana) total e por tipo."""
    conn = get_db_connection()
    result = get_throughput_weekly(conn, project_key, weeks)
    conn.close()
    return result


@app.get("/api/metrics/wave2/forecast")
def api_forecast(project_key: str, remaining_items: int, simulations: int = 10000, history_weeks: int = 12):
    """Monte Carlo Forecast: estima semanas para concluir N itens restantes."""
    if remaining_items <= 0:
        return {"error": "remaining_items deve ser > 0"}
    conn = get_db_connection()
    result = monte_carlo_forecast(conn, project_key, remaining_items, simulations, history_weeks)
    conn.close()
    return result


@app.get("/api/metrics/wave2/open-epics")
def api_open_epics(project_key: str):
    """Retorna épicos/parents abertos com contagem de itens restantes."""
    conn = get_db_connection()
    result = get_open_epics(conn, project_key)
    conn.close()
    return {"project_key": project_key, "epics": result}


@app.get("/api/metrics/wave2/aging-backlog")
def api_aging_backlog(project_key: str, min_days: int = 30):
    """Retorna issues inativas há mais de N dias (candidatas a cancelamento)."""
    conn = get_db_connection()
    result = get_aging_backlog(conn, project_key, min_days)
    conn.close()
    return result


# --- Wave 5: Compromisso de Prazo (Due Date Commitment) ---

from metrics.wave5_commitment import get_slippage_by_project, get_commitment_summary_all


@app.get("/api/metrics/wave5/slippage")
def api_slippage(project_key: str):
    """Compromisso de prazo do projeto: commitment score, por assignee e piores issues.

    Responde a pergunta nº1 dos gestores: a equipe cumpre prazo ou so empurra?
    Consome a tabela metrics_due_date_slippage (populada na ingestão / Wave 5).
    """
    conn = get_db_connection()
    result = get_slippage_by_project(conn, project_key)
    conn.close()
    return result


@app.get("/api/metrics/wave5/commitment-summary")
def api_commitment_summary():
    """Resumo de commitment score por projeto (todos), para a home 'Minha Visão'."""
    conn = get_db_connection()
    result = get_commitment_summary_all(conn)
    conn.close()
    return result


@app.get("/api/home/overview")
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

    from datetime import datetime, timedelta
    now = datetime.now()
    stale_cutoff = now - timedelta(days=14)
    active_states = ("In Progress", "Blocked", "Test", "Waiting for Delivery")
    active_ph = ",".join(["?"] * len(active_states))

    projects = []
    for pk in sorted(wanted):
        # Contagens de status ativo
        cursor.execute(
            f"SELECT status, assignee_name, key, summary, updated_at FROM issues "
            f"WHERE project_key = ? AND status IN ({active_ph})",
            [pk, *active_states],
        )
        active_rows = cursor.fetchall()

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
            "pushing": counts.get("pushing", 0),
            "attention": counts.get("attention", 0),
            "in_flight": in_flight,
            "blocked": blocked,
            "no_assignee": no_assignee,
            "stale": stale,
        })

    conn.close()
    # As issues por indicador sao carregadas sob demanda via /api/home/detail
    # (modal ao clicar no indicador do card). A home so devolve os agregados.
    return {"projects": projects}


@app.get("/api/home/detail")
def api_home_detail(project_key: str, metric: str):
    """Lista as issues reais por tras de um indicador da home 'Minha Visão'.

    metric: pushing | attention | blocked | no_assignee | in_flight | stale
    Alimenta o modal que abre ao clicar num indicador do card de projeto.
    """
    from datetime import datetime, timedelta

    valid = {"pushing", "attention", "blocked", "no_assignee", "in_flight", "stale"}
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
    }

    issues = []

    if metric in ("pushing", "attention"):
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
                "detail": f"{r['reschedules']} reprogramacoes · +{r['total_days_pushed']}d",
                "original_due": r["original_due"],
                "current_due": r["current_due"],
            })
    else:
        active_states = ("In Progress", "Blocked", "Test", "Waiting for Delivery")
        active_ph = ",".join(["?"] * len(active_states))
        cursor.execute(
            f"SELECT key, summary, status, assignee_name, updated_at FROM issues "
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


# --- Wave 3: Pessoas e Qualidade ---

from metrics.wave3_people import get_wip_per_person, get_workload_distribution, get_handoff_time, get_rework_rate


@app.get("/api/metrics/wave3/wip")
def api_wip_per_person(project_key: str):
    """Retorna WIP (issues ativas) por pessoa."""
    conn = get_db_connection()
    result = get_wip_per_person(conn, project_key)
    conn.close()
    return result


@app.get("/api/metrics/wave3/workload")
def api_workload(project_key: str, weeks: int = 12):
    """Retorna distribuição de carga (entregas por pessoa nas últimas N semanas)."""
    conn = get_db_connection()
    result = get_workload_distribution(conn, project_key, weeks)
    conn.close()
    return result


@app.get("/api/metrics/wave3/handoff")
def api_handoff(project_key: str):
    """Retorna análise de handoffs (mudanças de assignee) do projeto."""
    conn = get_db_connection()
    result = get_handoff_time(conn, project_key)
    conn.close()
    return result


@app.get("/api/metrics/wave3/rework")
def api_rework(project_key: str):
    """Retorna taxa de retrabalho (transições para trás no fluxo)."""
    conn = get_db_connection()
    result = get_rework_rate(conn, project_key)
    conn.close()
    return result


# --- Wave 4: Cross-time e Portfólio ---

from metrics.wave4_portfolio import get_epic_health, get_benchmarking, get_cross_project_throughput


@app.get("/api/metrics/wave4/epic-health")
def api_epic_health(project_key: str):
    """Retorna saúde de cada épico (progresso, forecast, risco)."""
    conn = get_db_connection()
    result = get_epic_health(conn, project_key)
    conn.close()
    return result


@app.get("/api/metrics/wave4/benchmarking")
def api_benchmarking():
    """Retorna comparação de métricas entre todos os projetos."""
    conn = get_db_connection()
    result = get_benchmarking(conn)
    conn.close()
    return result


@app.get("/api/metrics/wave4/cross-project-throughput")
def api_cross_project_throughput(weeks: int = 26):
    """Retorna throughput semanal consolidado de todos os projetos."""
    conn = get_db_connection()
    result = get_cross_project_throughput(conn, weeks)
    conn.close()
    return result


@app.post("/api/metrics/wave1/recalculate")
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

    # Verifica se já está rodando
    with wave1_lock:
        if wave1_state["running"]:
            raise HTTPException(status_code=409, detail="Recálculo já em andamento")

    # Inicia em background
    thread = threading.Thread(target=_run_wave1_recalculate, args=(project_key,), daemon=True)
    thread.start()

    return {"message": "Recálculo iniciado", "project_key": project_key}


# Estado do recalculate Wave1
wave1_state = {
    "running": False,
    "progress": [],
    "project_key": None,
}
wave1_lock = threading.Lock()


def _run_wave1_recalculate(project_key: str):
    """Recalcula métricas em background com progresso detalhado."""
    import time as time_mod
    import sys
    sys.path.insert(0, BASE_DIR)
    from metrics.base import calculate_metrics as calc_base
    from metrics.wave1_bottleneck.time_per_status import calculate_time_per_status, setup_table as setup_tps
    from metrics.wave1_bottleneck.percentiles import calculate_percentiles, setup_table as setup_perc
    from metrics.wave1_bottleneck.flow_efficiency import calculate_flow_efficiency, setup_table as setup_flow
    from metrics.wave1_bottleneck.cfd import calculate_cfd, setup_table as setup_cfd

    global wave1_state

    with wave1_lock:
        wave1_state["running"] = True
        wave1_state["progress"] = []
        wave1_state["project_key"] = project_key

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")

    # Busca keys
    cursor = conn.cursor()
    cursor.execute("SELECT key FROM issues WHERE project_key = ?", (project_key,))
    keys = [r[0] for r in cursor.fetchall()]

    with wave1_lock:
        wave1_state["progress"].append(f"Projeto: {project_key} ({len(keys)} issues)")

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
        with wave1_lock:
            wave1_state["progress"].append(f"[{idx}/{total}] {name}...")

        t0 = time_mod.time()
        try:
            result = fn()
            elapsed = round(time_mod.time() - t0, 1)
            with wave1_lock:
                wave1_state["progress"].append(f"  ✓ Concluído ({elapsed}s) — {result} registros")
        except Exception as e:
            elapsed = round(time_mod.time() - t0, 1)
            with wave1_lock:
                wave1_state["progress"].append(f"  ✗ Erro ({elapsed}s): {str(e)[:150]}")

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

    with wave1_lock:
        wave1_state["progress"].append("Recálculo finalizado!")
        wave1_state["running"] = False


def _cleanup_orphans(conn):
    """Remove registros de métricas órfãos."""
    cursor = conn.cursor()
    c1 = cursor.execute("DELETE FROM metrics_per_status WHERE issue_key NOT IN (SELECT key FROM issues)").rowcount
    c2 = cursor.execute("DELETE FROM metrics_flow WHERE issue_key NOT IN (SELECT key FROM issues)").rowcount
    conn.commit()
    return c1 + c2


@app.get("/api/metrics/wave1/recalculate/status")
def api_recalculate_status():
    """Status do recálculo Wave 1 em andamento."""
    with wave1_lock:
        return {
            "running": wave1_state["running"],
            "project_key": wave1_state["project_key"],
            "progress": list(wave1_state["progress"]),
        }


@app.get("/api/metrics/wave1/last-update")
def api_wave1_last_update(project_key: str):
    """Retorna data da última atualização de métricas Wave1 para o projeto."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT executed_at FROM wave_recalc_history WHERE project_key = ? AND wave = 'wave1'", (project_key,))
    row = cursor.fetchone()
    conn.close()
    return {"project_key": project_key, "last_wave1_update": row["executed_at"] if row else None}


# =============================================================================
# --- Hierarchy API (pipeline isolada — hierarchy.db) ---
# =============================================================================

from hierarchy_db import get_hierarchy_connection, HIERARCHY_DB_PATH
from metrics.hierarchy_metrics import calculate_hierarchy_metrics, get_excluded_projects
import json as _json

# Estado global de sync hierárquica
hierarchy_sync_state = {
    "running": False,
    "progress": [],
    "error": None,
}
hierarchy_sync_lock = threading.Lock()


def _load_hierarchy_config() -> list[dict]:
    """Carrega configuração de hierarquias do projects.yaml."""
    if not os.path.exists(PROJECTS_YAML):
        return []
    with open(PROJECTS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("hierarchy", [])


@app.get("/api/hierarchy/config")
def get_hierarchy_config():
    """Retorna configurações de hierarquias do projects.yaml."""
    return _load_hierarchy_config()


class HierarchyConfigEntry(BaseModel):
    key: str
    name: str
    type: str  # "initiative" ou "epic"


def _save_hierarchy_config(entries: list[dict]):
    """Salva a lista de hierarquias de volta no projects.yaml."""
    with open(PROJECTS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data["hierarchy"] = entries
    with open(PROJECTS_YAML, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


@app.post("/api/hierarchy/config", status_code=201)
def add_hierarchy_config(entry: HierarchyConfigEntry):
    """Adiciona uma nova entrada de hierarquia ao projects.yaml."""
    if entry.type not in ("initiative", "epic"):
        raise HTTPException(status_code=400, detail="type deve ser 'initiative' ou 'epic'")
    if not entry.key.strip():
        raise HTTPException(status_code=400, detail="key não pode ser vazio")

    entries = _load_hierarchy_config()

    # Verifica duplicata
    if any(e["key"] == entry.key.strip() for e in entries):
        raise HTTPException(status_code=409, detail=f"Key '{entry.key}' já existe na configuração")

    new_entry = {"key": entry.key.strip(), "name": entry.name.strip(), "type": entry.type}
    entries.append(new_entry)
    _save_hierarchy_config(entries)
    return new_entry


@app.put("/api/hierarchy/config/{key}")
def update_hierarchy_config(key: str, entry: HierarchyConfigEntry):
    """Atualiza uma entrada de hierarquia no projects.yaml."""
    entries = _load_hierarchy_config()
    idx = next((i for i, e in enumerate(entries) if e["key"] == key), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Key '{key}' não encontrada")

    entries[idx] = {"key": entry.key.strip(), "name": entry.name.strip(), "type": entry.type}
    _save_hierarchy_config(entries)
    return entries[idx]


@app.delete("/api/hierarchy/config/{key}")
def delete_hierarchy_config(key: str):
    """Remove uma entrada de hierarquia do projects.yaml."""
    entries = _load_hierarchy_config()
    new_entries = [e for e in entries if e["key"] != key]
    if len(new_entries) == len(entries):
        raise HTTPException(status_code=404, detail=f"Key '{key}' não encontrada")

    _save_hierarchy_config(new_entries)
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


@app.get("/api/hierarchy/config/{key}/data-stats")
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


@app.delete("/api/hierarchy/config/{key}/data")
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
    if not os.path.exists(PROJECTS_YAML):
        return []
    with open(PROJECTS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw = data.get("excluded_projects", []) or []
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


def _save_excluded_projects(keys: list[str]):
    """Salva a lista de projetos excluídos de volta no projects.yaml."""
    with open(PROJECTS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data["excluded_projects"] = keys
    with open(PROJECTS_YAML, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


class ExcludedProjectEntry(BaseModel):
    key: str


@app.get("/api/settings/excluded-projects")
def api_get_excluded_projects():
    """Retorna a lista de project_keys atualmente excluídos."""
    return {"excluded_projects": _load_excluded_projects()}


@app.post("/api/settings/excluded-projects", status_code=201)
def add_excluded_project(entry: ExcludedProjectEntry):
    """Adiciona um project_key à lista de exclusão.

    Aceita tanto o project_key ('PSDC') quanto a issue key ('PSDC-1404'),
    derivando sempre o prefixo do projeto.
    """
    key = _normalize_project_key(entry.key)
    if not key:
        raise HTTPException(status_code=400, detail="key não pode ser vazio")

    keys = _load_excluded_projects()
    if key in keys:
        raise HTTPException(status_code=409, detail=f"Projeto '{key}' já está excluído")

    keys.append(key)
    _save_excluded_projects(keys)
    return {"excluded_projects": keys}


@app.delete("/api/settings/excluded-projects/{key}")
def delete_excluded_project(key: str):
    """Remove um project_key da lista de exclusão."""
    key = _normalize_project_key(key)
    keys = _load_excluded_projects()
    new_keys = [k for k in keys if k != key]
    if len(new_keys) == len(keys):
        raise HTTPException(status_code=404, detail=f"Projeto '{key}' não encontrado")

    _save_excluded_projects(new_keys)
    return {"excluded_projects": new_keys}


@app.get("/api/hierarchy/sync/history")
def get_hierarchy_sync_history():
    """Retorna histórico completo de sincronizações hierárquicas."""
    conn = get_hierarchy_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM h_sync_history ORDER BY id DESC LIMIT 20")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/hierarchy/tree")
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
    done = sum(1 for s in stories if s.get("status") in ("Done", "Canceled"))
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


# --- Hierarchy Sync ---

@app.post("/api/hierarchy/sync")
def start_hierarchy_sync(initiative_key: str | None = None, epic_keys: str | None = None):
    """Dispara sincronização hierárquica em background.
    
    Parâmetros (query string):
      - initiative_key: key de uma iniciativa (ex: GPPGI-325)
      - epic_keys: keys de épicos separados por vírgula (ex: PSADB-1457,PSADB-1500)
    
    Se nenhum parâmetro for passado, usa a configuração do projects.yaml.
    """
    with hierarchy_sync_lock:
        if hierarchy_sync_state["running"]:
            raise HTTPException(status_code=409, detail="Sincronização hierárquica já em andamento")

    # Determina o que sincronizar
    if not initiative_key and not epic_keys:
        # Usa config do projects.yaml
        config = _load_hierarchy_config()
        if not config:
            raise HTTPException(status_code=400, detail="Nenhuma hierarquia configurada em projects.yaml e nenhum parâmetro fornecido")

    thread = threading.Thread(
        target=_run_hierarchy_sync,
        args=(initiative_key, epic_keys),
        daemon=True,
    )
    thread.start()

    return {
        "message": "Sincronização hierárquica iniciada",
        "initiative_key": initiative_key,
        "epic_keys": epic_keys,
    }


@app.get("/api/hierarchy/sync/status")
def get_hierarchy_sync_status():
    """Retorna status da sincronização hierárquica em andamento."""
    with hierarchy_sync_lock:
        return {
            "running": hierarchy_sync_state["running"],
            "progress": list(hierarchy_sync_state["progress"]),
            "error": hierarchy_sync_state["error"],
        }


@app.get("/api/hierarchy/last-sync")
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


def _run_hierarchy_sync(initiative_key: str | None, epic_keys: str | None):
    """Executa a sincronização hierárquica em background."""
    import sys
    import time as time_mod
    from datetime import datetime as dt

    with hierarchy_sync_lock:
        hierarchy_sync_state["running"] = True
        hierarchy_sync_state["progress"] = []
        hierarchy_sync_state["error"] = None

    start_time = time_mod.time()

    try:
        # Monta argumentos para o export_hierarchy.py
        cmd = [sys.executable, os.path.join(EXPORTER_DIR, "export_hierarchy.py")]

        if initiative_key:
            cmd.extend(["--initiative", initiative_key])
            with hierarchy_sync_lock:
                hierarchy_sync_state["progress"].append(f"Iniciando extração para iniciativa: {initiative_key}")
        elif epic_keys:
            cmd.extend(["--epics", epic_keys])
            with hierarchy_sync_lock:
                hierarchy_sync_state["progress"].append(f"Iniciando extração para épicos: {epic_keys}")
        else:
            # Usa configuração do projects.yaml
            config = _load_hierarchy_config()
            # Agrupa por tipo
            initiatives = [c["key"] for c in config if c.get("type") == "initiative"]
            epics = [c["key"] for c in config if c.get("type") == "epic"]

            if initiatives:
                # Executa para cada iniciativa
                for ini_key in initiatives:
                    with hierarchy_sync_lock:
                        hierarchy_sync_state["progress"].append(f"Extraindo iniciativa: {ini_key}")
                    _exec_hierarchy_extraction(["--initiative", ini_key])

                # Se também tem épicos avulsos, executa em batch
                if epics:
                    with hierarchy_sync_lock:
                        hierarchy_sync_state["progress"].append(f"Extraindo épicos: {','.join(epics)}")
                    _exec_hierarchy_extraction(["--epics", ",".join(epics)])

                # Calcula métricas
                with hierarchy_sync_lock:
                    hierarchy_sync_state["progress"].append("Calculando métricas (lead/cycle time)...")
                conn = get_hierarchy_connection()
                count = calculate_hierarchy_metrics(conn)
                conn.close()
                with hierarchy_sync_lock:
                    hierarchy_sync_state["progress"].append(f"  ✓ {count} métricas calculadas")

                # Registra sucesso
                _record_hierarchy_sync(start_time, "success", None)

                with hierarchy_sync_lock:
                    elapsed = round(time_mod.time() - start_time, 1)
                    hierarchy_sync_state["progress"].append(f"Sincronização hierárquica concluída ({elapsed}s)")
                    hierarchy_sync_state["running"] = False
                return

            elif epics:
                cmd.extend(["--epics", ",".join(epics)])
                with hierarchy_sync_lock:
                    hierarchy_sync_state["progress"].append(f"Extraindo épicos do config: {','.join(epics)}")
            else:
                with hierarchy_sync_lock:
                    hierarchy_sync_state["error"] = "Nenhuma hierarquia configurada"
                    hierarchy_sync_state["running"] = False
                return

        # Execução direta (initiative_key ou epic_keys fornecidos como parâmetro)
        with hierarchy_sync_lock:
            hierarchy_sync_state["progress"].append("Executando extrator hierárquico...")

        result = subprocess.run(cmd, cwd=EXPORTER_DIR, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            with hierarchy_sync_lock:
                hierarchy_sync_state["progress"].append(f"ERRO: {result.stderr[:300]}")
                hierarchy_sync_state["error"] = result.stderr[:300]
                hierarchy_sync_state["running"] = False
            _record_hierarchy_sync(start_time, "error", result.stderr[:200])
            return

        # Log do output
        for line in result.stdout.strip().split("\n")[-15:]:
            with hierarchy_sync_lock:
                hierarchy_sync_state["progress"].append(f"  {line.strip()}")

        # Calcula métricas
        with hierarchy_sync_lock:
            hierarchy_sync_state["progress"].append("Calculando métricas (lead/cycle time)...")
        conn = get_hierarchy_connection()
        count = calculate_hierarchy_metrics(conn)
        conn.close()
        with hierarchy_sync_lock:
            hierarchy_sync_state["progress"].append(f"  ✓ {count} métricas calculadas")

        _record_hierarchy_sync(start_time, "success", None)

        elapsed = round(time_mod.time() - start_time, 1)
        with hierarchy_sync_lock:
            hierarchy_sync_state["progress"].append(f"Sincronização hierárquica concluída ({elapsed}s)")
            hierarchy_sync_state["running"] = False

    except subprocess.TimeoutExpired:
        with hierarchy_sync_lock:
            hierarchy_sync_state["progress"].append("ERRO: Timeout (>10min)")
            hierarchy_sync_state["error"] = "Timeout"
            hierarchy_sync_state["running"] = False
        _record_hierarchy_sync(start_time, "error", "Timeout")

    except Exception as e:
        with hierarchy_sync_lock:
            hierarchy_sync_state["progress"].append(f"ERRO: {str(e)[:300]}")
            hierarchy_sync_state["error"] = str(e)[:200]
            hierarchy_sync_state["running"] = False
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


# ACTIVE_STATES for hierarchy aggregation (reuse from base concept)
ACTIVE_STATES = {"In Progress", "Blocked", "Test", "Waiting for Delivery"}


# --- Hierarchy: Epic Health Endpoint ---

from metrics.hierarchy_metrics import get_epic_health_data, get_all_epics_health, get_initiative_health_data, get_all_initiatives_health, get_dashboard_v2_data


@app.get("/api/hierarchy/epic-health")
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


@app.get("/api/hierarchy/initiative-health")
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


@app.get("/api/hierarchy/dashboard-v2")
def api_hierarchy_dashboard_v2():
    """Retorna dados consolidados do Dashboard V2.
    
    Inclui: big numbers, initiatives health, e épicos órfãos (sem iniciativa).
    """
    conn = get_hierarchy_connection()
    data = get_dashboard_v2_data(conn)
    conn.close()
    return data


@app.get("/api/hierarchy/roadmap")
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


@app.get("/api/hierarchy/issue-links")
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


# Serve static files from current directory
app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
