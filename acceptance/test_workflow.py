from acceptance.base import APICase


class WorkflowTests(APICase):
    def setUp(self):
        super().setUp()
        self.p = self.project()
        self.add_member(self.p)
        self.t = self.task(self.p)

    def test_all_allowed_transitions(self):
        self.as_user(self.member)
        for status in ("in_progress", "todo", "in_progress", "review", "in_progress", "review", "done", "todo"):
            result = self.move(self.t, status)
            self.assertEqual(result["status"], status)
        self.assertEqual(len(self.events(self.t)), 9)

    def test_rejected_transitions_do_not_change_task_or_history(self):
        for status in ("todo", "review", "done"):
            with self.subTest(status=status):
                self.move(self.t, status, status=409, error="invalid_transition")
        for invalid in (None, [], 1, "unknown"):
            with self.subTest(invalid=invalid):
                self.move(self.t, invalid, status=400, error="invalid_value")
        self.assertEqual(self.api("GET", self.task_url(self.t)), self.t)
        self.assertEqual(len(self.events(self.t)), 1)

    def test_event_content_order_and_actor(self):
        self.as_user(self.member)
        self.move(self.t, "in_progress")
        self.api("PATCH", self.task_url(self.t), {"title": "Updated", "assignee_id": self.member.pk})
        comment = self.api("POST", self.task_url(self.t, "comments/"), {"text": "Ready"}, status=201)
        events = self.events(self.t)
        self.assertEqual([e["kind"] for e in events], ["task_created", "status_changed", "task_updated", "comment_added"])
        self.assertEqual(events[0]["actor_id"], self.owner.pk)
        self.assertEqual(events[0]["data"], {})
        self.assertTrue(all(e["actor_id"] == self.member.pk for e in events[1:]))
        self.assertEqual(events[1]["data"], {"from": "todo", "to": "in_progress"})
        self.assertEqual(events[2]["data"], {"changes": {"title": {"old": "Build API", "new": "Updated"}, "assignee_id": {"old": None, "new": self.member.pk}}})
        self.assertEqual(events[3]["data"], {"comment_id": comment["id"]})
        self.assertEqual([e["id"] for e in events], sorted(e["id"] for e in events))

    def test_noop_patch_creates_no_event(self):
        self.api("PATCH", self.task_url(self.t), {"title": self.t["title"]})
        self.assertEqual(len(self.events(self.t)), 1)
        self.assertEqual(self.api("GET", self.task_url(self.t))["updated_at"], self.t["updated_at"])

    def test_comments_and_pagination(self):
        url = self.task_url(self.t, "comments/")
        first = self.api("POST", url, {"text": " First "}, status=201)
        self.as_user(self.member)
        second = self.api("POST", url, {"text": "Second"}, status=201)
        self.assertEqual(first["text"], "First")
        self.assertEqual(first["author_id"], self.owner.pk)
        self.assertEqual(second["author_id"], self.member.pk)
        self.assert_page(self.api("GET", url), [first["id"], second["id"]])
        result = self.api("GET", url, {"page": 2, "page_size": 1})
        self.assertEqual(result["count"], 2)
        self.assert_page(result, [second["id"]])

    def test_invalid_comment_has_no_side_effects(self):
        for value in ("", "   ", "x" * 2001, None, 12):
            with self.subTest(value=str(value)[:20]):
                self.api("POST", self.task_url(self.t, "comments/"), {"text": value}, status=400, error="invalid_value")
        self.api("POST", self.task_url(self.t, "comments/"), {"text": "Valid", "author_id": self.owner.pk}, status=400, error="invalid_fields")
        self.assertEqual(self.api("GET", self.task_url(self.t, "comments/"))["count"], 0)
        self.assertEqual(len(self.events(self.t)), 1)

    def test_history_is_read_only(self):
        url = self.task_url(self.t, "history/")
        self.api("POST", url, {"kind": "task_created"}, status=405, error="method_not_allowed")
        self.api("DELETE", url, status=405, error="method_not_allowed")
        self.assertEqual(len(self.events(self.t)), 1)

    def test_empty_project_summary(self):
        empty = self.project(name="Empty")
        self.assertEqual(self.api("GET", f'/api/projects/{empty["id"]}/summary/'), {
            "total": 0, "by_status": {"todo": 0, "in_progress": 0, "review": 0, "done": 0}, "overdue": 0})
