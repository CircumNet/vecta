import { api } from "../api.js";
import { store } from "../state.js";
import { html, icon, formModal, confirmBox, delegate, fmtRange, fmtDate, todayISO, addDays, toast, fail, emptyState, alertBox, badge, avatar } from "../ui.js";

export default async function (root) {
  async function render() {
    const rows = await api("/delegations/");
    const given = rows.filter((d) => d.delegator === store.user.id), got = rows.filter((d) => d.delegate === store.user.id);
    const today = todayISO();
    const status = (d) => d.start_date > today ? badge("Scheduled", "info") : d.end_date < today ? badge("Ended", "") : badge("Active now", "ok");
    root.innerHTML = html`<div class="page-h"><div><h1>Delegation</h1><p>Going away? Hand your approvals to a colleague so requests never get stuck.</p></div>
      <button class="btn primary" id="add">${icon("plus", 16)} Delegate my approvals</button></div>
      <div class="stack">${alertBox("While a delegation is active, your delegate sees your pending requests and can approve or reject them. Every decision is logged as made on your behalf. Requests still go to you first; delegation does not change who is assigned.", "", "info")}
      <div class="grid g2">
        <section class="card"><div class="card-h"><h2>I delegated to</h2></div>${given.length ? html`<div class="list">${given.map((d) => html`<div class="row between"><div class="row">${avatar(d.delegate_name, "sm")}<div><b>${d.delegate_name}</b><div class="small muted">${fmtRange(d.start_date, d.end_date)}${d.note ? " · " + d.note : ""}</div></div></div>
          <div class="row">${status(d)}<button class="btn sm" data-revoke="${d.id}">Revoke</button></div></div>`)}</div>` : emptyState("You have not delegated your approvals.", "swap")}</section>
        <section class="card"><div class="card-h"><h2>Delegated to me</h2></div>${got.length ? html`<div class="list">${got.map((d) => html`<div class="row between"><div class="row">${avatar(d.delegator_name, "sm")}<div><b>${d.delegator_name}</b><div class="small muted">${fmtRange(d.start_date, d.end_date)}${d.note ? " · " + d.note : ""}</div></div></div>${status(d)}</div>`)}</div>
          <p class="small muted" style="margin-top:10px">Their requests appear in your <a href="#/approvals">Approvals</a> while a delegation is active.</p>` : emptyState("Nobody has delegated to you.", "users")}</section></div></div>`;
  }

  delegate(root, "click", "#add", async () => {
    const people = await api("/directory/", { params: { all: 1 } });
    formModal({ title: "Delegate my approvals", submit: "Delegate", fields: [
      { name: "delegate", label: "Delegate to", type: "select", required: true, blank: "Choose a colleague…", options: people.map((p) => ({ value: p.id, label: `${p.full_name}${p.department_name ? " · " + p.department_name : ""}` })) },
      { name: "start_date", label: "From", type: "date", required: true, value: todayISO(), min: todayISO() },
      { name: "end_date", label: "Until", type: "date", required: true, value: addDays(todayISO(), 7), min: todayISO() },
      { name: "note", label: "Note (optional)", placeholder: "e.g. Annual leave" }],
      onSubmit: async (d) => { await api("/delegations/", { method: "POST", body: d }); toast("Delegation created"); await render(); } });
  });
  delegate(root, "click", "[data-revoke]", async (e, el) => {
    if (!(await confirmBox({ title: "Revoke delegation?", message: "Your delegate will no longer be able to decide on your behalf.", confirm: "Revoke", danger: true }))) return;
    try { await api(`/delegations/${el.dataset.revoke}/`, { method: "DELETE" }); toast("Delegation revoked"); await render(); } catch (ex) { fail(ex); }
  });
  await render();
}
