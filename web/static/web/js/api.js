const KEY = "lms.token";

export const auth = {
  get token() { return localStorage.getItem(KEY); },
  set(t) { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY); },
};

export class ApiError extends Error {
  constructor(status, data) {
    super(messages(data)[0] || "Something went wrong. Please try again.");
    this.status = status;
    this.data = data;
  }
}

/** Flatten any DRF error payload into a list of readable strings. */
export function messages(d) {
  if (d == null) return [];
  if (typeof d === "string") return d.startsWith("<") ? ["The server returned an error. Please try again."] : [d];
  if (Array.isArray(d)) return d.flatMap(messages);
  if (typeof d === "object") return Object.values(d).flatMap(messages);
  return [String(d)];
}

export async function api(path, { method = "GET", body, params } = {}) {
  let url = "/api" + path;
  if (params) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, v);
    const s = q.toString();
    if (s) url += (url.includes("?") ? "&" : "?") + s;
  }
  const headers = {};
  if (auth.token) headers.Authorization = "Token " + auth.token;
  let payload;
  if (typeof FormData !== "undefined" && body instanceof FormData) payload = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }

  let res;
  try { res = await fetch(url, { method, headers, body: payload }); }
  catch { throw new ApiError(0, "Cannot reach the server. Check your connection."); }

  if (res.status === 401 && auth.token && !path.startsWith("/auth/login")) {
    auth.set(null);
    location.hash = "#/login";
    location.reload();
    throw new ApiError(401, "Your session has ended. Please sign in again.");
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    if (typeof data === "string" && /^\s*</.test(data)) {  // an HTML error page from the server or a proxy
      data = { detail: res.status === 413 ? "That file is too large to upload." : `The server returned an error (HTTP ${res.status}). Please try again in a moment. If it keeps happening, tell your administrator.` };
    }
    throw new ApiError(res.status, data);
  }
  return data;
}

/** First page of a paginated endpoint (or the whole array for unpaginated ones). */
export async function list(path, params) {
  const d = await api(path, { params });
  return Array.isArray(d) ? d : d.results;
}

/** Walk every page (capped) – for building pickers. */
export async function listAll(path, params = {}) {
  let out = [], page = 1;
  for (;;) {
    const d = await api(path, { params: { ...params, page } });
    if (Array.isArray(d)) return d;
    out = out.concat(d.results);
    if (!d.next) return out;
    page++;
  }
}

/** Authenticated file download (attachments, CSV, .ics). */
export async function download(path, filename, params) {
  let url = "/api" + path;
  if (params) url += "?" + new URLSearchParams(params).toString();
  const res = await fetch(url, { headers: { Authorization: "Token " + auth.token } });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}
