from django.db.models import QuerySet
from pgvector.django import CosineDistance

from onboarding.models import Skill


def skill_search(*, embedding: list[float], limit: int = 10) -> QuerySet[Skill]:
    return Skill.objects.annotate(distance=CosineDistance("embedding", embedding)).order_by(
        "distance"
    )[:limit]
