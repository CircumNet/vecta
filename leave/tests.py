import datetime as dt

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Department, Roles, User
from leave import services
from leave.models import BlackoutPeriod, Delegation, Holiday, LeaveBalance, LeaveRequest, LeaveType


def work_week():
    """A Mon-Fri week at least 2 weeks ahead that does not straddle New Year."""
    d = timezone.localdate() + dt.timedelta(days=14)
    d += dt.timedelta(days=(7 - d.weekday()) % 7)
    while d.year != (d + dt.timedelta(days=4)).year:
        d += dt.timedelta(days=7)
    return d, d + dt.timedelta(days=4)


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.dept = Department.objects.create(name="Engineering")
        self.head = self.mk("head")
        self.dept.head = self.head
        self.dept.save()
        self.sup = self.mk("sup")
        self.staff = self.mk("staff")
        self.other = self.mk("other")
        self.hr = self.mk("hr")
        self.hr.groups.add(Group.objects.get(name=Roles.HR_MANAGER))
        self.annual = LeaveType.objects.create(name="Annual", default_days=20)
        self.sick = LeaveType.objects.create(name="Sick", default_days=10, requires_document=True)
        self.start, self.end = work_week()

    def mk(self, username, **kw):
        kw.setdefault("department", self.dept)
        return User.objects.create_user(
            username=username, password="pw-Test-12345", email=f"{username}@example.com",
            must_change_password=False, **kw,
        )

    def api(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def apply(self, user=None, **over):
        payload = {"leave_type": self.annual.pk, "start_date": self.start.isoformat(),
                   "end_date": self.end.isoformat(), "reason": "rest"}
        payload.update(over)
        return self.api(user or self.staff).post("/api/leave-requests/", payload, format="json")

    def balance(self, user=None, lt=None):
        return LeaveBalance.objects.get(user=user or self.staff, leave_type=lt or self.annual, year=self.start.year)


class RulesTests(Base):
    def test_working_days_skip_weekends_and_holidays(self):
        sat = self.start + dt.timedelta(days=5)
        self.assertEqual(services.count_working_days(self.start, sat + dt.timedelta(days=1)), 5)
        Holiday.objects.create(date=self.start + dt.timedelta(days=2), name="Test day")
        self.assertEqual(services.count_working_days(self.start, self.end), 4)

    def test_roles_are_derived_from_org_structure(self):
        self.assertEqual(self.staff.roles, ["staff"])
        self.assertEqual(self.sup.roles, ["staff"])
        self.assertEqual(self.head.roles, ["department_head", "staff"])
        self.assertIn("hr_manager", self.hr.roles)


class SubmitTests(Base):
    def test_submit_reserves_balance_and_routes_to_department_head(self):
        r = self.apply()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["status"], "pending")
        self.assertEqual(r.data["working_days"], 5)
        self.assertEqual(r.data["current_approver"], self.head.pk)
        self.assertEqual(self.balance().pending, 5)
        self.assertEqual(self.balance().available, 15)
        self.assertEqual(self.head.notifications.count(), 1)

    def test_staff_request_goes_to_department_head(self):
        r = self.apply(user=self.sup)
        self.assertEqual(r.data["current_approver"], self.head.pk)

    def test_department_head_without_approver_cannot_submit(self):
        r = self.apply(user=self.head)
        self.assertEqual(r.status_code, 400)
        self.assertIn("department head", str(r.data).lower())

    def test_insufficient_balance(self):
        self.annual.default_days = 3
        self.annual.save()
        r = self.apply()
        self.assertEqual(r.status_code, 400)
        self.assertIn("Insufficient", str(r.data))

    def test_overlap_rejected(self):
        self.assertEqual(self.apply().status_code, 201)
        r = self.apply(start_date=self.end.isoformat(), end_date=self.end.isoformat())
        self.assertEqual(r.status_code, 400)

    def test_past_dates_and_bad_ranges(self):
        yesterday = (timezone.localdate() - dt.timedelta(days=1)).isoformat()
        self.assertEqual(self.apply(start_date=yesterday, end_date=yesterday).status_code, 400)
        self.assertEqual(self.apply(end_date=(self.start - dt.timedelta(days=1)).isoformat()).status_code, 400)

    def test_document_required_and_validated(self):
        self.assertEqual(self.apply(leave_type=self.sick.pk).status_code, 400)
        c = self.api(self.staff)
        bad = SimpleUploadedFile("virus.exe", b"x")
        r = c.post("/api/leave-requests/", {"leave_type": self.sick.pk, "start_date": self.start, "end_date": self.end, "attachment": bad}, format="multipart")
        self.assertEqual(r.status_code, 400)
        mismatch = SimpleUploadedFile("note.pdf", b"not really a pdf")
        bad_pdf = c.post("/api/leave-requests/", {"leave_type": self.sick.pk, "start_date": self.start, "end_date": self.end, "attachment": mismatch}, format="multipart")
        self.assertEqual(bad_pdf.status_code, 400)
        good = SimpleUploadedFile("note.pdf", b"%PDF-1.4 test")
        r = c.post("/api/leave-requests/", {"leave_type": self.sick.pk, "start_date": self.start, "end_date": self.end, "attachment": good}, format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["has_attachment"])
        dl = c.get(f"/api/leave-requests/{r.data['id']}/attachment/")
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(self.api(self.other).get(f"/api/leave-requests/{r.data['id']}/attachment/").status_code, 403)


