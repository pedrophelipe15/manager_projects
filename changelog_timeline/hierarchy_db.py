"""Gerenciamento do banco hierarchy.db — isolado do issues.db.

Cria e gerencia o schema para a pipeline hierárquica (Iniciativas, Épicos, Stories, Sub-tasks).
"""

from __future__ import annotations

import os
import sqlite3

HIERARCHY_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hierarchy.db")


def get_hierarchy_connection() -> sqlite3.Connection:
    """Retorna conexão ao hierarchy.db com WAL e row_factory."""
    conn = sqlite3.connect(HIERARCHY_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def setup_hierarchy_db():
    """Cria todas as tabelas e índices do hierarchy.db se não existirem."""
    conn = sqlite3.connect(HIERARCHY_DB_PATH, timeout=30)
    cursor = conn.cursor()

    # Iniciativas (sem changelog)
    cursor.execute('''
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
        )
    ''')

    # Épicos (sem changelog)
    cursor.execute('''
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
        )
    ''')

    # Stories (com changelog)
    cursor.execute('''
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
        )
    ''')

    # Sub-tasks (com changelog)
    cursor.execute('''
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
        )
    ''')

    # Changelogs (apenas stories e subtasks)
    cursor.execute('''
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
        )
    ''')

    # Métricas calculadas (apenas stories e subtasks)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS h_metrics (
            issue_key TEXT PRIMARY KEY,
            parent_key TEXT,
            project_key TEXT,
            status TEXT,
            lead_time_ms INTEGER DEFAULT 0,
            cycle_time_ms INTEGER DEFAULT 0
        )
    ''')

    # Histórico de sync da hierarquia
    cursor.execute('''
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
        )
    ''')

    # Issue Links (relações entre issues: blocks, is blocked by, relates to, etc.)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS h_issue_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_key TEXT NOT NULL,
            linked_key TEXT NOT NULL,
            direction TEXT NOT NULL,
            relation TEXT NOT NULL
        )
    ''')

    # Índices
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_h_changelogs_issue ON h_changelogs(issue_key, field)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_h_changelogs_project ON h_changelogs(project_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_h_stories_parent ON h_stories(parent_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_h_subtasks_parent ON h_subtasks(parent_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_h_metrics_parent ON h_metrics(parent_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_h_epics_parent ON h_epics(parent_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_h_issue_links_key ON h_issue_links(issue_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_h_issue_links_linked ON h_issue_links(linked_key)')

    conn.commit()
    conn.close()


# Auto-setup ao importar
setup_hierarchy_db()
