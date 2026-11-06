"""ConfigStore: lock, escrita atômica, seções e integração com as rotas de configuração."""
import os
import subprocess
import sys
import threading
import time

import pytest
import yaml

from kernel.config_store import ConfigError, ConfigStore

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _store(tmp_path, content=None):
    p = tmp_path / "projects.yaml"
    if content is not None:
        p.write_text(content, encoding="utf-8")
    return ConfigStore(str(p)), p


# ------------------------------------------------------------------ básico
def test_update_preserves_unknown_keys_and_order(tmp_path):
    s, p = _store(tmp_path, "projects: [{key: A}]\nextra: {x: 1}\nhierarchy: []\n")
    s.section("hierarchy", owns=("hierarchy",)).update(lambda sub: sub["hierarchy"].append({"key": "H1"}))
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert list(data) == ["projects", "extra", "hierarchy"]
    assert data["extra"] == {"x": 1} and data["projects"] == [{"key": "A"}]
    assert data["hierarchy"] == [{"key": "H1"}]


def test_missing_file_is_created_on_update(tmp_path):
    s, p = _store(tmp_path)
    assert s.read() == {}
    s.set("projects", [1])
    assert yaml.safe_load(p.read_text()) == {"projects": [1]}


def test_no_write_when_nothing_changed(tmp_path):
    s, p = _store(tmp_path, "a: 1\n")
    m = os.path.getmtime(p)
    time.sleep(0.05)
    s.update(lambda d: None)
    assert os.path.getmtime(p) == m and not os.path.exists(str(p) + ".bak")


def test_mutator_exception_writes_nothing(tmp_path):
    s, p = _store(tmp_path, "a: 1\n")
    def boom(d):
        d["a"] = 2
        raise RuntimeError("abortar")
    with pytest.raises(RuntimeError):
        s.update(boom)
    assert yaml.safe_load(p.read_text()) == {"a": 1}


def test_invalid_yaml_is_never_overwritten(tmp_path):
    s, p = _store(tmp_path, "a: [1, 2\n")
    before = p.read_text()
    with pytest.raises(ConfigError):
        s.update(lambda d: d.update(b=1))
    assert p.read_text() == before


def test_non_mapping_top_level_rejected(tmp_path):
    s, _ = _store(tmp_path, "- 1\n- 2\n")
    with pytest.raises(ConfigError):
        s.read()


def test_backup_and_no_leftovers(tmp_path):
    s, p = _store(tmp_path, "a: 1\n")
    s.update(lambda d: d.update(a=2))
    assert yaml.safe_load(open(str(p) + ".bak", encoding="utf-8")) == {"a": 1}
    assert sorted(os.listdir(tmp_path)) == ["projects.yaml", "projects.yaml.bak"]


def test_stale_lock_is_recovered(tmp_path):
    s, p = _store(tmp_path, "a: 1\n")
    lock = str(p) + ".lock"
    open(lock, "w").close()
    old = time.time() - 600
    os.utime(lock, (old, old))
    s.update(lambda d: d.update(a=2))
    assert yaml.safe_load(p.read_text()) == {"a": 2}


# ------------------------------------------------------------------ seções
def test_section_cannot_write_foreign_keys(tmp_path):
    s, p = _store(tmp_path, "projects: [1]\nhierarchy: []\n")
    sec = s.section("hierarchy", owns=("hierarchy",))
    before = p.read_text()
    with pytest.raises(ConfigError):
        sec.update(lambda sub: sub.__setitem__("projects", ["invasor"]))
    assert p.read_text() == before
    with pytest.raises(ConfigError):
        sec.get("projects")


