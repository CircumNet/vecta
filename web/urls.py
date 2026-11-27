from django.urls import re_path

from . import views

# Single-page app: every non-API, non-admin, non-static path serves the shell.
urlpatterns = [re_path(r"^(?!api/|admin/|static/).*$", views.index)]
