/* The overview cards on the left: the situation at the as-of time, what each sensor family gave,
   and the measured track record of the alerts. Each card shows tool answers. It adds no fact. */
import { esc, num, pct, utc, dur, hoursBetween, FAMILY, FAMILY_ORDER, FAMILY_NOTE } from "./format.js";

const LEVELS = ["HIGH", "MEDIUM", "LOW"];
const COLOUR = { HIGH: "#e5542b", MEDIUM: "#ed903d", LOW: "#f5c16c" };

export function situation(root, { events, day, asOf, sinceHours }) {
  const count = Object.fromEntries(LEVELS.map((l) => [l, events.filter((e) => e.level === l).length]));
  const newest = day ? Object.values(day.newest_observed_at).sort().at(-1) : null;
  const bar = events.length
    ? LEVELS.map((l) => (count[l] ? `<span data-level="${l}" style="flex:${count[l]}"></span>` : "")).join("")
    : "";
  root.innerHTML = `
    <div class="card-head"><span class="label">Situation</span><span class="meta">${sinceHours} h to ${utc(asOf, false)}</span></div>
    <div class="figure">${num(events.length)}<small>${events.length === 1 ? "event" : "events"}</small></div>
    <div class="lede">with a new detection in the ${sinceHours} h before the as-of time</div>
    <div class="levelbar${events.length ? "" : " empty"}">${bar}</div>
    <div class="legend">${LEVELS.map((l) => `<span data-level="${l}"><span class="swatch"></span>${l}<b>${count[l]}</b></span>`).join("")}</div>
    ${day ? spark(day.steps) : ""}
    <div class="kv"><span>Newest detection</span><b>${newest ? `${utc(newest, false)} · ${dur(hoursBetween(newest, asOf))} before` : "none in 24 h"}</b></div>`;
}

/* The events of each hour by level, as small stacked bars. */
function spark(steps) {
  const most = Math.max(1, ...steps.map((s) => LEVELS.reduce((sum, l) => sum + s.events[l], 0)));
  const w = 100 / steps.length;
  const bars = steps.map((s, n) => {
    let base = 0;
    return LEVELS.map((l) => {
      const v = s.events[l];
      if (!v) return "";
      const h = (v / most) * 30, y = 32 - base - h;
      base += h;
      return `<rect x="${n * w + 0.3}" y="${y}" width="${w - 0.6}" height="${h}" fill="${COLOUR[l]}"/>`;
    }).join("");
  }).join("");
  return `<svg class="spark" viewBox="0 0 100 34" preserveAspectRatio="none" aria-label="Events of each hour">${bars}<line x1="0" x2="100" y1="32.5" y2="32.5" stroke="rgba(255,255,255,0.15)" stroke-width="0.4"/></svg>`;
}

export function sensors(root, { day, asOf }) {
  if (!day) { root.innerHTML = `<div class="card-head"><span class="label">Sensors</span></div><div class="note">Loading.</div>`; return; }
  const lanes = FAMILY_ORDER.map((family) => {
    const counts = day.steps.map((s) => s.detections[family] ?? 0);
    const most = Math.max(1, ...counts);
    const cells = counts.map((c) => `<i style="opacity:${c ? (0.25 + 0.75 * Math.log1p(c) / Math.log1p(most)).toFixed(2) : 0.06}"></i>`).join("");
    const newest = day.newest_observed_at[family];
    const total = counts.reduce((a, b) => a + b, 0);
    const when = newest ? `${utc(newest, false)} <small>${dur(hoursBetween(newest, asOf))} before</small>` : `– <small>none in 24 h</small>`;
    return `<div class="lane" style="--fam:var(--${family})">
      <span class="name">${FAMILY[family]} <small>${FAMILY_NOTE[family]}</small></span><span class="when">${when}</span>
      <span class="cells" title="${num(total)} detections in 24 h">${cells}</span></div>`;
  }).join("");
  root.innerHTML = `
    <div class="card-head"><span class="label">Sensors</span><span class="meta">each hour, 24 h · newest, UTC</span></div>
    <div class="lanes">${lanes}</div>
    <p class="note">No detection is not "no fire". Cloud, smoke and the time of a pass limit what a sensor sees.</p>`;
}

export function record(root, { summary, years, year, onYear, onLimits }) {
  const head = `<div class="card-head"><span class="label">Track record</span>
    <div class="seg">${years.map((y) => `<button type="button" data-year="${y}" aria-pressed="${y === year}">${y}</button>`).join("")}</div></div>`;
  if (!summary) { root.innerHTML = `${head}<div class="note">Loading.</div>`; wire(root, onYear, onLimits); return; }
  const levels = LEVELS.map((l) => summary.events.find((r) => r.final_level === l)).filter(Boolean);
  const rows = levels.map((r) => `<div class="barrow" data-level="${r.final_level}">
      <span class="k">${r.final_level}</span><span class="track"><i style="width:${pct(Number(r.matched_share), 1)}"></i></span>
      <span class="v">${pct(Number(r.matched_share))} <small>${num(Number(r.events_matched))}/${num(Number(r.events))}</small></span></div>`).join("");
  const names = [["merged, level LOW or higher", "Merged"], ...FAMILY_ORDER.map((f) => [`family ${f}`, FAMILY[f]])];
  const recall = names.map(([name, label]) => {
    const r = summary.configurations.find((c) => c.configuration === name);
    if (!r) return "";
    const merged = label === "Merged";
    return `<div class="barrow"${merged ? ' style="--lv:var(--fg-1)"' : ' style="--lv:var(--fg-4)"'}>
      <span class="k">${label}</span><span class="track"><i style="width:${pct(Number(r.fire_recall), 1)}"></i></span>
      <span class="v">${pct(Number(r.fire_recall))} <small>${num(Number(r.fires_found))}/${num(Number(r.fires))}</small></span></div>`;
  }).join("");
  root.innerHTML = `${head}
    <div class="lede" style="margin:-4px 0 12px">Events that matched a mapped fire, by level. ${esc(summary.role)[0].toUpperCase()}${esc(summary.role).slice(1)}.</div>
    <div class="bars">${rows}</div>
    <div class="label sub">Mapped fires found</div>
    <div class="bars">${recall}</div>
    <p class="note">Satellites only. An unmatched event is not a false alarm: a small fire can be absent from the map.
      <a href="#" data-limits style="color:var(--blue-text)">Limits</a></p>`;
  wire(root, onYear, onLimits);
}

function wire(root, onYear, onLimits) {
  root.querySelectorAll("[data-year]").forEach((b) => b.addEventListener("click", () => onYear(Number(b.dataset.year))));
  root.querySelector("[data-limits]")?.addEventListener("click", (e) => { e.preventDefault(); onLimits(); });
}
