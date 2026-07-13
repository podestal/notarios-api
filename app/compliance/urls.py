from django.urls import path

from compliance.views import (
    ComplianceDashboardView,
    ComplianceDetailView,
    ComplianceKardexErrorsView,
    ComplianceMyKardexErrorsView,
    ComplianceMyKardexMonthView,
    ComplianceMyKardexView,
    ComplianceOverviewView,
    ComplianceRefreshView,
    ComplianceUserKardexView,
    ComplianceUsersKardexView,
    ComplianceUsersMonthlyView,
)

app_name = "compliance"

urlpatterns = [
    path("", ComplianceDashboardView.as_view(), name="dashboard"),
    path("overview/", ComplianceOverviewView.as_view(), name="overview"),
    path("users/", ComplianceUsersMonthlyView.as_view(), name="users-monthly"),
    path("users/kardex/", ComplianceUsersKardexView.as_view(), name="users-kardex"),
    path(
        "users/<int:idusuario>/kardex/",
        ComplianceUserKardexView.as_view(),
        name="user-kardex",
    ),
    path("me/kardex/", ComplianceMyKardexView.as_view(), name="my-kardex"),
    path(
        "me/kardex/month/",
        ComplianceMyKardexMonthView.as_view(),
        name="my-kardex-month",
    ),
    path(
        "me/kardex/<str:kardex>/errors/",
        ComplianceMyKardexErrorsView.as_view(),
        name="my-kardex-errors",
    ),
    path("refresh/", ComplianceRefreshView.as_view(), name="refresh"),
    path(
        "kardex/<str:kardex>/errors/",
        ComplianceKardexErrorsView.as_view(),
        name="kardex-errors",
    ),
    path("<str:kardex>/", ComplianceDetailView.as_view(), name="detail"),
]
