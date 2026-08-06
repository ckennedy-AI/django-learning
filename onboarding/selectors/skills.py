from django.db.models import QuerySet
from pgvector.django import CosineDistance

from onboarding.models import Skill


def skill_search(*, embedding: list[float], limit: int = 10) -> QuerySet[Skill]:
    """Nearest skills by cosine distance, closest first.

    Rows whose embedding is still null are excluded rather than ranked. A skill
    created through skill_create has no vector until its Celery task runs, and
    there is no honest distance to report for it: Postgres would sort NULL to
    one end of the ordering and the endpoint would either hide real matches
    behind unscored rows or claim a similarity it never computed.
    """
    return (
        Skill.objects.exclude(embedding__isnull=True)
        .annotate(distance=CosineDistance("embedding", embedding))
        .order_by("distance")[:limit]
    )
