import { ApiError, messages } from "./api.js";

/* ---------- safe templating: html`...` escapes every interpolation unless it is already html ---------- */
export class Safe { constructor(s) { this.s = s; } toString() { return this.s; } }
export const raw = (s) => new Safe(String(s));
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const part = (v) => v instanceof Safe ? v.s : Array.isArray(v) ? v.map(part).join("") : (v === null || v === undefined || v === false) ? "" : esc(v);
export const html = (s, ...v) => new Safe(s.reduce((o, str, i) => o + str + (i < v.length ? part(v[i]) : ""), ""));

/* ---------- icons ---------- */
const P = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z", plus: "M12 5v14M5 12h14",
  calendar: "M7 3v3M17 3v3M4 8h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z",
  list: "M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01", inbox: "M4 13l2-8h12l2 8M4 13v6h16v-6M4 13h5l1 2h4l1-2h5",
  users: "M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9.5 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM21 20v-1a4 4 0 0 0-3-3.9M16 4.1a3.5 3.5 0 0 1 0 6.8",
  chart: "M4 20V10M10 20V4M16 20v-7M22 20H2", sliders: "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6",
  bell: "M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0", check: "M5 12l5 5L20 7", x: "M6 6l12 12M18 6 6 18",
  clock: "M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", download: "M12 4v11M7 11l5 5 5-5M5 20h14",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3", shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  logout: "M9 21H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h4M16 17l5-5-5-5M21 12H9", menu: "M4 7h16M4 12h16M4 17h16",
  sun: "M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z", swap: "M7 4 3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7",
  edit: "M4 20h4L19 9l-4-4L4 16z", trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  left: "M15 6l-6 6 6 6", right: "M9 6l6 6-6 6", alert: "M12 9v4M12 17h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  clip: "M21 11l-8.5 8.5a5 5 0 0 1-7-7L14 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L15 7",
  info: "M12 11v5M12 8h.01M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", user: "M20 21v-1a5 5 0 0 0-5-5H9a5 5 0 0 0-5 5v1M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  key: "M15 7a4 4 0 1 1-3.9 5H3v-3h2v-2h3v2h3.1A4 4 0 0 1 15 7z", file: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5",
  send: "M22 2 11 13M22 2l-7 20-4-9-9-4z", copy: "M9 9h11v11H9zM5 15V5h10",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  eyeoff: "M3 3l18 18M10.6 6.1A9.8 9.8 0 0 1 12 6c6 0 10 6 10 6a17 17 0 0 1-3.2 3.9M6.6 6.6C3.8 8.4 2 12 2 12s4 7 10 7a9.7 9.7 0 0 0 4.4-1.1M9.9 9.9a3 3 0 0 0 4.2 4.2",
};
export const icon = (n, size = 18) => new Safe(`<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${P[n] || ""}"/></svg>`);

/* ---------- dates & numbers ---------- */
export const D = (s) => new Date(s.length <= 10 ? s + "T00:00:00" : s);
export const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const todayISO = () => iso(new Date());
export const addDays = (s, n) => { const d = D(s); d.setDate(d.getDate() + n); return iso(d); };
export const fmtDate = (s, o = { day: "numeric", month: "short", year: "numeric" }) => s ? D(s).toLocaleDateString("en-GB", o) : "—";
export const fmtRange = (a, b) => a === b ? fmtDate(a) : `${fmtDate(a, { day: "numeric", month: "short" })} – ${fmtDate(b)}`;
export const fmtDT = (s) => s ? new Date(s).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";
export const ago = (s) => {
  const m = Math.round((Date.now() - new Date(s)) / 60000);
  if (m < 1) return "just now"; if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60); if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24); return d < 30 ? `${d} d ago` : fmtDate(s);
};
export const num = (n) => +(+n).toFixed(1);
export const days = (n) => `${num(n)} day${num(n) === 1 ? "" : "s"}`;
export const cap = (s) => s ? s[0].toUpperCase() + s.slice(1) : "";

