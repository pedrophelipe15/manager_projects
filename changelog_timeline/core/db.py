"""Acesso ao banco principal (issues.db): caminhos e helpers de conexao."""
import os
import sqlite3

# core/ fica um nivel abaixo da raiz da aplicacao
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# MANAGER_DB_PATH permite apontar para outro banco (ex.: testes); default inalterado.
DB_PATH = os.environ.get("MANAGER_DB_PATH") or os.path.join(BASE_DIR, "issues.db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def resolve_key(conn: sqlite3.Connection, key: str) -> str:
    """Normaliza uma key possivelmente antiga (issue migrada de projeto) para a key atual.

    Issues movidas entre projetos mudam de key (ex.: STN-3065 -> BKA-6703). A
    tabela key_aliases mapeia keys antigas para a atual. Se a key não for um
    alias conhecido, é retornada inalterada.
    """
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT current_key FROM key_aliases WHERE old_key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else key
    except sqlite3.OperationalError:
        # Tabela ainda não criada (banco anterior à migração): usa a key como está.
        return key
