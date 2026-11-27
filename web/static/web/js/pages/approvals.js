import { api } from "../api.js";
import { store } from "../state.js";
import { html, icon, table, pager, delegate, statusBadge, avatar, fmtRange, fmtDT, days, ago, askText, toast, fail, emptyState, badge } from "../ui.js";

export default async function (root, ctx) {
  let tab = "pending", page = 1;
  root.innerHTML = html`<div class="page-h"><div><h1>Approvals</h1><p>Decide on leave requests assigned to you${store.user.is_delegate ? " or delegated to you" : ""}.</p></div></div>
    <div class="tabs" id="tabs"><button class="on" data-tab="pending">Waiting for you</button><button data-tab="decided">Decided by you</button></div><div id="out"></div>`;
  const out = root.querySelector("#out");

  async function load() {
    if (tab === "pending") {
      const d = await api("/leave-requests/pending-approval/", { params: { page } });
      out.innerHTML = d.results.length ? html`<div class="stack">${d.results.map(card)}</div>${pager(page, d.count)}` : html`<div class="card">${emptyState("You are all caught up. Nothing is waiting for your decision.", "check")}</div>`;
    } else {
      const d = await api("/leave-requests/decided/", { params: { page } });
      out.innerHTML = html`<div class="card">${table([
        { h: "Staff", c: (r) => html`<div class="row">${avatar(r.user_name, "sm")}<b>${r.user_name}</b></div>` },
        { h: "Type", c: (r) => r.leave_type_name }, { h: "Dates", c: (r) => fmtRange(r.start_date, r.end_date) },
        { h: "Days", c: (r) => days(r.working_days) }, { h: "Decision", c: (r) => statusBadge(r.status) },
        { h: "Decided", c: (r) => html`<span class="muted">${fmtDT(r.decided_at)}</span>` },
      ], d.results, { href: (r) => "#/leave/" + r.id, empty: "You have not decided any requests yet." })}${pager(page, d.count)}</div>`;
    }
  }

  const card = (r) => html`<div class="card stack" data-card="${r.id}">
    <div class="row between wrap"><div class="row">${avatar(r.user_name)}<div><div style="font-weight:700">${r.user_name}</div><div class="small muted">${r.department || "No department"} · requested ${ago(r.created_at)}</div></div></div>
      <div class="row wrap">${badge(r.leave_type_name, "primary")}${r.approver !== store.user.id ? badge(`on behalf of ${r.approver_name}`, "info") : ""}</div></div>
    <div class="row wrap" style="gap:22px"><div><div class="small muted">Dates</div><b>${fmtRange(r.start_date, r.end_date)}</b></div><div><div class="small muted">Working days</div><b>${days(r.working_days)}</b></div>
      ${r.reason ? html`<div class="grow"><div class="small muted">Reason</div><div>${r.reason}</div></div>` : ""}</div>
    ${r.overlap_count ? html`<div class="alert warn">${icon("alert")}<div><b>${r.overlap_count} colleague${r.overlap_count === 1 ? " is" : "s are"} also away</b> on overlapping dates in this department.</div></div>` : ""}
    <div class="row wrap"><button class="btn ok sm" data-act="approve" data-id="${r.id}">${icon("check", 15)} Approve</button><button class="btn danger sm" data-act="reject" data-id="${r.id}">${icon("x", 15)} Reject</button>
      <a class="btn sm ghost" href="#/leave/${r.id}">View details ${icon("right", 14)}</a></div></div>`;

  delegate(root, "click", "[data-tab]", (e, el) => { tab = el.dataset.tab; page = 1; root.querySelectorAll("[data-tab]").forEach((b) => b.classList.toggle("on", b === el)); load().catch(fail); });
  delegate(root, "click", "[data-page]", (e, el) => { page = +el.dataset.page; load().catch(fail); });
  delegate(root, "click", "tr[data-href]", (e, el) => { location.hash = el.dataset.href; });
  delegate(root, "click", "[data-act]", async (e, el) => {
    const id = el.dataset.id, approve = el.dataset.act === "approve";
    const c = await askText(approve
      ? { title: "Approve request", label: "Comment (optional)", confirm: "Approve" }
      : { title: "Reject request", label: "Reason for rejecting", required: true, danger: true, confirm: "Reject", placeholder: "Explain so the requester can plan" });
    if (c === null) return;
    try {
      await api(`/leave-requests/${id}/${approve ? "approve" : "reject"}/`, { method: "POST", body: { comment: c } });
      toast(approve ? "Request approved" : "Request rejected");
      await load(); ctx.refreshBadges();
    } catch (ex) { fail(ex); }
  });
  await load();
}
