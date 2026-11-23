/* The history band: one time axis for the window. The events of each step by level, the detections
   of each sensor family, and the selected event: its days, its level changes and its growth steps.
   A click on a step moves the as-of time to the end of that step. */
import { esc, num, utc, day, FAMILY, FAMILY_ORDER } from "./format.js";

const LEVELS = [["HIGH", "#e5542b"], ["MEDIUM", "#ed903d"], ["LOW", "#f5c16c"]];
const FAMILY_COLOUR = { viirs: "#d9e7ea", abi: "#4fa3b8", modis: "#a59f8f", avhrr: "#6e736f" };
const G = 64, RIGHT = 10, TOP = 22, AXIS = 18, LANE = 7, LANE_GAP = 4, EVENT_LANE = 18;

export class History {
  constructor(root, handlers) {
    this.root = root;
    this.handlers = handlers;
    this.state = null;
    root.innerHTML = `<div class="h-head"></div><div class="h-plot" tabindex="0" aria-label="History of the window. Arrow keys move the as-of time."></div>`;
    this.head = root.querySelector(".h-head");
    this.plot = root.querySelector(".h-plot");
    new ResizeObserver(() => this.draw()).observe(this.plot);
    this.plot.addEventListener("keydown", (e) => this.key(e));
  }

  /* state: { activity, asOf, windows, windowIndex, record } */
  set(state) {
    this.state = state;
    this.header();
    this.draw();
  }

  header() {
    const { windows, windowIndex } = this.state;
    const buttons = windows.map((w, n) => `<button type="button" data-window="${n}" aria-pressed="${n === windowIndex}">${w.hours >= 48 ? `${w.hours / 24} d` : `${w.hours} h`}</button>`).join("");
    const legend = LEVELS.map(([name]) => `<span data-level="${name}"><span class="swatch"></span>${name}</span>`).join("");
    this.head.innerHTML = `<span class="label">History</span><div class="seg">${buttons}</div>
      <span class="note">Events with a new detection in each step, Pantanal box</span><div class="legend">${legend}</div>`;
    this.head.querySelectorAll("[data-window]").forEach((b) => b.addEventListener("click", () => this.handlers.window(Number(b.dataset.window))));
  }

  draw() {
    if (!this.state?.activity) { this.plot.innerHTML = ""; return; }
    const { activity, asOf, record } = this.state;
    const W = this.plot.clientWidth, H = this.plot.clientHeight;
    if (W < 50 || H < 50) return;
    const steps = activity.steps;
    const start = new Date(steps[0].start).getTime(), end = new Date(steps.at(-1).end).getTime();
    const x = (t) => G + ((new Date(t).getTime() - start) / (end - start)) * (W - G - RIGHT);
    const families = FAMILY_ORDER.filter((f) => steps.some((s) => s.detections[f]));
    const lanesTop = H - AXIS - families.length * (LANE + LANE_GAP) - (record ? EVENT_LANE + 6 : 0);
    const barsBottom = Math.max(lanesTop - 8, TOP + 16);
    const total = (s) => LEVELS.reduce((sum, [name]) => sum + s.events[name], 0);
    const most = Math.max(1, ...steps.map(total));
    const y = (n) => barsBottom - (n / most) * (barsBottom - TOP);
    const step = (W - G - RIGHT) / steps.length;
    const parts = [];
    parts.push(`<line x1="${G}" x2="${W - RIGHT}" y1="${barsBottom}" y2="${barsBottom}" stroke="rgba(255,255,255,0.12)"/>`);
    parts.push(`<text x="${G - 8}" y="${TOP + 3}" text-anchor="end">${num(most)}</text><text x="${G - 8}" y="${barsBottom}" text-anchor="end">0</text>`);
    parts.push(`<text class="lane-name" x="4" y="${(TOP + barsBottom) / 2 + 3}">EVENTS</text>`);
    steps.forEach((s, n) => {
      let base = 0;
      const left = G + n * step, width = Math.max(1, step - (step > 4 ? 1.2 : 0.3));
      for (const [name, colour] of LEVELS) {
        const value = s.events[name];
        if (!value) continue;
        parts.push(`<rect x="${left}" y="${y(base + value)}" width="${width}" height="${Math.max(0, y(base) - y(base + value))}" fill="${colour}"/>`);
        base += value;
      }
    });
    parts.push(this.lanes(steps, families, lanesTop, step));
    if (record) parts.push(this.eventLane(record, x, lanesTop + families.length * (LANE + LANE_GAP) + 4, start, end));
    parts.push(this.axis(start, end, x, H, activity.hours));
    const now = Math.min(Math.max(x(asOf), G), W - RIGHT);
    if (now < W - RIGHT - 0.5) parts.push(`<rect x="${now}" y="${TOP - 6}" width="${W - RIGHT - now}" height="${H - AXIS - TOP + 6}" fill="rgba(5,5,5,0.62)"/>`);
    parts.push(`<line x1="${now}" x2="${now}" y1="${TOP - 8}" y2="${H - AXIS}" stroke="#087cff" stroke-width="1.2"/>`);
    parts.push(`<text class="now" x="${now - 4}" y="${TOP - 10}" text-anchor="end">${utc(asOf)}</text>`);
    parts.push(steps.map((s, n) => `<rect class="hit" data-n="${n}" x="${G + n * step}" y="0" width="${step}" height="${H - AXIS}"/>`).join(""));
    this.plot.innerHTML = `<svg viewBox="0 0 ${W} ${H}">${parts.join("")}<rect class="col" x="0" y="${TOP - 6}" width="0" height="${H - AXIS - TOP + 6}" fill="rgba(255,255,255,0.05)" pointer-events="none"/></svg>`;
    this.wire(steps, step);
  }

