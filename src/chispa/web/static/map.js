/* The map: MapLibre with two bases, the biome as an island, a graticule, the events and the selection.
   This file draws. The level, the age and the position of each event come from the tools. */
import { coord, FAMILY } from "./format.js";

const LEVEL = { LOW: "#f5c16c", MEDIUM: "#ed903d", HIGH: "#e5542b" };
const FAMILY_COLOUR = { viirs: "#d9e7ea", abi: "#4fa3b8", modis: "#a59f8f", avhrr: "#6e736f" };
const CANVAS = "#050505", ICE = "#d9e7ea", BLUE = "#087cff";
const WORLD = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
const EMPTY = { type: "FeatureCollection", features: [] };
const STILL = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const HOME_PAD = 12; // the margin in pixels round the biome in the home view
const tiles = (key, name) => `https://api.maptiler.com/tiles/${name}/tiles.json?key=${key}`;

/* Imagery: the satellite mosaic, a little darker and less saturated, so that the marks stay legible.
   The mosaic is not of the as-of time. The relief comes from the elevation model. */
function imagery(key) {
  return {
    version: 8,
    glyphs: `https://api.maptiler.com/fonts/{fontstack}/{range}.pbf?key=${key}`,
    sources: {
      satellite: { type: "raster", url: tiles(key, "satellite-v2"), tileSize: 512 },
      shade: { type: "raster-dem", url: tiles(key, "terrain-rgb-v2"), tileSize: 256 },
      dem: { type: "raster-dem", url: tiles(key, "terrain-rgb-v2"), tileSize: 256 },
      osm: { type: "vector", url: tiles(key, "v3") },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": CANVAS } },
      { id: "satellite", type: "raster", source: "satellite",
        paint: { "raster-saturation": -0.18, "raster-contrast": 0.1, "raster-brightness-max": 0.86, "raster-fade-duration": 150 } },
      { id: "hillshade", type: "hillshade", source: "shade",
        paint: { "hillshade-exaggeration": 0.4, "hillshade-shadow-color": "rgba(0,0,0,0.6)", "hillshade-highlight-color": "rgba(255,255,255,0.07)", "hillshade-accent-color": "rgba(0,0,0,0.25)" } },
      { id: "rivers", type: "line", source: "osm", "source-layer": "waterway", filter: ["==", ["get", "class"], "river"],
        paint: { "line-color": "#7fc1d1", "line-opacity": ["interpolate", ["linear"], ["zoom"], 5, 0.22, 10, 0.5], "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.5, 12, 1.6] } },
      { id: "roads", type: "line", source: "osm", "source-layer": "transportation", minzoom: 6,
        filter: ["in", ["get", "class"], ["literal", ["motorway", "trunk", "primary", "secondary"]]],
        paint: { "line-color": "#e6e6de", "line-opacity": ["interpolate", ["linear"], ["zoom"], 6, 0.08, 11, 0.28], "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.5, 12, 1.4] } },
      { id: "places", type: "symbol", source: "osm", "source-layer": "place", filter: ["in", ["get", "class"], ["literal", ["city", "town"]]],
        layout: { "text-field": ["get", "name"], "text-font": ["Noto Sans Regular"], "text-size": ["interpolate", ["linear"], ["zoom"], 5, 10, 11, 13], "text-letter-spacing": 0.04 },
        paint: { "text-color": "#deded6", "text-opacity": 0.8, "text-halo-color": "rgba(0,0,0,0.8)", "text-halo-width": 1.2 } },
    ],
  };
}

/* Relief: the outdoor style with the land colours of the first prototype, water in the brand teal. */
const RELIEF = [
  [/^background$/, { "background-color": CANVAS }],
  [/^(globallandcover_(grass|scrub)|landcover_grass)$/, { "fill-color": "#475E34" }],
  [/^(globallandcover_(tree|forest)|landcover_wood)$/, { "fill-color": "#3A4D2B" }],
  [/^landcover_sand$/, { "fill-color": "#8A7956" }],
  [/^landuse_(residential|industrial)$/, { "fill-color": "#34342f", "fill-opacity": 0.9 }],
  [/^building$/, { "fill-color": "#44443e" }],
  [/^hillshade$/, { "hillshade-shadow-color": "#000000", "hillshade-highlight-color": "#6b6b60", "hillshade-accent-color": "#103943" }],
  [/^contour(_index)?$/, { "line-color": ICE, "line-opacity": 0.1 }],
  [/^water$/, { "fill-color": "#103943" }],
  [/^water_intermittent$/, { "fill-color": "#103943", "fill-opacity": 0.5 }],
  [/^waterway_/, { "line-color": "#287C91", "line-opacity": 0.6 }],
  [/^(road|tunnel)_(motorway|major|minor)$|^(road|tunnel_road)_(major|minor)$/, { "line-color": "#8a8a82", "line-opacity": 0.45 }],
];
const RELIEF_HIDE = /^(trail_|bicycle_|viaferrata|cablecar|ferry|waterway_tunnel|landuse_(cemetery|hospital|military)|limit_military|boundary_|road_path|poi|housenumber)/;

export class MapView {
  constructor(container, settings, handlers) {
    this.settings = settings;
    this.handlers = handlers;
    this.base = "imagery";
    this.solid = true;
    this.data = { events: EMPTY, detections: EMPTY, hover: null };
    this.border = fetch("/api/border").then((r) => (r.ok ? r.json() : null)).catch(() => null);
    const [west, south, east, north] = settings.box;
    // The home view: the box of the data requests until the border gives the limits of the biome.
    this.home = [[west, south], [east, north]];
    this.island = false;
    this.map = new maplibregl.Map({
      container, style: imagery(settings.map_key), maxPitch: 70, attributionControl: false, dragRotate: true,
    });
    // The camera keeps the free area between the panels as its padding. A fit adds its margin to that padding.
    this.map.setPadding(this.padding());
    this.fit(0);
    this.map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    this.map.addControl(new maplibregl.ScaleControl({ unit: "metric", maxWidth: 90 }), "bottom-left");
    this.map.on("style.load", () => this.dress());
    this.wire();
  }

  /* The free area between the panels, as map padding. */
  padding() {
    const box = document.querySelector(".map-ui").getBoundingClientRect();
    const map = document.getElementById("map").getBoundingClientRect();
    return { left: box.left - map.left, top: box.top - map.top, right: map.right - box.right, bottom: map.bottom - box.bottom };
  }

  async dress() {
    const map = this.map;
    if (this.base === "relief") this.repaint();
    const font = this.base === "relief" ? this.font() : ["Noto Sans Regular"];
    if (this.solid && this.dem()) map.setTerrain({ source: this.dem(), exaggeration: 1.5 });
    this.addGraticule(font);
    const border = await this.border;
    if (border && !map.getSource("border")) this.addIsland(border);
    if (border && !this.island) this.homeOnBiome(border);
    this.addEvents();
  }

  repaint() {
    for (const layer of this.map.getStyle().layers) {
      for (const [pattern, properties] of RELIEF) {
        if (!pattern.test(layer.id)) continue;
        for (const [name, value] of Object.entries(properties)) {
          try { this.map.setPaintProperty(layer.id, name, value); } catch (_) { /* The layer has no such property. */ }
        }
      }
      const label = layer.type === "symbol" && !/^place_(city|town)/.test(layer.id);
      if (RELIEF_HIDE.test(layer.id) || label) this.map.setLayoutProperty(layer.id, "visibility", "none");
    }
  }

  /* The elevation source: ours in the imagery style, MapTiler's in the outdoor style. */
  dem() {
    return ["dem", "terrain-rgb"].find((name) => this.map.getSource(name)) ?? null;
  }

  font() {
    const symbol = this.map.getStyle().layers.find((l) => l.type === "symbol" && l.layout && l.layout["text-font"]);
    return symbol ? symbol.layout["text-font"] : ["Noto Sans Regular"];
  }

  /* One line each degree. The labels are degrees, at the west and the south edge of the box. */
  addGraticule(font) {
    const [west, south, east, north] = this.settings.box;
    const lines = [], labels = [];
    for (let lat = Math.ceil(south - 1); lat <= Math.floor(north + 1); lat++) {
      lines.push([[west - 1.5, lat], [east + 1.5, lat]]);
      labels.push(point(west - 1.45, lat, { t: `${Math.abs(lat)}°S` }));
    }
    for (let lon = Math.ceil(west - 1); lon <= Math.floor(east + 1); lon++) {
      lines.push([[lon, south - 1.5], [lon, north + 1.5]]);
      labels.push(point(lon, south - 1.45, { t: `${Math.abs(lon)}°W` }));
    }
    this.map.addSource("graticule", { type: "geojson", data: { type: "Feature", geometry: { type: "MultiLineString", coordinates: lines } } });
    this.map.addLayer({ id: "graticule", type: "line", source: "graticule", paint: { "line-color": ICE, "line-opacity": 0.09, "line-width": 1 } });
    this.map.addSource("graticule-labels", { type: "geojson", data: collection(labels) });
    this.map.addLayer({ id: "graticule-labels", type: "symbol", source: "graticule-labels",
      layout: { "text-field": ["get", "t"], "text-font": font, "text-size": 10, "text-anchor": "bottom-left", "text-offset": [0.3, -0.2] },
      paint: { "text-color": ICE, "text-opacity": 0.45 } });
  }

  /* The biome as an island: a mask darkens the world outside the border. Events outside stay visible. */
  addIsland(border) {
    const polygons = outerRings(border);
    this.map.addSource("border", { type: "geojson", data: border });
    this.map.addSource("mask", { type: "geojson", data: { type: "Feature", geometry: { type: "Polygon", coordinates: [WORLD, ...polygons] } } });
    this.map.addLayer({ id: "mask", type: "fill", source: "mask", paint: { "fill-color": CANVAS, "fill-opacity": 0.84 } }, "graticule");
    this.map.addLayer({ id: "shore-glow", type: "line", source: "border", paint: { "line-color": ICE, "line-width": 7, "line-blur": 7, "line-opacity": 0.12 } }, "graticule");
    this.map.addLayer({ id: "shore", type: "line", source: "border", paint: { "line-color": ICE, "line-width": 1, "line-opacity": 0.55 } }, "graticule");
  }

  /* An event: a core dot sized by its detections, a ring for MEDIUM and HIGH, a glow for HIGH.
     The opacity falls with the age of the newest detection. */
  addEvents() {
    const map = this.map;
    const colour = ["match", ["get", "level"], "LOW", LEVEL.LOW, "MEDIUM", LEVEL.MEDIUM, LEVEL.HIGH];
    const fade = ["interpolate", ["linear"], ["get", "age"], 0, 1, 12, 0.75, 24, 0.5];
    const base = ["interpolate", ["linear"], ["log10", ["max", 1, ["get", "detections"]]], 0, 2.6, 2, 3.8, 4, 6, 5.5, 8.5];
    // The marks are smaller when the whole biome is in a small view, for example on a phone.
    const size = (add = 0) => ["interpolate", ["linear"], ["zoom"], 4, ["+", ["*", 0.6, base], add * 0.6], 7, ["+", base, add]];
    map.addSource("events", { type: "geojson", data: this.data.events });
    map.addSource("detections", { type: "geojson", data: this.data.detections });
    map.addLayer({ id: "ev-glow", type: "circle", source: "events", filter: ["==", ["get", "level"], "HIGH"],
      paint: { "circle-radius": size(7), "circle-blur": 1, "circle-color": LEVEL.HIGH, "circle-opacity": ["*", 0.22, fade] } });
    map.addLayer({ id: "ev-ring", type: "circle", source: "events", filter: ["==", ["get", "level"], "HIGH"],
      paint: { "circle-radius": size(3), "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": colour, "circle-stroke-width": 0.8, "circle-stroke-opacity": ["*", 0.55, fade] } });
    map.addLayer({ id: "ev-core", type: "circle", source: "events",
      paint: { "circle-radius": size(), "circle-color": colour, "circle-opacity": fade, "circle-stroke-color": "rgba(0,0,0,0.7)", "circle-stroke-width": 0.8 } });
    map.addLayer({ id: "ev-hover", type: "circle", source: "events", filter: ["==", ["get", "id"], this.data.hover ?? -1],
      paint: { "circle-radius": size(6), "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#f2f2ea", "circle-stroke-width": 1.2 } });
    map.addLayer({ id: "detections", type: "circle", source: "detections",
      paint: { "circle-radius": ["interpolate", ["linear"], ["sqrt", ["coalesce", ["get", "frp"], 0]], 0, 2, 40, 7],
        "circle-color": ["get", "colour"], "circle-opacity": 0.85, "circle-stroke-color": CANVAS, "circle-stroke-width": 0.8 } });
  }

  wire() {
    const map = this.map, layers = ["ev-core", "ev-ring"];
    const near = (p, pad) => (map.getLayer("ev-core") ? map.queryRenderedFeatures([[p.x - pad, p.y - pad], [p.x + pad, p.y + pad]], { layers }) : []);
    map.on("click", (e) => { const found = near(e.point, 8); if (found.length) this.handlers.select(found[0].properties.id); });
    map.on("mousemove", (e) => {
      const found = near(e.point, 6);
      map.getCanvas().style.cursor = found.length ? "pointer" : "";
      this.handlers.hover(found.length ? found[0].properties.id : null, e.originalEvent);
      document.getElementById("readout").textContent = coord(e.lngLat.lat, e.lngLat.lng, 4);
    });
    map.on("mouseout", () => this.handlers.hover(null));
  }

  setEvents(rows) {
    this.data.events = collection(rows.map((r) => point(r.lon, r.lat, { id: r.event_id, level: r.level, age: r.newest_observation_age_h, detections: r.detections })));
    this.map.getSource("events")?.setData(this.data.events);
  }

  hover(id) {
    this.data.hover = id;
    if (this.map.getLayer("ev-hover")) this.map.setFilter("ev-hover", ["==", ["get", "id"], id ?? -1]);
  }

  /* The selection: corner brackets at the event, its newest detections, and a camera move. */
  select(event, move = true) {
    this.marker?.remove();
    this.marker = null;
    if (!event) { this.setDetections([]); return; }
    const element = document.createElement("div");
    element.className = "target";
    element.innerHTML = `<span></span><b>${coord(event.lat, event.lon)}</b>`;
    this.marker = new maplibregl.Marker({ element }).setLngLat([event.lon, event.lat]).addTo(this.map);
    if (move) {
      const zoom = Math.max(this.map.getZoom(), event.detections > 5000 ? 8 : 9.5);
      this.map.easeTo({ center: [event.lon, event.lat], zoom, pitch: this.solid ? 45 : 0, padding: this.padding(), duration: STILL ? 0 : 1100 });
    }
  }

  setDetections(rows) {
    this.data.detections = collection(rows.map((d) => point(d.lon, d.lat, { frp: d.frp_mw, colour: FAMILY_COLOUR[d.sensor_family] ?? ICE, family: FAMILY[d.sensor_family] })));
    this.map.getSource("detections")?.setData(this.data.detections);
  }

  /* The first time that the border is in, the home view becomes the biome. The camera goes there at once,
     if no event is selected: the biome is a little smaller than the box of the start. */
  homeOnBiome(border) {
    let [west, south, east, north] = [Infinity, Infinity, -Infinity, -Infinity];
    for (const [lon, lat] of outerRings(border).flat()) {
      [west, south, east, north] = [Math.min(west, lon), Math.min(south, lat), Math.max(east, lon), Math.max(north, lat)];
    }
    this.home = [[west, south], [east, north]];
    this.island = true;
    if (!this.marker) this.fit(0);
  }

  /* The home view: all of the biome in the free area between the panels. */
  fit(duration = 900) {
    this.map.fitBounds(this.home, { padding: HOME_PAD, pitch: 0, bearing: 0, duration: STILL ? 0 : duration });
  }

  setBase(base) {
    if (base === this.base) return;
    this.base = base;
    const key = this.settings.map_key;
    this.map.setStyle(base === "imagery" ? imagery(key) : `https://api.maptiler.com/maps/outdoor/style.json?key=${key}`, { diff: false });
  }

  toggleSolid() {
    this.solid = !this.solid;
    if (this.solid && this.dem()) this.map.setTerrain({ source: this.dem(), exaggeration: 1.5 });
    if (!this.solid) this.map.setTerrain(null);
    this.map.easeTo({ pitch: this.solid && this.map.getZoom() > 7 ? 45 : 0, duration: STILL ? 0 : 600 });
    return this.solid;
  }

  zoom(delta) { this.map.zoomTo(this.map.getZoom() + delta, { duration: STILL ? 0 : 250 }); }
  resize() { this.map.resize(); this.map.setPadding(this.padding()); }
}

/* The outer ring of each polygon of the biome border. */
function outerRings(border) {
  const geometry = (border.features ? border.features[0] : border).geometry;
  const polygons = geometry.type === "MultiPolygon" ? geometry.coordinates : [geometry.coordinates];
  return polygons.map((p) => p[0]);
}

function point(lon, lat, properties) { return { type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties }; }
function collection(features) { return { type: "FeatureCollection", features }; }
export { LEVEL, BLUE };
