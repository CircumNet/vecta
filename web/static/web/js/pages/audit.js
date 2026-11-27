import { api } from "../api.js";
import { html, table, pager, delegate, fmtDT, fmtRange, badge, fail, cap } from "../ui.js";

const KIND = { submitted: "info", approved: "ok", rejected: "bad", cancelled: "", reassigned: "warn", hr_reviewed: "primary" };

export default async function (root) {
  let action = "", page = 1;
  root.innerHTML = html`<div class="page-h"><div><h1>Audit log</h1><p>A permanent record of every action taken on every leave request.</p></div></div>
    <div class="card"><div class="filters"><div class="field"><label for="a">Action</label><select class="select" id="a"><option value="">All actions</option>${Object.keys(KIND).map((k) => html`<option value="${k}">${cap(k.replace("_", " "))}</option>`)}</select></div></div><div id="out"></div></div>`;
  const out = root.querySelector("#out");
  async function load() {
    const d = await api("/activity/", { params: { action, page } });
    out.innerHTML = html`${table([
      { h: "When", c: (a) => html`<span class="nowrap">${fmtDT(a.created_at)}</span>` }, { h: "Action", c: (a) => badge(cap(a.action.replace("_", " ")), KIND[a.action]) },
      { h: "By", c: (a) => a.actor_name }, { h: "Request", c: (a) => html`<b>${a.requester_name}</b><div class="small muted">${a.leave_type_name} · ${fmtRange(a.start_date, a.end_date)}</div>` },
      { h: "Comment", c: (a) => a.comment ? html`<span class="muted">${a.comment}</span>` : "" },
    ], d.results, { href: (a) => "#/leave/" + a.request_id, empty: "Nothing recorded yet." })}${pager(page, d.count)}`;
  }
  delegate(root, "change", "#a", (e, el) => { action = el.value; page = 1; load().catch(fail); });
  delegate(root, "click", "[data-page]", (e, el) => { page = +el.dataset.page; load().catch(fail); });
  delegate(root, "click", "tr[data-href]", (e, el) => { location.hash = el.dataset.href; });
  await load();
}
