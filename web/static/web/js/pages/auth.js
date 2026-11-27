import { api, ApiError } from "../api.js";
import { html, icon, alertBox, delegate } from "../ui.js";
import { logoMark } from "../logo.js";

let timer = null;
const stopTimer = () => { clearInterval(timer); timer = null; };

/* ---------------------------------------------------------------- shared pieces */
const art = html`<section class="auth-art">
  <div class="brand">${logoMark(34)}<span>Vecta</span></div>
  <div><div class="statement">Leave, approved and on record.</div>
    <p class="plain">Request time off, send it to the right approver, and keep a clear history of every decision.</p></div>
  <div class="foot">Every action is recorded in an audit trail.</div></section>`;
const layout = (inner) => html`<div class="auth">${art}<section class="auth-form"><div class="auth-card stack" style="gap:20px">${inner}</div></section></div>`;

export const pwField = (id, name, label, { autocomplete = "current-password", hint = "", meter = false } = {}) => html`
  <div class="field"><label for="${id}">${label}</label>
    <div class="pw"><input class="input" id="${id}" name="${name}" type="password" autocomplete="${autocomplete}" required ${meter ? html`data-meter="${id}-m"` : ""}>
      <button type="button" class="icon-btn" data-toggle="${id}" aria-label="Show password">${icon("eye")}</button></div>
    ${meter ? html`<div class="meter" aria-hidden="true"><i id="${id}-m"></i></div>` : ""}${hint ? html`<small>${hint}</small>` : ""}</div>`;

const score = (p) => (p.length >= 8) + (p.length >= 12) + (/[a-z]/.test(p) && /[A-Z]/.test(p)) + /\d/.test(p) + /[^A-Za-z0-9]/.test(p);

/** Show/hide password buttons and the strength meter, for anything inside `root`. */
export function wirePasswords(root) {
  delegate(root, "click", "[data-toggle]", (e, btn) => {
    const input = root.querySelector("#" + btn.dataset.toggle), show = input.type === "password";
    input.type = show ? "text" : "password";
    btn.innerHTML = icon(show ? "eyeoff" : "eye");
    btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
  });
  delegate(root, "input", "[data-meter]", (e, input) => {
    const bar = root.querySelector("#" + input.dataset.meter), n = score(input.value);
    bar.style.width = (n * 20) + "%";
    bar.style.background = n <= 2 ? "var(--bad)" : n === 3 ? "var(--warn)" : "var(--primary)";
  });
}

export const codeHtml = () => html`<div class="code" id="code">${[0, 1, 2, 3, 4, 5].map((i) => html`<input inputmode="numeric" pattern="[0-9]*" maxlength="1" autocomplete="${i === 0 ? "one-time-code" : "off"}" aria-label="Digit ${i + 1} of 6">`)}</div>`;

/** Six single-digit boxes: auto-advance, backspace, arrow keys, paste a whole code. */
export function wireCode(root, onComplete) {
  const box = root.querySelector("#code"), ins = [...box.querySelectorAll("input")];
  const value = () => ins.map((i) => i.value).join("");
  ins.forEach((inp, i) => {
    inp.addEventListener("input", () => {
      inp.value = inp.value.replace(/\D/g, "").slice(-1);
      box.classList.remove("bad");
      if (inp.value && ins[i + 1]) ins[i + 1].focus();
      if (value().length === 6) onComplete(value());
    });
    inp.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && !inp.value && ins[i - 1]) { ins[i - 1].focus(); ins[i - 1].value = ""; }
      if (e.key === "ArrowLeft" && ins[i - 1]) ins[i - 1].focus();
      if (e.key === "ArrowRight" && ins[i + 1]) ins[i + 1].focus();
    });
    inp.addEventListener("paste", (e) => {
      e.preventDefault();
      const d = (e.clipboardData?.getData("text") || "").replace(/\D/g, "").slice(0, 6);
      d.split("").forEach((c, k) => { ins[k].value = c; });
      ins[Math.min(d.length, 5)].focus();
      if (d.length === 6) onComplete(d);
    });
  });
  ins[0].focus();
  return { value, reject() { box.classList.add("bad"); ins.forEach((i) => { i.value = ""; }); ins[0].focus(); } };
}

