import { api, auth } from "./api.js";
import { store, isHR, canApprove, canDelegate, setTheme, theme } from "./state.js";
import { html, icon, avatar, delegate, skeleton, alertBox, ago, toast } from "./ui.js";
import { startAuth, renderForceChange } from "./pages/auth.js";
import { logoMark } from "./logo.js";

const app = document.getElementById("app");

const NAV = [
  { h: "Workspace" },
  { path: "/dashboard", label: "Dashboard", icon: "home" },
  { path: "/apply", label: "Request leave", icon: "plus" },
  { path: "/leave", label: "My leave", icon: "list" },
  { path: "/calendar", label: "Team calendar", icon: "calendar" },
  { h: "Approvals", guard: canApprove },
  { path: "/approvals", label: "Approvals", icon: "inbox", guard: canApprove, badge: "pending" },
  { path: "/delegation", label: "Delegation", icon: "swap", guard: canDelegate },
  { h: "HR", guard: isHR },
  { path: "/hr/requests", label: "All requests", icon: "file", guard: isHR },
  { path: "/hr/reports", label: "Reports", icon: "chart", guard: isHR },
  { path: "/hr/people", label: "People", icon: "users", guard: isHR },
  { path: "/hr/policies", label: "Policies", icon: "sliders", guard: isHR },
  { path: "/hr/audit", label: "Audit log", icon: "shield", guard: isHR },
];

const ROUTES = [
  { path: "/dashboard", mod: "dashboard", title: "Dashboard" },
  { path: "/apply", mod: "apply", title: "Request leave" },
  { path: "/leave", mod: "myleave", title: "My leave" },
  { path: "/leave/:id", mod: "detail", title: "Leave request" },
  { path: "/calendar", mod: "calendar", title: "Team calendar" },
  { path: "/approvals", mod: "approvals", title: "Approvals", guard: canApprove },
  { path: "/delegation", mod: "delegation", title: "Delegation", guard: canDelegate },
  { path: "/hr/requests", mod: "hr_requests", title: "All requests", guard: isHR },
  { path: "/hr/reports", mod: "reports", title: "Reports", guard: isHR },
  { path: "/hr/people", mod: "people", title: "People", guard: isHR },
  { path: "/hr/policies", mod: "policies", title: "Policies", guard: isHR },
  { path: "/hr/audit", mod: "audit", title: "Audit log", guard: isHR },
  { path: "/account", mod: "account", title: "Account" },
];

function match(path) {
  const parts = path.split("/").filter(Boolean);
  for (const route of ROUTES) {
    const rp = route.path.split("/").filter(Boolean);
    if (rp.length !== parts.length) continue;
    const params = {};
    if (rp.every((seg, i) => seg.startsWith(":") ? ((params[seg.slice(1)] = parts[i]), true) : seg === parts[i])) return { route, params };
  }
  return null;
}

/* ---------------------------------------------------------------- shell */
function renderNav(active = "") {
  const items = NAV.filter((n) => !n.guard || n.guard());
  document.getElementById("nav").innerHTML = items.map((n) => n.h
    ? html`<div class="nav-h">${n.h}</div>`
    : html`<a href="#${n.path}" class="${active === n.path || (n.path !== "/dashboard" && active.startsWith(n.path + "/")) ? "active" : ""}">${icon(n.icon)}<span>${n.label}</span>${n.badge && store[n.badge] ? html`<span class="count">${store[n.badge]}</span>` : ""}</a>`).join("");
}

const sideUser = () => { const u = store.user; return html`<a class="side-user" href="#/account" style="text-decoration:none;color:inherit">${avatar(u.full_name)}<div style="min-width:0"><div style="font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${u.full_name}</div><div class="small muted">${u.job_title || u.roles.filter((r) => r !== "staff")[0] || "Staff"}</div></div></a>`; };

async function refreshUser() {
  store.user = await api("/auth/me/");
  const el = document.querySelector(".side-user");
  if (el) el.outerHTML = sideUser();
}

let navKeysBound = false;
const navOpen = () => {
  if (window.innerWidth > 900) return !document.body.classList.contains("sidebar-collapsed");
  return !!document.getElementById("sidebar")?.classList.contains("open");
};
function setNav(open) {
  const sb = document.getElementById("sidebar");
  if (!sb) return;
  const desktop = window.innerWidth > 900;
  if (desktop) {
    document.body.classList.toggle("sidebar-collapsed", !open);
    sb.classList.remove("open");
  } else {
    sb.classList.toggle("open", open);
    document.body.classList.toggle("nav-open", open);
  }
  const menu = document.getElementById("menu");
  menu?.setAttribute("aria-expanded", String(open));
  menu?.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  if (!open) menu?.focus?.();
}

