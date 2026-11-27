import { api, list, ApiError } from "../api.js";
import { go } from "../state.js";
import { html, icon, toast, fail, debounce, days, num, fmtRange, alertBox, todayISO, badge } from "../ui.js";

export default async function (root) {
  const [types, colleagues] = await Promise.all([list("/leave-types/"), api("/directory/")]);
  const active = types.filter((t) => t.is_active);
  if (!active.length) { root.innerHTML = html`<div class="card">${alertBox("No leave types are configured yet. Please contact HR.", "warn")}</div>`; return; }
  const today = todayISO();

  root.innerHTML = html`<div class="page-h"><div><h1>Request leave</h1><p>Your approver is notified immediately. The summary updates as you type.</p></div></div>
    <div class="split"><form class="card form" id="lf" novalidate>
      <div class="field"><label for="leave_type">Leave type</label>
        <select class="select" id="leave_type" name="leave_type">${active.map((t) => html`<option value="${t.id}">${t.name}</option>`)}</select><div class="chips" id="rules"></div></div>
      <div class="two"><div class="field"><label for="start_date">From</label><input class="input" type="date" id="start_date" name="start_date" min="${today}" required></div>
        <div class="field"><label for="end_date">To</label><input class="input" type="date" id="end_date" name="end_date" min="${today}" required></div></div>
      <div class="field" id="part-box"><label for="day_part">Duration</label><select class="select" id="day_part" name="day_part"><option value="full">Full day(s)</option><option value="morning">Morning only (half day)</option><option value="afternoon">Afternoon only (half day)</option></select><small>Half days are available when you pick a single date.</small></div>
      <div class="field"><label for="relief_officer">Relief officer <span class="muted">(optional)</span></label>
        <select class="select" id="relief_officer" name="relief_officer"><option value="">Nobody in particular</option>${colleagues.map((c) => html`<option value="${c.id}">${c.full_name}${c.job_title ? " · " + c.job_title : ""}</option>`)}</select></div>
      <div class="field"><label for="reason">Reason <span class="muted">(optional)</span></label><textarea class="textarea" id="reason" name="reason" maxlength="2000" placeholder="Anything your approver should know?"></textarea></div>
      <div class="field"><label for="attachment" id="att-label">Supporting document <span class="muted">(optional · PDF, JPG or PNG up to 5 MB)</span></label><input class="input" type="file" id="attachment" name="attachment" accept=".pdf,.jpg,.jpeg,.png"></div>
      <div id="form-error"></div></form>
      <aside class="card stack" style="position:sticky;top:76px"><h2>Summary</h2><div id="sum"></div>
        <button class="btn primary" id="submit" disabled>${icon("send", 16)} Submit request</button></aside></div>`;

  const f = root.querySelector("#lf"), $ = (id) => root.querySelector("#" + id), F = (n) => f.elements[n];
  const typeOf = () => active.find((t) => String(t.id) === $("leave_type").value);
  let seq = 0, lastOk = false;

  function paintRules() {
    const t = typeOf(), c = [];
    if (t.min_notice_days) c.push(badge(`${t.min_notice_days}+ days notice`, "info"));
    if (t.max_consecutive_days) c.push(badge(`max ${t.max_consecutive_days} days`, "info"));
    if (t.requires_document) c.push(badge("document required", "warn"));
    if (!t.is_paid) c.push(badge("unpaid", ""));
    if (t.ignore_blackouts) c.push(badge("allowed in blackout periods", "ok"));
    $("rules").innerHTML = html`${c}`;
    $("att-label").innerHTML = t.requires_document ? html`Supporting document * <span class="muted">(PDF, JPG or PNG up to 5 MB)</span>` : html`Supporting document <span class="muted">(optional · PDF, JPG or PNG up to 5 MB)</span>`;
  }

  const refresh = debounce(async () => {
    const s = F('start_date').value, e = F('end_date').value, box = $("sum"), id = ++seq;
    const single = s && s === e;
    $("day_part").disabled = !single;
    if (!single) $("day_part").value = "full";
    if (!s || !e) { box.innerHTML = html`<p class="muted">Pick your dates to see how many working days this uses and what is left afterwards.</p>`; lastOk = false; $("submit").disabled = true; return; }
    try {
      const body = { leave_type: +$("leave_type").value, start_date: s, end_date: e, day_part: $("day_part").value };
      if ($("relief_officer").value) body.relief_officer = +$("relief_officer").value;
      const r = await api("/leave-requests/preview/", { method: "POST", body });
      if (id !== seq) return;
      lastOk = r.ok;
      const needDoc = typeOf().requires_document && !F('attachment').files.length;
      box.innerHTML = html`<div class="stat"><div><div class="num" style="font-size:2.2rem">${r.working_days === null ? "–" : num(r.working_days)}</div><div class="lbl">working day${num(r.working_days) === 1 ? "" : "s"}</div></div></div>
        <dl class="kv" style="grid-template-columns:120px 1fr"><dt>Dates</dt><dd>${fmtRange(s, e)}</dd>
          <dt>Balance now</dt><dd>${r.balance_available === null ? "–" : days(r.balance_available)}</dd>
          <dt>After this</dt><dd>${r.balance_after === null ? "–" : days(r.balance_after)}</dd>
          <dt>Approver</dt><dd>${r.approver || "Not set"}</dd></dl>
        ${r.ok ? alertBox(needDoc ? "Looks good. Attach the required document to continue." : "All checks passed. Ready to submit.", needDoc ? "warn" : "ok", needDoc ? "clip" : "check")
               : r.errors.map((m) => alertBox(m, "bad", "alert"))}`;
      $("submit").disabled = !(r.ok && !needDoc);
    } catch (ex) { box.innerHTML = alertBox(ex.message, "bad", "alert"); $("submit").disabled = true; }
  }, 200);

  f.addEventListener("change", (e) => {
    if (e.target.name === "start_date" && F('end_date').value < F('start_date').value) F('end_date').value = F('start_date').value;
    if (e.target.name === "start_date" && !F('end_date').value) F('end_date').value = F('start_date').value;
    if (e.target.name === "leave_type") paintRules();
    refresh();
  });
  f.addEventListener("submit", (e) => e.preventDefault());

  $("submit").addEventListener("click", async () => {
    const fd = new FormData();
    for (const k of ["leave_type", "start_date", "end_date", "day_part", "reason"]) fd.append(k, F(k).value);
    if (F('relief_officer').value) fd.append("relief_officer", F('relief_officer').value);
    if (F('attachment').files[0]) fd.append("attachment", F('attachment').files[0]);
    $("submit").disabled = true;
    try {
      const r = await api("/leave-requests/", { method: "POST", body: fd });
      toast("Leave request submitted");
      go("/leave/" + r.id);
    } catch (ex) {
      $("form-error").innerHTML = alertBox(ex.message, "bad", "alert");
      $("submit").disabled = !lastOk;
    }
  });
  paintRules(); refresh();
}
