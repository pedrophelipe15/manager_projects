"""Fase 5: menu dinâmico, estáticos por módulo (404 se desligado) e assets da plataforma."""
import os
import re
import sys
import textwrap

import pytest
from fastapi.testclient import TestClient

from kernel.app_factory import create_app
from kernel.static import PLATFORM_ASSETS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OLD_HARDCODED_MENU = [   # o que o antigo nav.js tinha fixo no código
    ("Minha Visão", [("Minha Visão", "/minha-visao.html")]),
    ("Prazos", [("Compromisso", "/compromisso.html"), ("Previsibilidade", "/wave2.html")]),
    ("Pessoas", [("Maturidade", "/maturidade.html"), ("Pessoas", "/wave3.html")]),
    ("Fluxo", [("Gargalo e Fluxo", "/wave1.html"), ("Portfólio", "/wave4.html"), ("Dashboard", "/dashboard.html")]),
    ("Hierarquia", [("Hierarquia", "/hierarchy/dashboard-v2.html")]),
    ("Dados", [("Inconsistências", "/inconsistencies.html"), ("Configurações", "/settings.html")]),
]
PLATFORM_MENU = ("Plataforma", [("Módulos", "/modules.html")])   # item da própria plataforma (fase 7)


def _app(tmp_path, flow, hier, package="modules"):
    cfg = tmp_path / "m.yaml"
    cfg.write_text(f"modules:\n  flow: {{enabled: {str(flow).lower()}}}\n"
                   f"  hierarchy: {{enabled: {str(hier).lower()}}}\n")
    return TestClient(create_app(str(cfg), package=package), follow_redirects=False)


def _menu(c):
    return [(g["group"], [(l["label"], l["href"]) for l in g["links"]]) for g in c.get("/api/platform/modules").json()["menu"]]


# ------------------------------------------------------------------ menu
def test_menu_equals_the_old_hardcoded_menu(client):
    assert _menu(client) == OLD_HARDCODED_MENU + [PLATFORM_MENU]


def test_menu_hides_disabled_module(tmp_path):
    c = _app(tmp_path, flow=True, hier=False)
    assert "Hierarquia" not in [g for g, _ in _menu(c)]
    c = _app(tmp_path, flow=False, hier=True)
    assert _menu(c) == [("Hierarquia", [("Hierarquia", "/hierarchy/dashboard-v2.html")]), PLATFORM_MENU]


def test_nav_js_has_no_hardcoded_links():
    src = open(os.path.join(ROOT, "nav.js"), encoding="utf-8").read()
    assert "/api/platform/modules" in src
    assert not re.search(r"\.html", src), "nav.js não pode ter páginas fixas"


# ------------------------------------------------------------------ estáticos por módulo
def test_hierarchy_disabled_pages_are_404_flow_stays(tmp_path):
    c = _app(tmp_path, flow=True, hier=False)
    for url in ("/hierarchy/dashboard-v2.html", "/hierarchy/hierarchy.css", "/hierarchy/nav.js"):
        assert c.get(url).status_code == 404, url
    for url in ("/wave1.html", "/minha-visao.html", "/settings.js", "/tokens.css", "/nav.js"):
        assert c.get(url).status_code == 200, url


def test_flow_disabled_pages_are_404_hierarchy_stays(tmp_path):
    c = _app(tmp_path, flow=False, hier=True)
    for url in ("/wave1.html", "/minha-visao.html", "/index.html", "/wave1.js", "/style.css"):
        assert c.get(url).status_code == 404, url
    for url in ("/hierarchy/dashboard-v2.html", "/hierarchy/pendencias.html", "/hierarchy/hierarchy.css",
                "/tokens.css", "/nav.css", "/dashboard.css", "/nav.js", "/ui.js", "/context.js"):
        assert c.get(url).status_code == 200, url


def test_root_redirects_to_first_enabled_module_home(tmp_path):
    r = _app(tmp_path, True, True).get("/")
    assert r.status_code in (302, 307) and r.headers["location"] == "/minha-visao.html"
    r = _app(tmp_path, False, True).get("/")
    assert r.headers["location"] == "/hierarchy/dashboard-v2.html"


