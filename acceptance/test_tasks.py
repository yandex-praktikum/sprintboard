from datetime import timedelta

from django.test import Client
from django.utils import timezone

from acceptance.base import APICase


class TaskTests(APICase):
    def setUp(self):
        super().setUp()
        self.p = self.project()
        self.add_member(self.p)
        self.url = f'/api/projects/{self.p["id"]}/tasks/'

    def test_create_defaults_and_fields(self):
        task = self.task(self.p)
        self.assertEqual(set(task), {"id", "project_id", "title", "description", "reporter_id", "assignee_id", "priority", "status", "due_date", "created_at", "updated_at"})
        self.assertEqual(task["status"], "todo")
        self.assertEqual(task["priority"], "medium")
        self.assertEqual(task["reporter_id"], self.owner.pk)
        self.assertIsNone(task["assignee_id"])
        self.assertIsNone(task["due_date"])
        self.assertEqual(task["description"], "")

    def test_member_creates_and_edits_task(self):
        self.as_user(self.member)
        task = self.task(self.p, assignee_id=self.owner.pk, priority="high", due_date="2030-05-20")
        self.assertEqual(task["reporter_id"], self.member.pk)
        result = self.api("PATCH", self.task_url(task), {"title": "  Updated  ", "description": "New body", "assignee_id": None, "due_date": None})
        self.assertEqual(result["title"], "Updated")
        self.assertIsNone(result["assignee_id"])
        self.assertIsNone(result["due_date"])
        self.assertEqual(self.api("GET", self.task_url(task)), result)

    def test_unknown_fields_and_invalid_values_do_not_create_tasks(self):
        bad = [
            {"status": "done"}, {"reporter_id": self.outsider.pk}, {"project_id": 999},
            {"title": " "}, {"title": "x" * 201}, {"description": None},
            {"priority": "urgent"}, {"priority": []}, {"assignee_id": True},
            {"due_date": "2030-02-30"}, {"due_date": "20300520"}, {"due_date": 1},
        ]
        for extra in bad:
            with self.subTest(extra=extra):
                self.api("POST", self.url, {"title": "Valid", **extra}, status=400)
        self.assertEqual(self.api("GET", self.url)["count"], 0)

    def test_assignee_must_belong_to_project(self):
        self.api("POST", self.url, {"title": "Valid", "assignee_id": self.outsider.pk}, status=400, error="invalid_assignee")
        task = self.task(self.p, assignee_id=self.member.pk)
        self.api("PATCH", self.task_url(task), {"assignee_id": self.outsider.pk}, status=400, error="invalid_assignee")
        self.assertEqual(self.api("GET", self.task_url(task))["assignee_id"], self.member.pk)
        self.assertEqual(len(self.events(task)), 1)

    def test_failed_patch_is_atomic(self):
        task = self.task(self.p)
        self.api("PATCH", self.task_url(task), {"title": "Changed", "due_date": "not-a-date"}, status=400)
        self.assertEqual(self.api("GET", self.task_url(task))["title"], task["title"])
        self.assertEqual(len(self.events(task)), 1)

    def test_status_and_identity_cannot_be_patched(self):
        task = self.task(self.p)
        for field, value in [("status", "done"), ("project_id", 999), ("reporter_id", self.member.pk), ("id", 999)]:
            with self.subTest(field=field):
                self.api("PATCH", self.task_url(task), {field: value}, status=400, error="invalid_fields")
        self.assertEqual(self.api("GET", self.task_url(task)), task)

    def test_outsider_cannot_read_or_change_task(self):
        task = self.task(self.p)
        self.as_user(self.outsider)
        for method, suffix, data in [("GET", "", None), ("PATCH", "", {"title": "Oops"}), ("DELETE", "", None),
                                     ("POST", "transition/", {"status": "in_progress"}),
                                     ("POST", "comments/", {"text": "Oops"}), ("GET", "comments/", None), ("GET", "history/", None)]:
            with self.subTest(method=method, suffix=suffix):
                self.api(method, self.task_url(task, suffix), data, status=404, error="not_found")
        for suffix in ("tasks/", "members/", "summary/"):
            self.api("GET", f'/api/projects/{self.p["id"]}/{suffix}', status=404, error="not_found")
        self.as_user(self.owner)
        self.assertEqual(self.api("GET", self.task_url(task)), task)
        self.assertEqual(len(self.events(task)), 1)
        self.assertEqual(self.api("GET", self.task_url(task, "comments/"))["count"], 0)

    def test_delete_only_owner_or_reporter(self):
        task = self.task(self.p)
        self.as_user(self.member)
        self.api("DELETE", self.task_url(task), status=403, error="forbidden")
        self.api("GET", self.task_url(task))
        own = self.task(self.p)
        self.api("DELETE", self.task_url(own), status=204)
        self.as_user(self.owner)
        self.api("DELETE", self.task_url(task), status=204)
        for suffix in ("", "comments/", "history/"):
            self.api("GET", self.task_url(task, suffix), status=404, error="not_found")

    def test_combined_filters_and_pagination(self):
        self.task(self.p, title="Other", priority="low")
        matched = self.task(self.p, title="Build API", priority="high", assignee_id=self.member.pk)
        self.task(self.p, title="Build API too", priority="high", assignee_id=self.owner.pk)
        data = self.api("GET", self.url, {"status": "todo", "priority": "high", "assignee_id": self.member.pk, "q": "API", "page_size": 1})
        self.assertEqual(data["count"], 1)
        self.assert_page(data, [matched["id"]])
        self.assert_page(self.api("GET", self.url, {"assignee_id": self.outsider.pk}), [])

    def test_search_in_description(self):
        found = self.task(self.p, title="First", description="Documentation here")
        self.task(self.p, title="Second")
        self.assert_page(self.api("GET", self.url, {"q": "Documentation"}), [found["id"]])

    def test_invalid_filters(self):
        for params in ({"status": "unknown"}, {"priority": "urgent"}, {"assignee_id": "true"}, {"assignee_id": 0},
                       {"q": " "}, {"overdue": "1"}, {"page_size": 0}, {"sort": "title"}):
            with self.subTest(params=params):
                self.api("GET", self.url, params, status=400, error="invalid_query")

    def test_project_isolation_and_newest_first(self):
        first, second = self.task(self.p), self.task(self.p)
        other = self.project(name="Elsewhere")
        self.task(other)
        result = self.api("GET", self.url)
        self.assertEqual(result["count"], 2)
        self.assert_page(result, [second["id"], first["id"]])

    def test_overdue_and_summary(self):
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        today = timezone.localdate().isoformat()
        late = self.task(self.p, due_date=yesterday)
        completed = self.task(self.p, due_date=yesterday)
        for status in ("in_progress", "review", "done"):
            self.move(completed, status)
        self.task(self.p, due_date=today)
        self.task(self.p)
        self.assert_page(self.api("GET", self.url, {"overdue": "true"}), [late["id"]])
        self.assertEqual(self.api("GET", self.url, {"overdue": "false"})["count"], 3)
        result = self.api("GET", f'/api/projects/{self.p["id"]}/summary/')
        self.assertEqual(result, {"total": 4, "by_status": {"todo": 3, "in_progress": 0, "review": 0, "done": 1}, "overdue": 1})

    def test_archive_blocks_mutations_but_not_reads(self):
        task = self.task(self.p)
        self.api("PATCH", f'/api/projects/{self.p["id"]}/', {"archived": True})
        for method, url, data in [
            ("POST", self.url, {"title": "No"}), ("PATCH", self.task_url(task), {"title": "No"}),
            ("DELETE", self.task_url(task), None), ("POST", self.task_url(task, "transition/"), {"status": "in_progress"}),
            ("POST", self.task_url(task, "comments/"), {"text": "No"}),
            ("POST", f'/api/projects/{self.p["id"]}/members/', {"username": "outsider"}),
            ("DELETE", f'/api/projects/{self.p["id"]}/members/{self.member.pk}/', None),
        ]:
            with self.subTest(method=method, url=url):
                self.api(method, url, data, status=409, error="project_archived")
        self.assertEqual(self.api("GET", self.task_url(task)), task)
        self.assertEqual(len(self.events(task)), 1)
        self.api("GET", self.url)
        self.api("PATCH", f'/api/projects/{self.p["id"]}/', {"archived": False})
        self.move(task, "in_progress")

    def test_csrf_is_enforced_on_domain_endpoints(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        task = self.task(self.p)
        self.api("PATCH", self.task_url(task), {"title": "No"}, client=client, status=403, error="csrf_failed")
        self.assertEqual(self.api("GET", self.task_url(task)), task)
