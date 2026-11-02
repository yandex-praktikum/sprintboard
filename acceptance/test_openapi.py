"""Validate the student's document and a real API conversation against it."""
import warnings

import yaml
from django.conf import settings
from django.test import SimpleTestCase
from openapi_spec_validator import validate_spec
from openapi_schema_validator import OAS30Validator
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from jsonschema import RefResolver

from acceptance.base import APICase

REQUIRED = {
    "/api/health/": {"get"}, "/api/auth/csrf/": {"get"}, "/api/auth/register/": {"post"},
    "/api/auth/login/": {"post"}, "/api/auth/logout/": {"post"}, "/api/auth/me/": {"get"},
    "/api/projects/": {"get", "post"}, "/api/projects/{project_id}/": {"get", "patch"},
    "/api/projects/{project_id}/members/": {"get", "post"},
    "/api/projects/{project_id}/members/{user_id}/": {"delete"},
    "/api/projects/{project_id}/tasks/": {"get", "post"},
    "/api/projects/{project_id}/summary/": {"get"},
    "/api/tasks/{task_id}/": {"get", "patch", "delete"},
    "/api/tasks/{task_id}/transition/": {"post"},
    "/api/tasks/{task_id}/comments/": {"get", "post"},
    "/api/tasks/{task_id}/history/": {"get"},
}
PUBLIC = {"/api/health/", "/api/auth/csrf/", "/api/auth/register/", "/api/auth/login/"}


def read_spec():
    with (settings.BASE_DIR / "openapi.yaml").open(encoding="utf-8") as stream:
        spec = yaml.safe_load(stream)
    def local_refs(value):
        if isinstance(value, dict):
            if "$ref" in value and not value["$ref"].startswith("#/"):
                raise AssertionError("Use only local $ref in openapi.yaml; validation must work offline")
            for child in value.values():
                local_refs(child)
        elif isinstance(value, list):
            for child in value:
                local_refs(child)
    local_refs(spec)
    return spec


def resolve(spec, value):
    while "$ref" in value:
        result = spec
        for part in value["$ref"][2:].split("/"):
            result = result[part.replace("~1", "/").replace("~0", "~")]
        value = result
    return value


class OpenAPIDocumentTests(SimpleTestCase):
    def test_document_is_valid_openapi_303(self):
        spec = read_spec()
        self.assertEqual(spec["openapi"], "3.0.3")
        validate_spec(spec)

    def test_all_required_operations_and_auth_are_documented(self):
        spec = read_spec()
        schemes = spec.get("components", {}).get("securitySchemes", {})
        session_names = {name for name, value in schemes.items() if value.get("type") == "apiKey" and value.get("in") == "cookie" and value.get("name") == "sessionid"}
        self.assertTrue(session_names, "Document sessionid cookie authentication")
        operation_ids = []
        for path, methods in REQUIRED.items():
            self.assertIn(path, spec["paths"], f"Missing path: {path}")
            for method in methods:
                self.assertIn(method, spec["paths"][path], f"Missing {method.upper()} {path}")
                op = spec["paths"][path][method]
                operation_ids.append(op["operationId"])
                security = op.get("security", spec.get("security", []))
                if path not in PUBLIC:
                    self.assertTrue(security and all(any(name in rule for name in session_names) for rule in security), path)
                    self.assertIn("401", op["responses"])
                else:
                    self.assertEqual(security, [], path)
                if method in {"post", "patch", "delete"}:
                    parameters = [resolve(spec, p) for p in op.get("parameters", []) + spec["paths"][path].get("parameters", [])]
                    self.assertTrue(any(p.get("in") == "header" and p.get("name", "").lower() == "x-csrftoken" and p.get("required") for p in parameters), path)
                    self.assertIn("403", op["responses"])
        self.assertEqual(len(operation_ids), len(set(operation_ids)))

    def test_filters_and_typed_response_fields(self):
        spec = read_spec()
        path = "/api/projects/{project_id}/tasks/"
        self.assertIn(path, spec["paths"], "Describe the task list first")
        op = spec["paths"][path]["get"]
        parameters = [resolve(spec, p) for p in op.get("parameters", []) + spec["paths"][path].get("parameters", [])]
        names = {p["name"] for p in parameters if p["in"] == "query"}
        self.assertTrue({"page", "page_size", "status", "priority", "assignee_id", "q", "overdue"} <= names)
        response = resolve(spec, op["responses"]["200"])
        schema = resolve(spec, response["content"]["application/json"]["schema"])
        self.assertTrue({"count", "results"} <= set(schema.get("required", [])))
        task = resolve(spec, schema["properties"]["results"]["items"])
        fields = {"id", "project_id", "title", "description", "reporter_id", "assignee_id", "priority", "status", "due_date", "created_at", "updated_at"}
        self.assertTrue(fields <= set(task.get("required", [])), "All task response fields must be required")
        for field in fields:
            self.assertIn("type", resolve(spec, task["properties"][field]), field)
        self.assertTrue(resolve(spec, task["properties"]["assignee_id"]).get("nullable"))
        self.assertTrue(resolve(spec, task["properties"]["due_date"]).get("nullable"))


class OpenAPIResponseTests(APICase):
    def test_real_scenario_matches_document(self):
        spec = read_spec()
        resolver = RefResolver.from_schema(spec)
        def check(path, method, data, code=200):
            self.assertIn(path, spec["paths"], f"Missing path: {path}")
            response = resolve(spec, spec["paths"][path][method]["responses"][str(code)])
            if code == 204:
                self.assertNotIn("content", response)
                return
            schema = response["content"]["application/json"]["schema"]
            OAS30Validator(schema, resolver=resolver, format_checker=OAS30Validator.FORMAT_CHECKER).validate(data)
        project = self.project()
        check("/api/projects/", "post", project, 201)
        check("/api/projects/", "get", self.api("GET", "/api/projects/"))
        check("/api/projects/{project_id}/", "get", self.api("GET", f'/api/projects/{project["id"]}/'))
        check("/api/projects/{project_id}/members/", "post", self.add_member(project), 201)
        task = self.task(project, due_date="2030-05-20")
        check("/api/projects/{project_id}/tasks/", "post", task, 201)
        check("/api/projects/{project_id}/tasks/", "get", self.api("GET", f'/api/projects/{project["id"]}/tasks/'))
        check("/api/tasks/{task_id}/", "patch", self.api("PATCH", self.task_url(task), {"description": "Edited", "due_date": None}))
        check("/api/tasks/{task_id}/transition/", "post", self.move(task, "in_progress"))
        check("/api/tasks/{task_id}/comments/", "post", self.api("POST", self.task_url(task, "comments/"), {"text": "Review"}, status=201), 201)
        check("/api/tasks/{task_id}/comments/", "get", self.api("GET", self.task_url(task, "comments/")))
        check("/api/tasks/{task_id}/history/", "get", self.api("GET", self.task_url(task, "history/")))
        check("/api/projects/{project_id}/summary/", "get", self.api("GET", f'/api/projects/{project["id"]}/summary/'))
        bad = self.move(task, "done", status=409, error="invalid_transition")
        check("/api/tasks/{task_id}/transition/", "post", bad, 409)
        check("/api/tasks/{task_id}/", "delete", self.api("DELETE", self.task_url(task), status=204), 204)
