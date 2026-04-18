// ============================================================================
// Timeline page — full-screen vis-timeline showing eggs, presence
// periods, and camera frames. Also drives the camera preview under the
// timeline as the user hovers / scrubs.
//
// Data injected from Django via <script id="timeline-config" type="application/json">:
//   {
//     "chickens": [{"id": <int>, "name": <string>}, ...],
//     "timeline_data_url": <string>,
//     "timeline_images_url": <string>
//   }
//
// Using json_script rather than string-interpolating the chicken names
// into the inline JS (a) correctly escapes names containing quotes or
// </script>, and (b) means this file doesn't need Django template
// rendering.
// ============================================================================

(function () {
  "use strict";

  const config = JSON.parse(document.getElementById("timeline-config").textContent);
  const { chickens, timeline_data_url, timeline_images_url } = config;

  const container = document.getElementById("visualization");
  const items = new vis.DataSet([]);
  const groups = new vis.DataSet([
    ...chickens.map((c) => ({
      id: "chicken_" + c.id,
      content: c.name,
      stack: false,
    })),
    { id: "unknown", content: "Unknown", stack: true },
  ]);

  const { startOfDay, endOfDay } = window.todayWindow();

  const options = {
    height: Math.round(window.innerHeight * 0.75) + "px",
    stack: true,
    showCurrentTime: true,
    zoomMin: 1000 * 60, // 1 minute
    start: startOfDay,
    end: endOfDay,
  };

  const timeline = new vis.Timeline(container, items, groups, options);

  // ──────────────────────────────────────────────────────────────────────
  // Camera preview state
  // ──────────────────────────────────────────────────────────────────────

  let cachedImages = [];
  let objectUrls = [];
  let currentAbortController = null;
  let lastMouseTime = null;
  let previewLineAdded = false;

  function loadImages(properties, signal) {
    const start = properties.start.toISOString();
    const end = properties.end.toISOString();
    const url =
      timeline_images_url +
      "?start=" +
      encodeURIComponent(start) +
      "&end=" +
      encodeURIComponent(end) +
      "&n=100";

    fetch(url, { signal })
      .then((response) => response.json())
      .then((data) => {
        if (signal.aborted) return;

        // Revoke any prior blob URLs that aren't currently displayed
        const imgElement = document.getElementById("dashboard-image");
        const currentSrc = imgElement ? imgElement.src : "";
        objectUrls.forEach((u) => {
          if (u !== currentSrc) URL.revokeObjectURL(u);
        });
        objectUrls = objectUrls.filter((u) => u === currentSrc);

        cachedImages = data.map((img) => ({
          timestamp: new Date(img.timestamp).getTime(),
          url: img.url,
          iso: img.timestamp,
          blobUrl: null,
        }));

        // Refresh preview if mouse is already over the timeline
        if (lastMouseTime) updatePreview(lastMouseTime);

        // Prioritise loading images closest to the mouse (or view centre)
        const startMs = properties.start.getTime();
        const endMs = properties.end.getTime();
        const centerMs = (startMs + endMs) / 2;
        const referenceTime = lastMouseTime
          ? lastMouseTime.getTime()
          : centerMs;

        const sortedForLoading = [...cachedImages].sort(
          (a, b) =>
            Math.abs(a.timestamp - referenceTime) -
            Math.abs(b.timestamp - referenceTime),
        );

        // Preload images as blobs so scrubbing doesn't trigger new network
        // requests between frames.
        sortedForLoading.forEach((img) => {
          fetch(img.url, { signal })
            .then((res) => res.blob())
            .then((blob) => {
              if (signal.aborted) return;
              const bUrl = URL.createObjectURL(blob);
              img.blobUrl = bUrl;
              objectUrls.push(bUrl);
              if (lastMouseTime) updatePreview(lastMouseTime);
            })
            .catch((err) => {
              if (err.name === "AbortError") return;
              console.error("Error preloading blob:", err);
            });
        });
      })
      .catch((err) => {
        if (err.name === "AbortError") return;
        console.error("Error loading image metadata:", err);
      });
  }

  const loadData = window.debounce(function (properties) {
    if (currentAbortController) currentAbortController.abort();
    currentAbortController = new AbortController();
    const signal = currentAbortController.signal;

    const start = properties.start.toISOString();
    const end = properties.end.toISOString();

    // Drop per-sensor "dot" items when zoomed out beyond 3 minutes —
    // they become visual noise.
    const durationMs = properties.end.getTime() - properties.start.getTime();
    const threeMinsMs = 3 * 60 * 1000;
    if (durationMs > threeMinsMs) {
      const dots = items.get({
        filter: (item) =>
          item.className && item.className.includes("timeline-presence-dot"),
      });
      if (dots.length > 0) items.remove(dots);
    }

    const url =
      timeline_data_url +
      "?start=" +
      encodeURIComponent(start) +
      "&end=" +
      encodeURIComponent(end);

    fetch(url, { signal })
      .then((response) => response.json())
      .then((data) => {
        if (signal.aborted) return;
        items.update(data);
      })
      .catch((err) => {
        if (err.name === "AbortError") return;
        console.error("Error loading timeline data:", err);
      });

    loadImages(properties, signal);
  }, 300);

  timeline.on("rangechanged", loadData);

  // Initial load
  loadData({ start: startOfDay, end: endOfDay });

  function updatePreview(time) {
    if (!cachedImages.length) return;

    const targetTime = time.getTime();
    let closest = null;
    let minDiff = Infinity;

    // 1. Prefer the closest LOADED image (no network)
    for (const img of cachedImages) {
      if (img.blobUrl) {
        const diff = Math.abs(targetTime - img.timestamp);
        if (diff < minDiff) {
          minDiff = diff;
          closest = img;
        }
      }
    }

    // 2. Fall back to the closest image regardless of load state
    if (!closest) {
      closest = cachedImages[0];
      minDiff = Math.abs(targetTime - closest.timestamp);
      for (let i = 1; i < cachedImages.length; i++) {
        const diff = Math.abs(targetTime - cachedImages[i].timestamp);
        if (diff < minDiff) {
          minDiff = diff;
          closest = cachedImages[i];
        }
      }
    }

    const imgElement = document.getElementById("dashboard-image");
    const timestampElement = document.getElementById("image-timestamp");

    if (imgElement && closest) {
      const displayUrl = closest.blobUrl || closest.url;
      if (
        imgElement.src !== displayUrl &&
        !imgElement.src.endsWith(displayUrl)
      ) {
        imgElement.src = displayUrl;
        imgElement.classList.remove("d-none");
      }
      if (timestampElement) {
        const date = new Date(closest.iso);
        timestampElement.innerText = "Photo from " + date.toLocaleString();
      }

      // Move the preview line to the exact timestamp of the shown image
      const imageDate = new Date(closest.timestamp);
      if (!previewLineAdded) {
        timeline.addCustomTime(imageDate, "preview-line");
        previewLineAdded = true;
      } else {
        timeline.setCustomTime(imageDate, "preview-line");
      }
    }
  }

  timeline.on("mouseMove", function (props) {
    if (props.time) {
      lastMouseTime = props.time;
      updatePreview(props.time);
    }
  });

  // If "now" is within the current viewport, refresh data once per second
  // so the live edge of the timeline keeps moving.
  setInterval(() => {
    const viewportWindow = timeline.getWindow();
    const now = new Date();
    if (now >= viewportWindow.start && now <= viewportWindow.end) {
      loadData(viewportWindow);
    }
  }, 1000);
})();
