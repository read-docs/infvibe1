// The observer's location, shared by every screen through localStorage, and a
// picker UI: search by name, use the browser's position, or click on a map.
const LOCATION_KEY = "skywatch.location";

function loadLocation() {
  try {
    const loc = JSON.parse(localStorage.getItem(LOCATION_KEY));
    return loc && Number.isFinite(loc.lat) && Number.isFinite(loc.lon) ? loc : null;
  } catch {
    return null;
  }
}

function saveLocation(loc) {
  localStorage.setItem(LOCATION_KEY, JSON.stringify(loc));
}

// Remembers the location's IANA time zone (Tonight's Sky learns it from the
// weather API) so other screens can show local times too.
function rememberTimezone(tz) {
  const loc = loadLocation();
  if (loc && tz && loc.timezone !== tz) saveLocation({ ...loc, timezone: tz });
}

// Formats a Unix time as HH:MM in the location's time zone, or the browser's if unknown.
function localTime(unix, tz) {
  if (unix == null) return "—";
  return new Date(unix * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: tz || undefined });
}

// "52.23°N, 21.01°E"
function formatCoords(lat, lon) {
  return `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(2)}°${lon >= 0 ? "E" : "W"}`;
}

// Builds the picker inside `root` and calls onChange(location) whenever the user
// picks a place. Opens itself when no location has been saved yet.
function createLocationPicker(root, onChange) {
  root.innerHTML = `
    <div class="loc-bar">
      <span class="loc-label">Location: <strong class="loc-name"></strong></span>
      <button type="button" class="loc-toggle">Change</button>
    </div>
    <div class="loc-picker" hidden>
      <form class="loc-search">
        <input type="search" placeholder="Search for a city…" aria-label="City name" autocomplete="off">
        <button type="submit">Search</button>
        <button type="button" class="loc-geo">Use my location</button>
      </form>
      <p class="loc-message" hidden></p>
      <ul class="loc-results"></ul>
      <div class="loc-map"></div>
      <p class="loc-hint">…or click anywhere on the map.</p>
    </div>`;

  const q = (sel) => root.querySelector(sel);
  const nameEl = q(".loc-name"), toggle = q(".loc-toggle"), picker = q(".loc-picker");
  const input = q(".loc-search input"), message = q(".loc-message"), results = q(".loc-results");
  let map = null, marker = null;

  function showMessage(text, isError = false) {
    message.textContent = text;
    message.className = isError ? "loc-message error" : "loc-message";
    message.hidden = !text;
  }

  function setOpen(open) {
    picker.hidden = !open;
    toggle.textContent = open ? "Close" : "Change";
    if (open) {
      // Leaflet measures its container, so it can only be created once visible.
      if (!map) initMap();
      map.invalidateSize();
      input.focus();
    }
  }

  function initMap() {
    const loc = loadLocation();
    map = L.map(q(".loc-map")).setView(loc ? [loc.lat, loc.lon] : [30, 0], loc ? 8 : 2);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    if (loc) marker = L.marker([loc.lat, loc.lon]).addTo(map);
    map.on("click", (e) => {
      const { lat, lng } = e.latlng.wrap();
      choose({ name: formatCoords(lat, lng), lat, lon: lng });
    });
  }

  function choose(loc) {
    saveLocation(loc);
    nameEl.textContent = loc.name;
    results.replaceChildren();
    showMessage("");
    setOpen(false);
    if (map) {
      if (marker) marker.setLatLng([loc.lat, loc.lon]);
      else marker = L.marker([loc.lat, loc.lon]).addTo(map);
      map.setView([loc.lat, loc.lon], Math.max(map.getZoom(), 8));
    }
    onChange(loc);
  }

  q(".loc-search").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    results.replaceChildren();
    showMessage("Searching…");
    try {
      const places = await fetchJson(`/api/geocode?q=${encodeURIComponent(text)}`);
      showMessage(places.length ? "" : `No places found for “${text}”.`);
      for (const p of places) {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = [p.name, p.region, p.country].filter(Boolean).join(", ");
        btn.addEventListener("click", () => choose({ name: p.name, lat: p.lat, lon: p.lon }));
        li.append(btn);
        results.append(li);
      }
    } catch (err) {
      showMessage(err.message, true);
    }
  });

  q(".loc-geo").addEventListener("click", () => {
    if (!navigator.geolocation) return showMessage("Your browser can't share its location.", true);
    showMessage("Asking your browser for your location…");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude: lat, longitude: lon } = pos.coords;
        choose({ name: `My location (${formatCoords(lat, lon)})`, lat, lon });
      },
      (err) => showMessage(`Couldn't get your location: ${err.message}`, true),
      { timeout: 15000 },
    );
  });

  toggle.addEventListener("click", () => setOpen(picker.hidden));

  // A shared link like /?lat=52.23&lon=21.01&name=Warsaw sets the location.
  const params = new URLSearchParams(location.search);
  const lat = parseFloat(params.get("lat")), lon = parseFloat(params.get("lon"));
  if (Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
    const fromUrl = { name: params.get("name") || formatCoords(lat, lon), lat, lon };
    const saved = loadLocation();
    if (!saved || saved.lat !== lat || saved.lon !== lon) saveLocation(fromUrl);
  }

  const saved = loadLocation();
  if (saved) {
    nameEl.textContent = saved.name;
    onChange(saved);
  } else {
    nameEl.textContent = "not set";
    setOpen(true);
  }
}