# ------------------------------------------------------------------ concorrência
def test_concurrent_threads_two_modules_lose_no_updates(tmp_path):
    s, p = _store(tmp_path, "projects: []\nhierarchy: []\n")
    flow = s.section("flow", owns=("projects",))
    hier = s.section("hierarchy", owns=("hierarchy",))
    errors = []

    def add(sec, key, i):
        try:
            sec.update(lambda sub: sub.setdefault(key, []).append(i))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=add, args=(flow, "projects", i)) for i in range(15)]
    ts += [threading.Thread(target=add, args=(hier, "hierarchy", i)) for i in range(15)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    data = yaml.safe_load(p.read_text())
    assert not errors
    assert sorted(data["projects"]) == list(range(15))
    assert sorted(data["hierarchy"]) == list(range(15))


def test_concurrent_processes_lose_no_updates(tmp_path):
    p = tmp_path / "projects.yaml"
    p.write_text("a: []\nb: []\n", encoding="utf-8")
    code = (
        "import sys; sys.path.insert(0, sys.argv[1])\n"
        "from kernel.config_store import ConfigStore\n"
        "s = ConfigStore(sys.argv[2]); key = sys.argv[3]\n"
        "for i in range(10):\n"
        "    s.update(lambda d: d[key].append(i))\n"
    )
    procs = [subprocess.Popen([sys.executable, "-c", code, ROOT, str(p), k])
             for k in ("a", "b", "a", "b")]
    assert [x.wait(timeout=60) for x in procs] == [0, 0, 0, 0]
    data = yaml.safe_load(p.read_text())
    assert len(data["a"]) == 20 and len(data["b"]) == 20


# ------------------------------------------------------------------ rotas (integração)
@pytest.fixture
def yaml_file():
    import conftest
    original = open(conftest.YAML, encoding="utf-8").read()
    yield conftest.YAML
    with open(conftest.YAML, "w", encoding="utf-8") as f:
        f.write(original)
    for ext in (".bak", ".lock"):
        if os.path.exists(conftest.YAML + ext):
            os.remove(conftest.YAML + ext)


def _data(path):
    return yaml.safe_load(open(path, encoding="utf-8").read())


def test_hierarchy_config_routes_preserve_projects(client, yaml_file):
    r = client.post("/api/hierarchy/config", json={"key": "INI-1", "name": "Ini", "type": "initiative"})
    assert r.status_code == 201
    assert client.post("/api/hierarchy/config", json={"key": "INI-1", "name": "x", "type": "epic"}).status_code == 409
    assert client.put("/api/hierarchy/config/INI-1", json={"key": "INI-1", "name": "Novo", "type": "epic"}).json()["name"] == "Novo"
    assert client.put("/api/hierarchy/config/NAO", json={"key": "N", "name": "n", "type": "epic"}).status_code == 404
    assert [e["key"] for e in client.get("/api/hierarchy/config").json()] == ["INI-1"]
    d = _data(yaml_file)
    assert d["projects"][0]["key"] == "REYK"          # config do flow intacta
    assert client.delete("/api/hierarchy/config/INI-1").status_code == 200
    assert client.delete("/api/hierarchy/config/INI-1").status_code == 404
    assert _data(yaml_file)["hierarchy"] == []


@pytest.mark.parametrize("base", ["/api/hierarchy/excluded-projects", "/api/settings/excluded-projects"])
def test_excluded_projects_new_and_legacy_routes(client, yaml_file, base):
    assert client.post(base, json={"key": "psdc-1404"}).json() == {"excluded_projects": ["PSDC"]}
    assert client.post(base, json={"key": "PSDC"}).status_code == 409
    assert client.post(base, json={"key": " "}).status_code == 400
    assert client.get(base).json() == {"excluded_projects": ["PSDC"]}
    assert client.delete(f"{base}/PSDC").json() == {"excluded_projects": []}
    assert client.delete(f"{base}/PSDC").status_code == 404
    assert _data(yaml_file)["projects"][0]["key"] == "REYK"


def test_project_routes_preserve_hierarchy_keys(client, yaml_file):
    client.post("/api/hierarchy/config", json={"key": "INI-9", "name": "I", "type": "initiative"})
    body = {"key": "NEW", "name": "Novo", "jql_project": 'project = "PS - Novo"'}
    assert client.post("/api/settings/projects", json=body).status_code == 201
    assert client.post("/api/settings/projects", json=body).status_code == 409
    d = _data(yaml_file)
    assert [p["key"] for p in d["projects"]] == ["REYK", "NEW"]
    assert d["hierarchy"][0]["key"] == "INI-9"         # config da hierarchy intacta
    assert client.delete("/api/settings/projects/NEW").status_code == 200
    assert client.delete("/api/settings/projects/NEW").status_code == 404
    assert [p["key"] for p in _data(yaml_file)["projects"]] == ["REYK"]
