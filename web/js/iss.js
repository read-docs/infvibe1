const els = {
  stats: document.getElementById("stats"),
  nowStatus: document.getElementById("now-status"),
  passes: document.getElementById("passes"),
  passesStatus: document.getElementById("passes-status"),
  onlyVisible: document.getElementById("only-visible"),
  check: document.getElementById("check"),
  passesTz: document.getElementById("passes-tz"),
};

const POSITION_MS = 5000;
const TRACK_MS = 3 * 60 * 1000;
const PASSES_MS = 10 * 60 * 1000;

let observer = null;  // the saved location, once picked
let lastPasses = null;
let passesTimer = null;

// --- Map

const map = L.map("iss-map", { worldCopyJump: true, minZoom: 1 }).setView([20, 0], 2);
// Standard OpenStreetMap tiles, darkened with a CSS filter to match the page.
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 10,
  className: "dark-tiles",
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

const issMarker = L.marker([0, 0], {
  icon: L.divIcon({ className: "iss-icon", html: "<span>ISS</span>", iconSize: [44, 22] }),
  zIndexOffset: 1000,
});
const observerMarker = L.circleMarker([0, 0], { radius: 6, color: "#f4efe6", weight: 2, fillOpacity: 0 });
const trackLayer = L.layerGroup().addTo(map);
let centredOnce = false;

// Splits a track into pieces wherever it wraps around the ±180° meridian, so
// Leaflet doesn't draw a line across the whole map.
function splitAtDateLine(points) {
  const pieces = [];
  let piece = [];
  for (const p of points) {
    if (piece.length && Math.abs(p.lon - piece[piece.length - 1][1]) > 180) {
      pieces.push(piece);
      piece = [];
    }
    piece.push([p.lat, p.lon]);
  }
  if (piece.length) pieces.push(piece);
  return pieces;
}

async function loadTrack() {
  try {
    const data = await fetchJson("/api/iss/track?minutes=95");
    trackLayer.clearLayers();
    const past = data.points.filter((p) => p.time <= data.now);
    const next = data.points.filter((p) => p.time >= data.now);
    for (const piece of splitAtDateLine(past)) {
      L.polyline(piece, { color: "#a9a3b8", weight: 2, dashArray: "4 6", interactive: false }).addTo(trackLayer);
    }
    for (const piece of splitAtDateLine(next)) {
      L.polyline(piece, { color: "#f2c46d", weight: 2, interactive: false }).addTo(trackLayer);
    }
  } catch {
    // The position updates report errors; a missing track line is self-explanatory.
  }
}

// --- Position and stats

function fact(term, value) {
  const div = document.createElement("div");
  const dt = document.createElement("dt");
  dt.textContent = term;
  const dd = document.createElement("dd");
  dd.textContent = value;
  div.append(dt, dd);
  return div;
}

function formatLatLon(lat, lon) {
  return `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(2)}°${lon >= 0 ? "E" : "W"}`;
}

function renderCheck(data) {
  const c = data.check;
  const tleAge = data.tle.age_hours < 48 ? `${Math.round(data.tle.age_hours)} hours` : `${(data.tle.age_hours / 24).toFixed(1)} days`;
  const source = `Our own SGP4 engine computes every position on this page from orbital elements (TLE) published by ${data.tle.source}, ${tleAge} old.`;
  if (!c || c.error) {
    els.check.textContent = `${source} The independent live position (wheretheiss.at) is unavailable right now${c ? `: ${c.error}` : ""}.`;
    return;
  }
  els.check.textContent = `${source} Compared with the live position from ${c.source}, it is ${c.difference_km.toFixed(2)} km off ` +
    `(ours ${formatLatLon(c.ours.lat, c.ours.lon)}, ${c.ours.alt_km} km up; theirs ${formatLatLon(c.live.lat, c.live.lon)}, ${c.live.alt_km} km up). ` +
    "The ISS moves 7.7 km every second, so a few km means the two agree to well under a second.";
}

let checkCounter = 0;

