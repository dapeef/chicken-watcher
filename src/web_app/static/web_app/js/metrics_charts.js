// ============================================================================
// Metrics page — Chart.js initialisation.
//
// All the chart data (labels, datasets, pie data) is injected via a single
// <script id="metrics-chart-data" type="application/json">…</script> blob
// emitted by ``{{ metrics_chart_data|json_script:"metrics-chart-data" }}``
// in metrics.html. Using json_script keeps this JS file Django-free so
// a) it's cacheable by the browser, b) it's easily testable, c) chicken
// names never get interpolated directly into JS source.
//
// Expected shape of the JSON blob:
//   {
//     "show_mean": bool,
//     "egg_prod_labels": [str, …],
//     "egg_prod_datasets": [Chart.js dataset, …],
//     "saleable_prod_datasets": [...],
//     "edible_prod_datasets": [...],
//     "messy_prod_datasets": [...],
//     "flock_count_dataset": Chart.js dataset,
//     "tod_labels": [...],
//     "tod_egg_datasets": [...],
//     "tod_nest_datasets": [...],
//     "nesting_box_time": { labels, datasets },
//     "nesting_box_visits": { labels, datasets },
//     "nesting_box_eggs": { labels, datasets },
//     "age_prod_labels": [...],
//     "age_prod_datasets": [...],
//   }
// ============================================================================

