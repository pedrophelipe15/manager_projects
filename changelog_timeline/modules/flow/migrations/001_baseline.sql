-- FLOW / issues.db — baseline do schema (reproduz o que antes era criado em
-- ingest_to_db.py, core/db_init.py e metrics/wave1|wave5). IF NOT EXISTS: seguro
-- tanto em banco novo quanto em banco legado já em uso.

-- Dados ingeridos do Jira
CREATE TABLE IF NOT EXISTS issues (
    key TEXT PRIMARY KEY,
    summary TEXT,
    issuetype_name TEXT,
    issuetype_hierarchy_level INTEGER,
    status TEXT,
    project_key TEXT,
    project_name TEXT,
    parent_key TEXT,
    assignee_name TEXT,
    reporter_name TEXT,
    labels TEXT,
    created_at TEXT,
    updated_at TEXT,
    due_date TEXT,
    resolved_at TEXT,
    executors_teams TEXT,
    pagseguro_teams TEXT,
    start_date TEXT
);

CREATE TABLE IF NOT EXISTS metrics (
    issue_key TEXT PRIMARY KEY,
    project_key TEXT,
    project_name TEXT,
    parent_key TEXT,
    status TEXT,
    created_at TEXT,
    updated_at TEXT,
    due_date TEXT,
    resolved_at TEXT,
    lead_time_ms INTEGER,
    cycle_time_ms INTEGER,
    FOREIGN KEY(issue_key) REFERENCES issues(key)
);

CREATE TABLE IF NOT EXISTS parsed_changelogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_key TEXT,
    project_key TEXT,
    project_name TEXT,
    author_name TEXT,
    author_avatar_url TEXT,
    event_date TEXT,
    field TEXT,
    from_value TEXT,
    to_value TEXT,
    is_cycle_time_interval BOOLEAN,
    FOREIGN KEY(issue_key) REFERENCES issues(key)
);

-- Mapa de keys antigas -> key atual (issues migradas entre projetos)
CREATE TABLE IF NOT EXISTS key_aliases (
    old_key TEXT PRIMARY KEY,
    current_key TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_changelogs_issue_field ON parsed_changelogs(issue_key, field);
CREATE INDEX IF NOT EXISTS idx_key_aliases_current ON key_aliases(current_key);
CREATE INDEX IF NOT EXISTS idx_changelogs_project ON parsed_changelogs(project_key);
CREATE INDEX IF NOT EXISTS idx_issues_project ON issues(project_key);
CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
CREATE INDEX IF NOT EXISTS idx_metrics_project ON metrics(project_key);

-- Configuração e histórico (settings, sync, expurgo, recálculo)
CREATE TABLE IF NOT EXISTS blacklist_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK(type IN ('author', 'field')),
    value TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

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
);

CREATE TABLE IF NOT EXISTS purge_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    executed_at TEXT NOT NULL,
    issues_removed INTEGER DEFAULT 0,
    changelogs_removed INTEGER DEFAULT 0,
    cutoff_date TEXT,
    scope TEXT NOT NULL DEFAULT 'all',
    sample_keys TEXT
);

CREATE TABLE IF NOT EXISTS wave_recalc_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_key TEXT NOT NULL,
    wave TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    duration_seconds REAL,
    UNIQUE(project_key, wave)
);

CREATE TABLE IF NOT EXISTS validation_rules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    statuses TEXT NOT NULL,
    query_type TEXT NOT NULL
);

-- Métricas Wave 1
CREATE TABLE IF NOT EXISTS metrics_per_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_key TEXT NOT NULL,
    project_key TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    entered_at TEXT,
    exited_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_mps_project ON metrics_per_status(project_key);
CREATE INDEX IF NOT EXISTS idx_mps_issue ON metrics_per_status(issue_key);

CREATE TABLE IF NOT EXISTS metrics_percentiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_key TEXT NOT NULL,
    metric_type TEXT NOT NULL,
    p50_ms INTEGER,
    p70_ms INTEGER,
    p85_ms INTEGER,
    p95_ms INTEGER,
    avg_ms INTEGER,
    count INTEGER,
    UNIQUE(project_key, metric_type)
);

CREATE TABLE IF NOT EXISTS metrics_flow (
    issue_key TEXT PRIMARY KEY,
    project_key TEXT NOT NULL,
    work_time_ms INTEGER DEFAULT 0,
    wait_time_ms INTEGER DEFAULT 0,
    lead_time_ms INTEGER DEFAULT 0,
    flow_efficiency REAL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_mf_project ON metrics_flow(project_key);

CREATE TABLE IF NOT EXISTS metrics_cfd (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_key TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    status TEXT NOT NULL,
    count INTEGER NOT NULL,
    UNIQUE(project_key, snapshot_date, status)
);
CREATE INDEX IF NOT EXISTS idx_cfd_project_date ON metrics_cfd(project_key, snapshot_date);

-- Métricas Wave 5 (compromisso de prazo)
CREATE TABLE IF NOT EXISTS metrics_due_date_slippage (
    issue_key TEXT PRIMARY KEY,
    project_key TEXT NOT NULL,
    assignee_name TEXT,
    reschedules INTEGER NOT NULL DEFAULT 0,
    pushes INTEGER NOT NULL DEFAULT 0,
    pulls INTEGER NOT NULL DEFAULT 0,
    total_days_pushed INTEGER NOT NULL DEFAULT 0,
    original_due TEXT,
    current_due TEXT,
    last_changed_at TEXT,
    classification TEXT NOT NULL DEFAULT 'kept'
);
CREATE INDEX IF NOT EXISTS idx_slippage_project ON metrics_due_date_slippage(project_key);
CREATE INDEX IF NOT EXISTS idx_slippage_assignee ON metrics_due_date_slippage(assignee_name);