/** Counts down on a "resend" button. */
export function countdown(btn, seconds, label = "Resend code") {
  stopTimer();
  let n = seconds;
  const tick = () => { btn.disabled = n > 0; btn.textContent = n > 0 ? `Resend in ${n}s` : label; if (n-- <= 0) stopTimer(); };
  tick();
  timer = setInterval(tick, 1000);
}
export { stopTimer };

const formValues = (f) => Object.fromEntries([...f.elements].filter((x) => x.name).map((x) => [x.name, x.value]));
function bind(root, selector, fn) {
  const f = root.querySelector(selector), err = f.querySelector("[data-error]"), btn = f.querySelector("button[type=submit]");
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.innerHTML = ""; btn.disabled = true;
    try { await fn(formValues(f)); }
    catch (ex) { err.innerHTML = alertBox(ex.message, "bad", "alert"); btn.disabled = false; }
  });
}

/* ---------------------------------------------------------------- the sign-in flow */
export function startAuth(root, { config, onSession, message = "", messageKind = "bad" }) {
  const go = (name, ctx = {}) => { stopTimer(); SCREENS[name](ctx); };
  const mount = (inner) => { root.innerHTML = layout(inner); root.querySelector("input")?.focus(); };
  const note = (m, kind = "ok") => m ? alertBox(m, kind, kind === "bad" ? "alert" : "check") : "";

  delegate(root, "click", "[data-go]", (e, el) => go(el.dataset.go, el.dataset.email ? { email: el.dataset.email } : {}));
  delegate(root, "click", "[data-provider]", async (e, el) => {
    el.disabled = true;
    try { const r = await api(`/auth/oauth/${el.dataset.provider}/start/`, { method: "POST", body: { mode: "login" } }); location.href = r.url; }
    catch (ex) { el.disabled = false; root.querySelector("[data-error]").innerHTML = alertBox(ex.message, "bad", "alert"); }
  });
  wirePasswords(root);

  const providers = () => config.providers.length ? html`<div class="divider">or continue with</div>
    <div class="oauth">${config.providers.map((p) => html`<button class="btn" type="button" data-provider="${p.id}"><span class="g" aria-hidden="true">${p.name[0]}</span> ${p.name}</button>`)}</div>` : "";

  /** One screen for every "enter the 6-digit code" step. */
  function codeScreen({ title, email, resendIn, verify, resend, back }) {
    mount(html`<div><h1>${title}</h1><p class="lead">We sent a 6-digit code to <b>${email}</b>. It expires in ${config.code_minutes} minutes.</p></div>
      ${codeHtml()}<div data-error></div>
      <div class="row between"><button class="linkish" type="button" id="resend"></button><button class="linkish" type="button" data-go="${back[1]}">${back[0]}</button></div>
      <p class="small muted">Not there? Check your spam folder.</p>`);
    const errBox = root.querySelector("[data-error]"), resendBtn = root.querySelector("#resend");
    let busy = false;
    const code = wireCode(root, async (value) => {
      if (busy) return;
      busy = true; errBox.innerHTML = "";
      try { await verify(value); }
      catch (ex) { errBox.innerHTML = alertBox(ex.message, "bad", "alert"); code.reject(); }
      busy = false;
    });
    countdown(resendBtn, resendIn ?? config.resend_seconds);
    resendBtn.addEventListener("click", async () => {
      errBox.innerHTML = "";
      try { const r = await resend(); errBox.innerHTML = alertBox("A new code is on its way.", "ok", "check"); countdown(resendBtn, r?.resend_in ?? config.resend_seconds); }
      catch (ex) { errBox.innerHTML = alertBox(ex.message, "bad", "alert"); if (ex.data?.retry_after) countdown(resendBtn, ex.data.retry_after); }
    });
  }

  const SCREENS = {
    login({ notice, kind } = {}) {
      mount(html`<div><h1>Sign in</h1><p class="lead">Welcome back to Vecta.</p></div>${note(notice || message, kind || (notice ? "ok" : messageKind))}
        <form class="form" id="f" novalidate>
          <div class="field"><label for="id">Email or username</label><input class="input" id="id" name="identifier" autocomplete="username" autocapitalize="none" spellcheck="false" required></div>
          ${pwField("pw", "password", "Password")}
          <div class="row between"><span></span><button class="linkish" type="button" data-go="forgot">Forgot password?</button></div>
          <div data-error></div><button class="btn primary" type="submit">Sign in</button></form>
        ${providers()}
        ${config.registration_enabled ? html`<p class="muted">New to Vecta? <button class="linkish" type="button" data-go="register">Create an account</button></p>` : html`<p class="small muted">Accounts are created by HR.</p>`}
        <p class="muted">Are you an HR Manager? <button class="linkish" type="button" data-go="hr-login">Sign in as HR Manager</button></p>`);
      bind(root, "#f", async (d) => {
        try { 
          onSession(
            await api("/auth/login/", {
               method: "POST", 
               body: d 
              }
            )
          ); 
        }
        catch (ex) {
          throw ex;
        }
      });
    },
    hrLogin() {
  mount(html`<div><h1>HR Manager Sign In</h1><p class="lead">This area is for authorised HR Managers only.</p></div>
    <form class="form" id="f" novalidate>
      <div class="field"><label for="id">Email or username</label><input class="input" id="id" name="identifier" autocomplete="username" autocapitalize="none" spellcheck="false" required></div>
      ${pwField("pw", "password", "Password")}
      <div class="row between"><span></span><button class="linkish" type="button" data-go="forgot">Forgot password?</button></div>
      <div data-error></div><button class="btn primary" type="submit">Sign in as HR</button></form>
    <p class="muted"><button class="linkish" type="button" data-go="login">← Back to Staff Login</button></p>`);
  bind(root, "#f", async (d) => {
    try {
      const r = await api("/auth/login/", { method: "POST", body: { ...d, role_required: "hr_manager" } });
      onSession(r);
    } catch (ex) {
      throw ex;
    }
  });
},

    register() {
      const dom = config.allowed_domains.length ? `Use your institution email (${config.allowed_domains.map((d) => "@" + d).join(", ")}).` : "";
      mount(html`<div><h1>Create your account</h1><p class="lead">Create your Vecta account to get started.</p></div>
        <form class="form" id="f" novalidate>
          <div class="two">

            <div class="field">
              <label for="staff_id">Staff ID</label>
              <input class="input" type="text" id="staff_id" name="staff_id" placeholder="Enter your staff ID" autocomplete="off" required>
            </div>
            <div class="field">
              <label for="fn">First name</label>
              <input class="input" id="fn" name="first_name" autocomplete="given-name" required>
            </div>

            <div class="field">
              <label for="ln">Last name</label>
              <input class="input" id="ln" name="last_name" autocomplete="family-name" required>
            </div>
          </div>
          <div class="field">
            <label for="em">Email</label>
            <input class="input" id="em" name="email" type="email" autocomplete="email" autocapitalize="none" required>${dom ? html`<small>${dom}</small>` : ""}
          </div>
          <div class="field">
            <label for="phone">Phone Number</label>
            <input class="input" type="tel" id="phone" name="phone" placeholder="Enter your phone number" autocomplete="tel" required>
          </div>
          <div class="field department-picker">
            <label for="department">Department</label>
            <input class="input" type="text" id="department" name="department" placeholder="Select your department" readonly autocomplete="off" required>
            <div class="department-menu" id="department-menu" hidden>
              <div class="department-category">
                <button type="button" class="department-category-btn">
                  Academic <span>›</span>
                </button>
                <div class="department-submenu">
                  <button type="button" data-department="Academic: Accounting">Accounting</button>
                  <button type="button" data-department="Academic: Banking and Finance">Banking and Finance</button>
                  <button type="button" data-department="Academic: Biochemistry">Biochemistry</button>
                  <button type="button" data-department="Academic: Business Admin">Business Admin</button>
                  <button type="button" data-department="Academic: Computer Science">Computer Science</button>
                  <button type="button" data-department="Academic: Cybersecurity">Cybersecurity</button>
                  <button type="button" data-department="Academic: Data Science">Data Science</button>
                  <button type="button" data-department="Academic: Economics">Economics</button>
                  <button type="button" data-department="Academic: Law">Law</button>
                  <button type="button" data-department="Academic: Mass Communication">Mass Communication</button>
                  <button type="button" data-department="Academic: Microbiology">Microbiology</button>
                  <button type="button" data-department="Academic: Nursing">Nursing</button>
                  <button type="button" data-department="Academic: Philosophy">Philosophy</button>
                  <button type="button" data-department="Academic: Public Admin">Public Admin</button>
                  <button type="button" data-department="Academic: Religious Studies">Religious Studies</button>
                </div>
              </div>
              <div class="department-category">
                <button type="button" class="department-category-btn">
                  Non-academic <span>›</span>
                </button>
                <div class="department-submenu">
                  <button type="button" data-department="Non-academic: Admin">Admin</button>
                  <button type="button" data-department="Non-academic: Bursary">Bursary</button>
                  <button type="button" data-department="Non-academic: Human Resources">Human Resources</button>
                  <button type="button" data-department="Non-academic: Works">Works</button>
                </div>
              </div>
            </div>
          </div>
          <style>
            .department-picker {
              position: relative;
            }
            .department-menu {
              position: absolute;
              top: 100%;
              left: 0;
              width: 220px;
              background: white;
              border: 1px solid #ddd;
              border-radius: 8px;
              box-shadow: 0 5px 15px rgba(0,0,0,0.12);
              z-index: 1000;
            }
            .department-menu[hidden] {
              display: none;
            }
            .department-category {
              position: relative;
            }
            .department-category-btn {
              width: 100%;
              padding: 12px;
              border: none;
              background: white;
              text-align: left;
              cursor: pointer;
              display: flex;
              justify-content: space-between;
            }
            .department-category-btn:hover,
            .department-submenu button:hover {
              background: #f0f0f0;
            }
            .department-submenu {
              display: none;
              position: absolute;
              left: 100%;
              top: 0;
              width: 230px;
              max-height: 280px;
              overflow-y: auto;
              background: white;
              border: 1px solid #ddd;
              border-radius: 8px;
              box-shadow: 0 5px 15px rgba(0,0,0,0.12);
            }
            .department-category:hover .department-submenu,
            .department-category:focus-within .department-submenu,
            .department-category.open .department-submenu {
              display: block;
            }
            .department-submenu button {
              display: block;
              width: 100%;
              padding: 10px;
              border: none;
              background: white;
              text-align: left;
              cursor: pointer;
            }
            </style>

          <div class="field">
            <label for="role">Role</label>
            <select class="input" id="role" name="role" required>
              <option value="">Select your role</option>
              <option value="staff">Staff</option>
              <option value="department_head">HOD</option>
            </select>
          </div>
          ${pwField("pw", "password", "Password", { 
            autocomplete: "new-password",
            placeholder: "Enter your password", 
            meter: true, 
            hint: "At least 8 characters. Avoid common passwords." })}

          <div class="field">
            <label for="confirm-password">Confirm Password</label>
            <input
              class="input"
              type="password"
              id="confirm-password"
              name="confirm_password"
              placeholder="Re-enter your password"
              autocomplete="new-password"
              required
            >
            <small id="password-match-message"></small>
          </div>

          <div data-error></div><button class="btn primary" type="submit">Continue</button></form>
        ${providers()}
        <p class="muted">Already have an account? <button class="linkish" type="button" data-go="login">Sign in</button></p>
        <p class="small muted">After you join, HR will place you in your department so you can request leave.</p>`);

      const departmentInput = root.querySelector("#department");
      const departmentMenu = root.querySelector("#department-menu");

      departmentInput.addEventListener("click", () => {
        departmentMenu.hidden = !departmentMenu.hidden;
      });

      root.querySelectorAll(".department-category-btn").forEach(button => {
        button.addEventListener("click", (event) => {
          event.stopPropagation();

          const category = button.closest(".department-category");

          root.querySelectorAll(".department-category").forEach(item => {
            if (item !== category) {
              item.classList.remove("open");
            }
          });

          category.classList.toggle("open");
        });
      });

      root.querySelectorAll("[data-department]").forEach(button => {
        button.addEventListener("click", () => {
          departmentInput.value = button.dataset.department;
          departmentMenu.hidden = true;

          root.querySelectorAll(".department-category").forEach(item => {
            item.classList.remove("open");
          });
        });
      });

      root.addEventListener("click", (event) => {
        if (!event.target.closest(".department-picker")) {
          departmentMenu.hidden = true;
        }
      });

      const passwordInput = root.querySelector("#pw");
      const confirmPasswordInput = root.querySelector("#confirm-password");
      const passwordMessage = root.querySelector("#password-match-message");

      function checkPasswordMatch() {
        if (!confirmPasswordInput.value) {
          passwordMessage.textContent = "";
          confirmPasswordInput.setCustomValidity("");
          return;
        }

        if (passwordInput.value !== confirmPasswordInput.value) {
          passwordMessage.textContent = "Passwords do not match.";
          passwordMessage.style.color = "red";

          confirmPasswordInput.setCustomValidity(
            "The passwords do not match."
          );
        } else {
          passwordMessage.textContent = "Passwords match.";
          passwordMessage.style.color = "green";

          confirmPasswordInput.setCustomValidity("");
        }
      }

      passwordInput.addEventListener("input", checkPasswordMatch);
      confirmPasswordInput.addEventListener("input", checkPasswordMatch);

      bind(root, "#f", async (d) => {
        if (d.password !== d.confirm_password) {
            confirmPasswordInput.setCustomValidity("Passwords do not match.");
            confirmPasswordInput.reportValidity();
            throw new ApiError(400, "Passwords do not match.");
        }

        delete d.confirm_password;

        await api("/auth/register/", {
            method: "POST",
            body: d
        });

        go("login", {
            notice: "Your account has been created successfully. You can now sign in.",
            kind: "ok"
        });
      });
    },

    verify({ email, resendIn }) {
      codeScreen({
        title: "Check your email", email, resendIn, back: ["Use a different email", "register"],
        verify: async (code) => onSession(await api("/auth/register/verify/", { method: "POST", body: { email, code } })),
        resend: () => api("/auth/register/resend/", { method: "POST", body: { email } }),
      });
    },

    forgot() {
      mount(html`<div><h1>Reset your password</h1><p class="lead">Enter the email address on your account and we will send you a 6-digit code.</p></div>
        <form class="form" id="f" novalidate><div class="field"><label for="em">Email</label><input class="input" id="em" name="email" type="email" autocomplete="email" autocapitalize="none" required></div>
          <div data-error></div><button class="btn primary" type="submit">Send code</button></form>
        <button class="linkish" type="button" data-go="login">Back to sign in</button>`);
      bind(root, "#f", async (d) => {
        const r = await api("/auth/password/forgot/", { method: "POST", body: d });
        go("resetCode", { email: d.email.trim(), resendIn: r.resend_in });
      });
    },

    resetCode({ email, resendIn }) {
      codeScreen({
        title: "Enter your code", email, resendIn, back: ["Use a different email", "forgot"],
        verify: async (code) => { const r = await api("/auth/password/verify/", { method: "POST", body: { email, code } }); go("resetNew", { token: r.reset_token }); },
        resend: () => api("/auth/password/forgot/", { method: "POST", body: { email } }),
      });
    },

    resetNew({ token }) {
      mount(html`<div><h1>Choose a new password</h1><p class="lead">Your code was accepted. Pick a password you have not used elsewhere.</p></div>
        <form class="form" id="f" novalidate>
          ${pwField("pw", "new_password", "New password", { autocomplete: "new-password", meter: true, hint: "At least 8 characters. Avoid common passwords." })}
          ${pwField("pw2", "confirm", "Confirm new password", { autocomplete: "new-password" })}
          <div data-error></div><button class="btn primary" type="submit">Update password</button></form>`);
      bind(root, "#f", async (d) => {
        if (d.new_password !== d.confirm) throw new ApiError(400, "The two passwords do not match.");
        await api("/auth/password/reset/", { method: "POST", body: { reset_token: token, new_password: d.new_password } });
        go("login", { notice: "Password updated. Sign in with your new password." });
      });
    },
  };
  go("login");
}

/* ---------------------------------------------------------------- first sign-in with a temporary password */
export function renderForceChange(root, { user, onDone, onLogout }) {
  root.innerHTML = layout(html`<div><h1>Set your own password</h1><p class="lead">Hi ${user.first_name || user.username}, your account uses a temporary password. Choose a new one to continue.</p></div>
    <form class="form" id="cf" novalidate>
      ${pwField("o", "old_password", "Temporary password")}
      ${pwField("n", "new_password", "New password", { autocomplete: "new-password", meter: true })}
      ${pwField("c", "confirm", "Confirm new password", { autocomplete: "new-password" })}
      <div data-error></div><button class="btn primary" type="submit">Save and continue</button></form>
    <button class="linkish" type="button" id="lo">Sign out</button>`);
  wirePasswords(root);
  bind(root, "#cf", async (d) => {
    if (d.new_password !== d.confirm) throw new ApiError(400, "The two new passwords do not match.");
    const r = await api("/auth/change-password/", { method: "POST", body: { old_password: d.old_password, new_password: d.new_password } });
    onDone(r.token);
  });
  root.querySelector("#lo").addEventListener("click", onLogout);
}
