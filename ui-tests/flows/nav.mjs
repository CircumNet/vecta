import { $, text, click, ev, sleep, check, until } from "./lib.mjs";
export default async function () {
  const sb = () => $("#sidebar"), open = () => sb().classList.contains("open") && document.body.classList.contains("nav-open");
  const closed = () => !sb().classList.contains("open") && !document.body.classList.contains("nav-open");
  check("nav: starts closed", closed() && $("#menu").getAttribute("aria-expanded") === "false");
  click("#menu"); check("nav: hamburger opens the drawer and a backdrop", open() && $("#menu").getAttribute("aria-expanded") === "true");
  click("#menu"); check("nav: hamburger toggles it closed again", closed());
  click("#menu"); click("#scrim"); check("nav: tapping outside (the backdrop) closes it", closed());
  click("#menu"); click("#side-close"); check("nav: the X button closes it", closed());
  click("#menu"); document.dispatchEvent(new (globalThis.__h.w.KeyboardEvent)("keydown", { key: "Escape", bubbles: true }));
  check("nav: Escape closes it", closed());
  location.hash = "#/dashboard"; await sleep(500);
  click("#menu"); click('#nav a[href="#/dashboard"]');
  check("nav: tapping the link for the CURRENT page still closes it", closed());
  click("#menu"); click('#nav a[href="#/leave"]');
  check("nav: tapping another link closes it and navigates", await until(() => closed() && /My leave/.test(document.getElementById("title").textContent), 4000));
  click("#menu"); globalThis.__h.w.innerWidth = 1280; globalThis.__h.w.dispatchEvent(new (globalThis.__h.w.Event)("resize"));
  check("nav: growing the window to desktop width closes the drawer", closed());
  const open2 = () => { globalThis.__h.w.innerWidth = 600; };
  open2(); click("#menu"); click("#menu"); check("nav: no stuck state after repeated toggles", closed());
}
