import { $, text, set, click, check, until } from "./lib.mjs";
export default async function () {
  const sub0 = (sel) => $(sel).dispatchEvent(new (globalThis.__h.w.Event)("submit", { bubbles: true, cancelable: true }));
  set("#id", "t.force"); set("#pw", process.env.TMP_PW); sub0("#f");
  check("first login: forced password change screen", await until(() => /Set your own password/.test(text()), 4000));
  const sub = () => $("#cf").dispatchEvent(new (globalThis.__h.w.Event)("submit", { bubbles: true, cancelable: true }));
  set("#o", process.env.TMP_PW); set("#n", "Brand-New-Pass-4821"); set("#c", "different"); sub();
  check("force change: mismatched confirmation is caught", await until(() => /do not match/.test(text()), 3000));
  set("#c", "Brand-New-Pass-4821"); sub();
  check("force change: success drops into the app", await until(() => $("#nav") && /Good (morning|afternoon|evening)/.test(text()), 6000));
}
