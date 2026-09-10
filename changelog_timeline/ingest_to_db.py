"""Ingestão de dados JSONL (issues + changelogs) para o banco SQLite do changelog_timeline."""

from __future__ import annotations

import argparse
import json
import sqlite3
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "issues.db")

# Garante que o pacote metrics é importável
sys.path.insert(0, BASE_DIR)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingesta JSONL do extrator Jira no SQLite")
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Diretório contendo issues_mapped.jsonl e changelogs.jsonl",
    )
    parser.add_argument(
        "--db-path",
        default=DB_PATH,
        help="Caminho para o banco SQLite (default: issues.db na raiz do projeto)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Limpa todas as tabelas antes da ingestão (full reload)",
    )
    parser.add_argument(
        "--only-keys",
        default=None,
        help="Recalcula métricas apenas para estas issue keys (separadas por vírgula). Se omitido, recalcula todas.",
    )
    parser.add_argument(
        "--exclude-statuses",
        default=None,
        help="Statuses a remover do banco (separados por vírgula). Issues com estes status serão deletadas.",
    )
    return parser.parse_args()


def setup_db(conn: sqlite3.Connection) -> None:
    """Cria as tabelas se não existirem."""
    cursor = conn.cursor()

    cursor.execute('''
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
    )
    ''')

    cursor.execute('''
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
    )
    ''')

    cursor.execute('''
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
    )
    ''')

    # Índices de performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_changelogs_issue_field ON parsed_changelogs(issue_key, field)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_changelogs_project ON parsed_changelogs(project_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_issues_project ON issues(project_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_metrics_project ON metrics(project_key)')

    conn.commit()


