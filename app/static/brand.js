"use strict";
/* The product name lives here and only here. Rename = change this one line. */
window.APP_NAME = "Recount";

document.title = window.APP_NAME;
document.querySelectorAll("[data-app-name]").forEach((el) => { el.textContent = window.APP_NAME; });
document.querySelectorAll("[data-app-label]").forEach((el) => {
  el.setAttribute("aria-label", el.dataset.appLabel.replace("{name}", window.APP_NAME));
});
