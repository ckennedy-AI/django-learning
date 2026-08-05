import time

from django.core.management.base import BaseCommand

from onboarding.models import ModuleAssignment
from onboarding.selectors import user_dashboard_cache_invalidate, user_dashboard_get


class Command(BaseCommand):
    help = "Time user_dashboard_get on a cold cache versus a warm cache."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, default=None)

    def handle(self, *args, **options):
        user_id = options["user_id"]

        if user_id is None:
            user_id = ModuleAssignment.objects.values_list("user_id", flat=True).first()

        if user_id is None:
            self.stdout.write(self.style.ERROR("No ModuleAssignment rows. Run seed_data first."))
            return

        user_dashboard_cache_invalidate(user_id=user_id)

        start = time.perf_counter()
        user_dashboard_get(user_id=user_id)
        cold_duration = time.perf_counter() - start

        start = time.perf_counter()
        user_dashboard_get(user_id=user_id)
        warm_duration = time.perf_counter() - start

        self.stdout.write(f"user_id: {user_id}")
        self.stdout.write(
            self.style.SUCCESS(f"Cold cache (2 queries): {cold_duration * 1000:.2f} ms")
        )
        self.stdout.write(
            self.style.SUCCESS(f"Warm cache (0 queries): {warm_duration * 1000:.2f} ms")
        )

        if warm_duration > 0:
            self.stdout.write(f"Speedup: {cold_duration / warm_duration:.1f}x")
