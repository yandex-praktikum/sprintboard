from django.urls import path
from board import views

urlpatterns = [
    path("projects/", views.projects),
    path("projects/<int:project_id>/", views.project_detail),
    path("projects/<int:project_id>/members/", views.members),
    path("projects/<int:project_id>/members/<int:user_id>/", views.member_detail),
    path("projects/<int:project_id>/tasks/", views.tasks),
    path("projects/<int:project_id>/summary/", views.summary),
    path("tasks/<int:task_id>/", views.task_detail),
    path("tasks/<int:task_id>/transition/", views.transition),
    path("tasks/<int:task_id>/comments/", views.comments),
    path("tasks/<int:task_id>/history/", views.history),
]
