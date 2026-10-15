"""Enkel bakgrundsjobbhanterare (import, modellval, synk) med förloppsrapportering."""
from __future__ import annotations

import threading
import traceback
import uuid
from typing import Any, Callable

from .core import App
from .timeutil import to_iso


class JobManager:
    def __init__(self, app: App):
        self.app = app
        self.jobs: dict[str, dict] = {}
        self.lock = threading.Lock()

    def start(self, kind: str, fn: Callable[[Callable[[str, int, int], None]], Any]) -> str:
        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "kind": kind, "status": "running", "message": "Startar…", "done": 0, "total": 1,
               "result": None, "error": None, "started_at_utc": to_iso(self.app.clock.now())}
        with self.lock:
            # bara ett jobb av samma typ åt gången
            for j in self.jobs.values():
                if j["kind"] == kind and j["status"] == "running":
                    return j["id"]
            self.jobs[jid] = job

        def progress(msg: str, done: int, total: int) -> None:
            job.update({"message": msg, "done": done, "total": max(total, 1)})

        def runner() -> None:
            try:
                job["result"] = fn(progress)
                job["status"] = "done"
                job["message"] = "Klar"
            except Exception as e:  # noqa: BLE001
                job["status"] = "error"
                job["error"] = str(e)
                job["trace"] = traceback.format_exc()[-2000:]
            job["finished_at_utc"] = to_iso(self.app.clock.now())

        threading.Thread(target=runner, name=f"job-{kind}", daemon=True).start()
        return jid

    def get(self, jid: str) -> dict | None:
        j = self.jobs.get(jid)
        return None if j is None else {k: v for k, v in j.items() if k != "trace"}

    def list(self) -> list[dict]:
        return [self.get(j) for j in list(self.jobs)][-20:]  # type: ignore[misc]
