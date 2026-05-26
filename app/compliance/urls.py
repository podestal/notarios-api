from django.urls import path

from compliance.views import (
    ComplianceDashboardView,
    ComplianceDetailView,
    ComplianceOverviewView,
    ComplianceRefreshView,
)

app_name = "compliance"

urlpatterns = [
    path("", ComplianceDashboardView.as_view(), name="dashboard"),
    path("overview/", ComplianceOverviewView.as_view(), name="overview"),
    path("refresh/", ComplianceRefreshView.as_view(), name="refresh"),
    path("<str:kardex>/", ComplianceDetailView.as_view(), name="detail"),
]
