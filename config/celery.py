"""The Celery application object.

https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html

Celery has supported Django natively since 3.1, so there is no bridge library
here. Three things happen in this module and nothing else:

1. `DJANGO_SETTINGS_MODULE` is set. A worker is not started through
   `manage.py`, so nothing else in the process would have set it.
2. Configuration is read from Django settings under the `CELERY` namespace,
   so `CELERY_BROKER_URL` in `config/settings.py` becomes Celery's
   `broker_url`. One settings file, one place environment variables are read.
3. `autodiscover_tasks()` imports `tasks.py` from every app in
   `INSTALLED_APPS`. Without it the worker starts cleanly, reports an empty
   task list, and rejects every message the web process sends with
   `NotRegistered`.

The app is imported in `config/__init__.py` so it is constructed during Django
startup. See caveat 16 in CLAUDE.md for why that import is load-bearing.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")

# namespace="CELERY" means only settings prefixed CELERY_ are read, and the
# prefix is stripped: CELERY_TASK_SERIALIZER configures task_serializer.
app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()
