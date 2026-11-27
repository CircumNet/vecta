import { api } from "../api.js";
import { store, isHR } from "../state.js";
import { html, icon, fmtRange, fmtDate, days, num, statusBadge, avatar, emptyState, alertBox, badge } from "../ui.js";
import { ring, barChart, hbars, donut } from "../charts.js";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default async function (root) {
  const d = await api("/dashboard/");
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const balances = d.me.balances.filter((b) => b.entitled > 0);

  root.innerHTML = html`
    <div class="page-h"><div><h1>${greet}, ${store.user.first_name || store.user.username}</h1>
      <p>${new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p></div>
      <a class="btn primary" href="#/apply">${icon("plus", 16)} Request leave</a></div>
    <div class="stack">
    ${d.approver.pending ? alertBox(html`You have <b>${d.approver.pending}</b> leave request${d.approver.pending === 1 ? "" : "s"} waiting for your decision${d.approver.as_delegate ? " (including some delegated to you)" : ""}. <a href="#/approvals">Review now</a>`, "warn", "inbox") : ""}

    <section><div class="card-h"><h2>My leave balances · ${new Date().getFullYear()}</h2></div>
      <div class="grid auto">${balances.map((b) => html`<div class="card stat">${ring(b.available, b.entitled, { label: `${b.leave_type_name} balance` })}
        <div><div class="lbl">${b.leave_type_name}</div><div class="num">${num(b.available)}<span class="muted small"> / ${num(b.entitled)}</span></div>
        <div class="small muted">${num(b.used)} used${b.pending ? html` · ${num(b.pending)} pending` : ""}</div></div></div>`)}</div></section>

    <div class="split">
      <section class="card"><div class="card-h"><h2>Upcoming leave</h2><a class="small" href="#/leave">View all</a></div>
        ${d.me.upcoming.length ? html`<div class="list">${d.me.upcoming.map((r) => html`<a class="row between" href="#/leave/${r.id}" style="color:inherit;text-decoration:none">
          <div><div style="font-weight:650">${r.leave_type_name}</div><div class="small muted">${fmtRange(r.start_date, r.end_date)} · ${days(r.working_days)}</div></div>${statusBadge(r.status)}</a>`)}</div>`
        : emptyState("No upcoming leave. Time for a break?", "calendar")}</section>
      <section class="card"><div class="card-h"><h2>${isHR() ? "Away today" : "Your team today"}</h2>${badge(d.away_today.length, "info")}</div>
        ${d.away_today.length ? html`<div class="list">${d.away_today.map((a) => html`<div class="row">${avatar(a.name, "sm")}<div class="grow"><div style="font-weight:600">${a.name}</div><div class="small muted">${a.leave_type} · back after ${fmtDate(a.until, { day: "numeric", month: "short" })}</div></div></div>`)}</div>`
        : emptyState("Everyone is in today.", "users")}</section>
    </div>

    ${isHR() && d.hr ? hrSection(d.hr) : ""}
    </div>`;
}

function hrSection(h) {
  const months = MONTHS.map((m, i) => ({ label: m, value: +(h.monthly.find((x) => new Date(x.month + "T00:00:00").getMonth() === i)?.days || 0) }));
  return html`<section class="stack">${h.needs_setup ? alertBox(html`<b>${h.needs_setup}</b> new account${h.needs_setup === 1 ? " has" : "s have"} no department or supervisor yet, so they cannot request leave. <a href="#/hr/people?setup=1">Set them up</a>`, "warn", "users") : ""}<div class="card-h" style="margin:8px 0 0"><h2>Institution overview · ${h.year}</h2><a class="small" href="#/hr/reports">Full reports</a></div>
    <div class="grid g4">
      <div class="card kpi"><span class="lbl">Awaiting HR review</span><span class="num">${h.awaiting_review}</span><a href="#/hr/requests?reviewed=false">Review them</a></div>
      <div class="card kpi"><span class="lbl">Pending decisions</span><span class="num">${h.pending_total}</span><a href="#/hr/requests?status=pending">${h.stale_pending ? `${h.stale_pending} waiting over 7 days` : "None overdue"}</a></div>
      <div class="card kpi"><span class="lbl">On leave today</span><span class="num">${h.on_leave_today}</span><span class="small muted">of ${h.headcount} active staff</span></div>
      <div class="card kpi"><span class="lbl">Days taken this year</span><span class="num">${num(months.reduce((s, m) => s + m.value, 0))}</span><span class="small muted">approved working days</span></div>
    </div>
    <div class="grid g2"><div class="card"><div class="card-h"><h2>Leave taken per month</h2><span class="small muted">working days</span></div>${barChart(months)}</div>
      <div class="card"><div class="card-h"><h2>By department</h2><span class="small muted">working days</span></div>${hbars(h.by_department.map((x) => ({ label: x.name, value: +x.days })))}</div></div>
    <div class="card"><div class="card-h"><h2>By leave type</h2></div>${donut(h.by_type.map((x) => ({ label: x.name, value: +x.days })))}</div></section>`;
}
