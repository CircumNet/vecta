import { $, text, set, click, sleep, check, until, submit, mailCode, typeCode } from "./lib.mjs";
export default async function () {
  const stamp = Date.now(), email = `reg.${stamp}@example.com`, pw1 = "Maple-River-4821", pw2 = "Cedar-Lake-9273";
  check("login: form shown when signed out, with the Vecta mark", !!$("#f") && /Sign in/.test(text()) && !!$(".auth-art svg"));
  check("login: no provider buttons when OAuth is not configured", !$("[data-provider]"));
  set("#id", "staff1"); set("#pw", "wrong"); submit("#f");
  check("login: wrong password shows an error", await until(() => /Incorrect email\/username or password/.test(text()), 4000));
  click('[data-toggle="pw"]'); check("login: show-password toggle works", $("#pw").type === "text");
  set("#id", "STAFF1@example.com"); set("#pw", "Passw0rd!123"); submit("#f");
  check("login: signing in by EMAIL works (any case)", await until(() => $("#nav") && /Good (morning|afternoon|evening)/.test(text()), 6000));
  click("#out"); check("logout: back to sign-in", await until(() => $("#f") && /Sign in/.test(text()), 4000));

  // ---- register -> email code -> signed in
  click('[data-go="register"]'); await until(() => /Create your account/.test(text()));
  set("#fn", "Reggie"); set("#ln", "Newcomer"); set("#em", email); set("#pw", "12345678"); submit("#f");
  check("register: weak password is rejected", await until(() => /(too common|entirely numeric|too short)/i.test(text()), 4000));
  const t0 = Date.now() - 500;
  set("#pw", pw1); submit("#f");
  check("register: moves to the code screen", await until(() => /Check your email/.test(text()) && $("#code"), 5000));
  const bad = ($("#code input"), "000000");
  const code = await mailCode(email, t0);
  check("register: the emailed code arrived", !!code, "no mail found - start the server with the file email backend (see README)");
  typeCode(bad === code ? "111111" : bad);
  check("register: wrong code is refused with attempts left", await until(() => /incorrect/i.test(text()), 4000));
  typeCode(code);
  check("register: correct code signs the new person in", await until(() => $("#nav") && /Good (morning|afternoon|evening)/.test(text()), 6000));
  location.hash = "#/account"; await until(() => $("#pf") && /HR has not placed you|Your place in the organisation/.test(text()));
  check("account: new self-registered user is told HR must place them", /HR has not placed you/.test(text()));
  click("#out"); await until(() => $("#f"));

  // ---- forgot password: email -> code -> new password
  click('[data-go="forgot"]'); await until(() => /Reset your password/.test(text()));
  const t1 = Date.now() - 500;
  set("#em", email); submit("#f");
  check("forgot: moves to the code screen", await until(() => /Enter your code/.test(text()) && $("#code"), 5000));
  const rc = await mailCode(email, t1);
  check("forgot: reset code arrived", !!rc);
  typeCode(rc);
  check("forgot: correct code opens the new-password step", await until(() => /Choose a new password/.test(text()), 5000));
  set("#pw", pw2); set("#pw2", "different"); submit("#f");
  check("forgot: mismatched confirmation is caught", await until(() => /do not match/.test(text()), 3000));
  set("#pw2", pw2); submit("#f");
  check("forgot: success returns to sign-in with a notice", await until(() => /Password updated/.test(text()) && $("#id"), 5000));
  set("#id", email); set("#pw", pw1); submit("#f");
  check("forgot: the OLD password no longer works", await until(() => /Incorrect email\/username or password/.test(text()), 4000));
  set("#pw", pw2); submit("#f");
  check("forgot: the NEW password signs in", await until(() => $("#nav") && /Good (morning|afternoon|evening)/.test(text()), 6000));
}
