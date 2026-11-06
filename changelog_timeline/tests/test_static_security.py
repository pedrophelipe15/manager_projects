"""Estáticos: só o frontend é servido; dados, código e segredos não."""
import os
import re

import pytest

from kernel.static import StaticPolicy, is_allowed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DENIED = [
    "/issues.db", "/hierarchy.db", "/projects.yaml", "/config/modules.yaml",
    "/ingest_to_db.py", "/api.py", "/routers/wave1.py", "/core/db.py", "/kernel/registry.py",
    "/requirements.txt", "/README.md", "/docs/DATASHEET.md", "/tests/conftest.py",
    "/exporter_jira/.env", "/exporter_jira/export_jira.py", "/.venv/pyvenv.cfg",
    "/.gitignore", "/.env", "/hierarchy/../issues.db", "/%2e%2e/issues.db",
    "/hierarchy/.env", "/hierarchy/data.json", "/start_service.ps1",
]


@pytest.mark.parametrize("path", DENIED)
def test_sensitive_paths_are_not_served(client, path):
    assert client.get(path).status_code == 404, path


@pytest.mark.parametrize("path", ["/", "/index.html", "/wave1.html", "/tokens.css", "/nav.js",
                                  "/hierarchy/dashboard-v2.html", "/hierarchy/hierarchy.css",
                                  "/hierarchy/nav.js"])
def test_frontend_is_served(client, path):
    assert client.get(path).status_code == 200, path


def test_is_allowed_unit():
    both = StaticPolicy(dirs=frozenset({"hierarchy"}), root=True)
    assert is_allowed("", both) and is_allowed("wave1.html", both) and is_allowed("hierarchy/x.js", both)
    assert not is_allowed("issues.db", both) and not is_allowed(".env", both)
    assert not is_allowed("docs/a.html", both) and not is_allowed("hierarchy/a.json", both)
    # sem módulos ligados: só os assets da plataforma
    none = StaticPolicy()
    assert is_allowed("tokens.css", none) and is_allowed("nav.js", none)
    assert not is_allowed("wave1.html", none) and not is_allowed("hierarchy/x.js", none)
    assert not is_allowed("", none)


def _local_refs(html_path):
    text = open(html_path, encoding="utf-8").read()
    refs = re.findall(r'(?:src|href)=["\']([^"\'#?]+)', text)
    return [r for r in refs if not re.match(r"^(https?:|//|mailto:|javascript:|data:)", r)]


def _html_files():
    out = []
    for base in (ROOT, os.path.join(ROOT, "hierarchy")):
        for f in os.listdir(base):
            if f.endswith(".html"):
                out.append(os.path.join(base, f))
    return out


def test_every_local_asset_referenced_by_pages_is_served(client):
    """Nenhuma página pode referenciar um arquivo que a allowlist bloqueia."""
    missing = []
    for html in _html_files():
        page_dir = os.path.dirname(html)
        for ref in _local_refs(html):
            target = os.path.normpath(os.path.join(page_dir, ref) if not ref.startswith("/")
                                      else os.path.join(ROOT, ref.lstrip("/")))
            if os.path.isdir(target) or not os.path.exists(target):
                continue  # link de navegação para rota/dir ou arquivo inexistente (fora do escopo)
            url = "/" + os.path.relpath(target, ROOT).replace(os.sep, "/")
            if client.get(url).status_code != 200:
                missing.append((os.path.relpath(html, ROOT), ref, url))
    assert not missing, f"referências bloqueadas: {missing}"
