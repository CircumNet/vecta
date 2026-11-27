import { api, auth, download } from "../api.js";
import { store, setTheme, theme } from "../state.js";
import { html, icon, avatar, badge, alertBox, formModal, modal, confirmBox, toast, fail, delegate, fmtDT } from "../ui.js";
import { pwField, wirePasswords, codeHtml, wireCode, countdown, stopTimer } from "./auth.js";

const ROLE = { staff: "Staff", supervisor: "Supervisor", department_head: "Department head", hr_manager: "HR manager", admin: "Administrator" };
const TABS = [["profile", "Profile"], ["security", "Security"], ["preferences", "Preferences & data"]];

export default async function (root, ctx) {
  let tab = TABS.some((t) => t[0] === ctx.query.tab) ? ctx.query.tab : "profile";
  let me = await api("/auth/me/");
  const refresh = async () => { me = await api("/auth/me/"); Object.assign(store.user, me); ctx.refreshUser(); };

  root.innerHTML = html`<div class="page-h"><div><h1>Your account</h1><p>Your details, how you sign in, and your preferences.</p></div></div>
    <div class="tabs" id="tabs">${TABS.map(([k, l]) => html`<button class="${k === tab ? "on" : ""}" data-tab="${k}">${l}</button>`)}</div><div id="out"></div>`;
  const out = root.querySelector("#out");
  const show = () => { stopTimer(); ({ profile, security, preferences })[tab](); };

  /* ------------------------------------------------------------ profile */
  function profile() {
    out.innerHTML = html`<div class="split"><div class="stack">
      <form class="card form" id="pf" novalidate>
        <div class="profile-head">${avatar(me.full_name)}<div><h2>${me.full_name}</h2><div class="muted">@${me.username}</div></div></div>
        <div class="two"><div class="field"><label for="fn">First name</label><input class="input" id="fn" name="first_name" value="${me.first_name}" required></div>
          <div class="field"><label for="ln">Last name</label><input class="input" id="ln" name="last_name" value="${me.last_name}" required></div></div>
        <div class="field"><label for="ph">Phone <span class="muted">(optional)</span></label><input class="input" id="ph" name="phone" type="tel" value="${me.phone}" autocomplete="tel"></div>
        <div data-error></div><div><button class="btn primary" type="submit">Save changes</button></div></form>
      <div class="card"><div class="card-h"><h2>Email address</h2><button class="btn sm" data-act="email">Change email</button></div>
        <p class="row wrap" style="gap:8px">${me.email || html`<span class="muted">No email set</span>`} ${me.email ? (me.email_verified ? badge("Verified", "ok") : badge("Not verified", "warn")) : ""}</p>
        <p class="small muted" style="margin-top:6px">Leave updates and sign-in codes are sent here. Changing it needs a code sent to the new address.</p></div></div>
      <div class="card"><div class="card-h"><h2>Your place in the organisation</h2></div><dl class="kv">
        <dt>Department</dt><dd>${me.department_name || html`<span class="muted">Not set yet</span>`}</dd><dt>Job title</dt><dd>${me.job_title || "—"}</dd>
        <dt>Reports to</dt><dd>${me.supervisor_name || html`<span class="muted">Not set yet</span>`}</dd><dt>Staff ID</dt><dd>${me.staff_id || "—"}</dd>
        <dt>Roles</dt><dd class="chips">${me.roles.map((r) => badge(ROLE[r] || r, r === "staff" ? "" : "primary"))}</dd></dl>
        ${me.needs_setup ? html`<div style="margin-top:12px">${alertBox("HR has not placed you in a department or assigned an approver yet. You can request leave once they have.", "warn", "alert")}</div>` : html`<p class="small muted" style="margin-top:12px">These are managed by HR. Ask them if something is wrong.</p>`}</div></div>`;
    const f = out.querySelector("#pf"), err = f.querySelector("[data-error]");
    f.addEventListener("submit", async (e) => {
      e.preventDefault(); err.innerHTML = "";
      try { await api("/account/profile/", { method: "PATCH", body: { first_name: f.elements.first_name.value.trim(), last_name: f.elements.last_name.value.trim(), phone: f.elements.phone.value.trim() } }); await refresh(); toast("Profile saved"); profile(); }
      catch (ex) { err.innerHTML = alertBox(ex.message, "bad", "alert"); }
    });
  }

  function emailCodeModal(email, resendIn) {
    const m = modal({ title: "Confirm your new email", body: html`<p>We sent a 6-digit code to <b>${email}</b>.</p><div style="margin:14px 0">${codeHtml()}</div><div data-error></div>
      <div style="margin-top:10px"><button class="linkish" type="button" id="resend"></button></div>`, onClose: stopTimer });
    const err = m.el.querySelector("[data-error]"), btn = m.el.querySelector("#resend");
    let busy = false;
    const code = wireCode(m.el, async (value) => {
      if (busy) return; busy = true; err.innerHTML = "";
      try { await api("/account/email/confirm/", { method: "POST", body: { new_email: email, code: value } }); m.close(); await refresh(); toast("Email address updated"); show(); }
      catch (ex) { err.innerHTML = alertBox(ex.message, "bad", "alert"); code.reject(); }
      busy = false;
    });
    countdown(btn, resendIn);
    btn.addEventListener("click", async () => {
      try { const r = await api("/account/email/request/", { method: "POST", body: lastRequest }); countdown(btn, r.resend_in); err.innerHTML = alertBox("A new code is on its way.", "ok", "check"); }
      catch (ex) { err.innerHTML = alertBox(ex.message, "bad", "alert"); }
    });
  }
  let lastRequest = null;

  /* ------------------------------------------------------------ security */
  function security() {
    const providers = store.config.providers;
    out.innerHTML = html`<div class="split"><div class="stack">
      ${me.has_password ? html`<form class="card form" id="pw" novalidate><h2>Change password</h2>
          ${pwField("o", "old_password", "Current password")}${pwField("n", "new_password", "New password", { autocomplete: "new-password", meter: true, hint: "At least 8 characters. Avoid common passwords." })}${pwField("c", "confirm", "Confirm new password", { autocomplete: "new-password" })}
          <div data-error></div><div><button class="btn primary" type="submit">Update password</button></div></form>`
        : html`<form class="card form" id="pw" novalidate><h2>Set a password</h2><p class="muted">You sign in with an external account and have no password yet. Adding one gives you a second way in.</p>
          ${pwField("n", "new_password", "New password", { autocomplete: "new-password", meter: true })}${pwField("c", "confirm", "Confirm new password", { autocomplete: "new-password" })}
          <div data-error></div><div><button class="btn primary" type="submit">Set password</button></div></form>`}
      <div class="card"><h2 style="margin-bottom:4px">Sign-in methods</h2><div class="setting"><div><b>Email and password</b><div class="small muted">${me.has_password ? "Set" : "Not set"}</div></div>${me.has_password ? badge("On", "ok") : badge("Off")}</div>
        ${providers.length ? providers.map((p) => { const on = me.linked_providers.includes(p.id); return html`<div class="setting"><div><b>${p.name}</b><div class="small muted">${on ? "Connected. You can sign in with it." : "Sign in with one click using your " + p.name + " account."}</div></div>
          <button class="btn sm ${on ? "" : "primary"}" data-act="${on ? "unlink" : "link"}" data-p="${p.id}">${on ? "Disconnect" : "Connect"}</button></div>`; })
          : html`<p class="small muted" style="padding-top:10px">Google and Microsoft sign-in have not been set up by your administrator.</p>`}</div></div>
      <div class="card"><h2 style="margin-bottom:4px">Sessions</h2><div class="setting"><div><b>Last sign-in</b><div class="small muted">${me.last_login ? fmtDT(me.last_login) : "This is your first sign-in"}</div></div></div>
        <div class="setting"><div><b>Sign out other devices</b><div class="small muted">Use this if you signed in on a shared or lost device. You stay signed in here.</div></div><button class="btn sm" data-act="revoke">Sign out others</button></div></div></div>`;
    wirePasswords(out);
    const f = out.querySelector("#pw"), err = f.querySelector("[data-error]");
    f.addEventListener("submit", async (e) => {
      e.preventDefault(); err.innerHTML = "";
      try {
        if (f.elements.new_password.value !== f.elements.confirm.value) throw new Error("The two new passwords do not match.");
        const r = me.has_password
          ? await api("/auth/change-password/", { method: "POST", body: { old_password: f.elements.old_password.value, new_password: f.elements.new_password.value } })
          : await api("/account/password/set/", { method: "POST", body: { new_password: f.elements.new_password.value } });
        auth.set(r.token); await refresh(); toast(me.has_password ? "Password updated" : "Password set"); security();
      } catch (ex) { err.innerHTML = alertBox(ex.message, "bad", "alert"); }
    });
  }

  /* ------------------------------------------------------------ preferences */
  function preferences() {
    out.innerHTML = html`<div class="split"><div class="stack">
      <div class="card"><h2 style="margin-bottom:4px">Notifications</h2><div class="setting"><div><b>Email me about my leave</b><div class="small muted">Approvals, rejections and reminders. In-app notifications always stay on.</div></div>
        <label class="switch"><input type="checkbox" id="en" ${me.email_notifications ? "checked" : ""} aria-label="Email notifications"><span></span></label></div></div>
      <div class="card"><h2 style="margin-bottom:10px">Appearance</h2><div class="chips" id="theme">${[["auto", "Match my device"], ["light", "Light"], ["dark", "Dark"]].map(([v, l]) => html`<button class="chip ${theme() === v ? "on" : ""}" data-t="${v}">${l}</button>`)}</div></div></div>
      <div class="card"><h2 style="margin-bottom:4px">Your data</h2>
        <div class="setting"><div><b>Calendar file</b><div class="small muted">Approved and pending leave as an .ics file for Google, Outlook or Apple Calendar.</div></div><button class="btn sm" data-act="ics">${icon("download", 14)} .ics</button></div>
        <div class="setting"><div><b>Download my data</b><div class="small muted">Your profile, balances, leave requests and notifications as JSON.</div></div><button class="btn sm" data-act="export">${icon("download", 14)} JSON</button></div></div></div>`;
    out.querySelector("#en").addEventListener("change", async (e) => {
      try { await api("/account/profile/", { method: "PATCH", body: { email_notifications: e.target.checked } }); await refresh(); toast(e.target.checked ? "Email notifications on" : "Email notifications off"); }
      catch (ex) { e.target.checked = !e.target.checked; fail(ex); }
    });
    out.querySelector("#theme").addEventListener("click", (e) => { const b = e.target.closest("[data-t]"); if (!b) return; setTheme(b.dataset.t); out.querySelectorAll("[data-t]").forEach((c) => c.classList.toggle("on", c === b)); });
  }

  /* ------------------------------------------------------------ actions */
  delegate(root, "click", "[data-tab]", (e, el) => { tab = el.dataset.tab; root.querySelectorAll("[data-tab]").forEach((b) => b.classList.toggle("on", b === el)); show(); });
  delegate(root, "click", "[data-act]", async (e, el) => {
    const act = el.dataset.act;
    try {
      if (act === "email") {
        formModal({ title: "Change email address", submit: "Send code", intro: html`<p class="small muted" style="margin-bottom:10px">We will send a 6-digit code to the new address to prove it is yours.</p>`, fields: [
          { name: "new_email", label: "New email address", type: "email", required: true },
          ...(me.has_password ? [{ name: "password", label: "Current password", type: "password", required: true }] : [])],
          onSubmit: async (d) => { lastRequest = d; const r = await api("/account/email/request/", { method: "POST", body: d }); emailCodeModal(d.new_email, r.resend_in); } });
      }
      if (act === "link") { const r = await api(`/auth/oauth/${el.dataset.p}/start/`, { method: "POST", body: { mode: "link" } }); location.href = r.url; }
      if (act === "unlink") {
        if (!(await confirmBox({ title: "Disconnect this account?", message: "You will no longer be able to sign in with it.", confirm: "Disconnect", danger: true }))) return;
        await api(`/account/identities/${el.dataset.p}/`, { method: "DELETE" }); await refresh(); toast("Disconnected"); security();
      }
      if (act === "revoke") {
        if (!(await confirmBox({ title: "Sign out other devices?", message: "Every other browser and phone signed in to your account will be signed out.", confirm: "Sign them out" }))) return;
        auth.set((await api("/account/sessions/revoke/", { method: "POST" })).token); toast("Other devices signed out");
      }
      if (act === "ics") await download("/me/calendar.ics", "my-leave.ics");
      if (act === "export") await download("/account/export/", "vecta-my-data.json");
    } catch (ex) { fail(ex); }
  });
  show();
}
