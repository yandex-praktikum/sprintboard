from django.test import Client

from acceptance.base import APICase


class ProjectTests(APICase):
    def test_creation_and_owner_membership(self):
        project = self.project(description="Team work")
        self.assertEqual(set(project), {"id", "name", "description", "owner_id", "archived", "created_at"})
        self.assertEqual(project["owner_id"], self.owner.pk)
        self.assertIs(project["archived"], False)
        result = self.api("GET", f'/api/projects/{project["id"]}/members/')
        self.assertEqual(result, {"count": 1, "results": [{"id": self.owner.pk, "username": "owner", "role": "owner"}]})

    def test_only_member_projects_are_visible(self):
        first = self.project()
        second = self.project(name="Second")
        self.add_member(first)
        self.assert_page(self.api("GET", "/api/projects/"), [second["id"], first["id"]])
        self.as_user(self.member)
        self.assert_page(self.api("GET", "/api/projects/"), [first["id"]])
        self.api("GET", f'/api/projects/{second["id"]}/', status=404, error="not_found")

    def test_anonymous_access_is_json_401(self):
        for url in ["/api/projects/", "/api/projects/999/", "/api/tasks/999/"]:
            with self.subTest(url=url):
                self.api("GET", url, client=Client(), status=401, error="authentication_required")

    def test_owner_changes_project(self):
        project = self.project()
        result = self.api("PATCH", f'/api/projects/{project["id"]}/', {"name": "New", "description": "Updated", "archived": True})
        self.assertEqual(result["name"], "New")
        self.assertIs(result["archived"], True)

    def test_member_cannot_change_project_or_members(self):
        project = self.project()
        self.add_member(project)
        self.as_user(self.member)
        url = f'/api/projects/{project["id"]}/'
        self.api("PATCH", url, {"name": "Hijacked"}, status=403, error="forbidden")
        self.api("POST", url + "members/", {"username": "outsider"}, status=403, error="forbidden")
        self.api("DELETE", url + f'members/{self.owner.pk}/', status=403, error="forbidden")
        self.assertEqual(self.api("GET", url)["name"], project["name"])
        self.assertEqual(self.api("GET", url + "members/")["count"], 2)

    def test_member_addition_duplicate_and_unknown_user(self):
        project = self.project()
        url = f'/api/projects/{project["id"]}/members/'
        self.assertEqual(self.add_member(project)["role"], "member")
        self.api("POST", url, {"username": "member"}, status=409, error="membership_exists")
        self.api("POST", url, {"username": "missing"}, status=404, error="user_not_found")
        self.assertEqual(self.api("GET", url)["count"], 2)

    def test_member_removal_revokes_access(self):
        project = self.project()
        self.add_member(project)
        task = self.task(project)
        self.api("DELETE", f'/api/projects/{project["id"]}/members/{self.member.pk}/', status=204)
        self.as_user(self.member)
        self.api("GET", self.task_url(task), status=404, error="not_found")
        self.assert_page(self.api("GET", "/api/projects/"), [])

    def test_owner_and_assigned_member_cannot_be_removed(self):
        project = self.project()
        self.add_member(project)
        task = self.task(project, assignee_id=self.member.pk)
        prefix = f'/api/projects/{project["id"]}/members/'
        self.api("DELETE", prefix + f'{self.owner.pk}/', status=409, error="owner_required")
        self.api("DELETE", prefix + f'{self.member.pk}/', status=409, error="member_in_use")
        self.assertEqual(self.api("GET", prefix)["count"], 2)
        self.api("PATCH", self.task_url(task), {"assignee_id": None})
        self.api("DELETE", prefix + f'{self.member.pk}/', status=204)

    def test_pagination_and_validation(self):
        first, second = self.project(), self.project()
        data = self.api("GET", "/api/projects/", {"page": 2, "page_size": 1})
        self.assertEqual(data["count"], 2)
        self.assert_page(data, [first["id"]])
        self.assert_page(self.api("GET", "/api/projects/", {"page": 3, "page_size": 1}), [])
        for params in ({"page": 0}, {"page_size": 101}, {"page": "1.5"}, {"unknown": "x"}, {"page": ""}):
            with self.subTest(params=params):
                self.api("GET", "/api/projects/", params, status=400, error="invalid_query")

    def test_project_fields_are_validated(self):
        for data in ({"name": " "}, {"name": "x" * 101}, {"name": None}, {"name": "Valid", "owner_id": self.outsider.pk}):
            with self.subTest(data=data):
                self.api("POST", "/api/projects/", data, status=400)
        self.assertEqual(self.api("GET", "/api/projects/")["count"], 0)
