import queue
import threading
import time
import uuid
import sys
import os
from collections import deque
from pathlib import Path
from typing import Optional


class CancelledError(Exception):
    pass


_TLS = threading.local()


def check_cancelled():
    ev = getattr(_TLS, "cancel_event", None)
    if ev is not None and ev.is_set():
        raise CancelledError("Job cancelled")


def get_cancel_event():
    return getattr(_TLS, "cancel_event", None)


def capture_job_context():
    return {
        "job_id": getattr(_TLS, "job_id", None),
        "cancel_event": getattr(_TLS, "cancel_event", None),
        "log_file": getattr(_TLS, "log_file", None),
    }


def run_in_job_context(ctx, fn, *args, **kwargs):
    prev_job_id = getattr(_TLS, "job_id", None)
    prev_cancel_event = getattr(_TLS, "cancel_event", None)
    prev_log_file = getattr(_TLS, "log_file", None)
    try:
        _TLS.job_id = (ctx or {}).get("job_id")
        _TLS.cancel_event = (ctx or {}).get("cancel_event")
        _TLS.log_file = (ctx or {}).get("log_file")
        return fn(*args, **kwargs)
    finally:
        _TLS.job_id = prev_job_id
        _TLS.cancel_event = prev_cancel_event
        _TLS.log_file = prev_log_file


