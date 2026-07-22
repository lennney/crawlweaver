"""Tests for task queue — concurrency control and job tracking."""

import threading
import time

from task_queue import JobStatus, TaskQueue


def test_job_status_enum():
    """Job should have pending/running/completed/failed states."""
    assert JobStatus.PENDING == "pending"
    assert JobStatus.RUNNING == "running"
    assert JobStatus.COMPLETED == "completed"
    assert JobStatus.FAILED == "failed"


def test_submit_job():
    """Submitting a job should return a job ID and store it."""
    tq = TaskQueue(max_workers=1)
    job_id = tq.submit(url="https://example.com", keyword="test", source="web")
    assert isinstance(job_id, str)
    assert len(job_id) > 0
    job = tq.get_job(job_id)
    assert job.url == "https://example.com"
    assert job.keyword == "test"
    # Job may have already completed by the time we check (no-op handler)
    assert job.status in (JobStatus.PENDING, JobStatus.COMPLETED)


def test_list_jobs():
    """Should list all jobs sorted by creation time."""
    tq = TaskQueue(max_workers=1)
    tq.submit(url="https://a.com", keyword="a", source="web")
    tq.submit(url="https://b.com", keyword="b", source="web")
    jobs = tq.list_jobs()
    assert len(jobs) == 2


def test_max_workers_limits_concurrency():
    """Should not run more than max_workers jobs simultaneously."""
    tq = TaskQueue(max_workers=1)
    running = []
    max_concurrent = []
    lock = threading.Lock()

    def slow_task(job):
        with lock:
            running.append(job.id)
            max_concurrent.append(len(running))
        time.sleep(0.2)
        with lock:
            running.remove(job.id)

    tq.set_handler(slow_task)
    tq.submit(url="https://a.com", keyword="a", source="web")
    tq.submit(url="https://b.com", keyword="b", source="web")
    time.sleep(0.5)

    assert max(max_concurrent) <= 1


def test_job_completed_status():
    """After handler runs, job should be completed."""
    tq = TaskQueue(max_workers=1)

    def handler(job):
        job.result = {"score": 85}

    tq.set_handler(handler)
    job_id = tq.submit(url="https://a.com", keyword="a", source="web")
    time.sleep(0.5)

    job = tq.get_job(job_id)
    assert job.status == JobStatus.COMPLETED
    assert job.result == {"score": 85}


def test_job_failed_status():
    """If handler raises, job should be failed with error."""
    tq = TaskQueue(max_workers=1)

    def bad_handler(job):
        raise RuntimeError("LLM exploded")

    tq.set_handler(bad_handler)
    job_id = tq.submit(url="https://a.com", keyword="a", source="web")
    time.sleep(0.5)

    job = tq.get_job(job_id)
    assert job.status == JobStatus.FAILED
    assert "LLM exploded" in job.error
