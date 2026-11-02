"""Replace these stubs; keep the public URL and JSON contract."""
from core.http import APIError, endpoint


def unfinished():
    raise APIError("not_implemented", 501)


@endpoint("GET", "POST")
def projects(request):
    return unfinished()


@endpoint("GET", "PATCH")
def project_detail(request, project_id):
    return unfinished()


@endpoint("GET", "POST")
def members(request, project_id):
    return unfinished()


@endpoint("DELETE")
def member_detail(request, project_id, user_id):
    return unfinished()


@endpoint("GET", "POST")
def tasks(request, project_id):
    return unfinished()


@endpoint("GET")
def summary(request, project_id):
    return unfinished()


@endpoint("GET", "PATCH", "DELETE")
def task_detail(request, task_id):
    return unfinished()


@endpoint("POST")
def transition(request, task_id):
    return unfinished()


@endpoint("GET", "POST")
def comments(request, task_id):
    return unfinished()


@endpoint("GET")
def history(request, task_id):
    return unfinished()
