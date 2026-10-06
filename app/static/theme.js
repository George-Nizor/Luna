// Applies the saved theme before first paint. "system" (the default) leaves data-theme unset, so the
// page follows prefers-color-scheme; "light" and "dark" pin it. app.js owns the toggle.
(function applySavedTheme() {
  let choice = "system";
  try { choice = localStorage.getItem("luna.theme") || "system"; } catch (_) { /* storage unavailable */ }
  if (choice === "light" || choice === "dark") document.documentElement.dataset.theme = choice;
}());
