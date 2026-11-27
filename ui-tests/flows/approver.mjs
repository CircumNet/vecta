import { $, text, set, click, sleep, check, until, askOk } from "./lib.mjs";
export default async function () {
  location.hash = "#/approvals"; await until(() => document.querySelector("[data-card]"));
  const cards = () => document.querySelectorAll("[data-card]").length;
  const n0 = cards();
  check("approvals: queue lists pending requests", n0 >= 2, "cards=" + n0);
  check("approvals: shows team-clash warning", /also away/.test(text()));
  const first = document.querySelector('[data-act="approve"]');
  click(first); await askOk("Enjoy");
  check("approvals: approve removes the card", await until(() => cards() === n0 - 1, 5000), `${n0} -> ${cards()}`);
  const rid = document.querySelector("[data-card]").dataset.card;
  location.hash = "#/leave/" + rid; await until(() => /Your decision/.test(text()), 5000);
  check("detail: approver sees decision panel and team clashes", /Your decision/.test(text()) && /(Team clashes|No department clashes)/.test(text()));
  click('[data-act="reject"]'); await until(() => $(".modal [data-ok]")); click(".modal [data-ok]");
  check("reject: reason is required", await until(() => /This field is required/.test(text()), 2000));
  await askOk("Project deadline");
  check("reject: succeeds with a reason", await until(() => /Rejected/.test(text()) && /Project deadline/.test(text()), 5000));
  location.hash = "#/approvals"; await until(() => $('[data-tab="decided"]')); click('[data-tab="decided"]');
  check("approvals: decided tab lists my decisions", await until(() => /Approved/.test(text()) && /Rejected/.test(text()), 4000));
  location.hash = "#/delegation"; await until(() => $("#add")); click("#add"); await until(() => $(".modal select"));
  const sel = $(".modal select[name=delegate]"); set(".modal select[name=delegate]", sel.options[1].value);
  click(".modal [data-submit]");
  check("delegation: creating a delegation works", await until(() => /Active now/.test(text()), 5000));
  click("[data-revoke]"); await askOk();
  check("delegation: revoke works", await until(() => /not delegated/.test(text()), 5000));
}