async function updatePosition() {
  // The live comparison only needs refreshing every 30 s.
  const check = checkCounter++ % 6 === 0;
  const params = new URLSearchParams();
  if (observer) {
    params.set("lat", observer.lat);
    params.set("lon", observer.lon);
  }
  if (check) params.set("check", "1");
  try {
    const d = await fetchJson(`/api/iss/now?${params}`);
    els.nowStatus.hidden = true;
    issMarker.setLatLng([d.lat, d.lon]);
    if (!map.hasLayer(issMarker)) issMarker.addTo(map);
    if (!centredOnce) {
      map.setView([d.lat, d.lon], 2);
      centredOnce = true;
    }
    const facts = [
      fact("Over", formatLatLon(d.lat, d.lon)),
      fact("Altitude", `${Math.round(d.alt_km)} km`),
      fact("Speed", `${d.speed_kms.toFixed(2)} km/s (${Math.round(d.speed_kms * 3600).toLocaleString("en")} km/h)`),
      fact("One orbit", `${Math.round(d.period_min)} min`),
      fact("Sunlight", d.sunlit ? "In sunlight" : "In Earth's shadow"),
    ];
    if (d.look) {
      facts.push(fact("From you", d.look.alt > 0
        ? `${Math.round(d.look.alt)}° up, ${d.look.direction}, ${d.look.range_km.toLocaleString("en")} km away`
        : `Below your horizon (${d.look.range_km.toLocaleString("en")} km away)`));
    }
    els.stats.replaceChildren(...facts);
    if (check) renderCheck(d);
  } catch (err) {
    els.nowStatus.textContent = `Couldn't compute the ISS position: ${err.message}`;
    els.nowStatus.className = "status error";
    els.nowStatus.hidden = false;
  }
}

// --- Passes

function dayLabel(unix) {
  return new Date(unix * 1000).toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "short", timeZone: observer.timezone || undefined,
  });
}

const timeLabel = (unix) => localTime(unix, observer.timezone);

function pointLabel(p) {
  return `${timeLabel(p.time)}  ${Math.round(p.alt)}° ${p.direction}`;
}

function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}

function renderPasses() {
  if (!lastPasses) return;
  const passes = lastPasses.filter((p) => p.visible || !els.onlyVisible.checked);
  els.passes.replaceChildren();
  if (!passes.length) {
    els.passes.hidden = true;
    els.passesStatus.textContent = els.onlyVisible.checked
      ? "No visible passes in the next 3 days. The ISS is either below your horizon, in Earth's shadow, or passing in daylight."
      : "No passes in the next 3 days.";
    els.passesStatus.className = "status";
    els.passesStatus.hidden = false;
    return;
  }
  const head = document.createElement("tr");
  for (const h of ["Date", "Appears", "Highest", "Disappears", "Brightness", "Sky"]) {
    const th = document.createElement("th");
    th.textContent = h;
    head.append(th);
  }
  els.passes.append(head);
  for (const p of passes) {
    const tr = document.createElement("tr");
    // For visible passes show the part you can actually see.
    const v = p.visible ? p.visible_part : null;
    tr.append(cell(dayLabel(p.rise.time), "body-name"));
    tr.append(cell(pointLabel(v ? v.start : p.rise)));
    tr.append(cell(v && v.max_alt < p.peak.alt - 1 ? `${Math.round(v.max_alt)}° (visible part)` : pointLabel(p.peak)));
    tr.append(cell(pointLabel(v ? v.end : p.set)));
    tr.append(v ? cell(`mag ${v.magnitude.toFixed(1).replace("-", "−")}`) : cell("Not visible", "muted"));
    // Cloud cover only matters (and is only given) for passes you could otherwise see.
    if (p.visible && p.cloud != null) tr.append(cell(p.clear ? `Clear (${p.cloud}% cloud)` : `Cloudy (${p.cloud}%)`, p.clear ? "" : "muted"));
    else tr.append(cell(p.visible ? "No forecast" : "", "muted"));
    if (p.visible && p.clear !== false) tr.className = "visible";
    els.passes.append(tr);
  }
  els.passes.hidden = false;
  els.passesStatus.hidden = true;
  els.passesTz.textContent = observer.timezone ? `Times in ${observer.timezone}` : "Times in your browser's time zone";
}

async function loadPasses() {
  clearTimeout(passesTimer);
  if (!observer) return;
  const loc = observer;
  if (!lastPasses) {
    els.passesStatus.textContent = "Calculating passes…";
    els.passesStatus.className = "status loading";
    els.passesStatus.hidden = false;
  }
  try {
    const data = await fetchJson(`/api/iss/passes?lat=${loc.lat}&lon=${loc.lon}&days=3`);
    if (loc !== observer) return;
    lastPasses = data.passes;
    renderPasses();
  } catch (err) {
    els.passes.hidden = true;
    els.passesStatus.textContent = `Couldn't predict passes: ${err.message}`;
    els.passesStatus.className = "status error";
    els.passesStatus.hidden = false;
  }
  passesTimer = setTimeout(loadPasses, PASSES_MS);
}

els.onlyVisible.addEventListener("change", renderPasses);

createLocationPicker(document.getElementById("location"), (loc) => {
  observer = loc;
  lastPasses = null;
  observerMarker.setLatLng([loc.lat, loc.lon]).addTo(map);
  checkCounter = 0;
  updatePosition();
  loadPasses();
});

updatePosition();
loadTrack();
setInterval(updatePosition, POSITION_MS);
setInterval(loadTrack, TRACK_MS);
