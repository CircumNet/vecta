export const store = { user: null, unread: 0, pending: 0, config: { providers: [], registration_enabled: true, resend_seconds: 60, code_minutes: 10, allowed_domains: [] } };

export const hasRole = (r) => !!store.user && store.user.roles.includes(r);
export const isAdmin = () => hasRole("admin");
export const isHR = () => hasRole("hr_manager") || hasRole("admin");
export const canApprove = () =>
  ["department_head", "hr_manager", "admin"].some(hasRole) || !!store.user?.is_delegate;
export const canDelegate = () => ["department_head", "hr_manager", "admin"].some(hasRole);
export const go = (path) => { location.hash = "#" + path; };

export const theme = () => localStorage.getItem("lms.theme") || "auto";
export function setTheme(t) {
  if (t === "auto") { localStorage.removeItem("lms.theme"); delete document.documentElement.dataset.theme; }
  else { localStorage.setItem("lms.theme", t); document.documentElement.dataset.theme = t; }
}
