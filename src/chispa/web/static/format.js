/* Formats for the page: times, durations, numbers, positions and names.
   These functions change how a value looks. They calculate no new fact. */

const NNBSP = " "; // A narrow space between groups of three digits: 194 932.

const NBSP = " "; // A number and its unit stay on one line.

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export function num(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  const fixed = Number(value).toFixed(digits);
  const [whole, part] = fixed.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, NNBSP);
  return part ? `${grouped}.${part}` : grouped;
}

export function pct(share, digits = 0) {
  return share === null || share === undefined ? "–" : `${(share * 100).toFixed(digits)}%`;
}

/* The parts of a time in a zone. `zone` is the zone of the page: an IANA name, or null for UTC. */
function parts(time, zone) {
  const options = { timeZone: zone ?? "UTC", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" };
  return Object.fromEntries(new Intl.DateTimeFormat("en-GB", options).formatToParts(new Date(time)).map((x) => [x.type, x.value]));
}

/* A time in the zone of the page: "2024-09-10 14:00", or "14:00" with no date. */
export function stamp(time, zone, withDate = true) {
  if (time === null || time === undefined || time === "") return "–";
  const p = parts(time, zone);
  return withDate ? `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}` : `${p.hour}:${p.minute}`;
}

/* The month and the day of a time in the zone of the page: "09-10". A UTC day ("2024-09-10") needs the zone null. */
export function day(time, zone) {
  if (!time) return "–";
  const p = parts(time, zone);
  return `${p.month}-${p.day}`;
}

/* How far the clock of the zone is from UTC at a time, in milliseconds: −4 h for Pantanal time, 0 for UTC. */
export function zoneShift(time, zone) {
  if (!zone) return 0;
  const p = parts(time, zone), minute = Math.floor(new Date(time).getTime() / 60_000) * 60_000;
  return Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day), Number(p.hour), Number(p.minute)) - minute;
}

/* The name of the zone of the page: "UTC", or "Pantanal, UTC−4" at a time. Short: "UTC" or "Pantanal". */
export function zoneLabel(zone, time) {
  return zone ? `Pantanal, ${offset(time, zone)}` : "UTC";
}

export function zoneTag(zone) {
  return zone ? "Pantanal" : "UTC";
}

/* The hours before the as-of time, as two times: "from 24 Nov 16:32 to 25 Nov 16:32 Pantanal". */
export function period(asOf, hours, zone) {
  const from = new Date(new Date(asOf).getTime() - hours * 3_600_000);
  return `from ${when(from, zone)} to ${when(asOf, zone)} ${zoneTag(zone)}`;
}

/* How long before the as-of time: "1.1 h ago" when live, "1.1 h earlier" in a replay (before the moment of the replay). */
export function ago(time, asOf, live) {
  return `${dur(hoursBetween(time, asOf))} ${live ? "ago" : "earlier"}`;
}

/* Hours as a short duration: 0.25 -> "15 min", 5.5 -> "5.5 h", 50 -> "2 d 2 h", 721 -> "30 d". */
export function dur(hours) {
  if (hours === null || hours === undefined) return "–";
  if (hours < 1) return `${Math.round(hours * 60)}${NBSP}min`;
  if (hours < 10) return `${hours.toFixed(1).replace(/\.0$/, "")}${NBSP}h`;
  if (hours < 48) return `${Math.round(hours)}${NBSP}h`;
  const days = Math.floor(hours / 24), rest = Math.round(hours - days * 24);
  return days < 10 && rest ? `${days}${NBSP}d ${rest}${NBSP}h` : `${Math.round(hours / 24)}${NBSP}d`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/* A time in a time zone, as parts: { date: "Tue 10 Sep", time: "14:00" }. The browser has the rules of the zone. */
export function zoned(time, zone, seconds = false) {
  const options = { timeZone: zone, weekday: "short", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" };
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", options).formatToParts(new Date(time)).map((x) => [x.type, x.value]));
  return { date: `${p.weekday} ${p.day} ${MONTHS[p.month - 1]}`, time: `${p.hour}:${p.minute}${seconds ? `:${p.second}` : ""}` };
}

/* The offset of a time zone at a time: "UTC−4". */
export function offset(time, zone) {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: zone, timeZoneName: "shortOffset" }).formatToParts(new Date(time));
  const name = parts.find((x) => x.type === "timeZoneName")?.value ?? "";
  return name.replace("GMT", "UTC").replace("-", "−");
}

