// ============================================================================
// Chicken detail page — mini nesting-behaviour timeline.
//
// Data injected from Django via <script id="chicken-detail-config"
// type="application/json">:
//   { "timeline_url": <string> }
// ============================================================================

(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", () => {
    const configEl = document.getElementById("chicken-detail-config");
    if (!configEl) return;
    const config = JSON.parse(configEl.textContent);
    const { timeline_url } = config;

    const nestContainer = document.getElementById("nest-visualization");
    if (!nestContainer) return;
    const nestItems = new vis.DataSet([]);
    const { startOfDay, endOfDay } = window.todayWindow();

    const nestTimeline = new vis.Timeline(nestContainer, nestItems, {
      height: "240px",
      stack: true,
      showCurrentTime: true,
      zoomMin: 1000 * 60, // 1 minute
      start: startOfDay,
      end: endOfDay,
    });

    function loadNestData(properties) {
      const start = properties.start.toISOString();
      const end = properties.end.toISOString();
      const url =
        timeline_url +
        "?start=" +
        encodeURIComponent(start) +
        "&end=" +
        encodeURIComponent(end);
      fetch(url)
        .then((r) => r.json())
        .then((data) => nestItems.update(data))
        .catch((err) =>
          console.error("Error loading nest timeline data:", err),
        );
    }

    nestTimeline.on("rangechanged", loadNestData);
    loadNestData({ start: startOfDay, end: endOfDay });

    // Refresh once every 10s while the current time is in view.
    setInterval(() => {
      const w = nestTimeline.getWindow();
      const now = new Date();
      if (now >= w.start && now <= w.end) loadNestData(w);
    }, 10000);
  });
})();
