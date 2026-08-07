import time

from celery.result import AsyncResult
from django.core.management.base import BaseCommand
from django.db import transaction

from onboarding.models import Skill
from onboarding.services import skill_create


class Command(BaseCommand):
    help = (
        "Create a skill, then poll the Celery result backend until its embedding "
        "task finishes. Requires a running celery-worker."
    )

    def add_arguments(self, parser):
        parser.add_argument("--name", default="Celery result demo")
        parser.add_argument(
            "--description",
            default="A throwaway skill created to watch a Celery task run end to end.",
        )
        parser.add_argument("--timeout", type=float, default=60.0)
        parser.add_argument(
            "--keep",
            action="store_true",
            help="Leave the created skill in the database instead of deleting it.",
        )

    def handle(self, *args, **options):
        name = options["name"]

        # A management command runs outside any request, and nothing wraps it in
        # a transaction by default, so the on_commit callback inside
        # skill_create fires as soon as its own atomic block exits. The explicit
        # atomic block here is not needed; it is written to make the ordering
        # visible, since the enqueue happening after commit is the whole point of
        # the phase.
        Skill.objects.filter(name=name).delete()

        with transaction.atomic():
            skill, task_id = skill_create(name=name, description=options["description"])

        self.stdout.write(f"Skill created: id={skill.id} name={skill.name!r}")
        self.stdout.write(f"Embedding at create time: {skill.embedding}")
        self.stdout.write(f"Task id: {task_id}")
        self.stdout.write("")

        result = AsyncResult(task_id)
        deadline = time.monotonic() + options["timeout"]
        last_state = None

        while time.monotonic() < deadline:
            # PENDING is Celery's answer for "no state is stored under this id",
            # which covers both "queued" and "this id was never a task", so it
            # is not proof the message arrived. STARTED only appears because
            # CELERY_TASK_TRACK_STARTED is on.
            state = result.state
            if state != last_state:
                self.stdout.write(f"  state: {state}")
                last_state = state

            if result.ready():
                break

            time.sleep(0.25)

        if not result.ready():
            self.stdout.write(
                self.style.ERROR(
                    f"Task did not finish within {options['timeout']:.0f}s. Is celery-worker up? "
                    "Check `docker compose logs -f celery-worker`."
                )
            )
            return

        if result.failed():
            self.stdout.write(self.style.ERROR(f"Task failed: {result.result!r}"))
            return

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Result from the backend: {result.result}"))

        skill.refresh_from_db()
        embedded = skill.embedding is not None
        self.stdout.write(
            self.style.SUCCESS(f"Embedding stored on the row: {embedded}")
            if embedded
            else self.style.ERROR("Embedding is still null on the row.")
        )

        if not options["keep"]:
            skill.delete()
            self.stdout.write("Created skill deleted. Pass --keep to retain it.")
