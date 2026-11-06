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
            f.write("from routers.projects import router  # hierarchy importando flow\n")
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
            "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in "
            "('routers','core','metrics','modules'))))")
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
    flow_code = {m for m in loaded if m.startswith(("routers.projects", "routers.wave", "routers.issues",
                                                    "core.", "metrics.base", "modules.flow."))}
    assert not flow_code, flow_code
    assert "routers.hierarchy_config" in loaded


def test_hierarchy_disabled_loads_no_hierarchy_code(tmp_path):
    loaded = _loaded_modules(tmp_path, flow_on=True, hier_on=False)
    hier_code = {m for m in loaded if "hierarchy" in m and m != "modules.hierarchy"}
    assert not hier_code, hier_code
    assert "routers.projects" in loaded


def _contract_sources():
    cp = configparser.ConfigParser()
    cp.read(os.path.join(ROOT, ".importlinter"), encoding="utf-8")
    out = {}
    for sec in cp.sections():
        if sec.endswith("flow-nao-importa-hierarchy"):
            out["flow"] = {x.strip() for x in cp[sec]["source_modules"].split() if x.strip()}
        if sec.endswith("hierarchy-nao-importa-flow"):
            out["hierarchy"] = {x.strip() for x in cp[sec]["source_modules"].split() if x.strip()}
    return out


def test_every_router_and_metric_belongs_to_a_module():
    """Arquivo novo em routers/ ou metrics/ precisa ser classificado em flow ou hierarchy no
    .importlinter; senão ele escaparia da checagem de fronteira."""
    groups = _contract_sources()
    classified = groups["flow"] | groups["hierarchy"]
    missing = []
    for pkg in ("routers", "metrics"):
        for name in os.listdir(os.path.join(ROOT, pkg)):
            if name.startswith("__") or name.endswith(".pyc"):
                continue
            mod = f"{pkg}.{os.path.splitext(name)[0]}"
            if mod not in classified:
                missing.append(mod)
    assert not missing, f"não classificados em .importlinter (flow ou hierarchy): {sorted(missing)}"
