"""Smoke: todas as rotas GET respondem sem erro 5xx sobre um banco completo.

Rotas de escrita (POST/PUT/DELETE: sync, purge, config) ficam fora de proposito:
alteram estado e/ou chamam o Jira.
"""
import pytest

P = "REYK"

# rota -> status esperado (default 200)
GET_ROUTES = {
    "/api/issues": 200,
    "/api/issues/REYK-2/timeline": 200,
    "/api/settings/blacklist": 200,
    "/api/settings/projects": 200,
    "/api/settings/projects/sync/status": 200,
    "/api/settings/purge/status": 200,
    "/api/settings/purge/history": 200,
    "/api/settings/purge/preview": 200,
    "/api/settings/validations": 200,
    "/api/settings/excluded-projects": 200,
    "/api/inconsistencies": 200,
    f"/api/inconsistencies?project_key={P}": 200,
    f"/api/metrics/due-date-changes?project_key={P}": 200,
    f"/api/metrics/wave1/time-per-status?project_key={P}": 200,
    f"/api/metrics/wave1/percentiles?project_key={P}": 200,
    f"/api/metrics/wave1/percentiles-weekly?project_key={P}": 200,
    f"/api/metrics/wave1/flow-efficiency?project_key={P}": 200,
    f"/api/metrics/wave1/flow-efficiency-weekly?project_key={P}": 200,
    f"/api/metrics/wave1/cfd?project_key={P}": 200,
    f"/api/metrics/wave1/aging-wip?project_key={P}": 200,
    f"/api/metrics/wave1/last-update?project_key={P}": 200,
    "/api/metrics/wave1/recalculate/status": 200,
    f"/api/insights?project_key={P}": 200,
    "/api/insights/alert-count": 200,
    f"/api/metrics/wave2/throughput?project_key={P}": 200,
    f"/api/metrics/wave2/throughput-impact?project_key={P}&cutoff_week=2026-W01": 200,
    f"/api/metrics/wave2/forecast?project_key={P}&remaining_items=5": 200,
    f"/api/metrics/wave2/open-epics?project_key={P}": 200,
    f"/api/metrics/wave2/aging-backlog?project_key={P}": 200,
    f"/api/metrics/wave3/wip?project_key={P}": 200,
    f"/api/metrics/wave3/workload?project_key={P}": 200,
    f"/api/metrics/wave3/handoff?project_key={P}": 200,
    f"/api/metrics/wave3/rework?project_key={P}": 200,
    f"/api/metrics/wave4/epic-health?project_key={P}": 200,
    "/api/metrics/wave4/benchmarking": 200,
    "/api/metrics/wave4/cross-project-throughput": 200,
    f"/api/metrics/wave5/slippage?project_key={P}": 200,
    "/api/metrics/wave5/commitment-summary": 200,
    "/api/home/overview": 200,
    f"/api/home/detail?project_key={P}&metric=throughput": None,  # valida so: sem 5xx
    "/api/hierarchy/config": 200,
    "/api/hierarchy/sync/status": 200,
    "/api/hierarchy/sync/history": 200,
    "/api/hierarchy/last-sync": 200,
    "/api/hierarchy/epic-health": 200,
    "/api/hierarchy/initiative-health": 200,
    "/api/hierarchy/dashboard-v2": 200,
    "/api/hierarchy/roadmap": 200,
    "/api/hierarchy/issue-links": 200,
    "/api/hierarchy/pending": 200,
}

STATIC_PAGES = ["/minha-visao.html", "/wave1.html", "/hierarchy/dashboard-v2.html", "/settings.html"]


@pytest.mark.parametrize("path,expected", list(GET_ROUTES.items()))
def test_get_route(client, path, expected):
    r = client.get(path)
    if expected is None:
        assert r.status_code < 500, f"{path} -> {r.status_code}: {r.text[:200]}"
    else:
        assert r.status_code == expected, f"{path} -> {r.status_code}: {r.text[:200]}"


@pytest.mark.parametrize("path", STATIC_PAGES)
def test_static_pages(client, path):
    assert client.get(path).status_code == 200


def test_api_does_not_leak_to_static(client):
    """Rota /api inexistente deve dar 404 (nao cair no mount estatico como 200)."""
    assert client.get("/api/__nao_existe__").status_code == 404


def test_fixture_has_data(client):
    """Garante que o banco de teste tem dados (senao o smoke nao prova nada)."""
    r = client.get(f"/api/metrics/wave2/throughput?project_key={P}")
    assert r.status_code == 200 and r.json()
