from django.urls import path

from uif.views import (
    UifErrorsCorrectView,
    UifErrorsDashboardView,
    UifReportExcelView,
    UifReportPlaneView,
)

app_name = "uif"

urlpatterns = [
    path("errors/", UifErrorsDashboardView.as_view(), name="errors_dashboard"),
    path("errors/correct/", UifErrorsCorrectView.as_view(), name="errors_correct"),
    path("reports/excel/", UifReportExcelView.as_view(), name="report_excel"),
    path("reports/plane/", UifReportPlaneView.as_view(), name="report_plane"),
]
