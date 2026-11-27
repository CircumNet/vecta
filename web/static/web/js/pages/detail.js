import { api, download } from "../api.js";
import { store, isHR, go } from "../state.js";
import { html, icon, statusBadge, fmtRange, fmtDate, fmtDT, days, num, avatar, alertBox, badge, askText, formModal, toast, fail, delegate, cap } from "../ui.js";

const STEP = {
  submitted: ["send", "info", "submitted the request"], approved: ["check", "ok", "approved the request"],
  rejected: ["x", "bad", "rejected the request"], cancelled: ["x", "", "cancelled the request"],
  reassigned: ["swap", "warn", "reassigned the approver"], hr_reviewed: ["shield", "info", "completed the HR review"],
};
const PART = { full: "", morning: " (morning only)", afternoon: " (afternoon only)" };

export default async function (root, ctx) {
  const id = ctx.params.id;
  let cur = null, wired = false;
  async function render() {
    const r = await api(`/leave-requests/${id}/`);
    cur = r;
    const mine = r.user === store.user.id;
    ctx.setTitle(mine ? `${r.leave_type_name} leave` : `${r.user_name} · ${r.leave_type_name}`);
    const needsReview = isHR() && ["approved", "rejected"].includes(r.status) && !r.hr_reviewed_at;
    root.innerHTML = html`
      <div class="page-h"><div><a class="small" href="javascript:history.back()">${icon("left", 14)} Back</a>
        <h1 style="margin-top:6px">${r.leave_type_name} leave · ${fmtRange(r.start_date, r.end_date)}</h1>
        <p class="row wrap">${statusBadge(r.status)} <span>${days(r.working_days)}${PART[r.day_part]}</span>${r.hr_reviewed_at ? badge("HR reviewed", "info") : ""}</p></div>
        <div class="row wrap">${r.can_cancel ? html`<button class="btn" data-act="cancel">Cancel request</button>` : ""}
          ${isHR() && r.status === "pending" ? html`<button class="btn" data-act="reassign">${icon("swap", 15)} Reassign approver</button>` : ""}
          ${needsReview ? html`<button class="btn primary" data-act="review">${icon("shield", 15)} Complete HR review</button>` : ""}</div></div>

      <div class="split"><div class="stack">
        ${r.can_decide ? html`<div class="card stack" style="border-color:var(--primary)"><h2>Your decision</h2>
          <p class="muted">${r.user_name} is asking for ${days(r.working_days)}. ${r.team_overlap.length ? "Check the team clashes on the right before deciding." : "No colleagues from the department are away on these dates."}</p>
          <div class="row"><button class="btn ok" data-act="approve">${icon("check", 16)} Approve</button><button class="btn danger" data-act="reject">${icon("x", 16)} Reject</button></div></div>` : ""}

        <div class="card"><h2 style="margin-bottom:12px">Details</h2><dl class="kv">
          <dt>Requester</dt><dd class="row">${avatar(r.user_name, "sm")} ${r.user_name}${r.department ? html` <span class="muted">· ${r.department}</span>` : ""}</dd>
          <dt>Leave type</dt><dd>${r.leave_type_name}</dd><dt>Dates</dt><dd>${fmtRange(r.start_date, r.end_date)}${PART[r.day_part]}</dd>
          <dt>Working days</dt><dd>${days(r.working_days)}</dd><dt>Reason</dt><dd>${r.reason || html`<span class="muted">None given</span>`}</dd>
          <dt>Relief officer</dt><dd>${r.relief_officer_name || html`<span class="muted">None</span>`}</dd>
          <dt>Approver</dt><dd>${r.approver_name || "—"}</dd>
          ${r.has_attachment ? html`<dt>Document</dt><dd><button class="btn sm" data-act="file">${icon("clip", 14)} Download attachment</button></dd>` : ""}
          ${r.hr_reviewed_at ? html`<dt>HR review</dt><dd>${r.hr_reviewed_by_name} · ${fmtDT(r.hr_reviewed_at)}${r.hr_note ? html`<div class="quote">${r.hr_note}</div>` : ""}</dd>` : ""}</dl></div>

        <div class="card"><h2 style="margin-bottom:14px">History</h2><div class="tl">${r.actions.map((a) => {
          const [ic, kind, text] = STEP[a.action] || ["info", "", a.action];
          return html`<div><span class="pin ${kind}">${icon(ic, 14)}</span><div><b>${a.actor_name || "System"}</b> ${text}</div><div class="small faint">${fmtDT(a.created_at)}</div>${a.comment ? html`<div class="quote">${a.comment}</div>` : ""}</div>`;
        })}</div></div></div>

      <div class="stack">
        ${!mine && r.team_overlap.length ? html`<div class="card"><h2 class="row" style="margin-bottom:10px;color:var(--warn)">${icon("alert")} Team clashes</h2><p class="small muted" style="margin-bottom:8px">Colleagues in ${r.department} away on overlapping dates:</p>
          <div class="list">${r.team_overlap.map((t) => html`<div class="row between"><div><b>${t.user_name}</b><div class="small muted">${fmtRange(t.start_date, t.end_date)}</div></div>${statusBadge(t.status)}</div>`)}</div></div>`
          : !mine ? html`<div class="card">${alertBox("No department clashes on these dates.", "ok", "check")}</div>` : ""}
        ${r.requester_balance ? html`<div class="card"><h2 style="margin-bottom:10px">${mine ? "Your" : "Requester's"} ${r.leave_type_name} balance</h2><dl class="kv" style="grid-template-columns:110px 1fr">
          <dt>Entitled</dt><dd>${days(r.requester_balance.entitled)}</dd><dt>Used</dt><dd>${days(r.requester_balance.used)}</dd><dt>Pending</dt><dd>${days(r.requester_balance.pending)}</dd><dt>Available</dt><dd>${days(r.requester_balance.available)}</dd></dl></div>` : ""}
      </div></div>`;
    if (!wired) { wired = true; wire(); }
  }

  const after = async (msg) => { toast(msg); await render(); ctx.refreshBadges(); };
  function wire() {
    delegate(root, "click", "[data-act]", async (e, el) => {
      const act = el.dataset.act;
      try {
        if (act === "approve") { const c = await askText({ title: "Approve request", label: "Comment (optional)", confirm: "Approve" }); if (c !== null) { await api(`/leave-requests/${id}/approve/`, { method: "POST", body: { comment: c } }); await after("Request approved"); } }
        if (act === "reject") { const c = await askText({ title: "Reject request", label: "Reason for rejecting", required: true, danger: true, confirm: "Reject", placeholder: "Explain so the requester can plan" }); if (c !== null) { await api(`/leave-requests/${id}/reject/`, { method: "POST", body: { comment: c } }); await after("Request rejected"); } }
        if (act === "cancel") { const c = await askText({ title: "Cancel this request?", label: "Reason (optional)", confirm: "Cancel request", danger: true }); if (c !== null) { await api(`/leave-requests/${id}/cancel/`, { method: "POST", body: { comment: c } }); await after("Request cancelled"); } }
        if (act === "review") { const c = await askText({ title: "Complete HR review", label: "Note for the record (optional)", confirm: "Mark as reviewed" }); if (c !== null) { await api(`/leave-requests/${id}/review/`, { method: "POST", body: { comment: c } }); await after("Review recorded"); } }
        if (act === "file") await download(`/leave-requests/${id}/attachment/`, `leave-${id}-document`);
        if (act === "reassign") {
          const users = await api("/directory/", { params: { all: 1 } });
          formModal({ title: "Reassign approver", submit: "Reassign", fields: [
            { name: "approver", label: "New approver", type: "select", required: true, blank: "Choose a person…", options: users.filter((u) => u.id !== cur.user).map((u) => ({ value: u.id, label: `${u.full_name}${u.department_name ? " · " + u.department_name : ""}` })) },
            { name: "comment", label: "Reason", type: "textarea", placeholder: "e.g. Supervisor is on leave" }],
            onSubmit: async (d) => { await api(`/leave-requests/${id}/reassign/`, { method: "POST", body: d }); await after("Approver reassigned"); } });
        }
      } catch (ex) { fail(ex); }
    });
  }
  await render();
}
