import time
from urllib.parse import parse_qs, urlparse

from django.core.management.base import BaseCommand
from django.test import RequestFactory, override_settings
from rest_framework.pagination import Cursor, PageNumberPagination
from rest_framework.request import Request

from api.pagination import CursorPagination
from onboarding.models import ActivityEvent


class _DeepPageNumberPagination(PageNumberPagination):
    page_size = 20


class _ActivityEventCursorPagination(CursorPagination):
    ordering = "id"
    page_size = 20


class Command(BaseCommand):
    help = (
        "Time DRF's PageNumberPagination (OFFSET) against this project's "
        "CursorPagination (WHERE-based seek) on a deep page of ActivityEvent."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--depth",
            type=float,
            default=0.99,
            help="Fraction of the table to page into, e.g. 0.99 means 99%% of the way through.",
        )

    def handle(self, *args, **options):
        total = ActivityEvent.objects.count()
        page_size = 20

        if total < page_size * 3:
            self.stdout.write(self.style.ERROR("Not enough rows. Run seed_data first."))
            return

        deep_offset = int(total * options["depth"])
        factory = RequestFactory()
        queryset = ActivityEvent.objects.all()

        # Building a request with RequestFactory defaults to HTTP_HOST=testserver,
        # which paginate_queryset rejects unless it's an allowed host. Only
        # affects this benchmark's fake requests, not real traffic.
        with override_settings(ALLOWED_HOSTS=["testserver"]):
            # PageNumberPagination jumps straight to the deep page in one request.
            # Under the hood this is an OFFSET query: the database still has to
            # walk past every skipped row before it can return this page.
            deep_page_number = (deep_offset // page_size) + 1
            page_paginator = _DeepPageNumberPagination()
            page_request = Request(factory.get("/", {"page": deep_page_number}))

            start = time.perf_counter()
            page_paginator.paginate_queryset(queryset, page_request)
            offset_duration = time.perf_counter() - start

            # CursorPagination never receives an offset from the client, only an
            # opaque cursor encoding the ordering field's value at the last row it
            # saw. In real use a client gets this by clicking "next" repeatedly, it
            # is never computed from scratch. Building one directly here simulates
            # a client that already holds it, which is the only way cursor
            # pagination is ever actually used.
            target_id = ActivityEvent.objects.order_by("id").values_list("id", flat=True)[
                deep_offset
            ]
            cursor_paginator = _ActivityEventCursorPagination()
            cursor_paginator.base_url = "http://testserver/"
            cursor = Cursor(offset=0, reverse=False, position=str(target_id))
            encoded_url = cursor_paginator.encode_cursor(cursor)
            cursor_param = parse_qs(urlparse(encoded_url).query)["cursor"][0]
            cursor_request = Request(factory.get("/", {"cursor": cursor_param}))

            start = time.perf_counter()
            cursor_paginator.paginate_queryset(queryset, cursor_request)
            cursor_duration = time.perf_counter() - start

        self.stdout.write(f"Total ActivityEvent rows: {total}")
        self.stdout.write(f"Deep offset: {deep_offset} ({options['depth']:.0%} through the table)")
        self.stdout.write(
            self.style.SUCCESS(
                f"PageNumberPagination, page {deep_page_number} (OFFSET {deep_offset}): "
                f"{offset_duration * 1000:.2f} ms"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"CursorPagination, cursor at id={target_id} (WHERE seek): "
                f"{cursor_duration * 1000:.2f} ms"
            )
        )
