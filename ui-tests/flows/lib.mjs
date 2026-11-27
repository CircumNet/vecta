const h = () => globalThis.__h;
export const $ = (s) => document.querySelector(s);
export const text = () => document.body.textContent.replace(/\s+/g, " ");
export const ev = (el, t) => el.dispatchEvent(new (h().w.Event)(t, { bubbles: true }));
export const set = (sel, v) => { const el = $(sel); if (!el) throw new Error("missing " + sel); el.value = v; ev(el, "input"); ev(el, "change"); };
export const click = (sel) => { const el = typeof sel === "string" ? $(sel) : sel; if (!el) throw new Error("missing " + sel); el.dispatchEvent(new (h().w.MouseEvent)("click", { bubbles: true })); };
export const sleep = (ms) => h().sleep(ms);
export const results = [];
export const check = (name, cond, extra = "") => { results.push(cond); console.log(`${cond ? "PASS" : "FAIL"}  ${name}${cond ? "" : "  " + extra}`); };
export const until = async (fn, ms = 4000) => { for (let t = 0; t < ms; t += 80) { try { if (fn()) return true; } catch {} await sleep(80); } return false; };
export const ymd = (plusDays, monday = true) => { const d = new Date(); d.setDate(d.getDate() + plusDays); if (monday) d.setDate(d.getDate() + ((8 - d.getDay()) % 7)); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
export const askOk = async (txt) => { await until(() => $(".modal [data-ok]")); if (txt !== undefined) { $(".modal textarea").value = txt; } click(".modal [data-ok]"); };

import fs from "node:fs";
import path from "node:path";
const MAIL_DIR = process.env.MAIL_DIR || path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../sent_emails");
/** Wait for an email to `to` that arrived after `since`, and return the 6-digit code in it. */
export const mailCode = async (to, since = 0) => {
  let code = null;
  await until(() => {
    if (!fs.existsSync(MAIL_DIR)) return false;
    const files = fs.readdirSync(MAIL_DIR).map((f) => ({ f, t: fs.statSync(path.join(MAIL_DIR, f)).mtimeMs })).filter((x) => x.t >= since).sort((a, b) => b.t - a.t);
    for (const { f } of files) {
      const body = fs.readFileSync(path.join(MAIL_DIR, f), "utf8");
      if (new RegExp("^To: .*" + to.replace(/[.+]/g, "\\$&"), "im").test(body)) { const m = body.match(/Your code is (\d{6})/); if (m) { code = m[1]; return true; } }
    }
    return false;
  }, 8000);
  return code;
};
export const submit = (sel) => $(sel).dispatchEvent(new (h().w.Event)("submit", { bubbles: true, cancelable: true }));
export const typeCode = (code) => { const ins = document.querySelectorAll("#code input, .modal #code input"); [...code].forEach((d, i) => { ins[i].value = d; ev(ins[i], "input"); }); };
