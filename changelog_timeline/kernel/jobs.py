"""JobRunner: execução em background de um job por vez, com estado, log e cancelamento.

Substitui o padrão copiado em 3 lugares (sync do flow, recálculo Wave 1, sync da hierarquia):
`dict de estado + threading.Lock + thread` montados à mão. Garantias que o padrão antigo
não dava:
  - início ATÔMICO: dois POSTs simultâneos não iniciam dois jobs (antes: checava `running`,
    soltava o lock e só a thread marcava running => janela de corrida);
  - `running` fica True já na resposta do POST (antes só quando a thread começava);
  - exceção inesperada no job NÃO deixa o job "rodando" para sempre: o erro é registrado
    no log/estado e `running` volta a False (antes só reiniciando o servidor);
  - API única de log/estado/cancelamento, para todo módulo novo reutilizar.

Uso:
    job = JobRunner("sync", extras={"current_project": None, "completed": []})
    def work(job, keys):            # o job recebe o próprio runner como 1º argumento
        job.log("começou"); ...
        if job.cancelled: return
    if not job.start(work, args=(keys,)):   # False => já está rodando (responda 409)
        ...
    job.snapshot("running", "progress")     # cópia segura do estado para o endpoint de status
"""
from __future__ import annotations

import copy
import threading
from typing import Any, Callable, Iterable, Optional


class JobRunner:
    def __init__(self, name: str, extras: Optional[dict] = None):
        self.name = name
        self._extras = copy.deepcopy(extras or {})
        self._lock = threading.RLock()
        self._state: dict[str, Any] = {}
        self._reset({})

    # ------------------------------------------------------------------ estado
    def _reset(self, init: dict) -> None:
        self._state = {
            "running": False,
            "progress": [],
            "error": None,
            "cancel_requested": False,
            **copy.deepcopy(self._extras),
            **copy.deepcopy(init),
        }

    @property
    def running(self) -> bool:
        with self._lock:
            return bool(self._state["running"])

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return bool(self._state["cancel_requested"])

    def log(self, message: str) -> None:
        with self._lock:
            self._state["progress"].append(message)

    def set(self, **values: Any) -> None:
        with self._lock:
            self._state.update(values)

    def add(self, key: str, value: Any) -> None:
        """Acrescenta a uma lista do estado (ex.: projetos concluídos)."""
        with self._lock:
            self._state[key].append(value)

    def snapshot(self, *keys: str) -> dict:
        """Cópia do estado (listas copiadas). Sem argumentos: tudo."""
        with self._lock:
            src = {k: self._state[k] for k in keys} if keys else self._state
            return copy.deepcopy(src)

    # ------------------------------------------------------------------ ciclo de vida
    def start(self, fn: Callable[..., Any], args: Iterable = (), init: Optional[dict] = None) -> bool:
        """Inicia `fn(job, *args)` em thread daemon. Retorna False se já há um job rodando."""
        with self._lock:
            if self._state["running"]:
                return False
            self._reset(init or {})
            self._state["running"] = True
        thread = threading.Thread(target=self._run, args=(fn, tuple(args)), daemon=True,
                                  name=f"job-{self.name}")
        thread.start()
        return True

    def _run(self, fn: Callable[..., Any], args: tuple) -> None:
        try:
            fn(self, *args)
        except Exception as exc:  # noqa: BLE001 — o job nunca pode ficar preso em "running"
            with self._lock:
                self._state["progress"].append(f"ERRO: {str(exc)[:300]}")
                self._state["error"] = str(exc)[:200]
        finally:
            with self._lock:
                self._state["running"] = False

    def request_cancel(self, message: Optional[str] = None) -> bool:
        """Pede cancelamento cooperativo (o job consulta `job.cancelled`). False se não há job."""
        with self._lock:
            if not self._state["running"]:
                return False
            self._state["cancel_requested"] = True
            if message:
                self._state["progress"].append(message)
            return True
