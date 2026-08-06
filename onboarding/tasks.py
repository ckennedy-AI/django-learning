"""Celery tasks, and nothing else.

Every task in here is thin on purpose: it receives an ID, calls a service, and
returns whatever that service returned. Business logic lives in the service so
it is reachable from a test, a shell, or a management command without a broker
in the picture, and so the only difference between running work in-process and
running it on a worker is which of the two calls it.

A task runs outside the request cycle. There is no `request.user`, no
permission class, and no way to ask who triggered it. Authorization was decided
before the enqueue: `generate_skill_embedding` only ever runs because
`SkillCreateApi` let a staff caller through, or because `SkillAdmin` did.

Services import their task with a `_task` suffix at module level; tasks import
their service inside the function body. That asymmetry is what breaks the
import cycle, since `onboarding.services` imports `onboarding.tasks` at import
time and the reverse would deadlock at first import.
"""

from celery import shared_task


@shared_task
def generate_skill_embedding(skill_id: int) -> dict:
    """Embeds one skill's description.

    @shared_task rather than @app.task so this module never imports the Celery
    app: the task binds to whichever app is current, which is the one
    config/__init__.py constructed at Django startup.

    The argument is an ID, not a Skill. Two distinct reasons: the row may have
    changed between enqueue and execution, so the worker should read current
    state rather than a snapshot, and CELERY_TASK_SERIALIZER is json, which
    cannot represent a model instance at all.
    """
    from onboarding.services import skill_embedding_set

    return skill_embedding_set(skill_id=skill_id)
