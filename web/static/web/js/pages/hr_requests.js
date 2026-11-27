import { api, list, download } from "../api.js";
import { html, icon, table, pager, delegate, statusBadge, badge, avatar, fmtRange, days, askText, toast, fail, debounce } from "../ui.js";

export default async function (root, ctx) {
  const [depts, types] = await Promise.all([list("/departments/"), list("/leave-types/")]);
  const f = { status: ctx.query.status || "", department: "", leave_type: "", from: "", to: "", reviewed: ctx.query.reviewed || "" };
  let page = 1, rows = [];
  const sel = (name, label, opts) => html`<div class="field"><label for="f_${name}">${label}</label><select class="select" id="f_${name}" name="${name}"><option value="">All</option>${opts.map(([v, l]) => html`<option value="${v}" ${String(f[name]) === String(v) ? "selected" : ""}>${l}</option>`)}</select></div>`;

  root.innerHTML = html`<div class="page-h"><div><h1>All requests</h1><p>Every leave request in the institution. Complete the HR review once a decision is made.</p></div>
    <button class="btn" id="csv">${icon("download", 16)} Export CSV</button></div>
    <div class="card"><form class="filters" id="filters">
      ${sel("status", "Status", [["pending", "Pending"], ["approved", "Approved"], ["rejected", "Rejected"], ["cancelled", "Cancelled"]])}
      ${sel("reviewed", "HR review", [["false", "Awaiting review"], ["true", "Reviewed"]])}
      ${sel("department", "Department", depts.map((d) => [d.id, d.name]))}${sel("leave_type", "Leave type", types.map((t) => [t.id, t.name]))}
      <div class="field"><label for="f_from">From</label><input class="input" type="date" id="f_from" name="from"></div>
      <div class="field"><label for="f_to">To</label><input class="input" type="date" id="f_to" name="to"></div></form><div id="out"></div></div>`;
  const out = root.querySelector("#out");

  async function load() {
    const d = await api("/leave-requests/", { params: { ...f, page } });
    rows = d.results;
    out.innerHTML = html`${table([
      { h: "Staff", c: (r) => html`<div class="row">${avatar(r.user_name, "sm")}<div><b>${r.user_name}</b><div class="small muted">${r.department || "—"}</div></div></div>` },
      { h: "Type", c: (r) => r.leave_type_name }, { h: "Dates", c: (r) => fmtRange(r.start_date, r.end_date) }, { h: "Days", c: (r) => days(r.working_days) },
      { h: "Status", c: (r) => statusBadge(r.status) }, { h: "Approver", c: (r) => r.approver_name || "—" },
      { h: "HR review", c: (r) => r.hr_reviewed_at ? badge("Reviewed", "info") : ["approved", "rejected"].includes(r.status) ? html`<button class="btn sm primary" data-review="${r.id}">Review</button>` : html`<span class="faint">—</span>` },
    ], rows, { href: (r) => "#/leave/" + r.id, empty: "No requests match these filters." })}${pager(page, d.count)}`;
  }

  root.querySelector("#filters").addEventListener("change", debounce((e) => { f[e.target.name] = e.target.value; page = 1; load().catch(fail); }, 80));
  delegate(root, "click", "[data-page]", (e, el) => { page = +el.dataset.page; load().catch(fail); });
  delegate(root, "click", "[data-review]", async (e, el) => {
    e.stopPropagation();
    const note = await askText({ title: "Complete HR review", label: "Note for the record (optional)", confirm: "Mark as reviewed" });
    if (note === null) return;
    try { await api(`/leave-requests/${el.dataset.review}/review/`, { method: "POST", body: { comment: note } }); toast("Review recorded"); await load(); } catch (ex) { fail(ex); }
  });
  delegate(root, "click", "tr[data-href]", (e, el) => { if (!e.target.closest("button,a")) location.hash = el.dataset.href; });
  root.querySelector("#csv").onclick = () => {
    const y = new Date().getFullYear();
    download("/reports/leave/", "leave-requests.csv", { from: f.from || `${y}-01-01`, to: f.to || `${y}-12-31`, department: f.department, status: f.status, export: "csv" }).catch(fail);
  };
  await load();
}