/* ---------- small building blocks ---------- */
const STATUS = { pending: ["warn", "Pending"], approved: ["ok", "Approved"], rejected: ["bad", "Rejected"], cancelled: ["", "Cancelled"] };
export const statusBadge = (s) => html`<span class="badge ${STATUS[s]?.[0] || ""}">${STATUS[s]?.[1] || cap(s)}</span>`;
export const badge = (text, kind = "") => html`<span class="badge ${kind}">${text}</span>`;
export const avatar = (name, cls = "") => {
  const ini = String(name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";
  return html`<span class="avatar ${cls}" aria-hidden="true">${ini}</span>`;
};
export const emptyState = (msg, ic = "inbox") => html`<div class="empty">${icon(ic, 34)}<div>${msg}</div></div>`;
export const alertBox = (msg, kind = "", ic = "info") => html`<div class="alert ${kind}">${icon(ic)}<div>${msg}</div></div>`;
export const skeleton = (n = 3) => html`<div class="stack">${Array.from({ length: n }, () => html`<div class="skeleton" style="height:64px"></div>`)}</div>`;

export function table(cols, rows, { empty = "Nothing here yet.", href } = {}) {
  if (!rows.length) return emptyState(empty);
  return html`<div class="table-wrap"><table class="table"><thead><tr>${cols.map((c) => html`<th class="${c.cls || ""}">${c.h}</th>`)}</tr></thead>
    <tbody>${rows.map((r) => html`<tr ${href ? html`class="click" data-href="${href(r)}"` : ""}>${cols.map((c) => html`<td class="${c.cls || ""}">${c.c(r)}</td>`)}</tr>`)}</tbody></table></div>`;
}
export const pager = (page, count, size = 25) => {
  if (count <= size) return count ? html`<div class="pager small">${count} result${count === 1 ? "" : "s"}</div>` : "";
  const last = Math.ceil(count / size);
  return html`<div class="pager"><span class="small">Page ${page} of ${last} · ${count} results</span>
    <span class="row"><button class="btn sm" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>${icon("left", 15)} Prev</button>
    <button class="btn sm" data-page="${page + 1}" ${page >= last ? "disabled" : ""}>Next ${icon("right", 15)}</button></span></div>`;
};

/* ---------- helpers ---------- */
export const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
export function delegate(root, type, selector, fn) {
  root.addEventListener(type, (e) => { const el = e.target.closest(selector); if (el && root.contains(el)) fn(e, el); });
}
export function toast(msg, kind = "") {
  const box = document.getElementById("toasts");
  const t = document.createElement("div");
  t.className = "toast " + kind; t.textContent = msg; box.append(t);
  setTimeout(() => t.remove(), kind ? 6000 : 3500);
}
export const fail = (e) => toast(e instanceof ApiError || e?.message ? e.message : "Something went wrong.", "bad");

/* ---------- modal & forms ---------- */
export function modal({ title, body = "", footer = "", wide = false, onClose }) {
  const wrap = document.createElement("div");
  wrap.className = "backdrop";
  wrap.innerHTML = html`<div class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${title}">
    <header><h3>${title}</h3><button class="icon-btn" data-close aria-label="Close">${icon("x")}</button></header>
    <div class="modal-body">${body}</div>${footer ? html`<footer>${footer}</footer>` : ""}</div>`;
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const close = () => { wrap.remove(); document.removeEventListener("keydown", onKey); onClose?.(); };
  wrap.addEventListener("mousedown", (e) => { if (e.target === wrap) close(); });
  wrap.addEventListener("click", (e) => { if (e.target.closest("[data-close]")) close(); });
  document.addEventListener("keydown", onKey);
  document.body.append(wrap);
  wrap.querySelector("input:not([type=hidden]),select,textarea")?.focus();
  return { el: wrap, close, body: wrap.querySelector(".modal-body") };
}

export function fieldHtml(f) {
  const v = f.value ?? "", id = "f_" + f.name;
  if (f.type === "checkbox") return html`<div class="field"><label class="check"><input type="checkbox" name="${f.name}" ${v ? "checked" : ""}><span>${f.label}${f.hint ? html`<br><small>${f.hint}</small>` : ""}</span></label></div>`;
  const common = html`id="${id}" name="${f.name}" ${f.required ? "required" : ""} ${f.disabled ? "disabled" : ""}`;
  let ctl;
  if (f.type === "select") ctl = html`<select class="select" ${common}>${f.blank !== undefined ? html`<option value="">${f.blank}</option>` : ""}${(f.options || []).map((o) => html`<option value="${o.value}" ${String(o.value) === String(v) ? "selected" : ""}>${o.label}</option>`)}</select>`;
  else if (f.type === "textarea") ctl = html`<textarea class="textarea" ${common} placeholder="${f.placeholder || ""}">${v}</textarea>`;
  else ctl = html`<input class="input" type="${f.type || "text"}" ${common} value="${v}" placeholder="${f.placeholder || ""}" ${f.min !== undefined ? html`min="${f.min}"` : ""} ${f.step ? html`step="${f.step}"` : ""} autocomplete="off">`;
  return html`<div class="field"><label for="${id}">${f.label}${f.required ? " *" : ""}</label>${ctl}${f.hint ? html`<small>${f.hint}</small>` : ""}<small class="field-err" data-err="${f.name}"></small></div>`;
}

export function readForm(form, fields) {
  const out = {};
  for (const f of fields) {
    const el = form.elements[f.name];
    if (!el) continue;
    if (f.type === "checkbox") out[f.name] = el.checked;
    else if (f.type === "number") out[f.name] = el.value === "" ? null : Number(el.value);
    else if (f.type === "select" || f.type === "date") out[f.name] = el.value === "" ? null : el.value;
    else out[f.name] = el.value;
  }
  return out;
}

export function showFormError(form, box, e) {
  let general = [];
  if (e?.data && typeof e.data === "object" && !Array.isArray(e.data)) {
    for (const [k, v] of Object.entries(e.data)) {
      const slot = form.querySelector(`[data-err="${k}"]`);
      if (slot) slot.textContent = messages(v).join(" "); else general.push(...messages(v));
    }
  } else general = [e?.message || "Something went wrong."];
  if (general.length) { box.textContent = general.join(" "); box.hidden = false; }
}

/** Modal with a generated form. onSubmit(data, modal) may throw ApiError to show field errors. */
export function formModal({ title, fields, value = {}, submit = "Save", intro = "", wide = false, danger = false, onSubmit }) {
  const fs = fields.map((f) => ({ ...f, value: f.value !== undefined ? f.value : value[f.name] }));
  const m = modal({
    title, wide,
    body: html`${intro}<form class="form" novalidate>${fs.map(fieldHtml)}<div class="form-error" hidden></div></form>`,
    footer: html`<button class="btn ghost" data-close>Cancel</button><button class="btn ${danger ? "danger" : "primary"}" data-submit>${submit}</button>`,
  });
  const form = m.el.querySelector("form"), btn = m.el.querySelector("[data-submit]"), box = m.el.querySelector(".form-error");
  const go = async () => {
    form.querySelectorAll(".field-err").forEach((x) => (x.textContent = ""));
    box.hidden = true; btn.disabled = true;
    try { await onSubmit(readForm(form, fs), m); m.close(); }
    catch (e) { showFormError(form, box, e); btn.disabled = false; }
  };
  btn.addEventListener("click", go);
  form.addEventListener("submit", (e) => { e.preventDefault(); go(); });
  return m;
}

/** Ask for a short text (rejection reason, HR note...). Resolves to the text, or null if dismissed. */
export function askText({ title, label, intro = "", confirm = "Confirm", danger = false, required = false, placeholder = "" }) {
  return new Promise((resolve) => {
    let settled = false;
    const done = (v) => { if (!settled) { settled = true; resolve(v); } };
    const m = modal({
      title, onClose: () => done(null),
      body: html`${intro}<div class="field"><label for="ask">${label}${required ? " *" : ""}</label><textarea class="textarea" id="ask" placeholder="${placeholder}"></textarea><small class="field-err"></small></div>`,
      footer: html`<button class="btn ghost" data-close>Cancel</button><button class="btn ${danger ? "danger" : "primary"}" data-ok>${confirm}</button>`,
    });
    const ta = m.el.querySelector("textarea");
    m.el.querySelector("[data-ok]").addEventListener("click", () => {
      const v = ta.value.trim();
      if (required && !v) { m.el.querySelector(".field-err").textContent = "This field is required."; return; }
      done(v); m.close();
    });
  });
}

export function confirmBox({ title, message, confirm = "Confirm", danger = false }) {
  return new Promise((resolve) => {
    let settled = false;
    const done = (v) => { if (!settled) { settled = true; resolve(v); } };
    const m = modal({
      title, onClose: () => done(false), body: html`<p>${message}</p>`,
      footer: html`<button class="btn ghost" data-close>Cancel</button><button class="btn ${danger ? "danger" : "primary"}" data-ok>${confirm}</button>`,
    });
    m.el.querySelector("[data-ok]").addEventListener("click", () => { done(true); m.close(); });
  });
}
