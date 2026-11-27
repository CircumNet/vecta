import { $, text, set, click, sleep, check, until, submit, mailCode, typeCode, askOk } from "./lib.mjs";
export default async function () {
  const stamp = Date.now(), newEmail = `staff2.${stamp}@example.com`;
  location.hash = "#/account"; await until(() => $("#pf"));
  check("account: profile tab shows name, email and verified badge", /Zainab Musa/.test(text()) && /zmusa|staff2@example.com/.test(text()) && /Verified/.test(text()));
  check("account: organisation details are read-only and explained", /Engineering/.test(text()) && /managed by HR/.test(text()));
  set("#ph", "0803 111 2222"); submit("#pf");
  check("account: saving the profile works", await until(() => /Profile saved/.test(text()), 4000));
  // email change with a code sent to the new address
  click('[data-act="email"]'); await until(() => $(".modal form"));
  set('.modal [name="new_email"]', newEmail); set('.modal [name="password"]', "Passw0rd!123");
  const t0 = Date.now() - 500; click(".modal [data-submit]");
  check("email change: asks for the code sent to the NEW address", await until(() => /Confirm your new email/.test(text()) && $(".modal #code"), 5000));
  const code = await mailCode(newEmail, t0);
  check("email change: code email arrived at the new address", !!code);
  typeCode(code);
  check("email change: confirming updates the address", await until(() => text().includes(newEmail) && /Email address updated/.test(text()), 6000));
  // security
  click('[data-tab="security"]'); await until(() => $("#pw"));
  check("security: change-password form, sign-in methods and sessions are shown", /Change password/.test(text()) && /Sign-in methods/.test(text()) && /Sign out other devices/.test(text()));
  check("security: explains when no external provider is configured", /have not been set up/.test(text()));
  set("#o", "Passw0rd!123"); set("#n", "short"); set("#c", "short"); submit("#pw");
  check("security: weak new password is refused by the server", await until(() => /(too short|too common)/i.test(text()), 4000));
  set("#n", "Willow-Creek-5530"); set("#c", "Willow-Creek-5530"); submit("#pw");
  check("security: valid change succeeds and keeps me signed in", await until(() => /Password updated/.test(text()), 5000));
  click('[data-act="revoke"]'); await askOk();
  check("security: sign out other devices keeps this session alive", await until(() => /Other devices signed out/.test(text()), 5000));
  // preferences
  click('[data-tab="preferences"]'); await until(() => $("#en"));
  $("#en").checked = false; $("#en").dispatchEvent(new (globalThis.__h.w.Event)("change", { bubbles: true }));
  check("preferences: email notifications can be switched off", await until(() => /Email notifications off/.test(text()), 4000));
  location.hash = "#/dashboard"; check("session still valid after all that", await until(() => /Good (morning|afternoon|evening)/.test(text()), 5000));
}
