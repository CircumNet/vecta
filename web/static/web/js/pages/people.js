import { api, list, listAll } from "../api.js";
import { store, isAdmin } from "../state.js";
import { html, icon, table, pager, delegate, formModal, modal, confirmBox, avatar, badge, toast, fail, debounce, emptyState } from "../ui.js";

const ROLE_LABEL = { hr_manager: "HR manager", admin: "Admin", department_head: "Department head" };

export default async function (root, ctx) {
  let tab = "users", page = 1, search = "", dept = "", setup = ctx?.query?.setup ? "1" : "", rows = [], depts = await list("/departments/"), people = await listAll("/users/");
  const personOpts = (skip) => people.filter((p) => p.is_active && p.id !== skip).map((p) => ({ value: p.id, label: `${p.full_name}${p.job_title ? " · " + p.job_title : ""}` }));
  const refreshPeople = async () => { people = await listAll("/users/"); depts = await list("/departments/"); };

  root.innerHTML = html`<div class="page-h"><div><h1>People</h1><p>Create staff accounts and manage departments.</p></div><div class="row" id="actions"></div></div>
    <div class="tabs"><button class="on" data-tab="users">Staff accounts</button><button data-tab="depts">Departments</button></div><div id="out"></div>`;
  const out = root.querySelector("#out"), actions = root.querySelector("#actions");

  async function loadUsers() {
    actions.innerHTML = html`<button class="btn primary" id="add-user">${icon("plus", 16)} Add staff member</button>`;
    const d = await api("/users/", { params: { page, search, department: dept, needs_setup: setup } });
    rows = d.results;
    if (!out.querySelector("#ufilters")) out.innerHTML = html`<div class="card"><div class="filters" id="ufilters"><div class="field grow"><label for="q">Search</label><input class="input" id="q" placeholder="Name, username or staff ID" value="${search}"></div>
      <div class="field"><label for="d">Department</label><select class="select" id="d"><option value="">All</option>${depts.map((x) => html`<option value="${x.id}" ${String(x.id) === dept ? "selected" : ""}>${x.name}</option>`)}</select></div><div class="field"><label class="check" style="padding-bottom:9px"><input type="checkbox" id="ns" ${setup ? "checked" : ""}> Needs setup only</label></div></div><div id="utable"></div></div>`;
    out.querySelector("#utable").innerHTML = html`${table([
      { h: "Name", c: (u) => html`<div class="row">${avatar(u.full_name, "sm")}<div><b>${u.full_name}</b> ${u.needs_setup ? badge("Needs setup", "warn") : ""}<div class="small muted">@${u.username}${u.job_title ? " · " + u.job_title : ""}</div></div></div>` },
      { h: "Staff ID", c: (u) => u.staff_id || "—" }, { h: "Department", c: (u) => u.department_name || "—" },
      { h: "Roles", c: (u) => html`<div class="chips">${u.roles.filter((r) => r !== "staff").map((r) => badge(ROLE_LABEL[r] || r, r === "admin" || r === "hr_manager" ? "primary" : "info"))}</div>` },
      { h: "Status", c: (u) => u.is_active ? badge("Active", "ok") : badge("Inactive") },
      { h: "", cls: "right nowrap", c: (u) => html`<button class="btn sm" data-edit="${u.id}">Edit</button> ${isAdmin() ? html`<button class="btn sm" data-roles="${u.id}">Roles</button> ` : ""}${u.id !== store.user.id ? html`<button class="btn sm ${u.is_active ? "" : "primary"}" data-toggle="${u.id}">${u.is_active ? "Deactivate" : "Activate"}</button>` : ""}` },
    ], rows, { empty: "No staff match your search." })}${pager(page, d.count)}`;
  }

  const userFields = (u) => [
    { name: "first_name", label: "First name", required: true }, { name: "last_name", label: "Last name", required: true },
    { name: "username", label: "Username", required: true }, { name: "email", label: "Email", type: "email", required: true, hint: "Notifications and password resets go here." },
    { name: "staff_id", label: "Staff ID" }, { name: "job_title", label: "Job title" },
    { name: "department", label: "Department", type: "select", blank: "No department", options: depts.map((d) => ({ value: d.id, label: d.name })) },
    ...(u ? [] : [{ name: "password", label: "Password", type: "password", hint: "Leave blank to generate a temporary one. The user must change it on first sign-in." }]),
  ];
  const clean = (d) => { const o = { ...d, staff_id: d.staff_id || null }; if (!o.password) delete o.password; return o; };


  async function loadDepts() {
    actions.innerHTML = html`<button class="btn primary" id="add-dept">${icon("plus", 16)} Add department</button>`;
    await refreshPeople();
    out.innerHTML = html`<div class="card">${table([{ h: "Department", c: (d) => html`<b>${d.name}</b>` }, { h: "Department head", c: (d) => d.head_name || html`<span class="muted">Not set</span>` },
      { h: "", cls: "right", c: (d) => html`<button class="btn sm" data-dedit="${d.id}">Edit</button>` }], depts, { empty: "No departments yet." })}</div>`;
  }
  const deptFields = [{ name: "name", label: "Name", required: true }, { name: "head", label: "Department head", type: "select", blank: "No head", options: [] }];

  const show = () => (tab === "users" ? loadUsers() : loadDepts()).catch(fail);

  delegate(root, "click", "[data-tab]", (e, el) => { tab = el.dataset.tab; page = 1; root.querySelectorAll("[data-tab]").forEach((b) => b.classList.toggle("on", b === el)); out.innerHTML = ""; show(); });
  delegate(root, "click", "[data-page]", (e, el) => { page = +el.dataset.page; show(); });
  delegate(root, "input", "#q", debounce((e, el) => { search = el.value; page = 1; show(); }, 300));
  delegate(root, "change", "#d", (e, el) => { dept = el.value; page = 1; show(); });
  delegate(root, "change", "#ns", (e, el) => { setup = el.checked ? "1" : ""; page = 1; show(); });

  delegate(root, "click", "#add-user", () => formModal({ title: "Add staff member", submit: "Create account", fields: userFields(null), wide: true,
    onSubmit: async (d, m) => {
      const u = await api("/users/", { method: "POST", body: clean(d) });
      await refreshPeople(); await show();
      if (u.temporary_password) {
        modal({ title: "Account created", body: html`<p>Share this temporary password with <b>${u.full_name}</b> securely. It is shown only once, and they must change it at first sign-in.</p>
          <div class="row" style="margin-top:12px"><input class="input" readonly value="${u.temporary_password}" id="tp" style="font-family:ui-monospace,monospace"><button class="btn" id="cp">${icon("copy", 15)} Copy</button></div>`, footer: html`<button class="btn primary" data-close>Done</button>` })
          .el.querySelector("#cp").onclick = () => navigator.clipboard?.writeText(u.temporary_password).then(() => toast("Copied"));
      } else toast("Account created");
    } }));
  delegate(root, "click", "[data-edit]", (e, el) => { const u = rows.find((r) => r.id === +el.dataset.edit); formModal({ title: `Edit ${u.full_name}`, submit: "Save changes", fields: userFields(u), value: u, wide: true,
    onSubmit: async (d) => { await api(`/users/${u.id}/`, { method: "PATCH", body: clean(d) }); toast("Saved"); await refreshPeople(); await show(); } }); });
  delegate(root, "click", "[data-toggle]", async (e, el) => {
    const u = rows.find((r) => r.id === +el.dataset.toggle);
    try {
      if (u.is_active) { if (!(await confirmBox({ title: `Deactivate ${u.full_name}?`, message: "They will be signed out and unable to log in. Their leave history is kept.", confirm: "Deactivate", danger: true }))) return; await api(`/users/${u.id}/`, { method: "DELETE" }); }
      else await api(`/users/${u.id}/`, { method: "PATCH", body: { is_active: true } });
      toast(u.is_active ? "Account deactivated" : "Account reactivated"); await refreshPeople(); await show();
    } catch (ex) { fail(ex); }
  });
  delegate(root, "click", "[data-roles]", (e, el) => { const u = rows.find((r) => r.id === +el.dataset.roles);
    formModal({ title: `Roles for ${u.full_name}`, submit: "Save roles", intro: html`<p class="small muted" style="margin-bottom:10px"> Everyone is staff. Department head status comes from department settings and is not assigned here.</p>`,
      fields: [{ name: "hr_manager", label: "HR manager", type: "checkbox", hint: "Sees every request, reviews decisions, runs reports and manages people and policies.", value: u.roles.includes("hr_manager") },
               { name: "admin", label: "Administrator", type: "checkbox", hint: "Everything HR can do, plus assigning roles.", value: u.roles.includes("admin") }],
      onSubmit: async (d) => { await api(`/users/${u.id}/roles/`, { method: "POST", body: { roles: Object.keys(d).filter((k) => d[k]) } }); toast("Roles updated"); await show(); } }); });

  delegate(root, "click", "#add-dept", () => formModal({ title: "Add department", fields: deptFields.map((f) => f.name === "head" ? { ...f, options: personOpts() } : f), submit: "Create",
    onSubmit: async (d) => { await api("/departments/", { method: "POST", body: d }); toast("Department created"); await show(); } }));
  delegate(root, "click", "[data-dedit]", (e, el) => { const d = depts.find((x) => x.id === +el.dataset.dedit);
    formModal({ title: `Edit ${d.name}`, value: d, fields: deptFields.map((f) => f.name === "head" ? { ...f, options: personOpts() } : f), submit: "Save",
      onSubmit: async (v) => { await api(`/departments/${d.id}/`, { method: "PATCH", body: v }); toast("Saved"); await show(); } }); });

  await show();
}
