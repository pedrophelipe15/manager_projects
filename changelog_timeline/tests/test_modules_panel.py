"""Fase 7: painel de módulos (somente leitura) e dados que ele consome."""
import os
import re
import textwrap

from fastapi.testclient import TestClient

from kernel.app_factory import create_app
from kernel.migrations import read_version

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _mods(client):
    return {m["id"]: m for m in client.get("/api/platform/modules").json()["modules"]}


# ------------------------------------------------------------------ dados do painel
def test_enabled_modules_report_health_with_schema_version(client):
    m = _mods(client)
    assert m["flow"]["state"] == "enabled" and m["flow"]["health"]["ok"] is True
    assert "issues.db" in m["flow"]["health"]["detail"] and "schema v3" in m["flow"]["health"]["detail"]
    assert m["hierarchy"]["health"]["ok"] and "schema v1" in m["hierarchy"]["health"]["detail"]
    assert m["flow"]["home"] == "/minha-visao.html"


def test_health_does_not_leak_server_paths(client):
    body = client.get("/api/platform/modules").text
    assert not re.search(r"[A-Za-z]:\\\\|/Users/|/home/|\\\\Users", body), "caminho absoluto no status"
    assert ROOT.replace("\\", "\\\\") not in body and ROOT not in body


def test_read_version_is_read_only_and_safe(tmp_path):
    assert read_version(str(tmp_path / "nao_existe.db")) is None
    import sqlite3
    p = tmp_path / "vazio.db"
    sqlite3.connect(str(p)).close()
    assert read_version(str(p)) is None                       # sem tabela schema_version
    conn = sqlite3.connect(str(p))
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='schema_version'").fetchone() is None
    conn.close()                                               # leitura não criou a tabela


def test_failed_module_shows_cause_and_disabled_shows_state(tmp_path):
    pkg = tmp_path / "panelmods"
    (pkg / "bad").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "bad" / "__init__.py").write_text("")
    (pkg / "bad" / "module.py").write_text("raise RuntimeError('causa visivel no painel')\n", encoding="utf-8")
    cfg = tmp_path / "m.yaml"
    cfg.write_text(textwrap.dedent("""
        modules:
          bad: {enabled: true}
          unused: {enabled: false}
    """))
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        c = TestClient(create_app(str(cfg), package="panelmods"))
        m = _mods(c)
        assert m["bad"]["state"] == "failed" and "causa visivel no painel" in m["bad"]["error"]
        assert m["unused"]["state"] == "disabled" and m["unused"]["health"] is None
    finally:
        sys.path.remove(str(tmp_path))
        for k in [k for k in sys.modules if k.startswith("panelmods")]:
            del sys.modules[k]


def test_module_id_that_yaml_reads_as_boolean_is_rejected(tmp_path):
    """`off:` sem aspas vira a chave False no YAML; antes sumia em silêncio."""
    import pytest
    from kernel.registry import load_config
    cfg = tmp_path / "m.yaml"
    cfg.write_text("modules:\n  off: {enabled: true}\n")
    with pytest.raises(ValueError, match="entre aspas"):
        load_config(str(cfg))
    cfg.write_text('modules:\n  "off": {enabled: true}\n')
    assert load_config(str(cfg)) == {"off": True}


# ------------------------------------------------------------------ página
def test_panel_page_and_assets_are_served_always(client):
    for url in ("/modules.html", "/modules.js", "/modules.css"):
        assert client.get(url).status_code == 200, url


def test_panel_is_read_only_and_safe():
    js = open(os.path.join(ROOT, "kernel", "web", "modules.js"), encoding="utf-8").read()
    html = open(os.path.join(ROOT, "kernel", "web", "modules.html"), encoding="utf-8").read()
    assert "innerHTML" not in js and "outerHTML" not in js and "insertAdjacentHTML" not in js
    assert "method" not in js.lower().replace("addeventlistener", "")  # só GET: nenhuma escrita
    assert "POST" not in js and "PUT" not in js and "DELETE" not in js
    assert "modules.yaml" in html          # orienta como ligar/desligar (por arquivo + reinício)
    assert 'id="main-nav"' in html and "nav.js" in html
