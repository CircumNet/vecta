from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views, views_extra

router = SimpleRouter()
router.register("leave-types", views.LeaveTypeViewSet, basename="leave-type")
router.register("holidays", views.HolidayViewSet, basename="holiday")
router.register("blackouts", views.BlackoutViewSet, basename="blackout")
router.register("leave-requests", views.LeaveRequestViewSet, basename="leave-request")
router.register("delegations", views_extra.DelegationViewSet, basename="delegation")

urlpatterns = [
    path("me/balances/", views.MyBalancesView.as_view()),
    path("me/calendar.ics", views_extra.MyCalendarICSView.as_view()),
    path("dashboard/", views_extra.DashboardView.as_view()),
    path("calendar/", views_extra.CalendarView.as_view()),
    path("directory/", views_extra.DirectoryView.as_view()),
    path("activity/", views_extra.ActivityView.as_view()),
    path("notifications/", views.NotificationListView.as_view()),
    path("notifications/mark-read/", views.NotificationMarkReadView.as_view()),
    path("reports/leave/", views.LeaveReportView.as_view()),
    path("reports/on-leave-today/", views.OnLeaveTodayView.as_view()),
] + router.urls
