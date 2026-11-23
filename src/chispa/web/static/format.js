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

/* "2024-09-10T18:00:00+00:00" -> "2024-09-10 18:00". All times on the page are UTC. */
export function utc(text, withDate = true) {
  if (!text) return "–";
  const d = new Date(text);
  const iso = d.toISOString();
  return withDate ? `${iso.slice(0, 10)} ${iso.slice(11, 16)}` : iso.slice(11, 16);
}

export function day(text) {
  return text ? new Date(text).toISOString().slice(5, 10) : "–";
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

/* The GOES mask groups (`docs/method.md` 7.2), as what GOES said for the pixel, and what that means. */
export const GOES_GROUP = {
  fire: "fire", possible_fire: "possible fire", no_fire: "examined, no fire", cloud: "cloud",
  no_background: "could not decide", water: "water", blocked: "blocked", not_processed: "not processed",
};
export const GOES_NOTE = {
  fire: "GOES found fire", possible_fire: "GOES found a possible fire", no_fire: "GOES examined the pixel and found no fire",
  cloud: "GOES did not examine the pixel", no_background: "GOES could not compute a background value for the pixel",
  water: "GOES does not examine water", blocked: "view angle or sun glint: GOES did not examine the pixel",
  not_processed: "GOES did not process the pixel",
};
