"""Caminhos da aplicação (sem dependência de nenhum módulo)."""
import os

# kernel/ fica um nível abaixo da raiz da aplicação (changelog_timeline/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Pasta dos scripts de extração do Jira e do .env com as credenciais.
# MANAGER_EXPORTER_DIR permite apontar para outra pasta (ex.: testes).
EXPORTER_DIR = os.environ.get("MANAGER_EXPORTER_DIR") or os.path.join(BASE_DIR, "exporter_jira")
