from django.test import Client

from acceptance.base import APICase


class BootstrapTests(APICase):
    def test_health(self):
        self.assertEqual(self.api("GET", "/api/health/", client=Client()), {"status": "ok"})

    def test_registration_login_logout(self):
        client = Client(enforce_csrf_checks=True)
        token = self.api("GET", "/api/auth/csrf/", client=client)["csrfToken"]
        credentials = {"username": "new_user", "password": "study-pass-123"}
        response = client.post("/api/auth/register/", credentials, content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.json()), {"id", "username"})
        self.api("GET", "/api/auth/me/", client=client, status=401, error="authentication_required")
        response = client.post("/api/auth/login/", credentials, content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.api("GET", "/api/auth/me/", client=client)["username"], "new_user")
        token = self.api("GET", "/api/auth/csrf/", client=client)["csrfToken"]
        self.assertEqual(client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=token).status_code, 204)
        self.api("GET", "/api/auth/me/", client=client, status=401)

    def test_csrf_is_required_for_browser_writes(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post("/api/auth/register/", {"username": "hello", "password": "study-pass-123"}, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "csrf_failed"})

    def test_duplicate_and_short_password(self):
        self.api("POST", "/api/auth/register/", {"username": "owner", "password": "study-pass-123"}, status=409, error="username_taken")
        self.api("POST", "/api/auth/register/", {"username": "hello", "password": "short"}, status=400, error="invalid_password")

    def test_bad_login(self):
        self.api("POST", "/api/auth/login/", {"username": "owner", "password": "wrong"}, status=401, error="invalid_credentials")

    def test_method_and_json_errors(self):
        self.api("GET", "/api/auth/login/", status=405, error="method_not_allowed")
        response = self.client.post("/api/auth/register/", "{", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "invalid_json"})
