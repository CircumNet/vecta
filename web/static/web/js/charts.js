import { html, raw, esc, num } from "./ui.js";

export const color = (i) => `var(--c${(i % 6) + 1})`;

/** Progress ring: value out of total, with the value in the middle. */
export function ring(value, total, { size = 64, label = "" } = {}) {
  const r = size / 2 - 6, c = 2 * Math.PI * r, pct = total > 0 ? Math.max(0, Math.min(1, value / total)) : 0;
  return html`<svg class="ring" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="${label}">
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--surface-2)" stroke-width="7"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${pct < 0.15 ? "var(--c3)" : "var(--c1)"}" stroke-width="7" stroke-linecap="round"
      stroke-dasharray="${(c * pct).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 ${size / 2} ${size / 2})"/>
    <text x="50%" y="50%" text-anchor="middle" dominant-baseline="central" font-size="${size * 0.27}">${num(value)}</text></svg>`;
}

/** Vertical bars. items: [{label, value}] */
export function barChart(items, { height = 210, unit = "" } = {}) {
  const W = Math.max(360, items.length * 48), H = height, pad = { t: 22, b: 26, l: 6, r: 6 };
  const max = Math.max(1, ...items.map((i) => i.value)), bw = (W - pad.l - pad.r) / items.length;
  const bars = items.map((it, i) => {
    const h = ((H - pad.t - pad.b) * it.value) / max, x = pad.l + i * bw + bw * 0.18, y = H - pad.b - h;
    return `<rect x="${x}" y="${y}" width="${bw * 0.64}" height="${Math.max(h, it.value ? 2 : 0)}" rx="5" fill="var(--c1)" opacity="${it.value ? 1 : 0.25}"><title>${esc(it.label)}: ${num(it.value)}${unit}</title></rect>
      ${it.value ? `<text class="val" x="${x + bw * 0.32}" y="${y - 5}" text-anchor="middle">${num(it.value)}</text>` : ""}
      <text x="${x + bw * 0.32}" y="${H - 8}" text-anchor="middle">${esc(it.label)}</text>`;
  }).join("");
  return raw(`<svg class="chart" viewBox="0 0 ${W} ${H}" width="100%" style="max-height:${H + 20}px" role="img"><line x1="0" x2="${W}" y1="${H - pad.b}" y2="${H - pad.b}"/>${bars}</svg>`);
}

/** Horizontal bar list. items: [{label, value}] */
export function hbars(items, { unit = "" } = {}) {
  if (!items.length) return html`<div class="muted">No data for this period.</div>`;
  const max = Math.max(1, ...items.map((i) => i.value));
  return html`<div>${items.map((it, i) => html`<div class="hbar"><span title="${it.label}" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${it.label}</span>
    <div class="track"><i style="width:${(it.value / max) * 100}%;background:${color(i)}"></i></div><b>${num(it.value)}${unit}</b></div>`)}</div>`;
}

/** Donut with legend. items: [{label, value}] */
export function donut(items, { size = 150 } = {}) {
  const total = items.reduce((s, i) => s + i.value, 0);
  if (!total) return html`<div class="muted">No data for this period.</div>`;
  const r = size / 2 - 14, c = 2 * Math.PI * r;
  let offset = 0;
  const arcs = items.map((it, i) => {
    const len = (it.value / total) * c, seg = `<circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color(i)}" stroke-width="18" stroke-dasharray="${len.toFixed(2)} ${(c - len).toFixed(2)}" stroke-dashoffset="${(-offset).toFixed(2)}" transform="rotate(-90 ${size / 2} ${size / 2})"><title>${esc(it.label)}: ${num(it.value)}</title></circle>`;
    offset += len; return seg;
  }).join("");
  return html`<div class="donut-wrap"><svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img">${raw(arcs)}
    <text x="50%" y="50%" text-anchor="middle" dominant-baseline="central" style="font-size:22px;font-weight:700;fill:var(--text)">${num(total)}</text></svg>
    <div class="legend">${items.map((it, i) => html`<div><i style="background:${color(i)}"></i><span>${it.label}</span><b>${num(it.value)}</b></div>`)}</div></div>`;
}
