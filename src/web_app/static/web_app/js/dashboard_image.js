// ============================================================================
// Dashboard — latest-image auto-refresher.
//
// The other dashboard panels auto-refresh via htmx hx-trigger="every 5s",
// but the latest-image panel needs special handling: we want to swap in
// the new image without a visible flash, so we preload it first and
// only update the <img src> once it's loaded.
//
// Data injected via <script id="dashboard-config" type="application/json">:
//   { "latest_image_url": <string> }
// ============================================================================

(function () {
  "use strict";

  const configEl = document.getElementById("dashboard-config");
  if (!configEl) return;
  const config = JSON.parse(configEl.textContent);
  const { latest_image_url } = config;

  function updateDashboardImage() {
    fetch(latest_image_url)
      .then((response) => response.text())
      .then((html) => {
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, "text/html");
        const newImg = doc.querySelector("#dashboard-image");
        const newTs = doc.querySelector("#image-timestamp");

        const currentImg = document.querySelector("#dashboard-image");
        const currentTs = document.querySelector("#image-timestamp");

        if (newImg && currentImg) {
          if (currentImg.src !== newImg.src) {
            // Preload the new image before swapping src so the user
            // doesn't see the image disappear-then-reappear.
            const tempImg = new Image();
            tempImg.onload = () => {
              currentImg.src = newImg.src;
              if (newTs && currentTs) {
                currentTs.innerText = newTs.innerText;
              }
            };
            tempImg.src = newImg.src;
          } else if (newTs && currentTs) {
            // Same image — just refresh the timestamp text.
            currentTs.innerText = newTs.innerText;
          }
        } else if (!currentImg && newImg) {
          // Image was previously absent but has just appeared —
          // swap the whole container in one go.
          document.querySelector("#image-container").innerHTML = html;
        }
      })
      .catch((err) => console.error("Error updating image:", err));
  }

  // 1-second polling for the image feels responsive without hammering.
  setInterval(updateDashboardImage, 1000);
})();
