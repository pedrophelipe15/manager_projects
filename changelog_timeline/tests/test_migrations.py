"""Migrações: schema idêntico ao legado, idempotência, bancos antigos e módulo desligado."""
import json
import os
import sqlite3
import subprocess
import sys
import textwrap

import pytest

from kernel.migrations import apply_migrations, current_version, discover
from modules.flow.schema import MIGRATIONS_DIR as FLOW_DIR
from modules.hierarchy.schema import MIGRATIONS_DIR as HIER_DIR
from schema_dump import dump_schema

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(os.path.dirname(__file__), "snapshots")


def _golden(name):
    with open(os.path.join(SNAP, name), encoding="utf-8") as f:
        return json.load(f)


def _fresh(tmp_path, mig_dir):
    conn = sqlite3.connect(str(tmp_path / "x.db"))
    apply_migrations(conn, mig_dir)
    return conn


# ---- schema gerado == schema que o código legado criava (golden capturado antes da fase 2)
def test_flow_schema_matches_legacy(tmp_path):
    assert dump_schema(_fresh(tmp_path, FLOW_DIR)) == _golden("schema_flow.json")


def test_hierarchy_schema_matches_legacy(tmp_path):
    assert dump_schema(_fresh(tmp_path, HIER_DIR)) == _golden("schema_hierarchy.json")


def test_idempotent_and_versioned(tmp_path):
    conn = _fresh(tmp_path, FLOW_DIR)
    before = dump_schema(conn)
    assert apply_migrations(conn, FLOW_DIR) == []
    assert dump_schema(conn) == before
    assert current_version(conn) == max(v for v, _, _ in discover(FLOW_DIR))
    assert [r[0] for r in conn.execute("SELECT version FROM schema_version ORDER BY 1")] == [1, 2, 3]


def test_seed_defaults_applied_once(tmp_path):
    conn = _fresh(tmp_path, FLOW_DIR)
    assert conn.execute("SELECT COUNT(*) FROM blacklist_rules").fetchone()[0] == 7
    assert conn.execute("SELECT COUNT(*) FROM validation_rules").fetchone()[0] == 6
    # usuário apaga todas as regras: NÃO reaparecem ao reaplicar (antes voltavam a cada restart)
    conn.execute("DELETE FROM blacklist_rules")
    conn.commit()
    apply_migrations(conn, FLOW_DIR)
    assert conn.execute("SELECT COUNT(*) FROM blacklist_rules").fetchone()[0] == 0


def test_existing_legacy_database_is_adopted_without_data_loss(tmp_path):
    """Banco em uso (tabelas existem, sem schema_version): só registra versões, preserva dados."""
    conn = _fresh(tmp_path, FLOW_DIR)
    conn.execute("INSERT INTO issues (key, summary, status, project_key) VALUES ('X-1','s','Done','X')")
    conn.execute("INSERT INTO blacklist_rules (type, value, enabled) VALUES ('field','custom',1)")
    conn.execute("DROP TABLE schema_version")
    conn.commit()
    apply_migrations(conn, FLOW_DIR)
    assert conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 1
    # tabela não estava vazia: seed não duplica
    assert conn.execute("SELECT COUNT(*) FROM blacklist_rules").fetchone()[0] == 8
    assert current_version(conn) == 3


def test_old_database_missing_columns_is_upgraded(tmp_path):
    """Banco de uma versão antiga: purge_history sem scope/sample_keys e sync_history sem mode."""
    conn = sqlite3.connect(str(tmp_path / "old.db"))
    conn.executescript("""
        CREATE TABLE purge_history (id INTEGER PRIMARY KEY AUTOINCREMENT, executed_at TEXT NOT NULL,
            issues_removed INTEGER DEFAULT 0, changelogs_removed INTEGER DEFAULT 0, cutoff_date TEXT);
        CREATE TABLE sync_history (id INTEGER PRIMARY KEY AUTOINCREMENT, project_key TEXT NOT NULL,
            started_at TEXT NOT NULL, finished_at TEXT, duration_seconds REAL, issues_inserted INTEGER DEFAULT 0,
            issues_updated INTEGER DEFAULT 0, changelogs_count INTEGER DEFAULT 0, status TEXT DEFAULT 'running',
            error_message TEXT);
        INSERT INTO purge_history (executed_at) VALUES ('2026-01-01');
    """)
    apply_migrations(conn, FLOW_DIR)
    cols = {r[1] for r in conn.execute("PRAGMA table_info('purge_history')")}
    assert {"scope", "sample_keys"} <= cols
    assert "mode" in {r[1] for r in conn.execute("PRAGMA table_info('sync_history')")}
    assert conn.execute("SELECT scope FROM purge_history").fetchone()[0] == "all"  # linha antiga preservada
    # ALTER TABLE ADD COLUMN acrescenta no fim da tabela: compara sem considerar a ordem das colunas
    def norm(s):
        return {t: {**v, "columns": sorted(v["columns"])} for t, v in s.items()}
    assert norm(dump_schema(conn)) == norm(_golden("schema_flow.json"))


def test_duplicate_version_is_rejected(tmp_path):
    (tmp_path / "001_a.sql").write_text("SELECT 1;")
    (tmp_path / "001_b.sql").write_text("SELECT 1;")
    with pytest.raises(ValueError):
        discover(str(tmp_path))


def test_failed_migration_is_not_recorded_and_can_retry(tmp_path):
    d = tmp_path / "m"
    d.mkdir()
    (d / "001_ok.sql").write_text("CREATE TABLE a (x INTEGER);")
    (d / "002_boom.py").write_text("def upgrade(conn):\n    raise RuntimeError('boom')\n")
    conn = sqlite3.connect(str(tmp_path / "t.db"))
    with pytest.raises(RuntimeError):
        apply_migrations(conn, str(d))
    assert current_version(conn) == 1
    (d / "002_boom.py").write_text("def upgrade(conn):\n    conn.execute('CREATE TABLE b (y INTEGER)')\n")
    assert apply_migrations(conn, str(d)) == ["002_boom"]


# ---- módulo desligado não cria banco (isolamento real, em subprocesso)
def _run_create_app(tmp_path, flow_on, hier_on):
    cfg = tmp_path / "modules.yaml"
    cfg.write_text(textwrap.dedent(f"""
        modules:
          flow: {{enabled: {str(flow_on).lower()}}}
          hierarchy: {{enabled: {str(hier_on).lower()}}}
    """))
    db, hdb = tmp_path / "i.db", tmp_path / "h.db"
    env = dict(os.environ, MANAGER_DB_PATH=str(db), MANAGER_HIERARCHY_DB_PATH=str(hdb),
               MANAGER_MODULES_FILE=str(cfg))
    r = subprocess.run([sys.executable, "-c", "import api"], cwd=ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return db.exists(), hdb.exists()


def test_disabled_hierarchy_does_not_create_its_database(tmp_path):
    flow_db, hier_db = _run_create_app(tmp_path, flow_on=True, hier_on=False)
    assert flow_db and not hier_db


def test_disabled_flow_does_not_create_its_database(tmp_path):
    flow_db, hier_db = _run_create_app(tmp_path, flow_on=False, hier_on=True)
    assert hier_db and not flow_db


def test_both_enabled_create_both_databases(tmp_path):
    assert _run_create_app(tmp_path, True, True) == (True, True)
