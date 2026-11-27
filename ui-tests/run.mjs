import { JSDOM } from "jsdom";
const BASE = process.env.BASE || "http://127.0.0.1:8000";
const ROOT = new URL("../web/static/web/js/", import.meta.url).href;
const user = process.argv[2], paths = (process.argv[3] || "").split(",").filter(Boolean), flow = process.argv[4];
const errors = [];
const realFetch = globalThis.fetch;

const login = user === "anon" ? { token: null } : await (await realFetch(BASE + "/api/auth/login/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: user, password: "Passw0rd!123" }) })).json();
const page = await (await realFetch(BASE + "/")).text();
const dom = new JSDOM(page, { url: BASE + "/", pretendToBeVisual: true });
const w = dom.window;
if (login.token) w.localStorage.setItem("lms.token", login.token);
const def = (k, v) => Object.defineProperty(globalThis, k, { value: v, configurable: true, writable: true });
for (const k of ["window", "document", "localStorage", "location", "history"]) def(k, w[k]);
def("navigator", w.navigator); def("matchMedia", () => ({ matches: false })); def("HTMLElement", w.HTMLElement);
def("fetch", (u, o) => realFetch(new URL(u, BASE), o));
def("URL", URL); if (user === "anon") def("FormData", w.FormData); w.scrollTo = () => {};
const ce = console.error; console.error = (...a) => { errors.push(a.map(String).join(" ").slice(0, 300)); };
process.on("unhandledRejection", (e) => errors.push("UNHANDLED " + (e?.stack || e)));
w.addEventListener("error", (e) => errors.push("WINDOW ERROR " + e.message));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function settle() { for (let i = 0; i < 60; i++) { await sleep(50); const v = document.getElementById("view"); if (v && !v.querySelector(".skeleton") && v.textContent.trim().length) { await sleep(120); return; } } }
const view = () => document.getElementById("view");
globalThis.__h = { sleep, settle, view, w, errors, BASE, realFetch, token: login.token };

await import(ROOT + "app.js");
await sleep(600);
if (user !== "anon") await settle();
const out = [];
for (const p of paths) {
  const before = errors.length;
  location.hash = "#" + p; await settle();
  const t = view().textContent.replace(/\s+/g, " ").trim();
  const bad = !!view().querySelector(".alert.bad") || /failed to load/i.test(t);
  out.push(`${bad || errors.length > before ? "FAIL" : "ok  "} ${p.padEnd(18)} title="${document.getElementById("title").textContent}" ${t.slice(0, 90)}`);
}
console.log = (...a) => process.stdout.write(a.join(" ") + "\n");
console.log(`--- ${user} (nav: ${[...document.querySelectorAll("#nav a")].map((a) => a.textContent.trim().replace(/\d+$/, "")).join(", ")})`);
out.forEach((l) => console.log(l));
if (errors.length) { console.log("ERRORS:"); errors.slice(0, 8).forEach((e) => console.log("  " + e)); }
if (flow) { const m = await import("./flows/" + flow + ".mjs"); await m.default(globalThis.__h); }
if (errors.length && flow) { console.log("ERRORS:"); errors.slice(0, 8).forEach((e) => console.log("  " + e)); }
process.exit(0);
