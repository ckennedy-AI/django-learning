"""Constructs the Celery app when Django starts.

This import is not decoration. `@shared_task` does not create a task on any
particular app, it registers against whichever Celery app is current, so the
app has to exist by the time `onboarding/tasks.py` is imported. Without this
line the `web` process can still import the task symbol and call
`.apply_async()` on it, which makes the failure look like a broker or worker
problem rather than a missing import. See caveat 16 in CLAUDE.md.
"""

from config.celery import app as celery_app

__all__ = ("celery_app",)