/* Seconds as a counter: 221 -> "00:03:41". Days go first: "2 d 04:00:09". */
export function counter(seconds) {
  const s = Math.max(0, Math.floor(seconds)), days = Math.floor(s / 86_400);
  const hms = [Math.floor((s % 86_400) / 3600), Math.floor((s % 3600) / 60), s % 60].map((v) => String(v).padStart(2, "0")).join(":");
  return days ? `${days}${NBSP}d ${hms}` : hms;
}

export function hoursBetween(a, b) {
  return (new Date(b) - new Date(a)) / 3_600_000;
}

export function coord(lat, lon, digits = 3) {
  const ns = lat < 0 ? "S" : "N", ew = lon < 0 ? "W" : "E";
  return `${Math.abs(lat).toFixed(digits)}°${NNBSP}${ns}  ${Math.abs(lon).toFixed(digits)}°${NNBSP}${ew}`;
}

export function km(metres) {
  if (metres === null || metres === undefined) return "–";
  return metres < 1000 ? `${Math.round(metres)}${NBSP}m` : `${(metres / 1000).toFixed(1)}${NBSP}km`;
}

const POINTS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
export function compass(degrees) {
  return POINTS[Math.round((((degrees % 360) + 360) % 360) / 22.5) % 16];
}

export const FAMILY = { viirs: "VIIRS", modis: "MODIS", abi: "ABI", avhrr: "AVHRR", camera: "Camera", person: "Person" };
export const FAMILY_ORDER = ["viirs", "modis", "abi", "avhrr"];
export const FAMILY_NOTE = { viirs: "polar orbit, 375 m", modis: "polar orbit, 1 km", abi: "GOES, each 10 min", avhrr: "polar orbit, 1.1 km" };

/* The inputs of the confidence model (`confidence.py`), in words. */
export const INPUT = {
  detections_log: "Detections", families: "Sensor families", has_abi: "ABI detection", has_viirs: "VIIRS detection",
  has_modis: "MODIS detection", has_avhrr: "AVHRR detection", has_high: "High source confidence", power_log: "Fire power",
  no_power: "No fire power", season_sin: "Season", season_cos: "Season", night: "Night at the place",
  on_forest: "Forest", on_savanna: "Savanna", on_wetland: "Wetland", on_grassland: "Grassland", on_pasture: "Pasture",
  on_farming: "Farming", people_log: "People near", protected_km_log: "Distance to protected land",
  indigenous_km_log: "Distance to indigenous land", near_log: "Detections near, 7 days before",
  extent_km_log: "Extent", has_advance: "Measured advance",
};

/* The parts of the severity (`severity.py`), in words. */
export const PART = { power: "Fire power", extent: "Extent", advance: "Advance", cover: "Land cover", people: "People", land: "Protected land" };

/* The GOES mask groups (`docs/method.md` 7.2), as what GOES said for a place, and what that means.
   A place can have more than one pixel: "no fire" is for each pixel, the other groups for one or more. */
export const GOES_GROUP = {
  fire: "fire", possible_fire: "possible fire", no_fire: "examined, no fire", cloud: "cloud",
  no_background: "could not decide", water: "water", blocked: "blocked", not_processed: "not processed",
};
/* What the group of the newest scan means for the place of the last detection. */
export const GOES_NOTE = {
  fire: "GOES saw fire at the place of the last detection",
  possible_fire: "GOES saw a possible fire there, too weak for a detection",
  no_fire: "GOES saw the place of the last detection and found no fire",
  cloud: "GOES could not see the place of the last detection",
  no_background: "GOES could not compute a background value, and made no decision",
  water: "GOES does not examine water",
  blocked: "the view angle or sun glint blocked the view",
  not_processed: "GOES did not process the place",
};

/* The answer of a run of GOES scans (`goes_view.runs_after_last_detection`). */
export const ANSWER = { fire: "fire", possible_fire: "possible fire", no_fire: "examined, no fire", not_seen: "could not see" };

/* A short time in the zone of the page: "20 Aug 13:25". `zone` null is UTC. */
export function when(text, zone) {
  const t = zoned(text, zone ?? "UTC");
  return `${t.date.split(" ").slice(1).join(" ")} ${t.time}`;
}
