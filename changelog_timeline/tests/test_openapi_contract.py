"""Contrato: o OpenAPI nao pode mudar sem intencao.

Para atualizar o snapshot apos uma mudanca INTENCIONAL de API:
    set UPDATE_SNAPSHOT=1 && pytest tests/test_openapi_contract.py
"""
import json
import os

SNAPSHOT = os.path.join(os.path.dirname(__file__), "snapshots", "openapi.json")


def _normalize(spec):
    return json.loads(json.dumps(spec, sort_keys=True))


def test_openapi_matches_snapshot(client):
    # app.openapi() direto: evita problema de decodificacao do cliente HTTP (acentos)
    current = _normalize(client.app.openapi())
    if os.environ.get("UPDATE_SNAPSHOT") == "1":
        os.makedirs(os.path.dirname(SNAPSHOT), exist_ok=True)
        with open(SNAPSHOT, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=1, sort_keys=True, ensure_ascii=False)
        return
    with open(SNAPSHOT, encoding="utf-8") as f:
        expected = json.load(f)
    cur_paths, exp_paths = set(current["paths"]), set(expected["paths"])
    assert cur_paths == exp_paths, f"rotas removidas: {exp_paths - cur_paths}; novas: {cur_paths - exp_paths}"
    assert current == expected, "OpenAPI mudou (parametros/schemas). Se intencional, regenere o snapshot."
