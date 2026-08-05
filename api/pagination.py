from collections import OrderedDict

from rest_framework.pagination import CursorPagination as _CursorPagination
from rest_framework.pagination import LimitOffsetPagination as _LimitOffsetPagination
from rest_framework.response import Response


class LimitOffsetPagination(_LimitOffsetPagination):
    default_limit = 10
    max_limit = 50

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("limit", self.limit),
                    ("offset", self.offset),
                    ("count", self.count),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )


class CursorPagination(_CursorPagination):
    """Base for cursor-paginated endpoints. `ordering` is left unset here.

    Cursor pagination has no notion of a total count and no OFFSET cost, which
    is why it's the right choice for deep pages on a volume table. Each
    endpoint must still set its own `ordering` to a field that is set once on
    creation, non-null, and effectively unique, since the cursor is derived
    from that field's value.
    """

    page_size = 20


def get_paginated_response(*, pagination_class, serializer_class, queryset, request, view):
    """Apply DRF pagination inside a plain APIView.

    Pagination is only automatic on generic views and viewsets. A plain
    APIView has to call into the pagination API itself, which is what this
    helper does: paginate the queryset, serialize the page, and return the
    paginator's response. If pagination doesn't apply (e.g. no page found),
    fall back to serializing the full queryset.
    """
    paginator = pagination_class()

    page = paginator.paginate_queryset(queryset, request, view=view)

    if page is not None:
        serializer = serializer_class(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = serializer_class(queryset, many=True)

    return Response(data=serializer.data)
