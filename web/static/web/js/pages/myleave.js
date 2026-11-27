import { api, download } from "../api.js";
import { html, icon, table, pager, delegate, statusBadge, fmtRange, days, ago, fail } from "../ui.js";
import { go } from "../state.js";

const FILTERS = [["", "All"], ["pending", "Pending"], ["approved", "Approved"], ["rejected", "Rejected"], ["cancelled", "Cancelled"]];

export default async function (root) {
  let status = "", page = 1;
  root.innerHTML = html`<div class="page-h"><div><h1>My leave</h1><p>Everything you have requested, and where it stands.</p></div>
    <div class="row"><button class="btn" id="ics">${icon("download", 16)} Add to my calendar (.ics)</button><a class="btn primary" href="#/apply">${icon("plus", 16)} Request leave</a></div></div>
    <div class="card"><div class="chips" id="chips" style="margin-bottom:14px">${FILTERS.map(([v, l]) => html`<button class="chip ${v === status ? "on" : ""}" data-s="${v}">${l}</button>`)}</div><div id="out"></div></div>`;
  const out = root.querySelector("#out");

  async function load() {
    const d = await api("/leave-requests/mine/", { params: { status, page } });
    out.innerHTML = html`${table([
      { h: "Type", c: (r) => html`<b>${r.leave_type_name}</b>` },
      { h: "Dates", c: (r) => fmtRange(r.start_date, r.end_date) },
      { h: "Days", c: (r) => days(r.working_days) },
      { h: "Status", c: (r) => statusBadge(r.status) },
      { h: "Approver", c: (r) => r.approver_name || "—" },
      { h: "Submitted", c: (r) => html`<span class="muted">${ago(r.created_at)}</span>` },
    ], d.results, { href: (r) => "#/leave/" + r.id, empty: status ? `No ${status} requests.` : "You have not requested any leave yet." })}${pager(page, d.count)}`;
  }
  delegate(root, "click", "[data-s]", (e, el) => { status = el.dataset.s; page = 1; root.querySelectorAll("[data-s]").forEach((c) => c.classList.toggle("on", c === el)); load().catch(fail); });
  delegate(root, "click", "[data-page]", (e, el) => { page = +el.dataset.page; load().catch(fail); });
  delegate(root, "click", "tr[data-href]", (e, el) => { location.hash = el.dataset.href; });
  root.querySelector("#ics").onclick = () => import("../api.js").then((m) => m.download("/me/calendar.ics", "my-leave.ics")).catch(fail);
  await load();
}
