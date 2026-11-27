import { api, list, download } from "../api.js";
import { html, icon, table, iso, addDays, num, days, fail, debounce, badge, alertBox } from "../ui.js";
import { barChart, hbars, donut } from "../charts.js";

const PRESETS = () => {
  const n = new Date(), y = n.getFullYear(), q = Math.floor(n.getMonth() / 3);
  return {
    year: ["This year", `${y}-01-01`, `${y}-12-31`],
    quarter: ["This quarter", iso(new Date(y, q * 3, 1)), iso(new Date(y, q * 3 + 3, 0))],
    month: ["This month", iso(new Date(y, n.getMonth(), 1)), iso(new Date(y, n.getMonth() + 1, 0))],
    last12: ["Last 12 months", addDays(iso(n), -365), iso(n)],
  };
};

export default async function (root) {
  const depts = await list("/departments/"), presets = PRESETS();
  const f = { from: presets.year[1], to: presets.year[2], department: "", status: "", preset: "year" };

  root.innerHTML = html`<div class="page-h"><div><h1>Reports</h1><p>Leave across the institution. Requests overlapping the range are included.</p></div>
    <div class="row no-print"><button class="btn" id="print">Print</button><button class="btn primary" id="csv">${icon("download", 16)} Export CSV</button></div></div>
    <div class="card" style="margin-bottom:16px"><div class="chips" id="presets" style="margin-bottom:12px">${Object.entries(presets).map(([k, p]) => html`<button class="chip ${k === f.preset ? "on" : ""}" data-p="${k}">${p[0]}</button>`)}</div>
      <form class="filters" id="filters" style="margin:0"><div class="field"><label for="from">From</label><input class="input" type="date" id="from" name="from" value="${f.from}"></div>
        <div class="field"><label for="to">To</label><input class="input" type="date" id="to" name="to" value="${f.to}"></div>
        <div class="field"><label for="department">Department</label><select class="select" id="department" name="department"><option value="">All</option>${depts.map((d) => html`<option value="${d.id}">${d.name}</option>`)}</select></div>
        <div class="field"><label for="status">Status</label><select class="select" id="status" name="status"><option value="">All</option><option value="approved">Approved</option><option value="pending">Pending</option><option value="rejected">Rejected</option><option value="cancelled">Cancelled</option></select></div></form></div>
    <div id="out"></div>`;
  const out = root.querySelector("#out");
  const params = () => ({ from: f.from, to: f.to, department: f.department, status: f.status });

  async function load() {
    if (!f.from || !f.to || f.to < f.from) { out.innerHTML = alertBox("Choose a valid date range.", "warn", "alert"); return; }
    const r = await api("/reports/leave/", { params: params() });
    const t = r.totals, avg = t.requests ? t.days / t.requests : 0;
    const month = (m) => new Date(m + "T00:00:00").toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
    out.innerHTML = html`<div class="stack"><div class="grid g4">
        <div class="card kpi"><span class="lbl">Requests</span><span class="num">${t.requests}</span></div>
        <div class="card kpi"><span class="lbl">Working days</span><span class="num">${num(t.days || 0)}</span></div>
        <div class="card kpi"><span class="lbl">Average length</span><span class="num">${num(avg)}</span><span class="small muted">days per request</span></div>
        <div class="card kpi"><span class="lbl">Awaiting HR review</span><span class="num">${r.awaiting_hr_review}</span><a href="#/hr/requests?reviewed=false">Open</a></div></div>
      <div class="grid g2"><div class="card"><div class="card-h"><h2>By month</h2><span class="small muted">working days, by start date</span></div>${r.by_month.length ? barChart(r.by_month.map((m) => ({ label: month(m.month), value: +m.days }))) : html`<div class="muted">No data for this period.</div>`}</div>
        <div class="card"><div class="card-h"><h2>By department</h2></div>${hbars(r.by_department.map((x) => ({ label: x.name || "Unassigned", value: +x.days })).sort((a, b) => b.value - a.value))}</div></div>
      <div class="grid g2"><div class="card"><div class="card-h"><h2>By leave type</h2></div>${donut(r.by_leave_type.map((x) => ({ label: x.name, value: +x.days })))}</div>
        <div class="card"><div class="card-h"><h2>By status</h2></div>${donut(r.by_status.map((x) => ({ label: x.status[0].toUpperCase() + x.status.slice(1), value: x.requests })))}</div></div>
      <div class="card"><div class="card-h"><h2>Most days taken</h2><span class="small muted">top ${r.by_staff.length}</span></div>${table([
        { h: "Staff", c: (s) => html`<b>${s.name}</b>` }, { h: "Requests", c: (s) => s.requests, cls: "right" }, { h: "Working days", c: (s) => days(s.days), cls: "right" }], r.by_staff.slice(0, 10), { empty: "No leave in this period." })}</div></div>`;
  }

  const reload = debounce(() => load().catch(fail), 120);
  root.querySelector("#presets").addEventListener("click", (e) => {
    const b = e.target.closest("[data-p]"); if (!b) return;
    const [, from, to] = presets[b.dataset.p]; f.from = from; f.to = to; f.preset = b.dataset.p;
    root.querySelector("#from").value = from; root.querySelector("#to").value = to;
    root.querySelectorAll("[data-p]").forEach((c) => c.classList.toggle("on", c === b)); reload();
  });
  root.querySelector("#filters").addEventListener("change", (e) => { f[e.target.name] = e.target.value; if (["from", "to"].includes(e.target.name)) root.querySelectorAll("[data-p]").forEach((c) => c.classList.remove("on")); reload(); });
  root.querySelector("#csv").onclick = () => download("/reports/leave/", `leave-report_${f.from}_${f.to}.csv`, { ...params(), export: "csv" }).catch(fail);
  root.querySelector("#print").onclick = () => window.print();
  await load();
}
