from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.serializers import as_serializer_error
from rest_framework.views import exception_handler as drf_exception_handler

from core.exceptions import ApplicationError


def exception_handler(exc, ctx):
    """Every error response takes the shape {"message": ..., "extra": {}}.

    Django's ValidationError, Http404, and PermissionDenied are converted to
    their DRF equivalents first so DRF's own handler can process them the
    same way it processes a DRF-native exception. An ApplicationError raised
    by a service or selector is the one case DRF's handler doesn't know
    about, since it isn't a DRF exception, so it's handled separately when
    the DRF handler returns None.
    """
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(as_serializer_error(exc))

    if isinstance(exc, Http404):
        exc = exceptions.NotFound()

    if isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, ctx)

    if response is None:
        if isinstance(exc, ApplicationError):
            return Response({"message": exc.message, "extra": exc.extra}, status=400)

        return response

    if isinstance(exc.detail, (list, dict)):
        response.data = {"detail": response.data}

    if isinstance(exc, exceptions.ValidationError):
        response.data["message"] = "Validation error"
        response.data["extra"] = {"fields": response.data["detail"]}
    else:
        response.data["message"] = response.data["detail"]
        response.data["extra"] = {}

    del response.data["detail"]

    return response
