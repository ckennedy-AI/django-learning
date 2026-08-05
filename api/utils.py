from rest_framework import serializers


def inline_serializer(*, fields: dict, data=None, **kwargs):
    """Build a one-off serializer for nesting inside an OutputSerializer.

    Used instead of importing another API's serializer, since a shared
    serializer that changes for one endpoint would break the others silently.
    """
    serializer_class = type("InlineSerializer", (serializers.Serializer,), fields)

    if data is not None:
        return serializer_class(data=data, **kwargs)

    return serializer_class(**kwargs)