function renderShell() {
  const u = store.user;
  app.innerHTML = html`<div class="shell">
    <aside class="sidebar" id="sidebar">
      <div class="brand">${logoMark(28)}<span>Vecta</span><button class="icon-btn side-close" id="side-close" aria-label="Close menu">${icon("x")}</button></div>
      <nav class="nav" id="nav" aria-label="Main"></nav>
      ${sideUser()}
    </aside>
    <div class="scrim" id="scrim" aria-hidden="true"></div>
    <div class="main">
      <header class="topbar">
        <button class="icon-btn menu-btn" id="menu" aria-label="Open menu" aria-controls="sidebar" aria-expanded="false">${icon("menu")}</button>
        <h2 id="title"></h2><span class="grow"></span>
        <div class="rel"><button class="icon-btn" id="bell" aria-label="Notifications">${icon("bell")}<span class="dot" id="bell-dot" hidden></span></button><div id="pop"></div></div>
        <button class="icon-btn" id="theme" aria-label="Toggle theme"></button>
        <button class="icon-btn" id="out" aria-label="Sign out" title="Sign out">${icon("logout")}</button>
      </header>
      <main class="content" id="view"></main>
    </div></div>`;
  document.getElementById("menu").onclick = () => setNav(!navOpen());
  document.getElementById("scrim").onclick = () => setNav(false);
  document.getElementById("side-close").onclick = () => setNav(false);
  // Any tap on a link in the drawer closes it, including the link for the page you are already on
  // (that one does not change the URL, so the router never runs).
  document.getElementById("sidebar").addEventListener("click", (e) => { if (e.target.closest("a") && window.innerWidth <= 900) setNav(false); });
  if (!navKeysBound) {
    navKeysBound = true;
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && window.innerWidth <= 900 && navOpen()) setNav(false); });
    window.addEventListener("resize", () => {
      const menu = document.getElementById("menu");
      if (window.innerWidth > 900) {
        document.getElementById("sidebar")?.classList.remove("open");
        document.body.classList.remove("nav-open");
        menu?.setAttribute("aria-expanded", String(navOpen()));
        menu?.setAttribute("aria-label", navOpen() ? "Close menu" : "Open menu");
      } else {
        document.body.classList.remove("sidebar-collapsed");
        document.getElementById("sidebar")?.classList.remove("open");
        document.body.classList.remove("nav-open");
        menu?.setAttribute("aria-expanded", "false");
        menu?.setAttribute("aria-label", "Open menu");
      }
    });
  }
  document.getElementById("out").onclick = logout;
  const paintTheme = () => (document.getElementById("theme").innerHTML = icon(document.documentElement.dataset.theme === "dark" || (theme() === "auto" && matchMedia?.("(prefers-color-scheme: dark)").matches) ? "sun" : "moon"));
  document.getElementById("theme").onclick = () => {
    const dark = document.documentElement.dataset.theme === "dark" || (theme() === "auto" && matchMedia?.("(prefers-color-scheme: dark)").matches);
    setTheme(dark ? "light" : "dark"); paintTheme();
  };
  paintTheme();
  document.getElementById("bell").onclick = (e) => { e.stopPropagation(); toggleNotifications(); };
  document.addEventListener("click", closePop);
  renderNav();
}

const closePop = () => { const p = document.getElementById("pop"); if (p) p.innerHTML = ""; };

async function toggleNotifications() {
  const pop = document.getElementById("pop");
  if (pop.innerHTML) return closePop();
  pop.innerHTML = html`<div class="pop"><div class="pop-h"><b>Notifications</b></div><div class="pop-scroll" style="padding:14px">${skeleton(2)}</div></div>`;
  const items = (await api("/notifications/")).slice(0, 20);
  pop.innerHTML = html`<div class="pop" id="pop-box"><div class="pop-h"><b>Notifications</b><button class="btn sm ghost" id="readall">Mark all read</button></div>
    <div class="pop-scroll">${items.length ? items.map((n) => html`<div class="item ${n.read_at ? "" : "unread"}" data-id="${n.id}" data-req="${n.leave_request || ""}">
      <div class="grow"><div>${n.message}</div><div class="small faint">${ago(n.created_at)}</div></div></div>`) : html`<div class="empty">You are all caught up.</div>`}</div></div>`;
  const box = document.getElementById("pop-box");
  box.addEventListener("click", (e) => e.stopPropagation());
  document.getElementById("readall").onclick = async () => { await api("/notifications/mark-read/", { method: "POST", body: {} }); store.unread = 0; paintBell(); closePop(); };
  delegate(box, "click", ".item", async (e, el) => {
    if (el.classList.contains("unread")) { await api("/notifications/mark-read/", { method: "POST", body: { ids: [+el.dataset.id] } }); store.unread = Math.max(0, store.unread - 1); paintBell(); }
    closePop();
    if (el.dataset.req) location.hash = "#/leave/" + el.dataset.req;
  });
}