(function () {
  "use strict";

  const dataEl = document.getElementById("metrics-chart-data");
  if (!dataEl) return; // Page doesn't contain the metrics config (e.g. partial)
  const data = JSON.parse(dataEl.textContent);

  const SHOW_MEAN = Boolean(data.show_mean);

  // -- Colour helpers --------------------------------------------------

  /** Convert a #rrggbb hex colour to rgba(r,g,b,alpha). */
  function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }

  /** When mean is active, fade individual chicken lines so the mean
   * stands out. "Sum" and "Mean" datasets are left untouched. */
  function applyMeanFade(datasets) {
    if (!SHOW_MEAN) return datasets;
    return datasets.map((ds) => {
      if (ds.label === "Sum" || ds.label === "Mean") return ds;
      const faded = hexToRgba(ds.borderColor, 0.25);
      return { ...ds, borderColor: faded };
    });
  }

  /** Initialise a chart the first time its Bootstrap collapse panel is
   * fully open.
   *
   * We listen for ``shown.bs.collapse`` (past tense, fires after the CSS
   * transition completes) rather than ``show.bs.collapse`` (present tense,
   * fires at the start of the transition). At the start of the transition
   * the panel is still ``display: none`` or mid-animation, so Chart.js
   * measures a zero clientWidth and produces a zero-height canvas — most
   * visible on mobile where the viewport is narrow. After the transition the
   * canvas has its full dimensions and Chart.js renders correctly.
   */
  function lazyChart(collapseId, factory) {
    const el = document.getElementById(collapseId);
    if (!el) return;
    let initialised = false;
    el.addEventListener("shown.bs.collapse", () => {
      if (!initialised) {
        initialised = true;
        factory();
      }
    });
  }

  /** Format a duration in seconds as "Xh Ym" (or "Ym" if <1h). */
  function fmtSeconds(s) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
  }

  // -- Chart setup -----------------------------------------------------

  document.addEventListener("DOMContentLoaded", () => {
    const noAnimation = { animation: false };
    const todAxisTitle = {
      display: true,
      text: "Time of day (UTC \u2014 not adjusted for BST)",
    };
    const todXScale = {
      ticks: { maxTicksLimit: 12 },
      title: todAxisTitle,
    };

    // Egg production
    new Chart(document.getElementById("eggProdChart"), {
      type: "line",
      data: {
        labels: data.egg_prod_labels,
        datasets: applyMeanFade(data.egg_prod_datasets),
      },
      options: {
        ...noAnimation,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            title: { display: true, text: "eggs / day" },
          },
          x: { ticks: { maxTicksLimit: 15 } },
        },
        plugins: {
          legend: { position: "bottom" },
          tooltip: { intersect: false, mode: "index" },
        },
      },
    });

    // Egg quality breakdown — all three share one collapsible panel
    const qualityChartDefs = [
      {
        canvasId: "saleableProdChart",
        datasets: data.saleable_prod_datasets,
        yLabel: "saleable / day",
      },
      {
        canvasId: "edibleProdChart",
        datasets: data.edible_prod_datasets,
        yLabel: "edible / day",
      },
      {
        canvasId: "messyProdChart",
        datasets: data.messy_prod_datasets,
        yLabel: "messy / day",
      },
    ];
    lazyChart("qualityProdCollapse", () => {
      qualityChartDefs.forEach(({ canvasId, datasets, yLabel }) => {
        new Chart(document.getElementById(canvasId), {
          type: "line",
          data: {
            labels: data.egg_prod_labels,
            datasets: applyMeanFade(datasets),
          },
          options: {
            ...noAnimation,
            maintainAspectRatio: false,
            scales: {
              y: {
                beginAtZero: true,
                title: { display: true, text: yLabel },
              },
              x: { ticks: { maxTicksLimit: 15 } },
            },
            plugins: {
              legend: { position: "bottom" },
              tooltip: { intersect: false, mode: "index" },
            },
          },
        });
      });
    });

    // Flock count — collapsed by default, lazy
    lazyChart("flockSizeCollapse", () => {
      new Chart(document.getElementById("flockCountChart"), {
        type: "line",
        data: {
          labels: data.egg_prod_labels,
          datasets: [data.flock_count_dataset],
        },
        options: {
          ...noAnimation,
          maintainAspectRatio: false,
          scales: {
            y: {
              beginAtZero: true,
              precision: 0,
              title: { display: true, text: "chickens alive" },
            },
            x: { ticks: { maxTicksLimit: 15 } },
          },
          plugins: {
            legend: { display: false },
            tooltip: { intersect: false, mode: "index" },
          },
        },
      });
    });

    // Egg time-of-day KDE
    new Chart(document.getElementById("todEggChart"), {
      type: "line",
      data: {
        labels: data.tod_labels,
        datasets: applyMeanFade(data.tod_egg_datasets),
      },
      options: {
        ...noAnimation,
        maintainAspectRatio: false,
        scales: {
          x: todXScale,
          y: { beginAtZero: true, ticks: { display: false } },
        },
        plugins: {
          legend: { position: "bottom" },
          tooltip: { intersect: false, mode: "index" },
        },
      },
    });

    // Nesting time-of-day
    new Chart(document.getElementById("todNestChart"), {
      type: "line",
      data: {
        labels: data.tod_labels,
        datasets: applyMeanFade(data.tod_nest_datasets),
      },
      options: {
        ...noAnimation,
        maintainAspectRatio: false,
        scales: {
          x: todXScale,
          y: {
            beginAtZero: true,
            precision: 0,
            title: { display: true, text: "days present" },
          },
        },
        plugins: {
          legend: { position: "bottom" },
          tooltip: { intersect: false, mode: "index" },
        },
      },
    });

    // -- Pie options factory ------------------------------------------
    const pieOptions = (labelFn) => ({
      ...noAnimation,
      maintainAspectRatio: false,
      rotation: 180,
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const label = ctx.label || "";
              const value = labelFn(ctx.parsed);
              const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
              const pct =
                total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : "0.0";
              return `${label}: ${value} (${pct}%)`;
            },
          },
        },
      },
    });

    // Nesting box preference — by time spent
    new Chart(document.getElementById("nestBoxTimeChart"), {
      type: "pie",
      data: data.nesting_box_time,
      options: pieOptions(fmtSeconds),
    });

    // Nesting box preference — by visits
    new Chart(document.getElementById("nestBoxVisitsChart"), {
      type: "pie",
      data: data.nesting_box_visits,
      options: pieOptions((v) => `${v} visit${v !== 1 ? "s" : ""}`),
    });

    // Nesting box preference — by eggs
    new Chart(document.getElementById("nestBoxEggsChart"), {
      type: "pie",
      data: data.nesting_box_eggs,
      options: pieOptions((v) => `${v} egg${v !== 1 ? "s" : ""}`),
    });

    // Egg production vs age — collapsed by default, lazy
    lazyChart("ageProdCollapse", () => {
      new Chart(document.getElementById("ageProdChart"), {
        type: "line",
        data: {
          labels: data.age_prod_labels,
          datasets: applyMeanFade(data.age_prod_datasets),
        },
        options: {
          ...noAnimation,
          maintainAspectRatio: false,
          scales: {
            y: {
              beginAtZero: true,
              title: { display: true, text: "eggs / day" },
            },
            x: {
              ticks: { maxTicksLimit: 15 },
              title: { display: true, text: "age (days)" },
            },
          },
          plugins: {
            legend: { position: "bottom" },
            tooltip: { intersect: false, mode: "index" },
          },
        },
      });
    });
  });
})();