class DecisionTests(Base):
    def setUp(self):
        super().setUp()
        self.rid = self.apply().data["id"]

    def post(self, user, action, **data):
        return self.api(user).post(f"/api/leave-requests/{self.rid}/{action}/", data, format="json")

    def test_approve_moves_pending_to_used(self):
        r = self.post(self.head, "approve", comment="enjoy")
        self.assertEqual(r.status_code, 200, r.data)
        
        # NEW: Because 5 days <= 14, this is a standard HOD approval
        self.assertEqual(r.data["status"], "approved")
        b = self.balance()
        self.assertEqual((b.pending, b.used, b.available), (0, 5, 15))
        self.assertEqual([a["action"] for a in r.data["actions"]], ["submitted", "approved"])
        self.assertEqual(self.staff.notifications.filter(kind="leave_approved").count(), 1)

    def test_only_the_assigned_approver_can_decide(self):
        for user in (self.staff, self.sup, self.other, self.hr):
            self.assertEqual(self.post(user, "approve").status_code, 403, user.username)
        response = self.post(self.head, "approve")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "approved")

    def test_cannot_decide_twice(self):
        self.post(self.head, "approve")
        self.assertEqual(self.post(self.head, "reject", comment="changed my mind").status_code, 400)

    def test_reject_needs_reason_and_releases_balance(self):
        self.assertEqual(self.post(self.head, "reject").status_code, 400)
        r = self.post(self.head, "reject", comment="Project deadline")
        self.assertEqual(r.status_code, 200)
        b = self.balance()
        self.assertEqual((b.pending, b.used, b.available), (0, 0, 20))

    def test_cancel_pending_and_cancel_approved_before_start(self):
        self.assertEqual(self.post(self.other, "cancel").status_code, 403)
        self.assertEqual(self.post(self.staff, "cancel").status_code, 200)
        self.assertEqual(self.balance().available, 20)
        rid2 = self.apply().data["id"]
        self.api(self.head).post(f"/api/leave-requests/{rid2}/approve/", {}, format="json")
        self.assertEqual(self.balance().used, 5)
        self.api(self.staff).post(f"/api/leave-requests/{rid2}/cancel/", {}, format="json")
        self.assertEqual(self.balance().used, 0)

    def test_pending_approval_queue(self):
        r = self.api(self.head).get("/api/leave-requests/pending-approval/")
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(self.api(self.other).get("/api/leave-requests/pending-approval/").data["count"], 0)

    def test_hr_review_flow(self):
        self.assertEqual(self.post(self.hr, "review", comment="x").status_code, 400)  # still pending
        self.post(self.head, "approve")
        self.assertEqual(self.post(self.head, "review", comment="x").status_code, 403)
        r = self.post(self.hr, "review", comment="Verified")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "approved")  # decision untouched
        self.assertEqual(r.data["hr_note"], "Verified")
        self.assertEqual(self.post(self.hr, "review", comment="again").status_code, 400)

    def test_hr_can_reassign_pending_request(self):
        self.assertEqual(
            self.post(self.head, "reassign", approver=self.other.pk).status_code,
            403,
        )
        r = self.post(
            self.hr,
            "reassign",
            approver=self.other.pk,
            comment="Department head unavailable",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.post(self.head, "approve").status_code, 403)
        self.assertEqual(self.post(self.other, "approve").status_code, 200)
    
    def test_long_leave_goes_to_hr_after_hod_approval(self):
        """Test that >14 day leaves route to HR after HOD approval."""
        self.annual.default_days = 30
        self.annual.max_consecutive_days = 0
        self.annual.save()
        
        # Pick a Monday far enough out that won't overlap with self.start
        today = timezone.localdate()
        candidate = today + dt.timedelta(days=60)
        candidate += dt.timedelta(days=(7 - candidate.weekday()) % 7)
        
        # Ensure the 3-week span stays within one year
        while candidate.year != (candidate + dt.timedelta(days=20)).year:
            candidate += dt.timedelta(days=7)
        
        long_start = candidate
        long_end = long_start + dt.timedelta(days=20)
        
        # Use self.other to avoid overlap with self.rid from setUp
        LeaveBalance.objects.update_or_create(
            user=self.other, leave_type=self.annual, year=long_start.year,
            defaults={"entitled": 30, "used": 0, "pending": 0},
        )
        
        r = self.apply(
            user=self.other,
            start_date=long_start.isoformat(),
            end_date=long_end.isoformat(),
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["working_days"], 15, r.data)
        rid = r.data["id"]
        
        r = self.api(self.head).post(f"/api/leave-requests/{rid}/approve/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "awaiting_hr")
        
        b = LeaveBalance.objects.get(user=self.other, leave_type=self.annual, year=long_start.year)
        self.assertEqual(b.pending, 15)
        self.assertEqual(b.used, 0)
        
        self.assertEqual(self.hr.notifications.filter(kind="leave_awaiting_hr").count(), 1)
        
        r = self.api(self.hr).post(f"/api/leave-requests/{rid}/approve/", {"comment": "HR final approval"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "approved")
        
        b.refresh_from_db()
        self.assertEqual(b.pending, 0)
        self.assertEqual(b.used, 15)

class VisibilityAndReportTests(Base):
    def setUp(self):
        super().setUp()
        self.rid = self.apply().data["id"]

    def test_who_can_see_a_request(self):
        url = f"/api/leave-requests/{self.rid}/"
        for user in (self.staff, self.head, self.hr):
            self.assertEqual(self.api(user).get(url).status_code, 200, user.username)
        self.assertEqual(self.api(self.other).get(url).status_code, 403)

    def test_full_list_is_hr_only_and_mine_is_scoped(self):
        self.assertEqual(self.api(self.staff).get("/api/leave-requests/").status_code, 403)
        self.assertEqual(self.api(self.hr).get("/api/leave-requests/").data["count"], 1)
        self.assertEqual(self.api(self.other).get("/api/leave-requests/mine/").data["count"], 0)
        self.assertEqual(self.api(self.staff).get("/api/leave-requests/mine/").data["count"], 1)

    def test_report_json_and_csv(self):
        self.api(self.head).post(f"/api/leave-requests/{self.rid}/approve/", {}, format="json")
        q = f"?from={self.start}&to={self.end}"
        self.assertEqual(self.api(self.staff).get("/api/reports/leave/" + q).status_code, 403)
        r = self.api(self.hr).get("/api/reports/leave/" + q)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["totals"], {"requests": 1, "days": 5})
        self.assertEqual(r.data["awaiting_hr_review"], 1)
        self.assertEqual(r.data["by_department"][0]["name"], "Engineering")
        csv_resp = self.api(self.hr).get("/api/reports/leave/" + q + "&export=csv")
        self.assertEqual(csv_resp["Content-Type"], "text/csv")
        self.assertIn("Annual", csv_resp.content.decode())
        self.assertEqual(self.api(self.hr).get("/api/reports/leave/").status_code, 400)


class AccountTests(Base):
    def test_hr_creates_user_with_temp_password_and_forced_change(self):
        c = self.api(self.hr)
        r = c.post("/api/users/", {"username": "newbie", "email": "n@example.com", "first_name": "New",
                                   "department": self.dept.pk}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["roles"], ["staff"])
        temp = r.data["temporary_password"]

        anon = APIClient()
        login = anon.post("/api/auth/login/", {"username": "newbie", "password": temp}, format="json")
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.data["must_change_password"])
        anon.credentials(HTTP_AUTHORIZATION="Token " + login.data["token"])
        self.assertEqual(anon.get("/api/me/balances/").status_code, 403)
        self.assertEqual(anon.get("/api/auth/me/").status_code, 200)
        ch = anon.post("/api/auth/change-password/", {"old_password": temp, "new_password": "A-brand-new-Pass-4821"}, format="json")
        self.assertEqual(ch.status_code, 200, ch.data)
        anon.credentials(HTTP_AUTHORIZATION="Token " + ch.data["token"])
        self.assertEqual(anon.get("/api/me/balances/").status_code, 200)

    def test_bad_login_and_staff_cannot_manage_users(self):
        self.assertEqual(APIClient().post("/api/auth/login/", {"username": "staff", "password": "nope"}, format="json").status_code, 401)
        self.assertEqual(self.api(self.staff).get("/api/users/").status_code, 403)

    def test_only_admin_assigns_roles_and_staff_role_is_kept(self):
        self.assertEqual(self.api(self.hr).post(f"/api/users/{self.other.pk}/roles/", {"roles": ["hr_manager"]}, format="json").status_code, 403)
        admin = self.mk("boss")
        admin.groups.add(Group.objects.get(name=Roles.ADMIN))
        r = self.api(admin).post(f"/api/users/{self.other.pk}/roles/", {"roles": ["hr_manager"]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(sorted(r.data["roles"]), ["hr_manager", "staff"])
        self.assertEqual(self.api(admin).post(f"/api/users/{self.other.pk}/roles/", {"roles": ["invalid_role"]}, format="json").status_code, 400)

    def test_deleting_a_user_only_deactivates(self):
        self.assertEqual(self.api(self.hr).delete(f"/api/users/{self.other.pk}/").status_code, 204)
        self.other.refresh_from_db()
        self.assertFalse(self.other.is_active)


class PolicyTests(Base):
    def test_half_day(self):
        r = self.apply(start_date=self.start.isoformat(), end_date=self.start.isoformat(), day_part="morning")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["working_days"], 0.5)
        self.assertEqual(self.balance().pending, 0.5)
        self.assertEqual(self.apply(day_part="afternoon").status_code, 400)  # multi-day half day

    def test_min_notice_and_max_consecutive(self):
        self.annual.min_notice_days = 365
        self.annual.save()
        self.assertIn("notice", str(self.apply().data))
        self.annual.min_notice_days, self.annual.max_consecutive_days = 0, 3
        self.annual.save()
        self.assertIn("limited to 3", str(self.apply().data))
        self.annual.max_consecutive_days = 5
        self.annual.save()
        self.assertEqual(self.apply().status_code, 201)

    def test_blackout_periods(self):
        other_dept = Department.objects.create(name="Finance")
        BlackoutPeriod.objects.create(name="Audit", start_date=self.start, end_date=self.end, department=other_dept)
        self.assertEqual(self.apply().status_code, 201)  # other department's blackout does not apply
        self.api(self.staff).post(f"/api/leave-requests/{LeaveRequest.objects.get().pk}/cancel/", {}, format="json")
        BlackoutPeriod.objects.create(name="Exams", start_date=self.start, end_date=self.end, reason="Invigilation")
        r = self.apply()
        self.assertEqual(r.status_code, 400)
        self.assertIn("Exams", str(r.data))
        self.annual.ignore_blackouts = True
        self.annual.save()
        self.assertEqual(self.apply().status_code, 201)

    def test_preview_writes_nothing(self):
        body = {"leave_type": self.annual.pk, "start_date": self.start.isoformat(), "end_date": self.end.isoformat()}
        r = self.api(self.staff).post("/api/leave-requests/preview/", body, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["ok"])
        self.assertEqual((r.data["working_days"], r.data["balance_after"]), (5, 15))
        self.assertEqual(r.data["approver"], "head")
        self.annual.max_consecutive_days = 2
        self.annual.save()
        r = self.api(self.staff).post("/api/leave-requests/preview/", body, format="json")
        self.assertFalse(r.data["ok"])
        self.assertTrue(r.data["errors"])
        self.assertEqual(LeaveRequest.objects.count(), 0)
        self.assertEqual(LeaveBalance.objects.filter(user=self.staff, leave_type=self.annual, year=self.start.year).count(), 0)


class DelegationTests(Base):
    def delegate(self, user, delegate, days=(0, 7)):
        today = timezone.localdate()
        return self.api(user).post("/api/delegations/", {
            "delegate": delegate.pk, "start_date": (today + dt.timedelta(days=days[0])).isoformat(),
            "end_date": (today + dt.timedelta(days=days[1])).isoformat()}, format="json")

    def test_delegate_sees_queue_and_can_approve_on_behalf(self):
        rid = self.apply().data["id"]
        self.assertEqual(self.api(self.other).get("/api/leave-requests/pending-approval/").data["count"], 0)
        self.assertEqual(self.delegate(self.head, self.other).status_code, 201)
        self.assertEqual(self.api(self.other).get("/api/leave-requests/pending-approval/").data["count"], 1)
        r = self.api(self.other).post(f"/api/leave-requests/{rid}/approve/", {"comment": "ok"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIn("on behalf of head", r.data["actions"][-1]["comment"])
        self.assertTrue(self.api(self.other).get("/api/auth/me/").data["is_delegate"])

    def test_future_expired_and_revoked_delegations_do_not_count(self):
        rid = self.apply().data["id"]
        self.delegate(self.head, self.other, days=(3, 9))
        self.assertEqual(self.api(self.other).post(f"/api/leave-requests/{rid}/approve/", {}, format="json").status_code, 403)
        d = self.delegate(self.head, self.other, days=(0, 5)).data
        self.assertEqual(self.api(self.other).delete(f"/api/delegations/{d['id']}/").status_code, 403)  # not the delegator
        self.assertEqual(self.api(self.head).delete(f"/api/delegations/{d['id']}/").status_code, 204)
        self.assertEqual(self.api(self.other).post(f"/api/leave-requests/{rid}/approve/", {}, format="json").status_code, 403)

    def test_only_approvers_can_delegate_and_not_to_self(self):
        self.assertEqual(self.delegate(self.staff, self.other).status_code, 403)
        self.assertEqual(self.delegate(self.head, self.head).status_code, 400)


class InsightTests(Base):
    def test_team_overlap_for_approver_not_requester(self):
        rid = self.apply().data["id"]
        other_rid = self.apply(user=self.other).data["id"]
        mine = self.api(self.head).get(f"/api/leave-requests/{rid}/").data
        self.assertEqual([t["user_name"] for t in mine["team_overlap"]], ["other"])
        self.assertTrue(mine["can_decide"])
        self.assertEqual(self.api(self.staff).get(f"/api/leave-requests/{rid}/").data["team_overlap"], [])
        queue = self.api(self.head).get("/api/leave-requests/pending-approval/").data["results"]
        self.assertEqual({q["overlap_count"] for q in queue}, {1})
        self.assertIn(other_rid, [q["id"] for q in queue])

    def test_calendar_visibility(self):
        rid = self.apply().data["id"]
        q = f"?from={self.start}&to={self.end}"
        other_view = self.api(self.other).get("/api/calendar/" + q).data["events"]
        self.assertEqual(other_view, [])
        self.api(self.head).post(f"/api/leave-requests/{rid}/approve/", {}, format="json")
        ev = self.api(self.other).get("/api/calendar/" + q).data["events"]
        self.assertEqual(ev, [])
        head_events = self.api(self.head).get("/api/calendar/" + q).data["events"]
        self.assertEqual(len(head_events), 1)
        self.assertEqual(head_events[0]["leave_type"], "Annual")
        self.assertEqual(self.api(self.hr).get("/api/calendar/" + q).data["events"][0]["leave_type"], "Annual")
        own_events = self.api(self.staff).get("/api/calendar/" + q).data["events"]
        self.assertEqual(len(own_events), 1)
        self.assertEqual(own_events[0]["leave_type"], "Annual")
        
    def test_calendar_staff_sees_own_and_hr_sees_cross_department(self):
        rid = self.apply().data["id"]
        self.api(self.head).post(f"/api/leave-requests/{rid}/approve/", {}, format="json")
        q = f"?from={self.start}&to={self.end}"
        self.assertEqual(len(self.api(self.staff).get("/api/calendar/" + q).data["events"]), 1)
        finance = Department.objects.create(name="Finance")
        finance_staff = self.mk("finance_staff", department=finance)
        LeaveRequest.objects.create(user=finance_staff, leave_type=self.annual, start_date=self.start,
                                    end_date=self.end, working_days=5, status=LeaveRequest.Status.APPROVED)
        self.assertEqual(len(self.api(self.head).get("/api/calendar/" + q).data["events"]), 1)
        self.assertEqual(len(self.api(self.hr).get("/api/calendar/" + q).data["events"]), 2)

    def test_directory_search_cannot_escape_department(self):
        finance = Department.objects.create(name="Finance")
        outsider = self.mk("outsider", department=finance)
        result = self.api(self.staff).get("/api/directory/?search=outsider").data
        self.assertEqual(result, [])
        hr_result = self.api(self.hr).get("/api/directory/?search=outsider").data
        self.assertEqual([item["id"] for item in hr_result], [outsider.pk])

    def test_dashboard_sections_follow_role(self):
        self.apply()
        s = self.api(self.staff).get("/api/dashboard/").data
        self.assertNotIn("hr", s)
        self.assertEqual(s["me"]["pending"], 1)
        self.assertEqual(self.api(self.head).get("/api/dashboard/").data["approver"]["pending"], 1)
        h = self.api(self.hr).get("/api/dashboard/").data
        self.assertEqual(h["hr"]["pending_total"], 1)

    def test_escalation_moves_stale_request_to_department_head(self):
        rid = self.apply().data["id"]
        LeaveRequest.objects.filter(pk=rid).update(
            created_at=timezone.now() - dt.timedelta(days=10)
        )
        self.assertEqual(services.escalate_stale(7), (0, 1))
        self.assertEqual(
            self.hr.notifications.filter(
                kind="leave_escalated",
                leave_request_id=rid,
            ).count(),
            1,
        )
        self.assertEqual(services.escalate_stale(7), (0, 0))

    def test_ics_activity_directory_and_decided(self):
        rid = self.apply().data["id"]
        self.api(self.head).post(f"/api/leave-requests/{rid}/approve/", {}, format="json")
        ics = self.api(self.staff).get("/api/me/calendar.ics")
        self.assertEqual(ics["Content-Type"], "text/calendar")
        self.assertIn("BEGIN:VEVENT", ics.content.decode())
        self.assertEqual(self.api(self.staff).get("/api/activity/").status_code, 403)
        feed = self.api(self.hr).get("/api/activity/?action=approved").data
        self.assertEqual(feed["count"], 1)
        names = [d["full_name"] for d in self.api(self.staff).get("/api/directory/").data]
        self.assertNotIn("staff", names)
        self.assertIn("sup", names)
        self.assertEqual(self.api(self.head).get("/api/leave-requests/decided/").data["count"], 1)
        self.assertEqual(self.api(self.staff).get("/api/leave-requests/decided/").data["count"], 0)

class ReportExportTests(Base):
    def test_leave_report_and_csv_export(self):
        # 1. Create some data
        # Staff submits 5 days of Annual Leave
        rid1 = self.apply().data["id"]
        self.api(self.head).post(f"/api/leave-requests/{rid1}/approve/", {}, format="json")
        
        # Other staff submits 2 days of Sick Leave
        self.sick.requires_document = False
        self.sick.save()
        rid2 = self.apply(user=self.other, leave_type=self.sick.pk, start_date=self.start.isoformat(), end_date=(self.start + dt.timedelta(days=1)).isoformat()).data["id"]
        
        # 2. Test JSON Report
        url = f"/api/reports/leave/?from={self.start}&to={self.end}"
        r = self.api(self.hr).get(url)
        self.assertEqual(r.status_code, 200)
        
        data = r.data
        self.assertEqual(data["totals"]["requests"], 2)
        self.assertEqual(data["totals"]["days"], 7) # 5 + 2
        
        # Check by status (one approved, one pending)
        statuses = {item["status"]: item["days"] for item in data["by_status"]}
        self.assertEqual(statuses.get("approved"), 5)
        self.assertEqual(statuses.get("pending"), 2)
        
        # Check by leave type
        types = {item["name"]: item["days"] for item in data["by_leave_type"]}
        self.assertEqual(types.get("Annual"), 5)
        self.assertEqual(types.get("Sick"), 2)
        
        # Check by department
        depts = {item["name"]: item["days"] for item in data["by_department"]}
        self.assertEqual(depts.get("Engineering"), 7)
        
        # 3. Test CSV Export
        csv_url = f"/api/reports/leave/?from={self.start}&to={self.end}&export=csv"
        csv_r = self.api(self.hr).get(csv_url)
        self.assertEqual(csv_r.status_code, 200)
        self.assertEqual(csv_r["Content-Type"], "text/csv")
        
        content = csv_r.content.decode()
        # Check headers
        self.assertIn("Staff ID,Name,Department,Leave type,Start,End,Working days,Status", content)
        # Check data rows (staff, head, hr, other)
        self.assertIn("Annual", content)
        self.assertIn("Sick", content)
        self.assertIn("Engineering", content)

    def test_report_requires_hr(self):
        url = f"/api/reports/leave/?from={self.start}&to={self.end}"
        self.assertEqual(self.api(self.staff).get(url).status_code, 403)
        self.assertEqual(self.api(self.head).get(url).status_code, 403)