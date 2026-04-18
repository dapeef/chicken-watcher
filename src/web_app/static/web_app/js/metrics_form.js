// ============================================================================
// Metrics page — form helpers.
//
// Small imperative helpers invoked from the metrics-page sidebar's
// onclick / onchange handlers. Previously defined inline at the top of
// metrics.html's <script> block.
//
// These functions are intentionally exposed on ``window`` (no module
// system) because they're called from HTML attributes.
// ============================================================================

(function () {
  "use strict";

  /** Submit the metrics form, preserving the current scroll position and
   * pushing the serialised params onto the history so the back button /
   * bookmarks work. */
  function submitForm() {
    const form = document.getElementById("metrics-form");
    const params = new URLSearchParams(new FormData(form));
    history.pushState(null, "", "?" + params.toString());
    form.submit();
  }

  function selectAll() {
    document
      .querySelectorAll(".chicken-cb")
      .forEach((cb) => (cb.checked = true));
    submitForm();
  }

  function selectNone() {
    document
      .querySelectorAll(".chicken-cb")
      .forEach((cb) => (cb.checked = false));
    submitForm();
  }

  function selectAlive() {
    document.querySelectorAll(".chicken-cb").forEach((cb) => {
      cb.checked = cb.dataset.alive === "1";
    });
    submitForm();
  }

  function setStart(y, m, d, offsetDays) {
    const dt = new Date(y, m - 1, d);
    dt.setDate(dt.getDate() + offsetDays);
    document.getElementById("id_start").value = dt.toISOString().slice(0, 10);
    submitForm();
  }

  function setStartAbsolute(isoDate) {
    document.getElementById("id_start").value = isoDate;
    submitForm();
  }

  function setEndToday(isoDate) {
    document.getElementById("id_end").value = isoDate;
    submitForm();
  }

  // Expose to inline onclick / onchange attributes.
  window.submitForm = submitForm;
  window.selectAll = selectAll;
  window.selectNone = selectNone;
  window.selectAlive = selectAlive;
  window.setStart = setStart;
  window.setStartAbsolute = setStartAbsolute;
  window.setEndToday = setEndToday;
})();
