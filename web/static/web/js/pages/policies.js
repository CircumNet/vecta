import { api, list } from "../api.js";
import { html, icon, table, delegate, formModal, confirmBox, badge, fmtDate, fmtRange, toast, fail, todayISO } from "../ui.js";

export default async function (root) {
  let tab = "types", year = new Date().getFullYear();
  const depts = await list("/departments/");
  root.innerHTML = html`<div class="page-h"><div><h1>Leave policies</h1><p>The rules the system enforces automatically when staff request leave.</p></div><div class="row" id="actions"></div></div>
    <div class="tabs"><button class="on" data-tab="types">Leave types</button><button data-tab="holidays">Public holidays</button><button data-tab="blackouts">Blackout periods</button></div><div id="out"></div>`;
  const out = root.querySelector("#out"), actions = root.querySelector("#actions");
  let rows = [];

  const typeFields = [
    { name: "name", label: "Name", required: true },
    { name: "default_days", label: "Yearly entitlement (working days)", type: "number", required: true, min: 0 },
    { name: "min_notice_days", label: "Minimum notice (calendar days)", type: "number", required: true, min: 0, hint: "0 = can start any day, e.g. for sick leave." },
    { name: "max_consecutive_days", label: "Longest single request (working days)", type: "number", required: true, min: 0, hint: "0 = no limit." },
    { name: "carry_over_cap", label: "Max days carried into next year", type: "number", required: true, min: 0 },
    { name: "requires_document", label: "Requires a supporting document", type: "checkbox" },
    { name: "is_paid", label: "Paid leave", type: "checkbox" },
    { name: "ignore_blackouts", label: "Allowed during blackout periods", type: "checkbox", hint: "Typically sick, maternity and compassionate leave." },
  ];
  const blackoutFields = [{ name: "name", label: "Name", required: true, placeholder: "e.g. Semester examinations" },
    { name: "start_date", label: "From", type: "date", required: true }, { name: "end_date", label: "To", type: "date", required: true },
    { name: "department", label: "Applies to", type: "select", blank: "Whole institution", options: depts.map((d) => ({ value: d.id, label: d.name })) },
    { name: "reason", label: "Reason shown to staff", placeholder: "Optional" }];

  async function show() {
    if (tab === "types") {
      actions.innerHTML = html`<button class="btn primary" data-new="types">${icon("plus", 16)} Add leave type</button>`;
      rows = await list("/leave-types/");
      out.innerHTML = html`<div class="card">${table([
        { h: "Type", c: (t) => html`<b>${t.name}</b> ${t.is_active ? "" : badge("Inactive")}` }, { h: "Days / year", c: (t) => t.default_days },
        { h: "Rules", c: (t) => html`<div class="chips">${t.min_notice_days ? badge(`${t.min_notice_days}d notice`, "info") : ""}${t.max_consecutive_days ? badge(`max ${t.max_consecutive_days}d`, "info") : ""}${t.requires_document ? badge("document", "warn") : ""}${t.is_paid ? "" : badge("unpaid")}${t.ignore_blackouts ? badge("ignores blackouts", "ok") : ""}${t.carry_over_cap ? badge(`carry ${t.carry_over_cap}`, "primary") : ""}</div>` },
        { h: "", cls: "right nowrap", c: (t) => html`<button class="btn sm" data-edit="${t.id}">Edit</button> <button class="btn sm" data-off="${t.id}">${t.is_active ? "Retire" : "Restore"}</button>` }], rows)}</div>`;
    } else if (tab === "holidays") {
      actions.innerHTML = html`<button class="btn primary" data-new="holidays">${icon("plus", 16)} Add holiday</button>`;
      rows = await list("/holidays/", { year });
      out.innerHTML = html`<div class="card"><div class="chips" style="margin-bottom:12px">${[year - 1, year, year + 1].map((y) => html`<button class="chip ${y === year ? "on" : ""}" data-year="${y}">${y}</button>`)}</div>
        <p class="small muted" style="margin-bottom:10px">Public holidays are skipped when counting working days.</p>${table([{ h: "Date", c: (h) => fmtDate(h.date, { weekday: "short", day: "numeric", month: "long", year: "numeric" }) }, { h: "Holiday", c: (h) => html`<b>${h.name}</b>` },
        { h: "", cls: "right", c: (h) => html`<button class="btn sm" data-del="${h.id}">Delete</button>` }], rows, { empty: `No holidays set for ${year}.` })}</div>`;
    } else {
      actions.innerHTML = html`<button class="btn primary" data-new="blackouts">${icon("plus", 16)} Add blackout</button>`;
      rows = await list("/blackouts/");
      out.innerHTML = html`<div class="card"><p class="small muted" style="margin-bottom:10px">Staff cannot request leave that overlaps a blackout, except for leave types that allow it.</p>${table([
        { h: "Name", c: (b) => html`<b>${b.name}</b>${b.reason ? html`<div class="small muted">${b.reason}</div>` : ""}` }, { h: "Dates", c: (b) => fmtRange(b.start_date, b.end_date) }, { h: "Applies to", c: (b) => b.department_name || "Whole institution" },
        { h: "", cls: "right nowrap", c: (b) => html`<button class="btn sm" data-edit="${b.id}">Edit</button> <button class="btn sm" data-del="${b.id}">Delete</button>` }], rows, { empty: "No blackout periods." })}</div>`;
    }
  }
  const run = () => show().catch(fail);
  const API = { types: "/leave-types/", holidays: "/holidays/", blackouts: "/blackouts/" };
  const FIELDS = () => ({ types: typeFields, holidays: [{ name: "date", label: "Date", type: "date", required: true }, { name: "name", label: "Name", required: true }], blackouts: blackoutFields })[tab];

  delegate(root, "click", "[data-tab]", (e, el) => { tab = el.dataset.tab; root.querySelectorAll("[data-tab]").forEach((b) => b.classList.toggle("on", b === el)); out.innerHTML = ""; run(); });
  delegate(root, "click", "[data-year]", (e, el) => { year = +el.dataset.year; run(); });
  delegate(root, "click", "[data-new]", () => formModal({ title: "Add", fields: FIELDS(), value: tab === "types" ? { default_days: 20, min_notice_days: 0, max_consecutive_days: 0, carry_over_cap: 0, is_paid: true } : tab === "holidays" ? { date: todayISO() } : {}, submit: "Create",
    onSubmit: async (d) => { await api(API[tab], { method: "POST", body: d }); toast("Saved"); await show(); } }));
  delegate(root, "click", "[data-edit]", (e, el) => { const r = rows.find((x) => x.id === +el.dataset.edit);
    formModal({ title: `Edit ${r.name}`, fields: FIELDS(), value: r, submit: "Save changes", onSubmit: async (d) => { await api(`${API[tab]}${r.id}/`, { method: "PATCH", body: d }); toast("Saved"); await show(); } }); });
  delegate(root, "click", "[data-off]", async (e, el) => {
    const r = rows.find((x) => x.id === +el.dataset.off);
    try { if (r.is_active) { if (!(await confirmBox({ title: `Retire ${r.name}?`, message: "Staff can no longer request this type. Existing requests and balances are kept.", confirm: "Retire", danger: true }))) return; await api(`/leave-types/${r.id}/`, { method: "DELETE" }); }
      else await api(`/leave-types/${r.id}/`, { method: "PATCH", body: { is_active: true } });
      toast("Updated"); await show(); } catch (ex) { fail(ex); } });
  delegate(root, "click", "[data-del]", async (e, el) => {
    if (!(await confirmBox({ title: "Delete this entry?", message: "This cannot be undone.", confirm: "Delete", danger: true }))) return;
    try { await api(`${API[tab]}${el.dataset.del}/`, { method: "DELETE" }); toast("Deleted"); await show(); } catch (ex) { fail(ex); } });
  await show();
}