  lanes(steps, families, top, step) {
    return families.map((family, k) => {
      const yy = top + k * (LANE + LANE_GAP);
      const most = Math.max(1, ...steps.map((s) => s.detections[family] ?? 0));
      const cells = steps.map((s, n) => {
        const count = s.detections[family] ?? 0;
        if (!count) return "";
        const strength = 0.2 + 0.8 * (Math.log1p(count) / Math.log1p(most));
        return `<rect x="${G + n * step}" y="${yy}" width="${Math.max(1, step - 0.6)}" height="${LANE}" fill="${FAMILY_COLOUR[family]}" fill-opacity="${strength.toFixed(2)}"/>`;
      }).join("");
      return `<text class="lane-name" x="4" y="${yy + LANE}">${FAMILY[family]}</text><rect x="${G}" y="${yy}" width="${steps.length * step}" height="${LANE}" fill="rgba(255,255,255,0.025)"/>${cells}`;
    }).join("");
  }

  /* The selected event: its detections of each day, its level changes and its VIIRS growth steps. */
  eventLane(record, x, top, start, end) {
    const inside = (t) => { const v = new Date(t).getTime(); return v >= start && v <= end; };
    const most = Math.max(1, ...record.timeline.map((d) => d.detections));
    const parts = [`<text class="lane-name" x="4" y="${top + 12}" style="fill:#4f9dff">EVENT</text>`];
    parts.push(`<rect x="${G}" y="${top}" width="${x(end) - G}" height="${EVENT_LANE}" fill="rgba(8,124,255,0.05)"/>`);
    for (const d of record.timeline) {
      const from = Math.max(new Date(`${d.day}T00:00:00Z`).getTime(), start), to = Math.min(from + 86_400_000, end);
      if (to <= start || from >= end) continue;
      const h = 3 + (EVENT_LANE - 4) * (Math.log1p(d.detections) / Math.log1p(most));
      parts.push(`<rect x="${x(from)}" y="${top + EVENT_LANE - h}" width="${Math.max(1, x(to) - x(from) - 1)}" height="${h}" fill="#087cff" fill-opacity="0.35"/>`);
    }
    for (const s of record.growth_steps.filter((s) => inside(s.at))) {
      const moved = s.direction_deg !== null;
      parts.push(`<line x1="${x(s.at)}" x2="${x(s.at)}" y1="${top + (moved ? 0 : 9)}" y2="${top + EVENT_LANE}" stroke="${moved ? "#f5c16c" : "rgba(242,242,234,0.35)"}" stroke-width="${moved ? 1.5 : 1}"/>`);
    }
    const colour = Object.fromEntries(LEVELS);
    for (const c of record.level_changes.filter((c) => inside(c.at))) {
      const cx = x(c.at);
      parts.push(`<path d="M${cx} ${top - 4}l4 4l-4 4l-4-4z" fill="${colour[c.level]}" stroke="#050505"/>`);
    }
    return parts.join("");
  }

  axis(start, end, x, H, hours) {
    const every = hours <= 72 ? 12 : hours <= 168 ? 24 : 120;
    const parts = [];
    const first = Math.ceil(start / 3_600_000 / every) * every * 3_600_000;
    for (let t = first; t <= end; t += every * 3_600_000) {
      const iso = new Date(t).toISOString();
      const text = iso.slice(11, 13) === "00" ? day(iso) : iso.slice(11, 16);
      parts.push(`<line x1="${x(t)}" x2="${x(t)}" y1="${H - AXIS}" y2="${H - AXIS + 3}" stroke="rgba(255,255,255,0.25)"/><text x="${x(t) + 3}" y="${H - 4}">${text}</text>`);
    }
    return parts.join("");
  }

  wire(steps, step) {
    const svg = this.plot.querySelector("svg"), column = svg.querySelector(".col"), tip = document.getElementById("tip");
    svg.querySelectorAll(".hit").forEach((hit) => {
      const s = steps[Number(hit.dataset.n)];
      hit.addEventListener("mouseenter", () => {
        column.setAttribute("x", hit.getAttribute("x"));
        column.setAttribute("width", step);
        const fams = FAMILY_ORDER.filter((f) => s.detections[f]).map((f) => `${FAMILY[f]} ${num(s.detections[f])}`).join(" · ") || "no detection";
        tip.innerHTML = `<div class="mono">${utc(s.start)} – ${utc(s.end, false)}</div>
          <div>${LEVELS.map(([n]) => `<span data-level="${n}"><span class="swatch"></span>${n} <b>${s.events[n]}</b></span>`).join("&nbsp;&nbsp;")}</div>
          <div class="muted">${esc(fams)}</div><div class="muted">Click: as-of time ${utc(s.end, false)}</div>`;
        tip.hidden = false;
      });
      hit.addEventListener("mousemove", (e) => { tip.style.left = `${Math.min(e.clientX + 14, innerWidth - 270)}px`; tip.style.top = `${e.clientY - 90}px`; });
      hit.addEventListener("mouseleave", () => { tip.hidden = true; column.setAttribute("width", 0); });
      hit.addEventListener("click", () => this.handlers.asOf(s.end));
    });
  }

  key(e) {
    if (!this.state?.activity || !["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    const steps = this.state.activity.steps, asOf = new Date(this.state.asOf).getTime();
    let n = steps.findIndex((s) => new Date(s.end).getTime() >= asOf);
    n = Math.min(steps.length - 1, Math.max(0, (n < 0 ? steps.length - 1 : n) + (e.key === "ArrowLeft" ? -1 : 1)));
    e.preventDefault();
    this.handlers.asOf(steps[n].end);
  }
}
