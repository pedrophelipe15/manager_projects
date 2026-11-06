"""Arquitetura: fronteiras entre kernel e módulos (import-linter) + cobertura dos contratos."""
import configparser
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMD = [sys.executable, "-c", "from importlinter.cli import lint_imports_command; lint_imports_command()"]


def _lint():
    return subprocess.run(CMD, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def test_import_contracts_are_kept():
    r = _lint()
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-500:]
    assert "0 broken" in r.stdout


def test_linter_actually_detects_a_violation():
    """Garante que os contratos não são vácuos: injeta um import proibido e espera falha."""
    bad = os.path.join(ROOT, "modules", "hierarchy", "_tmp_violation.py")
    try:
        with open(bad, "w", encoding="utf-8") as f:
            f.write("from modules.flow.routers.projects import router  # hierarchy importando flow\n")
        r = _lint()
        assert r.returncode != 0 and "BROKEN" in r.stdout
    finally:
        if os.path.exists(bad):
            os.remove(bad)


def _loaded_modules(tmp_path, flow_on, hier_on):
    cfg = tmp_path / "modules.yaml"
    cfg.write_text(f"modules:\n  flow: {{enabled: {str(flow_on).lower()}}}\n"
                   f"  hierarchy: {{enabled: {str(hier_on).lower()}}}\n")
    code = ("import sys, json; import api; "
            "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] == 'modules')))")
    env = dict(os.environ, MANAGER_MODULES_FILE=str(cfg),
               MANAGER_DB_PATH=str(tmp_path / "i.db"), MANAGER_HIERARCHY_DB_PATH=str(tmp_path / "h.db"))
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    import json
    return set(json.loads(r.stdout.strip().splitlines()[-1]))


def test_flow_disabled_loads_no_flow_code(tmp_path):
    """Com flow desligado, hierarchy sobe sozinho (nenhum código do flow é importado)."""
    loaded = _loaded_modules(tmp_path, flow_on=False, hier_on=True)
    flow_code = {m for m in loaded if m == "modules.flow" or m.startswith("modules.flow.")}
    assert not flow_code, flow_code
    assert "modules.hierarchy.routers.config" in loaded


def test_hierarchy_disabled_loads_no_hierarchy_code(tmp_path):
    loaded = _loaded_modules(tmp_path, flow_on=True, hier_on=False)
    hier_code = {m for m in loaded if m == "modules.hierarchy" or m.startswith("modules.hierarchy.")}
    assert not hier_code, hier_code
    assert "modules.flow.routers.projects" in loaded


def test_every_module_directory_is_in_the_independence_contract():
    """Pasta nova em modules/ precisa entrar no contrato de independência do .importlinter;
    senão ela escaparia da checagem de fronteira."""
    cp = configparser.ConfigParser()
    cp.read(os.path.join(ROOT, ".importlinter"), encoding="utf-8")
    listed = set()
    for sec in cp.sections():
        if sec.endswith("modulos-independentes"):
            listed = {x.strip() for x in cp[sec]["modules"].split() if x.strip()}
    on_disk = {f"modules.{d}" for d in os.listdir(os.path.join(ROOT, "modules"))
               if os.path.isdir(os.path.join(ROOT, "modules", d)) and not d.startswith(("__", "."))}
    assert on_disk == listed, f"modules/ no disco: {sorted(on_disk)} x contrato: {sorted(listed)}"


def test_no_legacy_top_level_packages_remain():
    """routers/, metrics/, core/, hierarchy/ foram movidos para modules/<id>/ (fase 8)."""
    for legacy in ("routers", "metrics", "core", "hierarchy", "exporter_jira/jira_client.py"):
        assert not os.path.exists(os.path.join(ROOT, legacy)), legacy