class JobQueue:
    def __init__(self, lanes=None, lane_workers=None, log_dir: Optional[str] = None):
        if lanes is None:
            lanes = ["default"]
        lanes = [str(x).strip() for x in lanes if str(x).strip()]
        if not lanes:
            lanes = ["default"]

        self._lanes = lanes
        self._queues = {lane: queue.Queue() for lane in lanes}
        self._lane_workers = {}
        if isinstance(lane_workers, dict):
            for k, v in lane_workers.items():
                kk = str(k).strip()
                if not kk:
                    continue
                try:
                    n = int(v)
                except Exception:
                    n = 1
                if n < 1:
                    n = 1
                self._lane_workers[kk] = n
        self._lock = threading.Lock()
        self._jobs = {}
        self._order = []
        self._stop = threading.Event()
        self._threads = {}
        self._log_limit = 200000
        self._logs = {}
        self._log_counts = {}
        self._cancel_events = {}
        self._log_paths = {}
        self._log_bytes = {}
        self._log_write_locks = {}
        self._log_dir = Path(log_dir or "job_logs")
        self._router_installed = False
        self._orig_stdout = None
        self._orig_stderr = None
        self._stdout_lock = threading.Lock()
        self._stderr_lock = threading.Lock()

    def start(self):
        if any(t and t.is_alive() for t in self._threads.values()):
            return
        self._stop.clear()
        self._install_router()
        for lane in self._lanes:
            n = int(self._lane_workers.get(lane, 1) or 1)
            if n < 1:
                n = 1
            for i in range(n):
                name = f"job-worker-{lane}-{i}"
                t = threading.Thread(target=self._worker, args=(lane,), name=name, daemon=True)
                self._threads[name] = t
                t.start()

    def stop(self):
        self._stop.set()
        for lane, q in self._queues.items():
            n = int(self._lane_workers.get(lane, 1) or 1)
            if n < 1:
                n = 1
            try:
                for _ in range(n):
                    q.put_nowait(None)
            except Exception:
                pass

    def enqueue(self, mode, sku, stem, options, runner, prompt=None, lane="default", job_id: Optional[str] = None):
        lane = str(lane or "").strip() or "default"
        if lane not in self._queues:
            lane = self._lanes[0]
        job_id = job_id or uuid.uuid4().hex
        cancel_event = threading.Event()
        prompt = None if prompt is None else str(prompt)
        job = {
            "id": job_id,
            "mode": mode,
            "sku": sku,
            "stem": stem,
            "lane": lane,
            "prompt": prompt,
            "options": options or {},
            "status": "queued",
            "cancel_requested": False,
            "created_at": time.time(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
            "log_available": True,
            "log_truncated": False,
            "log_path": None,
            "log_bytes": 0,
        }
        with self._lock:
            self._jobs[job_id] = job
            self._order.append(job_id)
            self._logs[job_id] = deque()
            self._log_counts[job_id] = 0
            self._cancel_events[job_id] = cancel_event
            self._log_paths[job_id] = None
            self._log_bytes[job_id] = 0
            self._log_write_locks[job_id] = threading.Lock()
        self._queues[lane].put((job_id, runner))
        return job_id

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def get_log(self, job_id):
        with self._lock:
            if job_id not in self._logs:
                return None
            p = self._log_paths.get(job_id)
            if p:
                try:
                    path = Path(p)
                    if path.exists() and path.is_file():
                        data = path.read_bytes()
                        return data.decode("utf-8", errors="replace")
                except Exception:
                    pass
            return "".join(self._logs[job_id])

    def get_log_chunk(self, job_id, *, from_bytes=None, tail_bytes=None):
        with self._lock:
            if job_id not in self._logs:
                return None
            p = self._log_paths.get(job_id)
            total = int(self._log_bytes.get(job_id, 0) or 0)
        if p:
            try:
                path = Path(p)
                if path.exists() and path.is_file():
                    size = path.stat().st_size
                    total = size
                    if from_bytes is not None and from_bytes >= 0:
                        start = min(from_bytes, size)
                    elif tail_bytes is not None and tail_bytes > 0:
                        start = max(0, size - int(tail_bytes))
                    else:
                        start = 0
                    with open(path, "rb") as f:
                        if start:
                            f.seek(start, os.SEEK_SET)
                        b = f.read()
                    return {
                        "log": b.decode("utf-8", errors="replace"),
                        "from": start,
                        "to": start + len(b),
                        "total": total,
                        "log_path": str(path),
                    }
            except Exception:
                pass
        txt = self.get_log(job_id)
        if txt is None:
            return None
        if isinstance(tail_bytes, int) and tail_bytes > 0 and len(txt) > tail_bytes:
            txt = txt[-tail_bytes:]
        return {"log": txt, "from": 0, "to": len(txt), "total": len(txt), "log_path": None}

    def cancel(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False, "not found"
            status = job.get("status")
            if status in {"success", "failed", "cancelled"}:
                return True, status
            job["cancel_requested"] = True
            ev = self._cancel_events.get(job_id)
            if ev is not None:
                ev.set()
            if status == "queued":
                job["status"] = "cancelled"
                job["finished_at"] = time.time()
                job["error"] = None
            return True, "ok"

    def snapshot(self, recent_limit=50):
        with self._lock:
            ordered = list(self._order)[-recent_limit:]
            jobs = [dict(self._jobs[jid]) for jid in ordered if jid in self._jobs]
        running_jobs = [j for j in reversed(jobs) if j["status"] == "running"]
        running = running_jobs[0] if running_jobs else None
        queued = [j for j in jobs if j["status"] == "queued"]
        return {
            "running": running,
            "running_jobs": list(reversed(running_jobs)),
            "queued_count": len(queued),
            "jobs": jobs,
        }

    def _append_log(self, job_id, text):
        if not text:
            return
        with self._lock:
            if job_id not in self._logs:
                return
            dq = self._logs[job_id]
            dq.append(text)
            self._log_counts[job_id] += len(text)
            truncated = False
            while self._log_counts[job_id] > self._log_limit and dq:
                removed = dq.popleft()
                self._log_counts[job_id] -= len(removed)
                truncated = True
            _ = truncated

    def _install_router(self):
        if self._router_installed:
            return
        self._router_installed = True
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        parent = self

        class RouterStream:
            def __init__(self, original_stream, lock):
                self._original = original_stream
                self._lock = lock

            def write(self, s):
                if not s:
                    return 0
                job_id = getattr(_TLS, "job_id", None)
                log_file = getattr(_TLS, "log_file", None)
                job_lock = None
                if job_id and log_file is not None:
                    try:
                        job_lock = parent._log_write_locks.get(job_id)
                    except Exception:
                        job_lock = None
                try:
                    if self._lock:
                        self._lock.acquire()
                    if job_lock:
                        job_lock.acquire()
                    try:
                        if job_id and log_file is not None:
                            try:
                                b = s.encode("utf-8", errors="replace")
                                log_file.write(b)
                                try:
                                    log_file.flush()
                                except Exception:
                                    pass
                                with parent._lock:
                                    parent._log_bytes[job_id] = int(parent._log_bytes.get(job_id, 0) or 0) + len(b)
                            except Exception:
                                pass
                            parent._append_log(job_id, s)
                        try:
                            self._original.write(s)
                        except Exception:
                            pass
                    finally:
                        if job_lock:
                            try:
                                job_lock.release()
                            except Exception:
                                pass
                finally:
                    if self._lock:
                        try:
                            self._lock.release()
                        except Exception:
                            pass
                return len(s)

            def flush(self):
                job_id = getattr(_TLS, "job_id", None)
                log_file = getattr(_TLS, "log_file", None)
                if job_id and log_file is not None:
                    try:
                        log_file.flush()
                    except Exception:
                        pass
                try:
                    self._original.flush()
                except Exception:
                    pass

            def isatty(self):
                try:
                    return self._original.isatty()
                except Exception:
                    return False

        sys.stdout = RouterStream(self._orig_stdout, self._stdout_lock)
        sys.stderr = RouterStream(self._orig_stderr, self._stderr_lock)

    def _worker(self, lane):
        while not self._stop.is_set():
            item = self._queues[lane].get()
            if item is None:
                continue
            job_id, runner = item
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    continue
                if job.get("status") == "cancelled":
                    continue
                job["status"] = "running"
                job["started_at"] = time.time()
                job["error"] = None
                job["result"] = None
            try:
                _TLS.job_id = job_id
                _TLS.cancel_event = self._cancel_events.get(job_id)
                _TLS.log_file = None
                log_file = None
                try:
                    self._log_dir.mkdir(parents=True, exist_ok=True)
                    log_path = (self._log_dir / f"{job_id}.log").resolve()
                    log_file = open(log_path, "ab")
                    with self._lock:
                        self._log_paths[job_id] = str(log_path)
                        job = self._jobs.get(job_id)
                        if job is not None:
                            job["log_path"] = str(log_path)
                            job["log_bytes"] = int(self._log_bytes.get(job_id, 0) or 0)
                except Exception:
                    log_file = None
                _TLS.log_file = log_file
                result = runner()
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job:
                        job["status"] = "success"
                        job["result"] = result
                        job["finished_at"] = time.time()
                        job["log_path"] = self._log_paths.get(job_id)
                        job["log_bytes"] = int(self._log_bytes.get(job_id, 0) or 0)
            except CancelledError as e:
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job:
                        job["status"] = "cancelled"
                        job["error"] = str(e)
                        job["finished_at"] = time.time()
                        job["log_path"] = self._log_paths.get(job_id)
                        job["log_bytes"] = int(self._log_bytes.get(job_id, 0) or 0)
            except Exception as e:
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job:
                        job["status"] = "failed"
                        job["error"] = str(e)
                        job["finished_at"] = time.time()
                        job["log_path"] = self._log_paths.get(job_id)
                        job["log_bytes"] = int(self._log_bytes.get(job_id, 0) or 0)
            finally:
                _TLS.job_id = None
                _TLS.cancel_event = None
                _TLS.log_file = None
                try:
                    if log_file is not None:
                        log_file.close()
                except Exception:
                    pass
