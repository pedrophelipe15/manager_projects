import json
import random
import sys
import os
from copy import deepcopy
from datetime import datetime, timedelta

# =====================================================
# Configurações
# =====================================================

if len(sys.argv) != 2:
    print("Uso: python gerar_jira.py <quantidade>")
    sys.exit(1)

QUANTIDADE = int(sys.argv[1])

DATA_INICIAL = datetime(2026, 1, 1)
DATA_FINAL = datetime.now()

# =====================================================
# Dados para geração aleatória
# =====================================================

PROJETOS = [
    {"key": "REYK", "id": "13542", "name": "PS - REYKJAVIK"},
    {"key": "MAD3", "id": "13543", "name": "PS - MADRID"},
    {"key": "LOND", "id": "13544", "name": "PS - LONDON"},
    {"key": "PARI", "id": "13545", "name": "PS - PARIS"},
    {"key": "ROME", "id": "13546", "name": "PS - ROME"}
]

USUARIOS = [
    {
        "displayName": "Claudio Augusto Rosa David",
        "emailAddress": "claudio.david@empresa.com"
    },
    {
        "displayName": "Carlos Silva",
        "emailAddress": "carlos.silva@empresa.com"
    },
    {
        "displayName": "Fernanda Souza",
        "emailAddress": "fernanda.souza@empresa.com"
    },
    {
        "displayName": "Juliana Costa",
        "emailAddress": "juliana.costa@empresa.com"
    },
    {
        "displayName": "Patricia Lima",
        "emailAddress": "patricia.lima@empresa.com"
    }
]

STATUS = [
    "Open",
    "In Progress",
    "Waiting Approval",
    "Done",
    "Closed"
]

SUMMARIES = [
    "[MELHORIAS][RISCO] - MAD3 - PDBFINANCIALASSETRISK",
    "[CORRECAO] - Falha na carga de dados",
    "[MELHORIAS] - Otimizacao de consultas SQL",
    "[INCIDENTE] - Erro em producao",
    "[PROJETO] - Implementacao de API REST",
    "[AUTOMACAO] - Novo processo batch",
    "[SEGURANCA] - Revisao de acessos",
    "[PERFORMANCE] - Ajuste de banco de dados",
    "[MIGRACAO] - Atualizacao de ambiente",
    "[MONITORAMENTO] - Inclusao de novas metricas"
]

# =====================================================
# Template Base
# =====================================================

TEMPLATE = {
    "key": "",
    "fields": {
        "summary": "",
        "created": "",
        "project": {
            "self": "https://jiraps.atlassian.net/rest/api/3/project/13542",
            "id": "",
            "key": "",
            "name": "",
            "projectTypeKey": "software",
            "simplified": False,
            "avatarUrls": {
                "48x48": "https://jiraps.atlassian.net/rest/api/3/universal_avatar/view/type/project/avatar/14876",
                "24x24": "https://jiraps.atlassian.net/rest/api/3/universal_avatar/view/type/project/avatar/14876?size=small",
                "16x16": "https://jiraps.atlassian.net/rest/api/3/universal_avatar/view/type/project/avatar/14876?size=xsmall",
                "32x32": "https://jiraps.atlassian.net/rest/api/3/universal_avatar/view/type/project/avatar/14876?size=medium"
            },
            "projectCategory": {
                "self": "https://jiraps.atlassian.net/rest/api/3/projectCategory/11265",
                "id": "11265",
                "description": "",
                "name": "Flight Level 1"
            }
        },
        "assignee": {
            "self": "https://jiraps.atlassian.net/rest/api/3/user",
            "accountId": "712020:6258d302-e42f-42a3-9eda-08cbda910fa0",
            "emailAddress": "",
            "avatarUrls": {},
            "displayName": "",
            "active": True,
            "timeZone": "America/Sao_Paulo",
            "accountType": "atlassian"
        },
        "priority": {
            "self": "https://jiraps.atlassian.net/rest/api/3/priority/10002",
            "iconUrl": "https://jiraps.atlassian.net/images/icons/priorities/minor_new.svg",
            "name": "P3",
            "id": "10002"
        },
        "updated": "",
        "status": {
            "self": "https://jiraps.atlassian.net/rest/api/3/status/1",
            "description": "",
            "iconUrl": "https://jiraps.atlassian.net/images/icons/statuses/open.png",
            "name": "",
            "id": "1",
            "statusCategory": {
                "self": "https://jiraps.atlassian.net/rest/api/3/statuscategory/2",
                "id": 2,
                "key": "new",
                "colorName": "blue-gray",
                "name": "To Do"
            }
        }
    }
}

# =====================================================
# Funções
# =====================================================

def gerar_created_date():
    """
    Gera uma data aleatória entre 01/01/2026 e hoje.
    """
    intervalo = int((DATA_FINAL - DATA_INICIAL).total_seconds())

    return DATA_INICIAL + timedelta(
        seconds=random.randint(0, intervalo)
    )


def gerar_updated_date(created_date):
    """
    Gera uma data posterior ao created_date.
    Limita a no máximo DATA_FINAL.
    """
    updated = created_date + timedelta(
        minutes=random.randint(1, 43200)  # até 30 dias
    )

    return min(updated, DATA_FINAL)


# =====================================================
# Geração dos registros
# =====================================================

registros = []

for _ in range(QUANTIDADE):

    projeto = random.choice(PROJETOS)
    usuario = random.choice(USUARIOS)

    created_date = gerar_created_date()
    updated_date = gerar_updated_date(created_date)

    issue_number = random.randint(100, 9999)

    item = deepcopy(TEMPLATE)

    # Campos solicitados para variar
    item["key"] = f'{projeto["key"]}-{issue_number}'
    item["fields"]["summary"] = random.choice(SUMMARIES)

    item["fields"]["created"] = created_date.strftime(
        "%Y-%m-%dT%H:%M:%S.000-0300"
    )

    item["fields"]["project"]["id"] = projeto["id"]
    item["fields"]["project"]["key"] = projeto["key"]
    item["fields"]["project"]["name"] = projeto["name"]

    item["fields"]["assignee"]["emailAddress"] = usuario["emailAddress"]
    item["fields"]["assignee"]["displayName"] = usuario["displayName"]

    item["fields"]["updated"] = updated_date.strftime(
        "%Y-%m-%dT%H:%M:%S.000-0300"
    )

    item["fields"]["status"]["name"] = random.choice(STATUS)

    registros.append(item)

# =====================================================
# Grava arquivo (Timestamp e Pasta Upload)
# =====================================================

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
PASTA_UPLOAD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upload")
os.makedirs(PASTA_UPLOAD, exist_ok=True)

arquivo_saida = os.path.join(PASTA_UPLOAD, f"jira_mock_{TIMESTAMP}.json")

with open(arquivo_saida, "w", encoding="utf-8") as f:
    json.dump(
        registros,
        f,
        ensure_ascii=False,
        indent=2
    )

print(f"Arquivo '{arquivo_saida}' gerado com {QUANTIDADE} registros.")