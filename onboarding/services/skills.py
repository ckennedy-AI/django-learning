import uuid

from django.db import transaction

from onboarding.embeddings import embed_texts
from onboarding.models import Skill
from onboarding.tasks import generate_skill_embedding as generate_skill_embedding_task


def skill_create(*, name: str, description: str) -> tuple[Skill, str]:
    """Creates a skill and hands its embedding off to a worker.

    Returns the skill and the id of the task that will embed it, so the caller
    can report the id and later look the result up. Returning a tuple rather
    than stashing the id on the instance keeps it obvious at the call site that
    two separate things happened here: a row was written, and a message was
    queued.

    The task id is generated here instead of being read off the AsyncResult
    that apply_async returns, because that AsyncResult only exists inside the
    on_commit callback, which runs after this function has already returned.
    Pre-generating the id is what lets the enqueue stay on-commit and the
    response still name the task.
    """
    with transaction.atomic():
        skill = Skill(name=name, description=description)
        # full_clean before save, per the styleguide: it runs the field
        # validators and the unique check on `name`, and its Django
        # ValidationError is normalised to a 400 with the offending field by
        # api/exception_handlers.py. Without it, a duplicate name would surface
        # as an IntegrityError and a 500.
        skill.full_clean()
        skill.save()

        embedding_task_id = str(uuid.uuid4())

        # on_commit, not a bare .delay(). The worker is a separate process with
        # its own connection and its own view of committed state: enqueued
        # inside the transaction, it can win the race, query for a row Postgres
        # has not committed, and fail with DoesNotExist. The bug is
        # intermittent and load-dependent, which is the worst kind to chase.
        transaction.on_commit(
            lambda: generate_skill_embedding_task.apply_async(
                args=[skill.id], task_id=embedding_task_id
            )
        )

    return skill, embedding_task_id


def skill_embedding_set(*, skill_id: int) -> dict:
    """Computes and stores one skill's embedding. Called by the Celery task.

    Idempotent by construction: it recomputes from `description` and overwrites,
    so running it twice leaves the same vector on the row. That is a property of
    this particular task rather than a pattern, and it is not the deliberate
    idempotency work Phase 12 does on score_assessment_attempt, where the second
    run must avoid writing a second row.

    Skill.DoesNotExist is deliberately not caught. A missing skill here means
    either the row was deleted between enqueue and execution or the task was
    enqueued before its transaction committed, and both are things that should
    appear in the worker log and in the result backend as a FAILURE rather than
    be swallowed into a silent no-op.
    """
    skill = Skill.objects.get(id=skill_id)

    embedding = embed_texts([skill.description])[0]

    skill.embedding = embedding
    skill.save(update_fields=["embedding"])

    # The return value is stored in the result backend, so it must be
    # JSON-serializable per CELERY_RESULT_SERIALIZER. A Skill instance would
    # not be, and a vector of 384 floats is not worth keeping in Redis.
    return {"skill_id": skill.id, "dimensions": len(embedding)}
