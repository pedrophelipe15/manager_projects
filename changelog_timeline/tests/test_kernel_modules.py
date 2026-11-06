"""Testes do kernel: registry, isolamento de falhas e liga/desliga de módulos."""
import sys
import textwrap

import pytest
from fastapi.testclient import TestClient

from kernel.app_factory import create_app
from kernel.registry import Registry, load_config


def _write_modules(tmp_path, spec: str) -> str:
    f = tmp_path / "modules.yaml"
    f.write_text(textwrap.dedent(spec), encoding="utf-8")
    return str(f)


def _status(client):
    return {m["id"]: m for m in client.get("/api/platform/modules").json()["modules"]}


# ---------------------------------------------------------------- app real
def test_default_config_loads_both_modules(client):
    st = _status(client)
    assert st["flow"]["state"] == "enabled"
    assert st["hierarchy"]["state"] == "enabled"
    assert st["flow"]["nav"] and st["hierarchy"]["nav"]


def test_disable_hierarchy_removes_its_routes_keeps_flow(tmp_path):
    cfg = _write_modules(tmp_path, """
        modules:
          flow: {enabled: true}
          hierarchy: {enabled: false}
    """)
    c = TestClient(create_app(cfg))
    assert c.get("/api/hierarchy/config").status_code == 404
    assert c.get("/api/hierarchy/dashboard-v2").status_code == 404
    assert c.get("/api/issues").status_code == 200
    assert c.get("/api/metrics/wave2/throughput?project_key=REYK").status_code == 200
    st = _status(c)
    assert st["hierarchy"]["state"] == "disabled"
    assert st["flow"]["state"] == "enabled"


def test_disable_flow_removes_its_routes_keeps_hierarchy(tmp_path):
    cfg = _write_modules(tmp_path, """
        modules:
          flow: {enabled: false}
          hierarchy: {enabled: true}
    """)
    c = TestClient(create_app(cfg))
    assert c.get("/api/issues").status_code == 404
    assert c.get("/api/metrics/wave1/percentiles?project_key=REYK").status_code == 404
    assert c.get("/api/hierarchy/config").status_code == 200
    assert c.get("/api/hierarchy/dashboard-v2").status_code == 200


# ---------------------------------------------------- isolamento (pacote fake)
@pytest.fixture
def fake_pkg(tmp_path, monkeypatch):
    """Cria um pacote 'fakemods' com módulos ok / quebrado / dependente."""
    pkg = tmp_path / "fakemods"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")

    def mk(name, manifest, router_src=None):
        d = pkg / name
        d.mkdir()
        (d / "__init__.py").write_text("")
        (d / "module.py").write_text(textwrap.dedent(manifest))
        if router_src:
            (d / "routes.py").write_text(textwrap.dedent(router_src))

    ok_router = """
        from fastapi import APIRouter
        router = APIRouter()
        @router.get("/api/{name}/ping")
        def ping(): return {{"ok": True}}
    """
    mk("good", """
        from kernel.module_base import Module
        module = Module(id="good", name="Good", routers=("fakemods.good.routes",))
    """, ok_router.format(name="good"))
    mk("broken", """
        raise RuntimeError("explodiu no import")
    """)
    mk("badrouter", """
        from kernel.module_base import Module
        module = Module(id="badrouter", name="BR", routers=("fakemods.badrouter.nao_existe",))
    """)
    mk("badenable", """
        from kernel.module_base import Module
        def boom(): raise RuntimeError("falha ao criar banco")
        module = Module(id="badenable", name="BE", on_enable=boom)
    """)
    mk("needsgood", """
        from kernel.module_base import Module
        module = Module(id="needsgood", name="NG", requires=("good",), routers=("fakemods.needsgood.routes",))
    """, ok_router.format(name="needsgood"))
    mk("needsbroken", """
        from kernel.module_base import Module
        module = Module(id="needsbroken", name="NB", requires=("broken",))
    """)
    mk("cyc_a", """
        from kernel.module_base import Module
        module = Module(id="cyc_a", name="A", requires=("cyc_b",))
    """)
    mk("cyc_b", """
        from kernel.module_base import Module
        module = Module(id="cyc_b", name="B", requires=("cyc_a",))
    """)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield "fakemods"
    for k in [k for k in sys.modules if k.startswith("fakemods")]:
        del sys.modules[k]


def _reg(fake_pkg, cfg):
    return Registry(cfg, package=fake_pkg).load()


def test_failure_in_one_module_does_not_stop_others(fake_pkg):
    r = _reg(fake_pkg, {"broken": True, "good": True})
    assert r.status["broken"].state == "failed" and "explodiu" in r.status["broken"].error
    assert r.status["good"].state == "enabled"
    assert [m for m, _ in r.routers] == ["good"]


def test_bad_router_import_fails_module_without_partial_routes(fake_pkg):
    r = _reg(fake_pkg, {"badrouter": True, "good": True})
    assert r.status["badrouter"].state == "failed"
    assert all(m != "badrouter" for m, _ in r.routers)


def test_on_enable_failure_fails_module_and_registers_no_routes(fake_pkg):
    r = _reg(fake_pkg, {"badenable": True})
    assert r.status["badenable"].state == "failed" and "criar banco" in r.status["badenable"].error
    assert r.routers == []


def test_requires_satisfied_loads_dependency_first(fake_pkg):
    r = _reg(fake_pkg, {"needsgood": True, "good": True})
    assert r.status["needsgood"].state == "enabled"
    assert [m for m, _ in r.routers] == ["good", "needsgood"]


def test_requires_disabled_dependency_fails(fake_pkg):
    r = _reg(fake_pkg, {"needsgood": True, "good": False})
    assert r.status["needsgood"].state == "failed" and "good" in r.status["needsgood"].error
    assert r.status["good"].state == "disabled"


def test_requires_broken_dependency_fails(fake_pkg):
    r = _reg(fake_pkg, {"needsbroken": True, "broken": True})
    assert r.status["needsbroken"].state == "failed"


def test_circular_dependency_is_detected(fake_pkg):
    r = _reg(fake_pkg, {"cyc_a": True, "cyc_b": True})
    assert r.status["cyc_a"].state == "failed" and r.status["cyc_b"].state == "failed"


def test_unknown_module_is_failed_not_crash(fake_pkg):
    r = _reg(fake_pkg, {"nao_existe": True, "good": True})
    assert r.status["nao_existe"].state == "failed"
    assert r.status["good"].state == "enabled"


def test_load_config_validates(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("outra_coisa: 1")
    with pytest.raises(ValueError):
        load_config(str(bad))
    with pytest.raises(FileNotFoundError):
        load_config(str(tmp_path / "nao_existe.yaml"))


def test_failed_module_is_reported_by_endpoint(tmp_path, fake_pkg):
    cfg = _write_modules(tmp_path, """
        modules:
          broken: {enabled: true}
          good: {enabled: true}
    """)
    c = TestClient(create_app(cfg, package=fake_pkg))
    st = _status(c)
    assert st["broken"]["state"] == "failed" and st["good"]["state"] == "enabled"
    assert c.get("/api/good/ping").status_code == 200
