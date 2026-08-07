from django.db import models
from django.utils import timezone

from onboarding.models.users import User


class ActivityEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activity_events")
    event_type = models.CharField(max_length=100, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            # Each of these three exists because an EXPLAIN ANALYZE plan asked for
            # it. All three lead with a filter ActivityEventListApi actually
            # accepts and end with occurred_at, the cursor field, so the planner
            # can seek to the cursor position instead of sorting to find it. See
            # `manage.py explain_queries`.
            #
            # The user-scoped feed. Measured 0.26 ms for a 20 row page.
            models.Index(fields=["user", "-occurred_at"], name="activity_user_occurred_idx"),
            # The unfiltered feed, which is the default request. Without this the
            # composite index above cannot help, since it leads with user and
            # there is no user predicate to seek on, so a 100,000 row table was
            # costing a parallel sequential scan plus a top-N sort, measured at
            # 22 ms.
            models.Index(fields=["-occurred_at"], name="activity_occurred_idx"),
            # The event_type-scoped feed. The plain db_index on event_type finds
            # the matching rows but cannot return them in cursor order, so a
            # single event type was reading 11,099 rows and sorting them to
            # return 20, measured at 15.6 ms.
            models.Index(fields=["event_type", "-occurred_at"], name="activity_type_occurred_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} ({self.user})"
