from django.db import models


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class DepartmentProgressSnapshot(models.Model):
    """One row per department per day, written by the nightly rollup task.

    A rollup table rather than a cache entry. The dashboard cache in
    `selectors/dashboard.py` answers "what is true right now, cheaply"; this
    answers "what was true on that date", which a cache cannot do because it
    forgets. Nothing reads these rows yet, which is normal for a rollup: the
    history has to start accumulating before a trend report can exist.

    The unique constraint is the load-bearing part. `rollup_department_progress`
    is idempotent because of it, not because of anything in the task: re-running
    the job for a date updates the existing row instead of appending a second
    one, and two schedulers racing on the same date collide in Postgres rather
    than both succeeding. Without the constraint, `update_or_create` degrades
    into check-then-insert and the duplicates are silent.
    """

    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name="progress_snapshots"
    )
    # The date the snapshot describes, not the moment it was written. A rerun of
    # yesterday's rollup has to land on yesterday's row, so the service takes
    # this as an argument rather than reading the clock.
    captured_on = models.DateField()
    employee_count = models.PositiveIntegerField()
    completion_percentage = models.FloatField()
    activity_event_count = models.PositiveIntegerField()

    class Meta:
        ordering = ["-captured_on", "department__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["department", "captured_on"],
                name="unique_department_snapshot_per_day",
            )
        ]

    def __str__(self) -> str:
        return f"{self.department} on {self.captured_on}"
