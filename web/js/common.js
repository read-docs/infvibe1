// Fetches JSON from our C++ backend; throws with the server's error message on failure.
async function fetchJson(url) {
  const res = await fetch(url);
  let body;
  try {
    body = await res.json();
  } catch {
    throw new Error(`Server returned HTTP ${res.status}`);
  }
  if (!res.ok) throw new Error(body.error || `Server returned HTTP ${res.status}`);
  return body;
}

// Formats a Date as YYYY-MM-DD in local time.
function isoDate(d) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
