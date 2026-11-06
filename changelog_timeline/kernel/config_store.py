"""ConfigStore: acesso seguro ao projects.yaml, compartilhado entre módulos.

Resolve o risco de "um módulo sobrescrever a config do outro":
  - leitura-modificação-escrita sempre sob LOCK (threads do processo + arquivo .lock
    entre processos), sempre relendo o arquivo dentro do lock;
  - escrita ATÔMICA (arquivo temporário + os.replace) com cópia .bak da versão anterior;
  - SEÇÕES: cada módulo só enxerga e grava as chaves que possui (`owns`); as chaves dos
    outros módulos (e as desconhecidas) são preservadas por construção;
  - arquivo inválido NUNCA é sobrescrito (ConfigError) e só grava se algo mudou.

O formato do arquivo não muda (retrocompatível). Limitação conhecida: comentários YAML
não são preservados na escrita (já era assim antes).
"""
from __future__ import annotations

import copy
import os
import shutil
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Optional

import yaml

LOCK_TIMEOUT_S = 10.0
LOCK_STALE_S = 60.0


class ConfigError(Exception):
    pass


def default_path() -> str:
    from core.db import BASE_DIR
    return os.environ.get("MANAGER_PROJECTS_YAML") or os.path.join(BASE_DIR, "projects.yaml")


def _retry_perm(fn, attempts: int = 25, delay: float = 0.02):
    """Windows: os.replace/copy podem falhar transitoriamente com PermissionError
    (antivírus, indexador, leitor concorrente). Tenta de novo antes de desistir."""
    for i in range(attempts):
        try:
            return fn()
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay * (1 + i // 5))


_stores: dict[str, "ConfigStore"] = {}
_stores_guard = threading.Lock()


def get_store(path: Optional[str] = None) -> "ConfigStore":
    """Uma instância por arquivo (compartilha o lock entre todos os usuários do processo)."""
    p = os.path.abspath(path or default_path())
    with _stores_guard:
        if p not in _stores:
            _stores[p] = ConfigStore(p)
        return _stores[p]


class ConfigStore:
    def __init__(self, path: str):
        self.path = path
        self._tlock = threading.RLock()

    # ------------------------------------------------------------------ lock
    @contextmanager
    def _lock(self):
        with self._tlock:
            lock_path = self.path + ".lock"
            deadline = time.monotonic() + LOCK_TIMEOUT_S
            fd = None
            while fd is None:
                try:
                    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except (FileExistsError, PermissionError):
                    # Windows: criar o lock enquanto outro processo o apaga dá PermissionError
                    try:  # lock órfão (processo morreu): remove se velho
                        if time.time() - os.path.getmtime(lock_path) > LOCK_STALE_S:
                            os.remove(lock_path)
                            continue
                    except OSError:
                        pass
                    if time.monotonic() > deadline:
                        raise ConfigError(f"timeout aguardando lock de {self.path}")
                    time.sleep(0.02)
            try:
                os.write(fd, str(os.getpid()).encode())
                yield
            finally:
                os.close(fd)
                try:
                    os.remove(lock_path)
                except OSError:
                    pass

    # ------------------------------------------------------------------ leitura
    def read(self) -> dict:
        """Retorna o conteúdo atual (dict vazio se o arquivo não existe)."""
        if not os.path.exists(self.path):
            return {}
        last: Exception | None = None
        for _ in range(5):  # Windows: leitura pode colidir com os.replace de outro processo
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                break
            except PermissionError as exc:
                last = exc
                time.sleep(0.02)
            except yaml.YAMLError as exc:
                raise ConfigError(f"{self.path}: YAML inválido ({exc})") from exc
        else:
            raise ConfigError(f"{self.path}: não foi possível ler ({last})")
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ConfigError(f"{self.path}: o topo do arquivo deve ser um mapeamento")
        return data

    def get(self, key: str, default: Any = None) -> Any:
        val = self.read().get(key, default)
        return default if val is None else val

    # ------------------------------------------------------------------ escrita
    def update(self, mutator: Callable[[dict], Any]) -> Any:
        """Lock -> relê -> mutator(data) -> grava (atômico) se mudou. Retorna o que o mutator retornar.

        Se o mutator levantar exceção, NADA é gravado.
        """
        with self._lock():
            data = self.read()
            before = copy.deepcopy(data)
            result = mutator(data)
            if data != before:
                self._write(data)
            return result

    def set(self, key: str, value: Any) -> None:
        self.update(lambda d: d.__setitem__(key, value))

    def _write(self, data: dict) -> None:
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        tmp = f"{self.path}.tmp-{os.getpid()}-{threading.get_ident()}"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
                f.flush()
                os.fsync(f.fileno())
            if os.path.exists(self.path):
                _retry_perm(lambda: shutil.copy2(self.path, self.path + ".bak"))
            _retry_perm(lambda: os.replace(tmp, self.path))
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    # ------------------------------------------------------------------ seções
    def section(self, name: str, owns: Iterable[str]) -> "Section":
        return Section(self, name, tuple(owns))


class Section:
    """Visão de um módulo sobre o arquivo: só as chaves que ele possui."""

    def __init__(self, store: ConfigStore, name: str, owns: tuple[str, ...]):
        self.store, self.name, self.owns = store, name, owns

    def _check(self, key: str) -> None:
        if key not in self.owns:
            raise ConfigError(f"seção '{self.name}' não possui a chave '{key}' (possui: {self.owns})")

    def get(self, key: str, default: Any = None) -> Any:
        self._check(key)
        return self.store.get(key, default)

    def update(self, mutator: Callable[[dict], Any]) -> Any:
        """mutator recebe um dict SÓ com as chaves da seção; o resto do arquivo é preservado."""
        def _m(data: dict):
            sub = {k: data[k] for k in self.owns if k in data}
            result = mutator(sub)
            extra = set(sub) - set(self.owns)
            if extra:
                raise ConfigError(f"seção '{self.name}' tentou gravar chaves que não possui: {sorted(extra)}")
            for k, v in sub.items():
                data[k] = v
            return result
        return self.store.update(_m)
