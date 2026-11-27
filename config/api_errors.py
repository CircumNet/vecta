import logging
import uuid

from rest_framework.response import Response
from rest_framework.views import exception_handler

log = logging.getLogger("vecta.api")


def handler(exc, context):
    """
    DRF's own errors (validation, permissions...) pass through untouched. Anything unexpected becomes a
    readable JSON 500 with a short reference that is also written to the server log, so the person sees
    something useful instead of an HTML error page and the administrator can find the traceback.
    """
    response = exception_handler(exc, context)
    if response is not None:
        return response
    ref = uuid.uuid4().hex[:8]
    request = context.get("request")
    log.error("Unhandled error ref=%s %s %s", ref, getattr(request, "method", "?"), getattr(request, "path", "?"), exc_info=exc)
    return Response(
        {"detail": f"Something went wrong on our side (ref {ref}). Please try again. If it keeps happening, give this reference to your administrator.", "ref": ref},
        status=500,
    )
