-- HIERARCHY / hierarchy.db — baseline do schema (reproduz o antigo hierarchy_db.setup_hierarchy_db).
-- IF NOT EXISTS: seguro em banco novo e em banco legado já em uso.

CREATE TABLE IF NOT EXISTS h_initiatives (
    key TEXT PRIMARY KEY,
    summary TEXT,
    status TEXT,
    issuetype_name TEXT,
    project_key TEXT,
    assignee_name TEXT,
    due_date TEXT,
    created_at TEXT,
    updated_at TEXT,
    resolved_at TEXT,
    children_keys TEXT,
    last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS h_epics (
    key TEXT PRIMARY KEY,
    summary TEXT,
    status TEXT,
    issuetype_name TEXT,
    project_key TEXT,
    assignee_name TEXT,
    due_date TEXT,
    created_at TEXT,
    updated_at TEXT,
    resolved_at TEXT,
    parent_key TEXT,
    children_keys TEXT,
    last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS h_stories (
    key TEXT PRIMARY KEY,
    summary TEXT,
    status TEXT,
    issuetype_name TEXT,
    project_key TEXT,
    assignee_name TEXT,
    due_date TEXT,
    created_at TEXT,
    updated_at TEXT,
    resolved_at TEXT,
    parent_key TEXT,
    last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS h_subtasks (
    key TEXT PRIMARY KEY,
    summary TEXT,
    status TEXT,
    issuetype_name TEXT,
    project_key TEXT,
    assignee_name TEXT,
    due_date TEXT,
    created_at TEXT,
    updated_at TEXT,
    resolved_at TEXT,
    parent_key TEXT,
    last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS h_changelogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_key TEXT,
    project_key TEXT,
    author_name TEXT,
    author_avatar_url TEXT,
    event_date TEXT,
    field TEXT,
    from_value TEXT,
    to_value TEXT
);

CREATE TABLE IF NOT EXISTS h_metrics (
    issue_key TEXT PRIMARY KEY,
    parent_key TEXT,
    project_key TEXT,
    status TEXT,
    lead_time_ms INTEGER DEFAULT 0,
    cycle_time_ms INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS h_sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    initiative_key TEXT,
    started_at TEXT,
    finished_at TEXT,
    duration_seconds REAL,
    initiatives_count INTEGER DEFAULT 0,
    epics_count INTEGER DEFAULT 0,
    stories_count INTEGER DEFAULT 0,
    subtasks_count INTEGER DEFAULT 0,
    changelogs_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS h_issue_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_key TEXT NOT NULL,
    linked_key TEXT NOT NULL,
    direction TEXT NOT NULL,
    relation TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_h_changelogs_issue ON h_changelogs(issue_key, field);
CREATE INDEX IF NOT EXISTS idx_h_changelogs_project ON h_changelogs(project_key);
CREATE INDEX IF NOT EXISTS idx_h_stories_parent ON h_stories(parent_key);
CREATE INDEX IF NOT EXISTS idx_h_subtasks_parent ON h_subtasks(parent_key);
CREATE INDEX IF NOT EXISTS idx_h_metrics_parent ON h_metrics(parent_key);
CREATE INDEX IF NOT EXISTS idx_h_epics_parent ON h_epics(parent_key);
CREATE INDEX IF NOT EXISTS idx_h_issue_links_key ON h_issue_links(issue_key);
CREATE INDEX IF NOT EXISTS idx_h_issue_links_linked ON h_issue_links(linked_key);
