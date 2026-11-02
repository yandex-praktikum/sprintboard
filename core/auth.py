"""Working session authentication supplied with the starter."""
import re

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token

from core.http import APIError, body, endpoint, no_content


def user_data(user):
    return {"id": user.pk, "username": user.username}


@endpoint("GET", public=True)
def csrf(request):
    return JsonResponse({"csrfToken": get_token(request)})


@endpoint("POST", public=True)
def register(request):
    data = body(request, {"username", "password"}, {"username", "password"})
    username, password = data["username"], data["password"]
    if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", username):
        raise APIError("invalid_value")
    if not isinstance(password, str) or len(password) > 128:
        raise APIError("invalid_value")
    try:
        validate_password(password)
    except ValidationError:
        raise APIError("invalid_password")
    try:
        with transaction.atomic():
            user = User.objects.create_user(username=username, password=password)
    except IntegrityError:
        raise APIError("username_taken", 409)
    return JsonResponse(user_data(user), status=201)


@endpoint("POST", public=True)
def sign_in(request):
    data = body(request, {"username", "password"}, {"username", "password"})
    if not all(isinstance(data[key], str) for key in data):
        raise APIError("invalid_value")
    if len(data["username"]) > 30 or len(data["password"]) > 128:
        raise APIError("invalid_credentials", 401)
    user = authenticate(request, username=data["username"], password=data["password"])
    if user is None:
        raise APIError("invalid_credentials", 401)
    login(request, user)
    return JsonResponse(user_data(user))


@endpoint("POST")
def sign_out(request):
    logout(request)
    return no_content()


@endpoint("GET")
def me(request):
    return JsonResponse(user_data(request.user))
