from django.urls import path

from uif.views import UifErrorsDashboardView

app_name = "uif"

urlpatterns = [
    path("errors/", UifErrorsDashboardView.as_view(), name="errors_dashboard"),
]
