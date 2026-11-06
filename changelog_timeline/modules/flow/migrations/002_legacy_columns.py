"""Colunas adicionadas ao longo do tempo por ALTER TABLE (bancos legados).

Em banco novo a 001 já cria as colunas; aqui só completa bancos antigos.
"""
from kernel.migrations import add_column_if_missing


def upgrade(conn):
    add_column_if_missing(conn, "sync_history", "mode", "TEXT NOT NULL DEFAULT 'full'")
    add_column_if_missing(conn, "purge_history", "scope", "TEXT NOT NULL DEFAULT 'all'")
    add_column_if_missing(conn, "purge_history", "sample_keys", "TEXT")