def test_no_module_enabled_still_serves_platform_assets(tmp_path):
    c = _app(tmp_path, False, False)
    assert c.get("/").status_code == 503
    assert c.get("/tokens.css").status_code == 200 and c.get("/nav.js").status_code == 200
    assert c.get("/wave1.html").status_code == 404 and c.get("/hierarchy/dashboard-v2.html").status_code == 404
    # a plataforma mantém o próprio item de menu (painel de módulos), mesmo sem módulos
    assert _menu(c) == [PLATFORM_MENU]
    assert c.get("/modules.html").status_code == 200


# ------------------------------------------------------------------ módulo novo aparece sozinho
def test_new_module_appears_in_menu_and_serves_its_static_dir(tmp_path, monkeypatch):
    pkg = tmp_path / "fakemods2"
    (pkg / "xmod").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "xmod" / "__init__.py").write_text("")
    (pkg / "xmod" / "module.py").write_text(textwrap.dedent("""
        from kernel.module_base import Module, NavItem
        module = Module(id="xmod", name="Módulo X", home="/xmod/index.html", static_dirs=("xmod",),
                        nav=(NavItem("X Home", "/xmod/index.html", "Extras", 55, 10),))
    """), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        cfg = tmp_path / "m.yaml"
        cfg.write_text("modules:\n  hierarchy: {enabled: true}\n  xmod: {enabled: true}\n")
        c = TestClient(create_app(str(cfg), package="fakemods2"), follow_redirects=False)
        # (hierarchy não existe no pacote fake => falha isolada; xmod sobe)
        st = {m["id"]: m for m in c.get("/api/platform/modules").json()["modules"]}
        assert st["xmod"]["state"] == "enabled" and st["hierarchy"]["state"] == "failed"
        assert ("Extras", [("X Home", "/xmod/index.html")]) in _menu(c)
        assert c.get("/").headers["location"] == "/xmod/index.html"
    finally:
        for k in [k for k in sys.modules if k.startswith("fakemods2")]:
            del sys.modules[k]


# ------------------------------------------------------------------ fronteira do frontend
def _local_refs(path):
    text = open(path, encoding="utf-8").read()
    refs = re.findall(r'(?:src|href)=["\']([^"\'#?]+)', text)
    return [r for r in refs if not re.match(r"^(https?:|//|mailto:|javascript:|data:)", r)]


def test_hierarchy_pages_only_use_own_dir_and_platform_assets():
    bad = []
    hdir = os.path.join(ROOT, "hierarchy")
    for f in os.listdir(hdir):
        if not f.endswith(".html"):
            continue
        for ref in _local_refs(os.path.join(hdir, f)):
            target = os.path.normpath(os.path.join(hdir, ref))
            rel = os.path.relpath(target, ROOT).replace(os.sep, "/")
            in_own = rel.startswith("hierarchy/")
            if not (in_own or rel in PLATFORM_ASSETS):
                bad.append((f, ref))
    assert not bad, f"hierarchy referencia arquivos do flow: {bad}"


def test_flow_and_hierarchy_do_not_link_each_others_pages():
    flow_pages = r"/(?:minha-visao|dashboard|wave\d|compromisso|settings|insights|maturidade|inconsistencies|index|visao-projeto)\.html"
    for f in os.listdir(os.path.join(ROOT, "hierarchy")):
        if f.endswith((".js", ".html")):
            src = open(os.path.join(ROOT, "hierarchy", f), encoding="utf-8").read()
            assert not re.search(r'["\'`]' + flow_pages, src), f"hierarchy/{f} aponta para página do flow"
    for f in os.listdir(ROOT):
        if f.endswith((".js", ".html")):
            src = open(os.path.join(ROOT, f), encoding="utf-8").read()
            assert not re.search(r'(?:href|location(?:\.href)?)\s*=\s*["\']/hierarchy/', src), \
                f"{f} tem link fixo para /hierarchy/ (use o menu dinâmico)"
