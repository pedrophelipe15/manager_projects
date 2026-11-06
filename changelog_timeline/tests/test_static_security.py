"""Estáticos: só as pastas web dos módulos (e do kernel) são servidas; dados, código e segredos não."""
import os
import posixpath
import re

import pytest

from kernel.static import KERNEL_WEB_DIR, is_allowed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOW_WEB = os.path.join(ROOT, "modules", "flow", "web")
HIER_WEB = os.path.join(ROOT, "modules", "hierarchy", "web")

DENIED = [
    "/issues.db", "/hierarchy.db", "/projects.yaml", "/config/modules.yaml",
    "/ingest_to_db.py", "/api.py", "/kernel/registry.py", "/kernel/web/../registry.py",
    "/modules/flow/db.py", "/modules/flow/routers/wave1.py", "/modules/flow/web/wave1.html",
    "/modules/hierarchy/db.py", "/modules/flow/migrations/001_baseline.sql",
    "/requirements.txt", "/README.md", "/docs/DATASHEET.md", "/tests/conftest.py",
    "/exporter_jira/.env", "/exporter_jira/export_jira.py", "/.venv/pyvenv.cfg",
    "/.gitignore", "/.env", "/hierarchy/../issues.db", "/%2e%2e/issues.db",
    "/hierarchy/.env", "/hierarchy/data.json", "/hierarchy/db.py", "/start_service.ps1",
]


@pytest.mark.parametrize("path", DENIED)
def test_sensitive_paths_are_not_served(client, path):
    assert client.get(path).status_code == 404, path


@pytest.mark.parametrize("path", ["/", "/index.html", "/wave1.html", "/tokens.css", "/nav.js",
                                  "/hierarchy/dashboard-v2.html", "/hierarchy/hierarchy.css",
                                  "/hierarchy/pendencias.js", "/modules.html"])
def test_frontend_is_served(client, path):
    assert client.get(path, follow_redirects=True).status_code == 200, path


def test_is_allowed_unit():
    assert is_allowed("") and is_allowed(".") and is_allowed("wave1.html") and is_allowed("a/b.js")
    assert not is_allowed("issues.db") and not is_allowed(".env") and not is_allowed("a/.git/x.js")
    assert not is_allowed("x.py") and not is_allowed("x.yaml") and not is_allowed("x.json")


def test_web_dirs_contain_only_web_files():
    """Nada além de extensões web dentro das pastas servidas (defesa em profundidade)."""
    from kernel.static import ALLOWED_EXT
    for base in (KERNEL_WEB_DIR, FLOW_WEB, HIER_WEB):
        for dp, _dn, fn in os.walk(base):
            for f in fn:
                assert os.path.splitext(f)[1].lower() in ALLOWED_EXT, os.path.join(dp, f)


def _html_files():
    for base, prefix in ((FLOW_WEB, "/"), (HIER_WEB, "/hierarchy/"), (KERNEL_WEB_DIR, "/")):
        for f in os.listdir(base):
            if f.endswith(".html"):
                yield os.path.join(base, f), prefix


def _local_refs(html_path):
    text = open(html_path, encoding="utf-8").read()
    refs = re.findall(r'(?:src|href)=["\']([^"\'#?]+)', text)
    return [r for r in refs if not re.match(r"^(https?:|//|mailto:|javascript:|data:)", r)]


def test_every_local_asset_referenced_by_pages_is_served(client):
    """Resolve cada referência como o navegador (pela URL) e exige 200 — nenhuma página fica sem asset."""
    missing = []
    for html, prefix in _html_files():
        page_url = posixpath.join(prefix, os.path.basename(html))
        for ref in _local_refs(html):
            url = ref if ref.startswith("/") else posixpath.normpath(posixpath.join(posixpath.dirname(page_url), ref))
            if client.get(url).status_code != 200:
                missing.append((os.path.basename(html), ref, url))
    assert not missing, f"referências que dão 404: {missing}"