function paintBell() {
  const dot = document.getElementById("bell-dot");
  if (!dot) return;
  dot.hidden = !store.unread; dot.textContent = store.unread > 9 ? "9+" : store.unread;
}

export async function refreshBadges() {
  try {
    store.unread = (await api("/notifications/", { params: { unread: 1 } })).length;
    if (canApprove()) store.pending = (await api("/leave-requests/pending-approval/")).count;
  } catch { /* badges are best effort */ }
  paintBell();
  renderNav(currentPath());
}

const currentPath = () => (location.hash.slice(1) || "/dashboard").split("?")[0];

/* ---------------------------------------------------------------- router */
let navId = 0;
async function route() {
  if (!store.user) return;
  const [path, qs = ""] = (location.hash.slice(1) || "/dashboard").split("?");
  const view = document.getElementById("view");
  if (!view) return;
  const found = match(path);
  renderNav(path);
  if (window.innerWidth <= 900) setNav(false);
  ++navId;
  if (!found) { document.getElementById("title").textContent = "Not found"; view.innerHTML = html`<div class="card stack">${alertBox("That page does not exist.", "warn", "alert")}<div><a class="btn" href="#/dashboard">Go to the dashboard</a></div></div>`; return; }
  document.getElementById("title").textContent = found.route.title;
  if (found.route.guard && !found.route.guard()) { view.innerHTML = html`<div class="card">${alertBox("You do not have access to this page.", "bad", "alert")}</div>`; return; }
  const id = navId;
  document.title = found.route.title + " · Vecta";
  const root = document.createElement("div");
  root.innerHTML = skeleton();
  view.replaceChildren(root);
  try {
    const mod = await import(`./pages/${found.route.mod}.js`);
    if (id !== navId) return;
    root.innerHTML = "";
    await mod.default(root, {
      params: found.params, query: Object.fromEntries(new URLSearchParams(qs)), refreshBadges, refreshUser,
      setTitle: (t) => { document.getElementById("title").textContent = t; },
    });
  } catch (e) {
    if (id !== navId) return;
    root.innerHTML = html`<div class="card stack">${alertBox(e.message || "This page failed to load.", "bad", "alert")}<div><button class="btn" id="retry">Try again</button></div></div>`;
    root.querySelector("#retry").onclick = route;
    console.error(e);
  }
  if (id === navId) window.scrollTo?.(0, 0);
}

/* ---------------------------------------------------------------- session */
async function logout() {
  try { await api("/auth/logout/", { method: "POST" }); } catch { /* ignore */ }
  auth.set(null); store.user = null; location.hash = ""; boot();
}

let started = false;
export async function boot() {
  try { store.config = await api("/auth/config/"); } catch { /* keep defaults */ }

  // Back from Google/Microsoft: the URL carries a one-time code, an error, or a "linked" flag.
  const qp = new URL(location.href).searchParams;
  const oauth = { code: qp.get("oauth_code"), error: qp.get("oauth_error"), linked: qp.get("oauth_linked") };
  if (oauth.code || oauth.error || oauth.linked) history.replaceState(null, "", "/" + location.hash);
  let problem = oauth.error || "";
  if (oauth.code) {
    try { auth.set((await api("/auth/oauth/exchange/", { method: "POST", body: { code: oauth.code } })).token); }
    catch (e) { problem = e.message; }
  }

  if (!auth.token) {
    return startAuth(app, {
      config: store.config, message: problem,
      onSession: (res) => { auth.set(res.token); boot(); },
    });
  }
  try { store.user = await api("/auth/me/"); }
  catch (e) {
    if (e.status === 0) { app.innerHTML = html`<div class="auth-form" style="min-height:100vh"><div class="auth-card">${alertBox(e.message, "bad", "alert")}<button class="btn" onclick="location.reload()">Retry</button></div></div>`; return; }
    auth.set(null); return boot();
  }
  if (store.user.must_change_password) return renderForceChange(app, { user: store.user, onDone: (token) => { auth.set(token); boot(); }, onLogout: logout });
  renderShell();
  if (!started) { window.addEventListener("hashchange", route); setInterval(refreshBadges, 60000); started = true; }
  if (oauth.linked) { toast("Account connected"); location.hash = "#/account?tab=security"; }
  else if (problem) { toast(problem, "bad"); location.hash = "#/account?tab=security"; }
  else if (!location.hash) location.hash = "#/dashboard"; else route();
  refreshBadges();
}

boot();
