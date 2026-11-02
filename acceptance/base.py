import json

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class APICase(TestCase):
    """Black-box domain tests: no imports from board.models or board.services."""
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="study-pass-123")
        self.member = User.objects.create_user(username="member", password="study-pass-123")
        self.outsider = User.objects.create_user(username="outsider", password="study-pass-123")
        self.client.force_login(self.owner)

    def api(self, method, url, data=None, *, status=200, error=None, client=None):
        client = client or self.client
        if method == "GET":
            response = client.get(url, data or {})
        else:
            response = client.generic(method, url, json.dumps(data if data is not None else {}), content_type="application/json")
        self.assertEqual(response.status_code, status, response.content.decode()[:500])
        if status == 204:
            self.assertEqual(response.content, b"")
            return None
        self.assertEqual(response.headers["Content-Type"].split(";")[0], "application/json")
        result = response.json()
        if error is not None:
            self.assertEqual(result, {"error": error})
        return result

    def project(self, **extra):
        return self.api("POST", "/api/projects/", {"name": "Website", **extra}, status=201)

    def add_member(self, project, user=None):
        user = user or self.member
        return self.api("POST", f'/api/projects/{project["id"]}/members/', {"username": user.username}, status=201)

    def task(self, project, **extra):
        return self.api("POST", f'/api/projects/{project["id"]}/tasks/', {"title": "Build API", **extra}, status=201)

    def task_url(self, task, suffix=""):
        return f'/api/tasks/{task["id"]}/{suffix}'

    def events(self, task):
        return self.api("GET", self.task_url(task, "history/"))["results"]

    def move(self, task, target, **expected):
        return self.api("POST", self.task_url(task, "transition/"), {"status": target}, **expected)

    def as_user(self, user):
        self.client.force_login(user)

    def assert_page(self, data, ids):
        self.assertEqual(set(data), {"count", "results"})
        self.assertEqual([item["id"] for item in data["results"]], ids)
