"""Atalho de linha de comando: `python ingest_to_db.py --input-dir ...`.

A implementação vive em modules/flow/ingest.py (também: `python -m modules.flow.ingest`).
Este arquivo existe só para manter o comando antigo (cron, scripts, documentação) funcionando.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.flow.ingest import *  # noqa: E402,F401,F403  (reexporta funções para quem importava)
from modules.flow.ingest import main  # noqa: E402

if __name__ == "__main__":
    main()
