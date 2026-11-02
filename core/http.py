"""Supplied HTTP helpers; students implement domain rules in board/."""
import json
from functools import wraps

from django.http import HttpResponse, JsonResponse


class APIError(Exception):
    def __init__(self, code, status=400):
        self.code = code
        self.status = status


def endpoint(*methods, public=False):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method not in methods:
                response = JsonResponse({"error": "method_not_allowed"}, status=405)
                response["Allow"] = ", ".join(methods)
                return response
            if not public and not request.user.is_authenticated:
                return JsonResponse({"error": "authentication_required"}, status=401)
            try:
                return view(request, *args, **kwargs)
            except APIError as exc:
                return JsonResponse({"error": exc.code}, status=exc.status)
        return wrapped
    return decorate


def body(request, allowed, required=()):
    if request.content_type != "application/json":
        raise APIError("unsupported_media_type", 415)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise APIError("invalid_json")
    if not isinstance(data, dict):
        raise APIError("invalid_json")
    if set(data) - set(allowed) or set(required) - set(data):
        raise APIError("invalid_fields")
    return data


def text(value, maximum, *, blank=False):
    if not isinstance(value, str):
        raise APIError("invalid_value")
    value = value.strip()
    if len(value) > maximum or (not blank and not value):
        raise APIError("invalid_value")
    return value


def positive_id(value):
    if type(value) is not int or value < 1:
        raise APIError("invalid_value")
    return value


def query(request, allowed=()):
    if set(request.GET) - set(allowed) - {"page", "page_size"}:
        raise APIError("invalid_query")
    if any(len(request.GET.getlist(key)) != 1 for key in request.GET):
        raise APIError("invalid_query")


def page(request, queryset, serialize):
    values = []
    for key, default in (("page", "1"), ("page_size", "20")):
        raw = request.GET.get(key, default)
        if not raw.isascii() or not raw.isdecimal() or len(raw) > 9 or int(raw) < 1:
            raise APIError("invalid_query")
        values.append(int(raw))
    number, size = values
    if size > 100:
        raise APIError("invalid_query")
    offset = (number - 1) * size
    return JsonResponse({"count": queryset.count(), "results": [serialize(item) for item in queryset[offset:offset + size]]})


def csrf_failure(request, reason=""):
    return JsonResponse({"error": "csrf_failed"}, status=403)


@endpoint("GET", public=True)
def health(request):
    return JsonResponse({"status": "ok"})


def no_content():
    return HttpResponse(status=204)
