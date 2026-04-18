// ============================================================================
// Timeline utilities — shared between the full timeline page and the per-
// chicken timeline on the chicken detail page.
//
// Previously lived inline at the bottom of _timeline_assets.html.
// ============================================================================

/** Returns { startOfDay, endOfDay } for today's 00:00 → tomorrow 00:00. */
function todayWindow() {
  const startOfDay = new Date();
  startOfDay.setHours(0, 0, 0, 0);
  const endOfDay = new Date(startOfDay);
  endOfDay.setDate(endOfDay.getDate() + 1);
  return { startOfDay, endOfDay };
}

/** Standard debounce — invokes ``func`` once ``wait`` ms have elapsed
 * since the last call. */
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// Make the functions explicitly global (no module system here).
window.todayWindow = todayWindow;
window.debounce = debounce;
