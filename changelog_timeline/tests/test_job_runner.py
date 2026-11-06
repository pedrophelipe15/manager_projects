"""JobRunner (kernel/jobs.py): início atômico, estado, cancelamento e robustez a falhas."""
import threading
import time

from kernel.jobs import JobRunner


def _wait(cond, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_runs_and_finishes_with_log_and_extras():
    job = JobRunner("t", extras={"done": [], "current": None})

    def work(j, n):
        j.set(current="x")
        for i in range(n):
            j.log(f"passo {i}")
            j.add("done", i)

    assert job.start(work, args=(3,)) is True
    assert _wait(lambda: not job.running)
    s = job.snapshot()
    assert s["progress"] == ["passo 0", "passo 1", "passo 2"] and s["done"] == [0, 1, 2]
    assert s["current"] == "x" and s["error"] is None and s["cancel_requested"] is False


def test_running_is_true_immediately_after_start():
    gate = threading.Event()
    job = JobRunner("t")
    job.start(lambda j: gate.wait(5))
    assert job.running  # sem esperar a thread começar (antes havia uma janela)
    gate.set()
    assert _wait(lambda: not job.running)


def test_start_is_atomic_under_concurrent_calls():
    """Muitas threads tentando iniciar ao mesmo tempo: exatamente UMA consegue."""
    gate = threading.Event()
    job = JobRunner("t")
    ran = []
    results = []
    barrier = threading.Barrier(20)

    def work(j):
        ran.append(1)
        gate.wait(5)

    def attempt():
        barrier.wait()
        results.append(job.start(work))

    ts = [threading.Thread(target=attempt) for _ in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    gate.set()
    assert _wait(lambda: not job.running)
    assert results.count(True) == 1 and results.count(False) == 19
    assert len(ran) == 1


def test_second_start_while_running_returns_false_and_does_not_reset_state():
    gate = threading.Event()
    job = JobRunner("t")
    job.start(lambda j: (j.log("a"), gate.wait(5)))
    assert _wait(lambda: job.snapshot("progress")["progress"] == ["a"])
    assert job.start(lambda j: j.log("b")) is False
    assert job.snapshot("progress")["progress"] == ["a"]
    gate.set()
    assert _wait(lambda: not job.running)


def test_unhandled_exception_is_recorded_and_job_is_not_stuck():
    job = JobRunner("t")

    def boom(j):
        j.log("antes")
        raise RuntimeError("explodiu")

    job.start(boom)
    assert _wait(lambda: not job.running)
    s = job.snapshot()
    assert s["error"] == "explodiu" and s["progress"][-1] == "ERRO: explodiu"
    assert job.start(lambda j: None) is True  # pode rodar de novo
    assert _wait(lambda: not job.running)


def test_new_run_resets_state_but_keeps_extras_defaults():
    job = JobRunner("t", extras={"completed": []})
    job.start(lambda j: (j.log("x"), j.add("completed", "A"), j.set(error="e")))
    assert _wait(lambda: not job.running)
    job.start(lambda j: None, init={"project_key": "P"})
    assert _wait(lambda: not job.running)
    s = job.snapshot()
    assert s["progress"] == [] and s["completed"] == [] and s["error"] is None and s["project_key"] == "P"


def test_cancel_is_cooperative():
    job = JobRunner("t")
    assert job.request_cancel("nada") is False  # nada rodando
    started = threading.Event()

    def work(j):
        started.set()
        while not j.cancelled:
            time.sleep(0.01)
        j.log("cancelado")

    job.start(work)
    assert started.wait(5)
    assert job.request_cancel("pedido") is True
    assert _wait(lambda: not job.running)
    assert job.snapshot("progress")["progress"] == ["pedido", "cancelado"]


def test_snapshot_returns_copies():
    job = JobRunner("t")
    job.start(lambda j: j.log("a"))
    assert _wait(lambda: not job.running)
    snap = job.snapshot("progress")
    snap["progress"].append("intruso")
    assert job.snapshot("progress")["progress"] == ["a"]
