# Vendored third-party assets

These libraries are checked in, pinned to exact versions, and served
directly by Django's staticfiles rather than fetched from a CDN at
request time. Rationale:

* The app is intentionally LAN-only and often accessed from a Pi with
  flaky / no internet. CDN-loaded assets are a single-point-of-failure
  that would make the UI stall or break.
* The original `_timeline_assets.html` pulled `vis-timeline@latest`,
  which would silently pick up breaking changes whenever upstream
  released a major version.

## Versions

| Library        | Version  | Files                                                       |
|----------------|----------|-------------------------------------------------------------|
| Bootstrap      | 5.3.2    | `bootstrap-5.3.2/css/bootstrap.min.css`                     |
|                |          | `bootstrap-5.3.2/js/bootstrap.bundle.min.js`                |
| HTMX           | 1.9.10   | `htmx-1.9.10/htmx.min.js`                                   |
| Chart.js       | 4.4.0    | `chartjs-4.4.0/chart.umd.min.js`                            |
| vis-timeline   | 7.7.3    | `vis-timeline-7.7.3/standalone/umd/vis-timeline-graph2d.min.js` |
|                |          | `vis-timeline-7.7.3/styles/vis-timeline-graph2d.min.css`    |

## Upgrade procedure

1. Download the new version from its upstream CDN URL (see the original
   template refs in git history if you need them).
2. Place under `vendor/<libname>-<version>/…` (note the version pinning
   in the directory name — it's deliberate, to force callsites to be
   updated when they upgrade).
3. Update every `{% static '…' %}` reference in templates.
4. Smoke-test the dashboard, timeline, and metrics pages.

## Licences

Each library retains its own licence; see the first lines of each file
(they're minified but include the `/*! licence */` banner at the top).
Bootstrap and HTMX are MIT, Chart.js is MIT, vis-timeline is dual
Apache-2.0 / MIT.
