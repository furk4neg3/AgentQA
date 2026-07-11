from __future__ import annotations

import os
import socket
import time

from app.db.session import get_session_factory
from app.models import BatchRun
from app.services.run_service import RunService


def run_once() -> bool:
    worker_id = os.getenv("AGENTQA_WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}"
    with get_session_factory()() as db:
        batch = (
            db.query(BatchRun)
            .filter(BatchRun.status == "queued")
            .order_by(BatchRun.queued_at.asc(), BatchRun.id.asc())
            .first()
        )
        if batch is None:
            return False
        RunService(db).execute_batch(batch.id, worker_id=worker_id)
        return True


def main() -> None:
    poll_seconds = float(os.getenv("AGENTQA_WORKER_POLL_SECONDS", "1"))
    while True:
        if not run_once():
            time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
