"""Jobs em background (sync do flow, recálculo Wave 1, sync da hierarquia).

Testes de CARACTERIZAÇÃO: descrevem o contrato observável das rotas (formato do status,
409 se já rodando, cancelamento, mensagens) e valem antes e depois da migração para o JobRunner.
Nada chama o Jira: extração e subprocessos são substituídos por fakes.
"""
import sqlite3
import threading
import time
from datetime import datetime
from types import SimpleNamespace

import pytest

import conftest


def _wait_idle(client, status_url, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = client.get(status_url).json()
        if not st["running"]:
            return st
        time.sleep(0.05)
    raise AssertionError(f"job não terminou: {st}")


def _wait_running(client, status_url, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = client.get(status_url).json()
        if st["running"]:
            return st
        time.sleep(0.02)
    raise AssertionError("job não ficou 'running'")


# ======================================================================= flow sync
SYNC = "/api/settings/projects/sync"


@pytest.fixture
def fake_sync(monkeypatch):
    import modules.flow.routers.projects as rp
    gate = threading.Event()
    gate.set()  # por padrão não bloqueia
    calls = {"extraction": 0}

    def fake_extraction(jql, output_dir, key):
        calls["extraction"] += 1
        gate.wait(10)
        return {"ok": True, "info": ["Issues extraídas: 3"]}

    def fake_run(cmd, **kw):
        return SimpleNamespace(returncode=0, stdout="3 issues inseridas/atualizadas.\n", stderr="")

    monkeypatch.setattr(rp, "_run_extraction", fake_extraction)
    monkeypatch.setattr(rp.subprocess, "run", fake_run)
    return SimpleNamespace(gate=gate, calls=calls)


def test_sync_status_shape_and_happy_path(client, fake_sync):
    r = client.post(SYNC, json={"project_keys": ["REYK"], "mode": "delta"})
    assert r.status_code == 200 and r.json()["mode"] == "delta"
    st = _wait_idle(client, SYNC + "/status")
    assert set(st) == {"running", "current_project", "progress", "completed"}
    assert st["completed"] == ["REYK"] and st["current_project"] is None
    text = "\n".join(st["progress"])
    assert "Iniciando sincronização de 1 projeto(s)" in text
    assert "Extração concluída" in text and "REYK concluído!" in text
    assert text.rstrip().endswith("Pipeline finalizada.")


def test_sync_rejects_second_start_while_running(client, fake_sync):
    fake_sync.gate.clear()
    assert client.post(SYNC, json={"project_keys": ["REYK"]}).status_code == 200
    _wait_running(client, SYNC + "/status")
    r = client.post(SYNC, json={"project_keys": ["REYK"]})
    assert r.status_code == 409 and "já em andamento" in r.json()["detail"]
    fake_sync.gate.set()
    _wait_idle(client, SYNC + "/status")
    assert fake_sync.calls["extraction"] == 1  # a segunda tentativa não rodou nada


def test_sync_cancel(client, fake_sync):
    assert client.post(SYNC + "/cancel").status_code == 400  # nada rodando
    fake_sync.gate.clear()
    client.post(SYNC, json={"project_keys": ["REYK"]})
    _wait_running(client, SYNC + "/status")
    assert client.post(SYNC + "/cancel").status_code == 200
    fake_sync.gate.set()
    st = _wait_idle(client, SYNC + "/status")
    text = "\n".join(st["progress"])
    assert "Cancelamento solicitado" in text and "cancelada pelo usuário" in text
    assert st["completed"] == []


def test_sync_extraction_error_is_reported_and_job_ends(client, monkeypatch, fake_sync):
    import modules.flow.routers.projects as rp
    monkeypatch.setattr(rp, "_run_extraction", lambda *a, **k: {"ok": False, "error": "Jira fora do ar"})
    client.post(SYNC, json={"project_keys": ["REYK"]})
    st = _wait_idle(client, SYNC + "/status")
    assert "ERRO: Jira fora do ar" in "\n".join(st["progress"]) and st["completed"] == []


def test_sync_unexpected_exception_does_not_leave_job_stuck(client, monkeypatch, fake_sync):
    """Antes: exceção inesperada deixava running=True para sempre (só reiniciando o servidor)."""
    import modules.flow.routers.projects as rp

    def boom(*a, **k):
        raise RuntimeError("falha inesperada no extrator")
    monkeypatch.setattr(rp, "_run_extraction", boom)
    client.post(SYNC, json={"project_keys": ["REYK"]})
    st = _wait_idle(client, SYNC + "/status")
    assert not st["running"]
    assert client.post(SYNC, json={"project_keys": ["REYK"]}).status_code == 200  # destravado
    _wait_idle(client, SYNC + "/status")


# ======================================================================= hierarchy sync
HSYNC = "/api/hierarchy/sync"


@pytest.fixture
def fake_hier(monkeypatch):
    import modules.hierarchy.routers.sync as hs
    gate = threading.Event()
    gate.set()

    def fake_run(cmd, **kw):
        gate.wait(10)
        return SimpleNamespace(returncode=0, stdout="linha 1\nlinha 2\n", stderr="")

    monkeypatch.setattr(hs.subprocess, "run", fake_run)
    monkeypatch.setattr(hs, "calculate_hierarchy_metrics", lambda conn: 7)
    return SimpleNamespace(gate=gate, module=hs)


def test_hierarchy_sync_happy_path_and_shape(client, fake_hier):
    r = client.post(HSYNC, params={"initiative_key": "INI-1"})
    assert r.status_code == 200 and r.json()["initiative_key"] == "INI-1"
    st = _wait_idle(client, HSYNC + "/status")
    assert set(st) == {"running", "progress", "error"} and st["error"] is None
    text = "\n".join(st["progress"])
    assert "Iniciando extração para iniciativa: INI-1" in text
    assert "7 métricas calculadas" in text and "Sincronização hierárquica concluída" in text


def test_hierarchy_sync_409_while_running(client, fake_hier):
    fake_hier.gate.clear()
    assert client.post(HSYNC, params={"epic_keys": "E-1"}).status_code == 200
    _wait_running(client, HSYNC + "/status")
    assert client.post(HSYNC, params={"epic_keys": "E-1"}).status_code == 409
    fake_hier.gate.set()
    _wait_idle(client, HSYNC + "/status")


def test_hierarchy_sync_extractor_failure_sets_error(client, monkeypatch, fake_hier):
    import modules.hierarchy.routers.sync as hs
    monkeypatch.setattr(hs.subprocess, "run",
                        lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="", stderr="credenciais inválidas"))
    client.post(HSYNC, params={"initiative_key": "INI-1"})
    st = _wait_idle(client, HSYNC + "/status")
    assert st["error"] == "credenciais inválidas" and "ERRO: credenciais inválidas" in "\n".join(st["progress"])


def test_hierarchy_sync_without_config_and_params_is_400(client, fake_hier, monkeypatch):
    monkeypatch.setattr(fake_hier.module, "_load_hierarchy_config", lambda: [])
    assert client.post(HSYNC).status_code == 400


def test_hierarchy_sync_unexpected_exception_does_not_leave_job_stuck(client, monkeypatch, fake_hier):
    def boom(cmd, **kw):
        raise OSError("disco cheio")
    monkeypatch.setattr(fake_hier.module.subprocess, "run", boom)
    client.post(HSYNC, params={"initiative_key": "INI-1"})
    st = _wait_idle(client, HSYNC + "/status")
    assert st["error"] and "disco cheio" in st["error"]
    assert client.post(HSYNC, params={"initiative_key": "INI-1"}).status_code == 200
    _wait_idle(client, HSYNC + "/status")


# ======================================================================= wave1 recalculate
RECALC = "/api/metrics/wave1/recalculate"


@pytest.fixture
def recent_sync_record():
    conn = sqlite3.connect(conftest.DB)
    conn.execute("INSERT INTO sync_history (project_key, mode, started_at, status) VALUES (?,?,?,?)",
                 ("REYK", "delta", datetime.now().isoformat(), "success"))
    conn.commit()
    conn.close()


def test_wave1_recalculate_shape_and_progress(client, recent_sync_record):
    r = client.post(RECALC, params={"project_key": "REYK"})
    assert r.status_code == 200 and r.json()["project_key"] == "REYK"
    st = _wait_idle(client, RECALC + "/status")
    assert set(st) == {"running", "project_key", "progress"} and st["project_key"] == "REYK"
    text = "\n".join(st["progress"])
    assert "Projeto: REYK (" in text and "[1/6] Métricas base" in text and "[6/6] Cumulative Flow Diagram" in text
    assert text.rstrip().endswith("Recálculo finalizado!")
    last = client.get("/api/metrics/wave1/last-update", params={"project_key": "REYK"}).json()
    assert last["last_wave1_update"]


def test_wave1_recalculate_409_while_running(client, recent_sync_record, monkeypatch):
    import modules.flow.routers.wave1 as w1
    gate = threading.Event()
    real = w1._cleanup_orphans
    monkeypatch.setattr(w1, "_cleanup_orphans", lambda conn: (gate.wait(10), real(conn))[1])
    assert client.post(RECALC, params={"project_key": "REYK"}).status_code == 200
    _wait_running(client, RECALC + "/status")
    assert client.post(RECALC, params={"project_key": "REYK"}).status_code == 409
    gate.set()
    _wait_idle(client, RECALC + "/status")


def test_wave1_recalculate_requires_recent_sync(client):
    conn = sqlite3.connect(conftest.DB)
    conn.execute("DELETE FROM sync_history")
    conn.commit()
    conn.close()
    r = client.post(RECALC, params={"project_key": "REYK"})
    assert r.status_code == 400 and "Nenhuma sincronização anterior" in r.json()["detail"]
