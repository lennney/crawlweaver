"""Task Queue — concurrent job execution with backpressure.

Factor #8: Own your control flow. No Celery, no Redis.
Just threading.Semaphore + a dict of jobs.
"""
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("crawler.queue")


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    url: str
    keyword: str
    source: str
    content_type: str = "Beginner Guide"
    status: JobStatus = JobStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Any = None
    error: str = ""


class TaskQueue:
    """Simple concurrent task queue with semaphore-based backpressure.

    Usage:
        tq = TaskQueue(max_workers=2)
        tq.set_handler(my_crawl_function)  # handler(job: Job)
        job_id = tq.submit(url="...", keyword="...", source="youtube")
    """

    def __init__(self, max_workers: int = 2):
        self.max_workers = max_workers
        self._semaphore = threading.Semaphore(max_workers)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._handler: Optional[Callable[[Job], None]] = None

    def set_handler(self, handler: Callable[[Job], None]):
        """Set the function that processes each job."""
        self._handler = handler

    def submit(self, url: str, keyword: str, source: str = "youtube",
               content_type: str = "Beginner Guide") -> str:
        """Submit a job. Returns job ID."""
        job_id = uuid.uuid4().hex[:12]
        job = Job(
            id=job_id, url=url, keyword=keyword,
            source=source, content_type=content_type,
        )
        with self._lock:
            self._jobs[job_id] = job

        t = threading.Thread(target=self._run, args=(job,), daemon=True)
        t.start()

        logger.info(f"Job submitted: {job_id} ({keyword})")
        return job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 50) -> list[Job]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return jobs[:limit]

    def stats(self) -> dict:
        """Return queue statistics."""
        with self._lock:
            counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
            for j in self._jobs.values():
                counts[j.status.value] = counts.get(j.status.value, 0) + 1
            return counts

    def _run(self, job: Job):
        """Worker thread: wait for semaphore, run handler."""
        self._semaphore.acquire()
        try:
            with self._lock:
                job.status = JobStatus.RUNNING
                job.started_at = time.time()

            if self._handler:
                self._handler(job)

            with self._lock:
                job.status = JobStatus.COMPLETED
                job.finished_at = time.time()
            logger.info(f"Job completed: {job.id} ({job.keyword})")

        except Exception as e:
            with self._lock:
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.finished_at = time.time()
            logger.error(f"Job failed: {job.id} — {e}")

        finally:
            self._semaphore.release()