def clear_tables(conn: sqlite3.Connection) -> None:
    """Remove todos os dados existentes para full reload."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM parsed_changelogs")
    cursor.execute("DELETE FROM metrics")
    cursor.execute("DELETE FROM issues")
    conn.commit()
    print("Tabelas limpas para full reload.")


def read_jsonl(file_path: Path) -> list[dict[str, Any]]:
    """Lê um arquivo JSONL e retorna lista de dicts."""
    rows: list[dict[str, Any]] = []
    if not file_path.exists():
        return rows
    with file_path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def map_hierarchy_level(issue_type: str | None) -> int:
    """Mapeia tipo de issue para nível hierárquico."""
    if not issue_type:
        return 0
    issue_type_lower = issue_type.lower()
    if issue_type_lower in ("epic",):
        return 1
    elif issue_type_lower in ("sub-task", "subtask", "sub-tarefa"):
        return -1
    return 0  # Story, Task, Bug, etc.


def ingest_issues(conn: sqlite3.Connection, issues: list[dict[str, Any]]) -> int:
    """Insere ou atualiza issues no banco."""
    cursor = conn.cursor()
    count = 0

    for issue in issues:
        key = issue.get("jira_key")
        if not key:
            continue

        # Deriva project_key a partir da jira_key (ex: "REYK-840" -> "REYK")
        project_key = key.rsplit("-", 1)[0] if "-" in key else issue.get("project_id")

        issue_type = issue.get("issue_type", "")
        hierarchy_level = map_hierarchy_level(issue_type)

        cursor.execute('''
            INSERT OR REPLACE INTO issues 
            (key, summary, issuetype_name, issuetype_hierarchy_level, status, 
             project_key, project_name, parent_key, assignee_name, reporter_name,
             labels, created_at, updated_at, due_date, resolved_at,
             executors_teams, pagseguro_teams, start_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            key,
            issue.get("summary"),
            issue_type,
            hierarchy_level,
            issue.get("status"),
            project_key,
            issue.get("project_name"),
            issue.get("parent_key"),
            issue.get("assignee"),
            issue.get("reporter"),
            issue.get("labels"),
            issue.get("created_at_jira"),
            issue.get("updated_at_jira"),
            issue.get("due_date"),
            issue.get("resolved_at_jira"),
            issue.get("executor_teams"),
            issue.get("pagseguro_teams"),
            issue.get("start_date"),
        ))
        count += 1

    conn.commit()
    return count


def ingest_changelogs(conn: sqlite3.Connection, changelogs: list[dict[str, Any]]) -> int:
    """Insere changelogs no banco, marcando intervalos de cycle time."""
    cursor = conn.cursor()
    count = 0

    # Agrupa changelogs por issue para calcular is_cycle_time_interval
    by_issue: dict[str, list[dict[str, Any]]] = {}
    for entry in changelogs:
        issue_key = entry.get("issue_key")
        if not issue_key:
            continue
        by_issue.setdefault(issue_key, []).append(entry)

    # Batch delete de issues afetadas (1 query em vez de N)
    all_keys = list(by_issue.keys())
    for i in range(0, len(all_keys), 500):
        batch = all_keys[i:i+500]
        ph = ",".join(["?" for _ in batch])
        cursor.execute(f"DELETE FROM parsed_changelogs WHERE issue_key IN ({ph})", batch)

    # Prepara todos os registros para executemany
    all_rows = []
    for issue_key, entries in by_issue.items():
        entries.sort(key=lambda e: e.get("event_date") or "")
        derived_project_key = issue_key.rsplit("-", 1)[0] if "-" in issue_key else entries[0].get("project_key")

        for entry in entries:
            field = entry.get("field", "")
            to_value = entry.get("to_value", "")

            is_cycle = False
            if field and field.lower() == "status":
                from_val = (entry.get("from_value") or "").strip()
                to_val = (to_value or "").strip()
                cycle_states = {"In Progress", "Blocked", "Test", "Waiting for Delivery"}
                if to_val in cycle_states or from_val in cycle_states:
                    is_cycle = True

            all_rows.append((
                issue_key,
                derived_project_key,
                entry.get("project_name"),
                entry.get("author_name"),
                entry.get("author_avatar_url"),
                entry.get("event_date"),
                field,
                entry.get("from_value"),
                to_value,
                is_cycle,
            ))

    # Insere tudo de uma vez com executemany
    cursor.executemany('''
        INSERT INTO parsed_changelogs 
        (issue_key, project_key, project_name, author_name, author_avatar_url,
         event_date, field, from_value, to_value, is_cycle_time_interval)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', all_rows)

    count = len(all_rows)
    conn.commit()
    return count


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)

    if not input_dir.exists():
        raise FileNotFoundError(f"Diretório de entrada não encontrado: {input_dir}")

    print(f"Banco de dados: {args.db_path}")
    print(f"Diretório de entrada: {input_dir}")

    conn = sqlite3.connect(args.db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    setup_db(conn)

    if args.clear:
        clear_tables(conn)

    # 1. Ingerir issues
    issues_file = input_dir / "issues_mapped.jsonl"
    if issues_file.exists():
        print(f"\n[1/4] Ingerindo issues de {issues_file}...")
        issues = read_jsonl(issues_file)
        count = ingest_issues(conn, issues)
        print(f"  {count} issues inseridas/atualizadas.")
    else:
        print(f"\n[1/4] AVISO: {issues_file} não encontrado. Pulando ingestão de issues.")

    # 2. Remover issues com status excluído
    exclude_statuses = []
    if args.exclude_statuses:
        exclude_statuses = [s.strip() for s in args.exclude_statuses.split(",") if s.strip()]
    if exclude_statuses:
        print(f"\n[2/4] Removendo issues com status: {exclude_statuses}...")
        cursor = conn.cursor()
        placeholders = ",".join(["?" for _ in exclude_statuses])
        cursor.execute(f"SELECT key FROM issues WHERE status IN ({placeholders})", exclude_statuses)
        keys_to_remove = [r[0] for r in cursor.fetchall()]
        if keys_to_remove:
            for i in range(0, len(keys_to_remove), 500):
                batch = keys_to_remove[i:i+500]
                ph = ",".join(["?" for _ in batch])
                cursor.execute(f"DELETE FROM parsed_changelogs WHERE issue_key IN ({ph})", batch)
                cursor.execute(f"DELETE FROM metrics WHERE issue_key IN ({ph})", batch)
                cursor.execute(f"DELETE FROM issues WHERE key IN ({ph})", batch)
            conn.commit()
            print(f"  {len(keys_to_remove)} issues removidas.")
        else:
            print(f"  Nenhuma issue com status excluído encontrada.")
    else:
        print(f"\n[2/4] Sem exclusão de status configurada.")

    # 3. Ingerir changelogs
    changelogs_file = input_dir / "changelogs.jsonl"
    if changelogs_file.exists():
        print(f"\n[3/4] Ingerindo changelogs de {changelogs_file}...")
        changelogs = read_jsonl(changelogs_file)
        count = ingest_changelogs(conn, changelogs)
        print(f"  {count} eventos de changelog inseridos.")
    else:
        print(f"\n[3/4] AVISO: {changelogs_file} não encontrado. Pulando ingestão de changelogs.")

    # 4. Calcular métricas (lead time / cycle time)
    from metrics.base import calculate_metrics
    from metrics.wave1_bottleneck import run_wave1
    from metrics.changelog_cache import load_status_changelogs

    only_keys = None
    if args.only_keys:
        only_keys = [k.strip() for k in args.only_keys.split(",") if k.strip()]
        print(f"\n[4/5] Calculando métricas base para {len(only_keys)} issues...")
    else:
        if issues_file.exists():
            issues_data = read_jsonl(issues_file)
            only_keys = [i.get("jira_key") for i in issues_data if i.get("jira_key")]
            print(f"\n[4/5] Calculando métricas base para {len(only_keys)} issues afetadas...")
        else:
            print("\n[4/5] Calculando métricas base (lead time / cycle time)...")

    # Carrega changelogs de status UMA VEZ para todos os módulos
    status_cache = load_status_changelogs(conn, only_keys)

    count = calculate_metrics(conn, only_keys, status_cache=status_cache)
    print(f"  Métricas base: {count} issues.")

    # 5. Wave 1 — Gargalo e Fluxo (reutiliza status_cache carregado acima)
    print(f"\n[5/5] Calculando Wave 1 (Gargalo e Fluxo)...")
    wave1_results = run_wave1(conn, only_keys)
    print(f"  time_per_status: {wave1_results.get('time_per_status', 0)} intervalos")
    print(f"  percentiles: {wave1_results.get('percentiles', 0)} registros")
    print(f"  flow_efficiency: {wave1_results.get('flow_efficiency', 0)} issues")
    print(f"  cfd: {wave1_results.get('cfd', 0)} snapshots")

    conn.close()
    print("\nIngestão concluída com sucesso!")


if __name__ == "__main__":
    main()
