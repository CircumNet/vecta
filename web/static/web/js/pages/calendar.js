import { api, list } from "../api.js";
import { isHR, store } from "../state.js";
import { html, icon, iso, addDays, D, fmtRange, fmtDate, modal, statusBadge, delegate, fail, days, badge, avatar } from "../ui.js";

export default async function (root) {
  const now = new Date();
  let y = now.getFullYear(), m = now.getMonth(), dept = "", data = { events: [], holidays: [], blackouts: [] };
  const depts = isHR() ? await list("/departments/") : [];

  root.innerHTML = html`<div class="page-h"><div><h1>Team calendar</h1><p>See who is away. ${isHR() ? "You can see every department." : "Colleagues' leave types stay private."}</p></div>
    <div class="row wrap">${isHR() ? html`<select class="select" id="dept" style="width:auto"><option value="">All departments</option>${depts.map((d) => html`<option value="${d.id}">${d.name}</option>`)}</select>` : ""}
      <button class="btn" id="prev" aria-label="Previous month">${icon("left", 16)}</button><button class="btn" id="today">Today</button><button class="btn" id="next" aria-label="Next month">${icon("right", 16)}</button></div></div>
    <div class="card"><div class="row between wrap" style="margin-bottom:12px"><h2 id="label"></h2>
      <div class="row wrap small muted"><span class="ev mine">Mine</span><span class="ev">Colleague</span><span class="ev pending">Pending</span><span class="row gap-s"><i style="width:14px;height:14px;border-radius:3px;background:var(--bad-bg);display:inline-block;border:1px solid var(--border)"></i> Blackout</span></div></div>
      <div id="grid"></div></div>`;

  const start = () => { const f = new Date(y, m, 1); f.setDate(1 - ((f.getDay() + 6) % 7)); return f; };

  async function load() {
    const s = start(), from = iso(s), to = addDays(from, 41);
    root.querySelector("#label").textContent = new Date(y, m, 1).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
    data = await api("/calendar/", { params: { from, to, department: dept } });
    const byDay = {};
    for (const ev of data.events) for (let d = ev.start_date < from ? from : ev.start_date; d <= ev.end_date && d <= to; d = addDays(d, 1)) (byDay[d] ||= []).push(ev);
    const hol = Object.fromEntries(data.holidays.map((h) => [h.date, h.name]));
    const isBlack = (d) => data.blackouts.some((b) => b.start_date <= d && d <= b.end_date);
    const today = iso(new Date());
    const cells = [];
    for (let i = 0; i < 42; i++) {
      const d = addDays(from, i), dt = D(d), evs = byDay[d] || [], wk = dt.getDay() === 0 || dt.getDay() === 6;
      cells.push(html`<div class="day ${wk || hol[d] ? "off" : ""} ${dt.getMonth() !== m ? "out" : ""} ${isBlack(d) ? "black" : ""} ${d === today ? "today" : ""}" data-day="${d}" tabindex="0" role="button" aria-label="${fmtDate(d)}">
        <div class="n"><span>${dt.getDate()}</span>${evs.length > 3 ? html`<span class="small muted">${evs.length}</span>` : ""}</div>${hol[d] ? html`<div class="hol" title="${hol[d]}">${hol[d]}</div>` : ""}
        ${evs.slice(0, 3).map((e) => html`<div class="ev ${e.mine ? "mine" : e.status === "pending" ? "pending" : ""}" title="${e.name}${e.leave_type ? " · " + e.leave_type : ""}">${e.mine ? "Me" : e.name}${e.day_part !== "full" ? " ½" : ""}</div>`)}
        ${evs.length > 3 ? html`<div class="ev more">+${evs.length - 3} more</div>` : ""}</div>`);
    }
    root.querySelector("#grid").innerHTML = html`<div class="cal">${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((x) => html`<div class="dow">${x}</div>`)}${cells}</div>`;
    root._byDay = byDay; root._hol = hol;
  }

  function openDay(d) {
    const evs = root._byDay[d] || [], blk = data.blackouts.filter((b) => b.start_date <= d && d <= b.end_date);
    modal({ title: fmtDate(d, { weekday: "long", day: "numeric", month: "long", year: "numeric" }), body: html`
      ${root._hol[d] ? html`<p style="margin-bottom:10px">${badge(root._hol[d], "warn")} public holiday</p>` : ""}
      ${blk.map((b) => html`<div class="alert bad" style="margin-bottom:10px">${icon("alert")}<div><b>${b.name}</b> – leave is restricted${b.department_name ? ` for ${b.department_name}` : ""}.${b.reason ? " " + b.reason : ""}</div></div>`)}
      ${evs.length ? html`<div class="list">${evs.map((e) => html`<div class="row between"><div class="row">${avatar(e.name, "sm")}<div><b>${e.mine ? "You" : e.name}</b>
        <div class="small muted">${e.leave_type ? e.leave_type + " · " : ""}${fmtRange(e.start_date, e.end_date)}${e.department ? " · " + e.department : ""}</div></div></div>
        <div class="row">${statusBadge(e.status)}${e.detailed ? html`<a class="btn sm" href="#/leave/${e.id}" data-close>Open</a>` : ""}</div></div>`)}</div>` : html`<p class="muted">Nobody is away${root._hol[d] ? "" : " on this day"}.</p>`}` });
  }

  const shift = (n) => { m += n; if (m < 0) { m = 11; y--; } if (m > 11) { m = 0; y++; } load().catch(fail); };
  root.querySelector("#prev").onclick = () => shift(-1);
  root.querySelector("#next").onclick = () => shift(1);
  root.querySelector("#today").onclick = () => { y = now.getFullYear(); m = now.getMonth(); load().catch(fail); };
  root.querySelector("#dept")?.addEventListener("change", (e) => { dept = e.target.value; load().catch(fail); });
  delegate(root, "click", "[data-day]", (e, el) => openDay(el.dataset.day));
  delegate(root, "keydown", "[data-day]", (e, el) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDay(el.dataset.day); } });
  await load();
}
