"""Fixtures dos testes de contrato/smoke.

Cria, ANTES de importar a app, um ambiente isolado (bancos + projects.yaml em
diretorio temporario) e popula issues.db pelo pipeline real de ingestao
(ingest_to_db.py), de modo que todas as tabelas (base, Wave 1, Wave 5) existam.
Nada aqui toca em issues.db / hierarchy.db / projects.yaml de producao.
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="manager_tests_")
DB = os.path.join(TMP, "issues.db")
HDB = os.path.join(TMP, "hierarchy.db")
YAML = os.path.join(TMP, "projects.yaml")
INPUT = os.path.join(TMP, "input")
PROJECT = "REYK"

os.environ["MANAGER_DB_PATH"] = DB
os.environ["MANAGER_HIERARCHY_DB_PATH"] = HDB
os.environ["MANAGER_PROJECTS_YAML"] = YAML
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _write_dataset():
    os.makedirs(INPUT, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    people = ["Ana", "Bruno", "Carla"]
    issues, logs = [], []

    issues.append({
        "jira_key": f"{PROJECT}-1", "summary": "Epic de teste", "issue_type": "Epic",
        "status": "In Progress", "project_name": "PS - REYKJAVIK", "parent_key": None,
        "assignee": "Ana", "reporter": "Ana", "labels": "",
        "created_at_jira": _iso(now - timedelta(weeks=10)),
        "updated_at_jira": _iso(now - timedelta(days=1)),
        "due_date": (now + timedelta(days=30)).strftime("%Y-%m-%d"), "resolved_at_jira": None,
    })

    def add_story(n, status, created_days_ago, done_days_ago=None):
        key = f"{PROJECT}-{n}"
        created = now - timedelta(days=created_days_ago)
        start = created + timedelta(days=1)
        test = start + timedelta(days=3)
        done = (now - timedelta(days=done_days_ago)) if done_days_ago is not None else None
        issues.append({
            "jira_key": key, "summary": f"Story {n}", "issue_type": "Story", "status": status,
            "project_name": "PS - REYKJAVIK", "parent_key": f"{PROJECT}-1",
            "assignee": people[n % 3], "reporter": "Ana", "labels": "",
            "created_at_jira": _iso(created),
            "updated_at_jira": _iso(done or now - timedelta(days=1)),
            "due_date": (created + timedelta(days=20)).strftime("%Y-%m-%d"),
            "resolved_at_jira": _iso(done) if done else None,
        })
        def ev(when, frm, to):
            logs.append({"issue_key": key, "event_date": _iso(when), "field": "status",
                         "from_value": frm, "to_value": to, "author_name": people[n % 3],
                         "project_name": "PS - REYKJAVIK"})
        ev(start, "Open", "In Progress")
        if status in ("Test", "Done"):
            ev(test, "In Progress", "Test")
        if status == "Done":
            ev(done, "Test", "Done")

    n = 2
    for week in range(8):          # 2 entregas por semana nas ultimas 8 semanas
        for _ in range(2):
            add_story(n, "Done", created_days_ago=week * 7 + 12, done_days_ago=week * 7 + 2)
            n += 1
    add_story(n, "In Progress", 6); n += 1
    add_story(n, "Test", 9); n += 1
    add_story(n, "In Progress", 20); n += 1

    with open(os.path.join(INPUT, "issues_mapped.jsonl"), "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(i) for i in issues) + "\n")
    with open(os.path.join(INPUT, "changelogs.jsonl"), "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(i) for i in logs) + "\n")


def _write_yaml():
    with open(YAML, "w", encoding="utf-8") as f:
        f.write(
            "projects:\n"
            f"- key: {PROJECT}\n  name: PS - REYKJAVIK\n  exclude_statuses: [Canceled]\n"
            "  pipelines:\n    active: {name: Ativo, jql: 'project = X'}\n"
            "hierarchy: []\nexcluded_projects: []\n"
        )


_write_dataset()
_write_yaml()
_r = subprocess.run(
    [sys.executable, os.path.join(ROOT, "ingest_to_db.py"), "--input-dir", INPUT, "--db-path", DB],
    capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
)
assert _r.returncode == 0, f"ingestao do fixture falhou:\n{_r.stdout}\n{_r.stderr}"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    import api  # importa DEPOIS de configurar o ambiente isolado
    with TestClient(api.app) as c:
        yield c


@pytest.fixture(scope="session")
def project_key():
    return PROJECT
