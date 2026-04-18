# Chicken Watcher — Tech Debt Review

This document captures findings from a comprehensive code review performed across the entire codebase. The review was conducted by five specialized agents working in parallel, covering:

1. `hardware_agent/` and its tests
2. `web_app/` views, URLs, forms
3. Models, admin, utils, template tags, factories, migrations
4. Management commands, settings, `pyproject.toml`, Dockerfile
5. Templates and frontend

Findings are organized by severity. Each item includes `file:line` references where applicable and concrete refactoring suggestions.

## Deployment model

**This app is intentionally LAN-only, accessed directly over HTTP from trusted devices on the home network (with external access via VPN into that LAN).** The LAN + VPN boundary serves as the authentication and transport-security boundary.

Consequently, a number of items that would normally be "Tier 1 security" concerns — authentication, HTTPS, HSTS, secure cookies, CSRF trusted origins, rate-limiting, `ALLOWED_HOSTS` hardening — are **intentionally out of scope**. These are captured separately at the end of this document under **"Outside-of-LAN security changes"** so they can be picked up quickly if the deployment model ever changes.

The remaining Tier 1 items below are correctness / data-loss / ops concerns that matter regardless of the network threat model.

---

## Tier 1 — Correctness / Data-loss / Ops Risks

These can cause real damage and should be addressed first. None of them are about protecting the app from external attackers — they are about protecting *you* (and your data) from typos, crashes, race conditions, and silent misconfiguration.

### 1. `Egg.chicken` / `Egg.nesting_box` use `on_delete=CASCADE` ✅ (done in Wave 1)
~~`models.py:50-53`. Deleting a chicken obliterates all its eggs. Every field is already `null=True, blank=True`. Use `SET_NULL`.~~

Fixed in migration `0021_egg_fk_set_null.py`: both FKs now use `on_delete=SET_NULL`. Historical eggs are preserved when a chicken or nesting box is removed. Covered by `test_models.py::TestEggModel::test_deleting_chicken_preserves_eggs_with_null_chicken` and `…_nesting_box_…`.

### 2. `DEBUG` is not explicitly set in `prod.py` ✅ (done in Wave 1)
~~`DEBUG = True` in production isn't a *security* issue on a LAN, but it:~~
~~- Leaks stack traces with env-var values and DB settings on error pages (visible to anyone with VPN access, including future-you debugging over a flaky connection).~~
~~- Disables template caching and runs less-optimised code paths — measurable on a Pi.~~
~~- Changes middleware behaviour in ways that can mask bugs you'd only see in real deployment.~~

~~Set `DEBUG = False` explicitly in `prod.py` and make `dev.py` opt-in.~~

`prod.py` now sets `DEBUG = False` explicitly. Covered by `test/test_settings.py::TestProdSecretKeyFailFast::test_prod_has_debug_false`.

### 3. `SECRET_KEY` silently becomes `None` if env var missing ✅ (done in Wave 1)
~~`base.py:28` — `SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")`. If the env var is missing, Django boots in a half-broken state where sessions and CSRF are subtly broken until the first op that uses the key. Fail fast at startup: `SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]` in prod, with a dev fallback.~~

`prod.py` now raises `ImproperlyConfigured` at import time if `DJANGO_SECRET_KEY` is missing. `dev.py` provides a permissive, clearly-marked fallback. Covered by `test/test_settings.py::TestProdSecretKeyFailFast` and `TestDevFallback`.

### 4. `DJANGO_ENV` defaults to `"dev"` in `settings/__init__.py` ✅ (done in Wave 1)
~~Forgetting to set `DJANGO_ENV=prod` in Docker silently runs the prod container with **SQLite instead of Postgres**. You could run for hours without noticing, then lose data on container restart. Default to `"prod"` (fail-safe), or raise if unset.~~

`settings/__init__.py` now defaults to `"prod"` and raises `RuntimeError` on any other value except `"dev"`. Covered by `test/test_settings.py::TestSettingsDispatch::test_unset_env_defaults_to_prod` and `test_invalid_env_raises_runtime_error`.

### 5. `seed --mode=clear` and `seed --mode=spawn_test_data` have no guards ✅ (done in Wave 1)
~~Can wipe data by typo. Gate `spawn_test_data` behind `settings.DEBUG`, and require `--yes` on destructive modes. `delete_nesting_box_images` has the same problem — it wipes every image with no confirmation.~~

Destructive modes on `seed` and `delete_nesting_box_images` now:
1. Refuse to run non-interactively without `--yes`.
2. Prompt for `"yes"` confirmation in an interactive terminal.
3. `seed --mode=spawn_test_data` additionally refuses unless `settings.DEBUG` is `True` (cannot be bypassed with `--yes`).

Covered by `test_seed.py::TestDestructiveModeGuards` (7 tests) and `test_delete_nesting_box_images.py` (4 new tests).

### 6. `date.today()` used where timezone matters ✅ (done in Wave 1)
~~- `Chicken.age` (`models.py:26`) — day-boundary bug during BST.~~
~~- `views/metrics.py` uses `date.today()` 5+ times.~~

~~Replace with `timezone.localdate()` throughout.~~

All 7 `date.today()` calls in `src/` replaced with `timezone.localdate()` (`models.py`, `views/metrics.py` 5×, `management/commands/seed.py`). Covered by `test/web_app/test_timezone.py::TestChickenAgeTimezone` (3 tests including a BST-midnight-boundary scenario).

### 7. Period-grouping race condition ✅ (done in Wave 2)
~~`hardware_agent/handlers.py:87-118`. With 4 RFID readers per box, two simultaneous reads can each "find no recent period" and each create a duplicate period. No `select_for_update()`, no unique constraint. Real production risk.~~

`handle_tag_read` now wraps the period-lookup-or-create logic in a transaction with `Chicken.objects.select_for_update()` on the chicken row. Concurrent reads of the same chicken (typically from multiple RFID readers in the same box) serialise on that lock, so the previous TOCTOU window is closed. SQLite already serialises all writes, so the fix is portable. The period-grouping logic is also extracted into a testable `_find_extensible_period` helper. Covered by `test_handlers.py::TestHandleTagReadRaceCondition` (2 tests).

### 8. `save_frame_to_db` orphans images ⏭️ (dismissed in Wave 2)
~~`hardware_agent/handlers.py:158-179` never links the `NestingBoxImage` to a `nesting_box`. The `cam_name` parameter is silently dropped. The `prune_nesting_box_images` job can't correlate images to boxes.~~

**Reviewer's premise was incorrect for the actual deployment**: the camera is a single overhead unit that covers both nesting boxes (and some of the surrounding area). There is no meaningful per-box association to record. `cam_name` is already preserved in the stored filename (`{cam_name}_{timestamp}.jpg`), so multi-camera setups (if ever deployed) would remain distinguishable without a schema change.

Outcome: `save_frame_to_db` left as-is; no FK added; `NestingBoxImage` schema unchanged. A clarifying comment was added to `NestingBoxImage` explaining the design intent so this finding doesn't resurface.

### 9. `NestingBoxPresencePeriod` lost its `started_at <= ended_at` CheckConstraint ✅ (done in Wave 2)
~~This constraint existed on the old `NestingBoxVisit` model but wasn't carried across in migration `0011`. Regression.~~

Constraint re-added on the model and as migration `0022`. Covered by `test_models.py::TestNestingBoxPresencePeriodConstraints` (4 tests including the boundary case where started == ended).

### 10. `Chicken.tag` silently weakened from `OneToOneField` to `ForeignKey` ✅ (done in Wave 2)
~~Migration `0016` allows two chickens to share one RFID tag, with no detection. Restore uniqueness (either OneToOne or a unique partial constraint).~~

Kept as `ForeignKey` (so tags can be reassigned when a chicken dies) but added a partial `UniqueConstraint` (migration `0023`) that enforces "at most one *live* chicken per tag". Dead chickens keep their historical tag for provenance, freed tags can be reassigned. Covered by `test_models.py::TestChickenTagUniqueness` (5 tests).

### 11. `_reader` thread leak in `USBCamera` ✅ (done in Wave 2)
~~`hardware_agent/camera.py:87`. Each reconnect spawns a new reader thread without ever joining the old one. Over hours the thread count grows.~~

`USBCamera` now tracks the reader-thread handle in `self._reader_thread` and uses a per-connection `_reader_stop` event so `disconnect()` can signal and join the reader before releasing the capture device. The reader snapshot-captures `self.cap` at thread start to avoid racing with `disconnect()` blanking it. Covered by `test_camera.py::test_camera_reconnect_does_not_leak_reader_thread` (drives 5 reconnect cycles and verifies every reader was joined) and `test_disconnect_joins_reader_thread`.

### 12. No graceful shutdown path ✅ (done in Wave 2)
~~`service.py` uses `signal.pause()`; no SIGTERM handler, no `manager.stop_all()`. Sensors' serial/GPIO/camera resources may leak on container stop.~~

`service.run_agent` now installs SIGTERM/SIGINT handlers that set a shutdown event; on shutdown it calls `manager.stop_all()` in a `finally` block so every sensor releases its hardware handle regardless of exception path.

`BaseSensor` was rewritten to use a `threading.Event` (`_stop_event`) instead of a plain bool, replacing the unkillable `time.sleep(5)` backoffs with `event.wait(5)`. `stop()` is now idempotent, and interrupts a pending reconnect backoff within the event's resolution rather than waiting the full 5s. `HardwareManager.stop_all(timeout=…)` iterates every registered sensor, logs per-sensor errors but continues, and returns when all have been asked to stop.

Covered by `test_service.py` (3 tests: SIGTERM handler, SIGINT handler, `stop_all` runs in `finally`), `test_base_sensor.py::test_stop_interrupts_reconnect_backoff_fast` (asserts stop completes in <1s even with a 5s backoff active), `test_stop_is_idempotent`, `test_start_is_idempotent_while_alive`, and 3 new `HardwareManager.stop_all` tests.

### 13. Logging config is too verbose for a Pi running 24/7 ✅ (done in Wave 1)
~~`base.py:89-130` — root logger at DEBUG, third-party libraries included, file handler writes into the repo. On a Pi with an SD card:~~
~~- DEBUG volume is 10–100× INFO.~~
~~- SD cards fail faster under write load.~~
~~- The 10MiB × 5 cap helps but DEBUG defeats it.~~

~~Set root logger to INFO with `DEBUG` as an opt-in env override; move logs outside the repo (`/var/log/chicken-watcher/` or a mounted volume).~~

Logging config rewritten. Defaults:
- Root level: `INFO` (was `DEBUG`).
- `django.db.backends` pinned to INFO regardless of root level (opt in via `DJANGO_DB_LOG_LEVEL=DEBUG` for SQL echo).
- `django.utils.autoreload` pinned to INFO.

New env-var overrides: `LOG_LEVEL`, `LOG_DIR`, `LOG_FILENAME`, `LOG_FILE_BYTES`, `LOG_FILE_BACKUP_COUNT`, `DJANGO_DB_LOG_LEVEL`. When `LOG_DIR` cannot be created or isn't writable (e.g. read-only FS), the file handler is silently dropped and only the console handler remains, so settings import never crashes.

Covered by `test/test_logging.py` (7 tests including the read-only-fallback case).

---

## Tier 2 — Architecture / Design

These are maintainability issues that will compound.

### 14. `hardware_agent/handlers.py` doesn't belong in `hardware_agent`
It contains pure Django ORM code. It should live in `web_app/services/`, with the hardware agent receiving handler callables via DI. Decouples the two packages.

### 15. `MetricsView.get_context_data` is ~550 lines (`views/metrics.py:261-810`)
Mixes query-param parsing, multiple ORM pipelines, KDE smoothing, chart-builder dict construction. Refactor into:
- `MetricsParams` dataclass (parse request → typed config)
- `MetricsQueries` / manager methods on `Egg`/`Chicken`
- Per-chart builders (`build_tod_chart`, etc.)

### 16. `handle_tag_read` (`handlers.py:66-141`) does too much
Tag resolution, period-grouping, presence creation, exception handling. Push period-grouping onto a manager method: `NestingBoxPresencePeriod.objects.extend_or_create(chicken, box, at)`.

### 17. Analytics code lives in `views/`
`nesting_time_of_day`, `egg_time_of_day_kde`, `_gaussian_smooth_circular`, `rolling_average` are pure numerical functions scattered across `views/chickens.py`, `views/metrics.py`, `utils.py`. Move to `web_app/analytics.py`.

### 18. Per-hen N+1 loops in metrics
`views/metrics.py:389-394, 471-477, 661-697` — 25+ queries per metrics page for a 10-hen flock. Collapse to `chicken__in=chosen` + group in Python.

### 19. Dashboard partials fan-out
All 6 HTMX partials call `get_dashboard_context()` every 5s — 42 queries per refresh cycle. Split per-partial context functions.

### 20. `EggListView` N+1
`views/eggs.py:12-18` lacks `select_related("chicken", "nesting_box")`. Also no pagination.

### 21. `seed` command does 4 unrelated things
Destructive test-data generation, full wipe, and CSV upserts all behind one `--mode` flag. Split into focused commands.

### 22. `prune_nesting_box_images` vs `delete_nesting_box_images` duplicate each other
Identical delete bodies; one is safe (time-window), one is nuke-all. Collapse to a single command with `--mode` or at least extract the shared helper.

### 23. Three `add_*` methods in `HardwareManager` are identical patterns
`hardware_agent/manager.py:20-69`. Consolidate into one `add_sensor(type, instance, handler)` or a declarative registry.

### 24. `BaseSensor` abstraction leaks for event-driven devices
`BeamSensor.poll()` is a 10-second liveness check that doesn't poll anything (edge-triggered via gpiozero). `USBCamera` polls a buffer filled by its own reader thread. Consider splitting `BaseSensor` into `PolledSensor` and `EventSensor`.

### 25. Database-vendor dispatch in the dashboard view
`views/dashboard.py:24-49`. This belongs on a queryset manager: `NestingBoxPresencePeriod.objects.latest_per_box_since(dt)`. Currently the Postgres `DISTINCT ON` branch is never tested (tests run on SQLite only).

### 26. Admin has zero customisation
`admin.py:14-21` — every model uses `admin.site.register(Model)` with no `list_display`, `list_select_related`, `search_fields`, or `autocomplete_fields`. The Egg changelist N+1s.

### 27. Missing default orderings / managers
Most models have no `Meta.ordering`, leading to scattered `order_by(...)` calls in views. No custom querysets for common filters (`Egg.objects.saleable()`, `Chicken.objects.alive()`, `Egg.objects.laid_today()`).

### 28. `NestingBoxPresence.sensor_id` is a string sentinel
`models.py:106-108`. Empty-string default, no referential integrity. Should be `ForeignKey(HardwareSensor, null=True, on_delete=SET_NULL)`.

---

## Tier 3 — Frontend / Template Debt

### 29. Three huge inline `<script>` blocks
- `metrics.html:322-612` (290 lines)
- `timeline.html:45-263` (218 lines)
- `chicken_detail.html:101-135` (35 lines, duplicates timeline logic)

No `src/web_app/static/` directory exists. All CSS/JS is inline or CDN-loaded. Move to static files, use `{{ var|json_script }}` for data injection.

### 30. All frontend libs loaded from CDNs, including `vis-timeline@latest`
`_timeline_assets.html:1-2`. `@latest` is a ticking bomb. For a Pi-on-LAN IoT device, all assets should be vendored locally.

### 31. Duplicated patterns that should be partials / tags
- Sortable table header (`chicken_list.html`, `egg_list.html`) — diverging implementations
- Breadcrumbs (2 copies, missing from 1 place)
- Chart card structure (8× in metrics.html)
- HTMX poll panel (5× in dashboard.html)
- Quality / status badge colour logic (belongs on models)
- `dl.row` definition lists
- Timeline-loader JS (2 templates)

### 32. `egg_form.html` hand-renders every field
90 lines of manual `<input>`/`<select>` markup with stringified value-comparison logic. Use `{{ form.as_div }}` or a widget.

### 33. Accessibility gaps
- `<tr onclick>` in chicken list (not keyboard-navigable, breaks open-in-new-tab)
- Missing `<main>` landmark and active-nav state in base.html
- `<th>` without `scope="col"` throughout
- `<div role="button">` instead of real `<button>` in metrics.html
- `<img src="">` (empty string) in `_latest_image.html`
- No `aria-label` on emoji (`🪓` reads as "axe")

### 34. XSS risk in `timeline.html:50`
Chicken names are interpolated into a JS object literal with no escaping. A name containing `'` or `</script>` breaks the page. Use `{{ chickens|json_script:"timeline-groups" }}`.

### 35. No `{% if messages %}` in `base.html`
Django messages silently disappear.

---

## Tier 4 — Testing Quality

### 36. Threading-based hardware tests are flaky by construction
Uses `wait_for` polling up to 10s. Refactor `BaseSensor` to expose `_run_once()` for deterministic single-stepping.

### 37. Log-string assertions are pervasive
`test_handlers.py` asserts `"Unknown sensor"` substrings in log output. Brittle to wording changes. Test on logger name + level, or emit structured events.

### 38. Missing test coverage
- **Postgres `DISTINCT ON` branch** in dashboard — entirely untested (SQLite-only tests).
- **`NestingBoxPresencePeriod.duration`** — untested.
- **Constraint-violation tests** — `Tag.rfid_string` uniqueness, `HardwareSensor.name` uniqueness, etc.
- **Concurrent period-grouping** — the riskiest production scenario has zero coverage.
- **CSV seed error paths** — missing file, malformed row, bad date, duplicate name.
- **Edge cases**: `Chicken.age` day-boundary, empty `data` to `rolling_average`, `window > len(data)`.
- **`run_hardware_agent.py` and `service.py`** — no tests.
- **Template rendering** — `egg_form.html`, metrics sidebar, `_sensors.html`, `_latest_image.html`, sort-header variants.
- **Deletion ordering / crash-safety** in prune commands.

### 39. Brittle test patterns
- `test_templatetags.py:126` — `b"1y" in response.content or b"m" in response.content` (the "or m" makes this trivially pass).
- `test_camera.py:69` — `perf_counter` side-effect list of `[0, 6]` breaks on any new call.
- `test_metrics.py::test_all_expected_context_keys_present` — lists 17 keys; no behavioural value, changes constantly.
- Exact-text assertions like `b"Messy"` that break with any label change — prefer `data-testid`.

### 40. Factory shortcomings
- `EggFactory.quality = "saleable"` — magic string; use `Egg.Quality.SALEABLE`.
- `NestingBoxPresencePeriodFactory` defaults to zero-duration periods (same LazyFunction for both timestamps).
- No traits for common states (`.deceased`, `.edible`, `.offline`).
- `timezone.now().date()` used where `timezone.localdate()` is safer.

---

## Tier 5 — Quick Wins / Polish

### 41. `pyproject.toml`
- Description is `"Add your description here"`.
- No `[tool.ruff]` section — you're getting defaults.
- `psycopg2-binary` in prod deps — use `psycopg` (v3).
- `dotenv` → should be `python-dotenv`.
- `swig` as a runtime dep is vestigial.

### 42. Dockerfile
- Runs as root.
- No `HEALTHCHECK`.
- `--workers 3` hardcoded (unsuitable for Pi 3).
- Cron env-var allowlist (`printenv | grep`) misses `COOP_LATITUDE` etc.

### 43. `AGENTS.md` is stale
Line 88 references the `dud` flag, which was removed in migration `0020_egg_quality.py`.

### 44. `utils.py` (`rolling_average`)
- `raise Exception` (should be `ValueError`).
- `List[float]` typing (use `list[float | None]`).
- `buf.pop(0)` is O(n); use `collections.deque(maxlen=window)`.
- Belongs in `web_app/analytics.py` (used only by metrics).

### 45. Dead / unused code
- `hardware_agent/handlers.py:144-151` — `save_frame_to_file` is never called in production.
- `hardware_agent/rfid_reader.py` — `MIN_RESET_INTERVAL = 0.1` with `self.reset_interval = 0.1` makes `max()` a no-op.
- `views/metrics.py:402-404` — dead ternary (palette has no `rgba(` entries).

### 46. Magic numbers that should be settings
- `WINDOW = timedelta(seconds=30)` (prune interval)
- `60` seconds (presence-grouping window)
- `5` seconds (sensor reconnect backoff)
- `10` seconds (beam sensor liveness poll)
- JPEG quality `90`
- `0.8` lay rate, `6`/`20` hours, `0.05` quality probabilities in seed

---

## Suggested Rollout Order

Given the volume, tackle this in waves:

### Wave 1 — Stop the bleeding (1–2 sessions) ✅ COMPLETE
- ✅ Fix `Egg` CASCADE → SET_NULL (new migration)
- ✅ Fix `Chicken.age` day-boundary bug
- ✅ Set `DEBUG = False` explicitly in `prod.py`
- ✅ Make `SECRET_KEY` fail fast if env var missing
- ✅ Default `DJANGO_ENV` to `"prod"` (or raise if unset) — avoids silent SQLite
- ✅ Add `--yes` / DEBUG guards on destructive commands
- ✅ Tighten logging config for Pi longevity (INFO root, logs outside repo)

**Wave 1 summary:** 32 new tests added (438 total, 406 baseline), 0 regressions, ruff clean.

### Wave 2 — Correctness ✅ COMPLETE
- ✅ Fix period-grouping race (`select_for_update` on the chicken row)
- ⏭️ `save_frame_to_db` "orphan" bug — **dismissed**: the single overhead camera covers multiple boxes, so no FK association is meaningful. Clarifying comment added.
- ✅ Re-add `started_before_ended` check constraint
- ✅ Restore uniqueness on `Chicken.tag` (partial UniqueConstraint for live chickens)
- ✅ Fix `USBCamera` reader-thread leak + add graceful shutdown (signal handlers + `stop_all`)

**Wave 2 summary:** 23 new tests added (461 total, 438 after Wave 1), 3 new migrations (`0021`–`0023`), 0 regressions, ruff clean.

### Wave 3 — Refactor
- Extract `MetricsParams` / `MetricsQueries` / chart builders
- Move analytics out of `views/`
- Move `handlers.py` into `web_app/services/`
- Extract hardware sensor registry; kill `add_*` duplication
- Fix N+1s in metrics + dashboard partials
- Add custom managers / default orderings

### Wave 4 — Frontend
- Create `src/web_app/static/`; vendor Bootstrap/HTMX/vis-timeline
- Extract the 3 huge inline scripts to static JS
- Fix `<tr onclick>` accessibility
- Extract sort-header, chart-card, htmx-poll partials
- Switch `egg_form.html` to Django form rendering

### Wave 5 — Polish
- Split `seed` into focused commands
- Collapse prune/delete commands
- Admin customisation pass
- Ruff/mypy/coverage config
- Test-coverage fill-ins (especially Postgres branch, concurrent writes, CSV error paths)

---

## Detailed Appendix — Per-Area Findings

The following sections preserve the full, detailed findings from each of the five review agents. The consolidated list above is a synthesis; the detail below is the source material.

---

### A. Hardware Agent (`src/hardware_agent/` and `test/hardware_agent/`)

#### A.1 `src/hardware_agent/base.py`

**Threading / concurrency:**
- `base.py:13-16` — `self.running`, `self.callback`, `self.status_callback` are mutated from the caller thread (`start()`) and read from the worker thread (`_run_loop`). No synchronization, no `threading.Event`. `self.running = False` in `stop()` relies on Python's atomicity for bool assignment — works in practice, but the idiomatic and safe approach is `threading.Event`. With `Event` you get interruptible sleeps for free.
- `base.py:64,74` — `time.sleep(5)` is not interruptible. If `stop()` is called while sleeping, the thread blocks for up to 5s before reacting, and `thread.join(timeout=2)` in `stop()` will give up before the thread exits. Use `self._stop_event.wait(5)`.
- `base.py:41-43` — `start()` is not idempotent; calling twice leaks a thread.
- `base.py:50` — `stop()` calls `self.disconnect()` unconditionally even though the worker thread might still be in the middle of `poll()`.

**Error handling:**
- `base.py:69-74` — Catches bare `Exception`; fine, but always 5s, no exponential backoff. The 5s constant is duplicated (lines 64 and 74) — pull out a `RECONNECT_INTERVAL_SECONDS` class constant.
- `base.py:58-63` — The `status_callback` signature is `(name, connected, message="")` but the success branch calls it with only 2 args and the failure branch with 3. The type hint says the third arg is required, which contradicts the call on line 59. Manager works around this with `lambda n, c, m="": ...` — the default belongs on `report_status`, not every lambda.

**Separation of concerns:**
- Logger uses module-level `__name__` so all sensor subclasses log as `hardware_agent.base` — you lose per-sensor context. Use `logging.getLogger(f"hardware_agent.base.{self.name}")` in `__init__`.

**Naming:**
- `callback` and `status_callback` — too generic. Consider `on_event` / `on_status_change`.
- Unparameterised `Optional[Callable]` type hints.

#### A.2 `src/hardware_agent/manager.py`

**Code duplication:**
- `manager.py:20-31`, `33-44`, `46-69` — The three `add_*` methods follow an identical pattern: validate → log warning → report_status → return, else construct → append → start with a status-callback lambda. Refactor to a single `add_sensor(sensor_type_prefix, sensor_instance, handler)` helper or a declarative registry.
- The three lambdas (`manager.py:30, 43, 68`) all have the form `lambda n, c, m="": report_status(f"{prefix}_{n}", c, m)`.

**Separation of concerns:**
- `manager.py:46-62` — GPIO pin parsing lives in the manager. `int(gpio)` belongs either in `BeamSensor` or a config-parsing layer.
- The manager imports concrete sensor classes AND the handler functions. Splitting into a config-driven factory + an orchestrator would improve testability.

**Missing behaviour:**
- No `stop_all()` / `shutdown()` method. Threads are daemons so they die with the process, but serial ports/GPIO/camera handles may not release cleanly.
- `self.sensors` is a list — no way to look a sensor up by name. Consider `dict[str, BaseSensor]`.

**Coupling:**
- `report_status` is imported from handlers, meaning the manager talks directly to the DB layer. Consider injecting a status reporter.

#### A.3 `src/hardware_agent/service.py`

**Hard-coded wiring:**
- `service.py:21-24` — Hard-coded `("left", "right")` and `range(1, 5)`. Better: scan env vars matching `RFID_PORT_*`, or load from a config file / Django setting.
- `service.py:26` — Single camera hard-coded as `"cam"`.
- `service.py:33` — `LGPIOFactory(chip=0)` chip hard-coded.

**Error handling:**
- `service.py:32-36` — swallows exceptions from `LGPIOFactory` with only a warning.
- No graceful shutdown. `signal.pause()` won't exit cleanly on SIGTERM.

**Testability:**
- `run_agent()` is untested. The module has no tests at all.

#### A.4 `src/hardware_agent/handlers.py`

**Class / function size & separation of concerns:**
- `handle_tag_read()` (`handlers.py:66-141`) is ~75 lines and does: event reporting, logging, name-derivation, three DB lookups, period-grouping logic with a cross-box check, period create/update, presence create, and exception handling. Split into:
  - a pure "find or create the active period" function,
  - a wrapper that resolves the box/tag/chicken,
  - a presence recorder.
- Both `handle_tag_read` and `handle_beam_break` mix orchestration with domain logic. This logic belongs on `NestingBoxPresencePeriod` as a classmethod like `NestingBoxPresencePeriod.record_presence(chicken, box, at)`.

**Duplication:**
- `handlers.py:144-151` (`save_frame_to_file`) vs `handlers.py:158-179` (`save_frame_to_db`) — both encode a JPEG with quality 90 and build `cam_name_<timestamp>.jpg` filenames. `save_frame_to_file` is not called from anywhere in production code (dead code).
- Timestamp format differs: `save_frame_to_file` uses `"%Y-%m-%dT%H:%M:%S.%f"` (line 148) and `save_frame_to_db` uses `"%Y%m%dT%H%M%S%f"` (line 170). Also `datetime.now()` (naive) is used instead of `timezone.now()`.
- `report_status` and `report_event` (`handlers.py:25-45`) — near-identical try/except wrapper pattern.

**DB logic in wrong place:**
- `handlers.py` is really a web_app service module, not a hardware_agent module. It contains zero hardware logic — only Django model I/O. Move into `web_app/services/hardware_events.py`.

**Camera frame writes:**
- `save_frame_to_db` (`handlers.py:158-179`) does not link the image to a nesting box — `NestingBoxImage.objects.create(image=django_file)` on line 177 doesn't pass `nesting_box`, so every camera frame creates an orphan image.

**Exception handling:**
- `handlers.py:136-141` catches `DoesNotExist` but leaks `DatabaseError` etc.
- `handlers.py:204-205` — bare `except Exception` after specific `DoesNotExist` is inconsistent.
- `handlers.py:76` — `report_event` is called *before* the transaction, so even when the tag is unknown, `last_event_at` is updated.

**Magic numbers / constants:**
- `NESTING_BOX_PRESENCE_TIMEOUT = 60` lives far from the logic it governs. Move into the model or nearer to use.
- JPEG quality `90` duplicated (lines 150, 165).

**Race conditions:**
- The period-grouping logic at `handlers.py:87-118` is not protected against concurrent readers. If two RFID readers in the same box read the same tag simultaneously, both may find no recent period and create two new periods. Needs `select_for_update()` or an explicit lock / unique constraint.

**Dead code / unused imports:**
- `from datetime import datetime, timedelta` — `datetime` used only by the dead-ish `save_frame_to_file` and `save_frame_to_db`.
- `save_frame_to_file` appears unused in production.

#### A.5 `src/hardware_agent/rfid_reader.py`

**Magic numbers / constants:**
- `MIN_RESET_INTERVAL = 0.1` (line 13) duplicates the default `reset_interval=0.1` constructor arg. The `max(MIN_RESET_INTERVAL, self.reset_interval)` on line 75 means the min always wins when equal.

**Error handling:**
- `rfid_reader.py:52-53` — bare `except: pass` on close.
- `rfid_reader.py:86` — `frame[:-1].decode()` can raise `UnicodeDecodeError` on garbage frames; no validation. Also no checksum validation despite the comment.
- `rfid_reader.py:74-76` — If the callback raises, the `rts=True/sleep/rts=False` reset never happens.
- `recv_frame()` — infinite loop on line 92 if the line goes noisy without timing out.

**Threading:**
- `self.serial_conn` is set in `connect()` and read in `poll()`, `read_tag()`, `recv_frame()`, `disconnect()`. `disconnect()` may be called from the main thread while `poll()` is running. No lock.

**Coupling / testability:**
- `serial.Serial` constructed inline — tests have to patch `serial.Serial`. Injecting a serial factory would simplify.

#### A.6 `src/hardware_agent/beam_break_sensor.py`

**Design problems:**
- `beam_break_sensor.py:63-74` — `poll()` sleeps for **10 seconds** then reads `self.device.value` as a liveness check. Why 10s? No comment.
- `poll()` doesn't actually do the beam-break detection — `on_connect` wires `when_activated` which is edge-triggered by gpiozero's internal thread. A more honest design would have `BaseSensor` support event-driven sensors without pretending to poll.

**Error handling:**
- `beam_break_sensor.py:69-72` — `except Exception as e: raise Exception(f"GPIO error: {e}")` — wraps a specific exception with a generic one and loses the traceback chain. Use `raise RuntimeError(...) from e`.
- `beam_break_sensor.py:51` — bare `except: pass` on close.

#### A.7 `src/hardware_agent/camera.py`

**Class size / responsibilities:**
- `USBCamera` is a lot: device selection, backend heuristics, a reader thread, a frame-rate limiter, a startup timeout, and a device-listing utility.

**Threading / concurrency:**
- `camera.py:37,39,80-81` — `_next_ts`, `_latest_frame` are read/written across threads. `_latest_frame` is protected, `_next_ts` is only on the worker thread.
- `camera.py:93` — Reader thread may race with `disconnect()` setting `self.cap = None` while reader is in `cap.read()`, leading to undefined behaviour in OpenCV.
- Every reconnect in `_run_loop` triggers `on_connect` → spawns a **new** reader thread. The old one may still be running. No tracking of the reader thread handle to join on disconnect.

**Error handling / edge cases:**
- `camera.py:131-137` — If `poll()` times out, reader thread may already have died; reconnect will spawn a fresh one.
- `camera.py:134` — Raises `Exception` rather than a specific class.
- `camera.py:57` — `hw_fps = max(self.fps, 15)`: magic number 15.
- Resolution `(1920, 1080)` hard-coded default — many cheap USB cams don't support this.

**Type hints:**
- `camera.py:23` — `device: str = 0` — type says `str`, default is `int(0)`.

#### A.8 Hardware agent tests

- `test_base_sensor.py:42-71` — relies on `mocker.patch("hardware_agent.base.time.sleep")` to avoid waiting. But because the loop is running concurrently, there is no guarantee `sensor.should_connect = True` is observed before another poll iteration. Flaky.
- `test_base_sensor.py:74-92` — Comment on line 75 "we don't have a 5s sleep" is **wrong** — base.py line 74 has `time.sleep(5)` on the error path.
- No test for `stop()` being called while in sleep, repeated reconnect cycles, `handle_error` default behaviour, `start()` called twice, or exception raised inside callback.
- `test_manager.py` — Heavily over-mocked — every sensor is a mock, so tests verify wiring but not behaviour.
- `test_handlers.py:127-136, 138-149, 151-160` — Tests assert log messages by string-matching. Brittle to any log format change.
- `test_handlers.py:231-240` — `save_frame_to_file` test patches `pathlib.Path("frames")` globally.
- No test for concurrent writes / period-grouping race condition.
- No test that `save_frame_to_db` links `NestingBoxImage` to a nesting box — because it doesn't.
- No test for `handle_camera_frame` end-to-end.
- No test for non-UTF8 / malformed RFID tag strings.
- `test_rfid_reader.py` — No test for `disconnect()` when `serial_conn` is None or when `close()` raises, `poll()` when `callback` is None, `read_tag()` when decode fails.
- `test_beam_sensor.py:44-57` — Test assertion on line 57 is weak — just asserts `mock_dev.value == 1`, which is true by construction.
- `test_camera.py:28-54` — Uses busy-wait up to 2 seconds. Flaky.
- `test_camera.py:75-87` — Bypasses the reader thread by setting `camera._latest_frame` directly.
- No test for `_reader` thread exiting after 10 consecutive failures, reader thread exception handling, disconnect-during-read race, multiple `on_connect()` calls spawning multiple reader threads.

---

### B. Web App Views, URLs, Forms

#### B.1 Fat views / business logic in the wrong place

**`views/metrics.py` — severe bloat**
`MetricsView.get_context_data` (`metrics.py:261-810`) is ~550 lines of business logic crammed into one method. It mixes:
- Query-param parsing (eight separate try/except blocks, each doing the same "int-parse with fallback" dance: `metrics.py:274-334`)
- Multiple ORM aggregation pipelines
- Numerical smoothing/KDE calculation orchestration
- Chart.js dataset dict construction, colour assignment, JSON serialisation
- Sidebar state

Concrete refactor:
- Extract a `MetricsParams` dataclass with a `from_request(request)` classmethod.
- Extract a `MetricsQueries` service (or manager methods on `Egg`/`Chicken`).
- Extract chart builders: `build_tod_egg_chart(...)`, `build_nesting_box_pie(...)`, etc.
- The "egg production vs age" block (`metrics.py:639-754`) duplicates the Sum/Mean logic from `_build_egg_prod_datasets` (`metrics.py:201-253`).
- The date-label generation and the "warm-up + window + [window:]" pattern is repeated three times — extract `rolled_series_for_display(raw, window)`.

**`views/dashboard.py` — `get_dashboard_context()` does DB-vendor dispatch itself**
`get_dashboard_context` (`dashboard.py:15-62`) mixes the presence-period "latest per box" query with six unrelated queries. The PostgreSQL/SQLite branch (`dashboard.py:24-49`) belongs on a manager.

**`views/chickens.py` — KDE and time-of-day bucketing don't belong in a views module**
`nesting_time_of_day` (`chickens.py:91-126`) and `egg_time_of_day_kde` (`chickens.py:133-176`) are pure numerical functions imported into `views/metrics.py`. Move to `web_app/analytics.py`.

**`ChickenDetailView.get_context_data` (`chickens.py:72-84`)**
The `stats` aggregate belongs on the `Chicken` model: `chicken.stats()`.

**`chicken_timeline_data` and `timeline_data`**
These two views are nearly identical. Extract a `build_timeline_items(start, end, chicken=None, include_presences=False, include_group=False)` helper.

**`EggForm.clean_quality` (`forms.py:36-38`)**
Silently rewrites invalid/empty input to "saleable". The `or Quality.SALEABLE` branch only ever runs for empty input. Either rely on the model default entirely or make the intent explicit with a comment.

#### B.2 Query efficiency

**Dashboard:**
- **Six partial views all call `get_dashboard_context()` for every HTMX poll** (`dashboard.py:74-102`). Every tick of every polling widget re-runs *all seven queries*. Split into per-partial context functions.

**Chickens:**
- `ChickenListView.get_queryset` (`chickens.py:32-49`) — `select_related("tag")` is redundant when also adding aggregate annotations that force a `GROUP BY`.

**Eggs:**
- `EggListView.get_queryset` (`eggs.py:12-18`) — **N+1 here**: no `select_related("chicken", "nesting_box")`.
- No pagination on `EggListView`. Same on `ChickenListView`.

**Timeline:**
- `timeline_images` (`timeline.py:64-103`) — fetches all PKs into Python then does a second query with `id__in=…`. For a large range this pulls potentially thousands of IDs.

**Metrics:**
Multiple N+1 loops over `chosen`:
- `metrics.py:389-394` — one query per hen for `Egg.objects.filter(chicken=hen, ...)` inside the time-of-day KDE loop.
- `metrics.py:471-477` — same problem for `NestingBoxPresencePeriod`.
- `metrics.py:661-697` — again, one query per hen for the age chart.

For a flock of 8–10 birds this means 25+ queries per metrics load.

#### B.3 Code duplication

- **Six almost-identical partial view functions** in `dashboard.py:74-102`.
- **Repeated query-param parsing with fallback** — `metrics.py:304-334` has five clones.
- **`datetime.fromisoformat(t_str.replace("Z", "+00:00").replace(" ", "+"))`** appears in `timeline.py:116-117` and `timeline_utils.py:25,29`.
- **Sum/Mean aggregation across hens** — implemented twice in `metrics.py`.
- **KDE/histogram nesting loops** — very similar structure in `metrics.py:386-465` and `metrics.py:467-525`.
- **`datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)`** repeated ~10 times in `test_metrics.py`.

#### B.4 DB-vendor split logic

Only one site in views (`dashboard.py:24-49`). It's reasonably localised but:
- **It belongs on the model manager**, not in the view.
- The `ended_at__gte=today_start` filter is duplicated in both branches.
- The fallback loop does `N+1` queries per box.
- No test asserts the fallback path directly; `test_dashboard.py::test_latest_presence_*` runs on SQLite, so the Postgres `DISTINCT ON` branch is **never tested**.

#### B.5 URL patterns

- `chicken_timeline_data` is registered under `chickens/<pk>/timeline-data/` but the global timeline is at `timeline/data/` — inconsistent.
- Dashboard partials are under `partials/…` but the top-level `partial_image_at_time` is also under `partials/…` while `timeline_images` is under `timeline/…`. Inconsistent namespacing.
- No namespacing (`app_name = "web_app"`).

#### B.6 Authorization / auth

**There is none.**
- No `LoginRequiredMixin`, no `@login_required`, no `PermissionRequiredMixin` on any view.
- `EggCreateView`, `EggUpdateView`, `EggDeleteView` are fully anonymous.
- If intentional (LAN-only, trusted network), document it explicitly in `AGENTS.md`.

#### B.7 Date/time handling

**Concerns:**
- `metrics.py:336` — `today = date.today()` in a timezone-aware app is dangerous: server UTC may roll the date before or after local midnight. Use `timezone.localdate()`. Same issue at `metrics.py:158, 648, 664, 767, 769`.
- `metrics.py:299-302` — `_parse_date` returns `date`, defaulting to `date.today()`; combined with the filter `laid_at__date__range=(start, end)` this is a latent day-boundary bug especially near midnight.
- `timeline.py:117` — `datetime.fromisoformat(t_str.replace("Z", "+00:00").replace(" ", "+"))`. The `.replace(" ", "+")` is because `+` in URL query strings is often decoded to a space. Brittle.
- `forms.py:11-17` — `laid_at` widget format `"%Y-%m-%dT%H:%M"` drops seconds.

**DST bug risk** in `chickens.py:107-124`: `cursor += timedelta(minutes=10)` is safe only because everything is UTC.

#### B.8 Testing

**Brittleness:**
- `test_metrics.py::test_all_expected_context_keys_present` (`test_metrics.py:91-114`) simply lists 17 context keys. Delete it.
- `test_dashboard.py:113-130` asserts exact column header strings. Prefer `data-testid`.
- `test_egg_list_shows_quality_column` asserts `"Messy"`, `"Saleable"`, `"Edible"` text.
- `test_e2e.py:33-34` `assert b"Chickens" in response.content` — any matching string passes.

**Coverage gaps:**
- No tests for dashboard's PostgreSQL `DISTINCT ON` branch.
- No test for `parse_date_range` directly.
- No test for `partial_image_at_time`'s `OverflowError` path.
- No test for `timeline_images` with `n` larger than int-overflow.
- No authorization/permission tests.
- `night_periods` pole-case branch is not tested.

**Mocking:**
- `test_timeline_utils.py:252-258` mocks `web_app.views.timeline_utils.settings` oddly. Use `@override_settings` or `monkeypatch.delattr(settings, "COOP_LATITUDE", raising=False)`.

---

### C. Models, Admin, Utils, Template Tags, Factories, Migrations

#### C.1 Model design

**Missing `Meta` / `verbose_name_plural` / default ordering:**
Only `NestingBox` (`models.py:39-40`) has a `Meta` class. Every other model is missing:
- **`Tag`** — default ordering (`number`).
- **`Chicken`** — `ordering = ["name"]`.
- **`Egg`** — `ordering = ["-laid_at"]`.
- **`NestingBoxPresence`** — `ordering = ["-present_at"]`; consider `verbose_name = "nesting-box ping"`.
- **`NestingBoxPresencePeriod`** — `ordering = ["-started_at"]`. Model name is long; `PresenceSession` or `BoxVisit` would read better.
- **`NestingBoxImage`** — `ordering = ["-created_at"]`.
- **`HardwareSensor`** — `ordering = ["name"]`.

**Missing DB constraints:**
- **`Egg`**: no `CheckConstraint` preventing both `chicken` and `nesting_box` being null.
- **`NestingBoxPresencePeriod`**: no `started_at <= ended_at` check — regression from the original schema.
- **`Chicken`**: no check that `date_of_death >= date_of_birth`.
- **`Tag`**: `rfid_string` has no normalisation (case, whitespace).

**Missing indexes:**
- **`NestingBoxPresence.present_at`** (`models.py:98`) is *not* indexed. Given presence pings are queried by time range constantly, it should be `db_index=True`.

**Relationship smells:**
- **`Chicken.tag`** (`models.py:19-21`) is a `ForeignKey`. Originally `OneToOneField` in migration `0015`, weakened in `0016`. Restore uniqueness.
- **`Egg.chicken` and `Egg.nesting_box`** use `on_delete=CASCADE`. Use `SET_NULL`.
- **`NestingBoxPresence{,Period}.chicken/nesting_box`** use `CASCADE` — should be `SET_NULL` with nullable FKs, mirroring `Egg`.

**`sensor_id` on `NestingBoxPresence`:**
Empty string as sentinel is a classic Django anti-pattern. Should be `ForeignKey(HardwareSensor, on_delete=SET_NULL, null=True)`.

**`Egg.Quality` choices design:**
- **The three `is_saleable` / `is_edible` / `is_messy` properties** (`models.py:63-73`) are boilerplate. Drop them.
- The `max_length=10` (`models.py:57`) is tight. Use `max_length=16`.

**Missing custom managers / querysets:**
- `Egg.objects.saleable()`, `edible()`, `messy()`.
- `Egg.objects.laid_today()` / `laid_on(local_date)` / `laid_between(start, end)`.
- `Chicken.objects.alive()`.
- `HardwareSensor.objects.online()` / `offline()` / `stale(older_than=...)`.
- `NestingBoxPresencePeriod.objects.overlapping(start, end)` / `for_box(box)`.

**Business-logic placement:**
- **`Chicken.age`** (`models.py:23-27`) uses `date.today()` — **not timezone-aware**. Genuine day-boundary bug.
- **`NestingBoxPresencePeriod.duration`** — consider also adding `.is_active`, `.overlaps(other)`, `.contains(dt)`.
- **60-second presence-grouping logic** in `handlers.py` is conceptually model state.

#### C.2 Admin

All seven models registered with `admin.site.register(Model)` and **zero customisation** (`admin.py:14-21`). Opportunities:
- **`Tag`**: `list_display`, `search_fields`.
- **`Chicken`**: `list_display`, `list_filter`, `search_fields`, `autocomplete_fields`.
- **`Egg`**: `list_display`, `list_filter`, `date_hierarchy`, `autocomplete_fields`, `list_select_related` — essential because `__str__` hits both FKs and the current admin N+1s horribly.
- **`NestingBoxPresence`**: `list_display`, `list_filter`, `date_hierarchy`, `list_select_related`, `raw_id_fields`.
- **`NestingBoxPresencePeriod`**: `list_display`, `list_filter`, `date_hierarchy`, inline for `NestingBoxPresence`.
- **`HardwareSensor`**: `list_display`, `list_filter`, `readonly_fields`.

Migrate to the `@admin.register(Model)` decorator style.

#### C.3 `src/web_app/utils.py`

**Does it belong here?**
`rolling_average` is used in exactly one place — `views/metrics.py`. Move to `src/web_app/metrics.py` or `analytics.py`.

**Implementation issues:**
- **`raise Exception(...)`** (`utils.py:44`) — use `ValueError`.
- **`List[float]`** from `typing` — use `list[float]`.
- **`LEFT`, `RIGHT`, `CENTER`** as bare string constants — use `enum.StrEnum` or `Literal["left","right","center"]`.
- **Mutation of `buf`** via `pop(0)` — `O(n)`. Use `collections.deque(maxlen=window)`.
- **Accepts `None` values** but `List[float]` typing does not reflect that.
- No validation that `window >= 1` or `window <= len(data)`.

**Test coverage of utils:**
Missing:
- `window == 0` / negative (should raise).
- `window > len(data)` (current behaviour unclear).
- Empty `data`.
- Single-element data.
- Asserts actual exception type, not just `Exception`.

Also uses `SimpleTestCase` + `assertListAlmostEqual` style while the rest of the suite uses pytest.

#### C.4 Template tags

Overall: well-structured, good docstrings, pure functions, nicely tested.

**Minor issues:**
- **`duration_ymd` with 30-day months** — explicit approximation, documented.
- **`test_age_column_shows_ymd_format`** (`test_templatetags.py:121-126`): assertion is `b"1y" in response.content or b"m" in response.content`. The `or b"m"` is trivially true (HTML is full of `m`). Tighten.
- **`date.resolution * 400`** is a convoluted way to write `timedelta(days=400)`.

#### C.5 Factories

**Issues:**
- **`date_of_birth` uses `timezone.now().date()`** — `.date()` returns the UTC date, not the local date. Use `timezone.localdate()`.
- **`EggFactory.quality = "saleable"`** — magic string. Use `Egg.Quality.SALEABLE`.
- **No traits** for common states: `ChickenFactory.deceased`, `.untagged`, `EggFactory.edible/messy`, `HardwareSensorFactory.offline`, `NestingBoxPresencePeriodFactory.long_visit`.
- **`NestingBoxPresencePeriodFactory`** has `started_at == ended_at` — duration zero.
- **`NestingBoxImageFactory`** generates an actual image (heavy).

#### C.6 Test coverage gaps

- **`Chicken.age`** day-boundary behaviour.
- **`NestingBoxPresencePeriod.duration`** — untested.
- **`NestingBoxImage`** — no tests at all.
- **`Tag.__str__`** — no test.
- **Constraint-violation tests**: `Tag.rfid_string` uniqueness, `number` uniqueness, `HardwareSensor.name` uniqueness.
- **`Egg.Quality` tests** — not for choices list, properties, or default.

#### C.7 Migrations — schema smells

- **`NestingBoxVisit` existed in 0001** with a `CheckConstraint started_at ≤ ended_at`, but `NestingBoxPresencePeriod` created in `0011` does **not** have that check. Regression.
- **`0015_add_tag_model_and_refactor_chicken.py:36-41`** originally created `Chicken.tag` as `OneToOneField`. `0016` downgraded it.
- **`0018` adds `sensor_id` to both `NestingBoxPresence` and `NestingBoxPresencePeriod`; `0019` removes the one on Period.** Could have been a single migration.
- **No `default_auto_field = "BigAutoField"`** on AppConfig.
- **`NestingBoxImage.image`** is stored via `ImageField(upload_to="nesting_box_images")`. No width/height fields, no max size.

#### C.8 Cross-cutting observations

- **`AGENTS.md` is stale**: `AGENTS.md:88` describes `Egg` with "`dud` flag", but this was removed in migration `0020_egg_quality.py`.
- **No model-level `clean()`**: `Chicken.clean()` could enforce `date_of_death >= date_of_birth`, etc.
- **Consistent datetime helpers**: Project mixes `timezone.now()`, `timezone.localtime()`, `date.today()`, `timezone.localdate()`. A tiny `web_app/time.py` would help.

---

### D. Management Commands, Settings, `pyproject.toml`, Dockerfile

#### D.1 `seed.py`

**Major: `seed` is four unrelated commands wearing one hat**
The `SeedMode` enum lumps together:
- `SPAWN_TEST_DATA` — **destructive**, dev-only.
- `CLEAR` — **destructive**, wipes production data with no confirmation.
- `SEED_CHICKENS` / `SEED_TAGS` — **non-destructive** CSV upserts.
- `SEED_NESTING_BOXES` — non-destructive idempotent.

Recommend splitting into: `seed_test_data`, `flush_app_data`, `import_chickens`, `import_tags`, `ensure_nesting_boxes`.

**Major: `clear_data()` has no safety guard** (`seed.py:90-97`)
- Require `--yes` or Django's standard `--no-input`.
- Enumerate deletions explicitly and log counts per model.
- Consider delegating to `call_command("flush", ...)`.
- Add `NestingBoxImage` to the delete list.

**Minor: `SPAWN_TEST_DATA` has no DEBUG guard**
Guard with `if not settings.DEBUG: raise CommandError("spawn_test_data requires DEBUG=True")`.

**Minor: `populate_data()` is an unstructured god-function** (`seed.py:103-214`)
- Hard-codes six chickens with specific RFID strings and numbers.
- Magic numbers: `0.8` lay rate, `6`/`20` hours, `0.05`/`0.1` quality probabilities.
- Not wrapped in `transaction.atomic()`.
- Hoppy-specific branch couples business-logic quirks to seed data.

**Minor: `seed_tags_from_csv` / `seed_chickens_from_csv` error handling** (`seed.py:231-299`)
Zero resilience to bad rows, missing headers, missing files, duplicates.

**Minor: No `--dry-run` on any mode.**

**Minor: Stale comment**
`seed.py:22` — `# uv run manage.py seed --mode=refresh` references a non-existent mode.

#### D.2 Prune / delete image commands

**Major: Two commands doing almost the same thing**
- `prune_nesting_box_images.py:36-39` and `delete_nesting_box_images.py:20-22` — identical bodies. Extract a shared helper.

**Major: Storage delete before DB delete is the wrong order for crash safety**
```python
image.image.delete(save=False)  # removes file
image.delete()                  # removes DB row
```
If the process dies between these two lines, you have a DB row pointing to a file that no longer exists. Safer: delete DB row first.

**Minor: `WINDOW = timedelta(seconds=30)` is hard-coded** (`prune_nesting_box_images.py:11`)
**Minor: `WINDOW.seconds` in help text** — would silently break for a window ≥1 day. Use `total_seconds()`.
**Minor: No `--dry-run`.**
**Minor: No summary statistics on bytes freed.**
**Minor: Progress-log interval is magic 100.**

#### D.3 `run_hardware_agent.py`

- Zero argparse options (`--once`, `--poll-interval`, `--log-level`).
- No graceful shutdown handling.
- `help = "Start RFID hardware agent"` is misleading since the agent also does cameras and beam sensors.
- `options` is spelled `opts`.

#### D.4 Settings

**Critical: `ALLOWED_HOSTS = ["*"]` in base** (`base.py:36-38`) — wildcard applies in prod too.

**Critical: `DEBUG` not explicitly set in `prod.py`.**

**Critical: No security settings:**
- `SECURE_SSL_REDIRECT`
- `SECURE_HSTS_*`
- `SECURE_PROXY_SSL_HEADER`
- `SECURE_CONTENT_TYPE_NOSNIFF`
- `SESSION_COOKIE_SECURE`
- `CSRF_COOKIE_SECURE`
- `CSRF_TRUSTED_ORIGINS`

**Critical: `SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")`** — If env var missing, `SECRET_KEY` is `None`. Fail fast.

**Major: `LOGS_DIR` created at import** (`base.py:83-84`) — runs on every `django.setup()`.

**Major: Logging config not differentiated per env** — DEBUG level everywhere, file writes to repo under `BASE_DIR/logs`, root logger at DEBUG dumps third-party noise.

**Minor: `settings/__init__.py` strategy** — `DJANGO_ENV` defaulting to `"dev"` means forgetting to set it in prod → silently runs SQLite. Default to `prod` or raise.

**Minor: `COOP_LATITUDE` / `COOP_LONGITUDE` no validation.**

#### D.5 Hard-coded values that should be settings

| Value | Location | Recommendation |
|---|---|---|
| `WINDOW = timedelta(seconds=30)` | `prune_nesting_box_images.py:11` | `settings.NESTING_BOX_IMAGE_RETENTION_WINDOW` |
| 60-second presence grouping | `hardware_agent/handlers.py` | `settings.PRESENCE_PERIOD_GROUPING_WINDOW` |
| 5-second retry backoff | `hardware_agent/base.py` | `settings.SENSOR_RECONNECT_BACKOFF` |
| `ALLOWED_HOSTS = ["*"]` | `base.py:37` | Env-driven |
| Hard-coded chickens/tags in `populate_data` | `seed.py:120-150` | Read the CSVs |
| `0.8` lay rate, `0.05` quality probabilities | `seed.py:166-205` | Module constants |
| `10 MiB` / `5` log backup count | `base.py:117-118` | Env-driven |
| `3` uvicorn workers | `Dockerfile:78` | Env-driven |

#### D.6 `pyproject.toml`

- Description is `"Add your description here"`.
- No `[tool.ruff]` section.
- No `[tool.mypy]` / `[tool.pyright]`.
- No `pytest-cov` / `coverage`.
- No `.pre-commit-config.yaml`.
- `dotenv>=0.9.9` is the wrong package; use `python-dotenv`.
- `psycopg2-binary` — use `psycopg` (v3).
- `swig>=4.4.1` as a runtime dep is vestigial.

#### D.7 Testing gaps

**`test_seed.py`:**
- No test that `clear` mode deletes `NestingBoxImage` (because it doesn't).
- No error-path tests for `seed_chickens_from_csv` / `seed_tags_from_csv`.
- No test for `spawn_test_data` idempotency.
- No test that `SPAWN_TEST_DATA` refuses to run with `DEBUG=False`.
- Relies on `random()` producing at least one egg — seed the RNG.

**`test_prune_nesting_box_images.py`:**
- No test that a failure during file-delete doesn't leave DB in a broken state.
- No test for very large batches.
- No test for an image exactly `WINDOW` away.
- No idempotency test.
- No `--dry-run` test.

**`test_delete_nesting_box_images.py`:**
- Progress-log output test missing.
- Test that file-delete happens in correct order missing.
- Test behaviour when file-delete raises.

#### D.8 Missing pieces

- **Health check command** — no `manage.py healthcheck`.
- **DB migration wrapper** — a dedicated `manage.py bootstrap` command.
- **Wait-for-DB** — no retry on startup.
- **Backup / export commands** — `export_eggs --csv` / `export_all --sqlite`.
- **Admin user bootstrap** — no `createsuperuser --noinput` wrapper.
- **Image retention by count or size** — only time-proximity is checked.

#### D.9 Dockerfile findings

- `Dockerfile:92` — env-var allowlist for cron (`printenv | grep`) captures only `DJANGO_*`, `POSTGRES_*`, `MEDIA_ROOT`, `LOG_FILENAME`. Misses `COOP_LATITUDE/LONGITUDE` and `STATIC_ROOT`.
- `Dockerfile:22` — `UV_NO_DEV=1` only in builder; project-builder stage runs `uv sync` without that env.
- `Dockerfile:63-64` — copies `/usr/local/lib` and `/usr/local/bin` wholesale; potentially version skew.
- `Dockerfile:78` — `--workers 3` hard-coded. Use `UVICORN_WORKERS`.
- No `HEALTHCHECK`.
- No non-root `USER`.

---

### E. Templates and Frontend

#### E.1 Overview

The app uses Django templates with Bootstrap 5.3.2 and HTMX 1.9.10 (both loaded from CDNs), plus `vis-timeline` and `chart.js`. **No `src/web_app/static/` directory exists** — no static assets are shipped locally. All CSS and JS is inlined in templates or loaded from CDNs.

#### E.2 `base.html`

- **base.html:9** — Bootstrap CSS `<link>` has a double space.
- **base.html:9-10, 13, 41** — All CSS/JS loaded from public CDNs. Fragile for a Pi that may have intermittent internet.
- **base.html:13 vs base.html:41** — Bootstrap JS at bottom (good), HTMX in `<head>` blocking.
- **base.html:41** — `<script>` placed *outside* the closing `</body>` tag.
- **base.html:15-38** — No blocks for `body_class`, `page_header`, `footer`, `extra_scripts`, or `messages`. No `{% if messages %}` rendering.
- **base.html:17-42** — No `<main>` landmark.
- **base.html:27-31** — Nav links don't highlight the current page.

#### E.3 `dashboard.html`

- **dashboard.html:24-62** — 40-line inline `<script>` embedded mid-grid.
- **dashboard.html:25-57** — Hand-rolled `fetch`/`DOMParser` logic to do what HTMX already does elsewhere.
- **dashboard.html:61** — `setInterval` at 1s while adjacent HTMX partials poll every 5s.
- **dashboard.html:29-31** — `DOMParser` couples the JS tightly to the partial's exact DOM structure.

#### E.4 `chicken_detail.html`

- **chicken_detail.html:7-17** — Inline `<style>` duplicates `timeline.html:7-15`.
- **chicken_detail.html:69-70** — Magic querystring `?chickens_sent=1&chickens={{ hen.pk }}` hard-codes the metrics view's filter API.
- **chicken_detail.html:101-135** — 35-line inline script reimplements the timeline.html pattern.
- **chicken_detail.html:22-27** — Breadcrumb pattern duplicated in `egg_form.html:9-16`.
- **chicken_detail.html:41-55** — `dl.row` with `<dt>/<dd>` repeats — see `egg_confirm_delete.html:11-18`.

#### E.5 `chicken_list.html`

- **chicken_list.html:13-27** — 15 lines of sortable-header markup duplicated in `egg_list.html:15-23`. Should be a custom tag `{% sort_header %}`.
- **chicken_list.html:33** — `<tr onclick="location.href='...'">` — accessibility-hostile:
  - Not keyboard-accessible.
  - Not announced as a link.
  - Right-click / middle-click broken.
  - CSP concern.
- **chicken_list.html:43** — `colspan="7"` is hardcoded.
- **chicken_list.html:16, 20, 24** — Sort arrows `▲`/`▼` have no aria-label.

#### E.6 `egg_list.html`

- **egg_list.html:15-23** — Different sort-header convention from `chicken_list.html`.
- **egg_list.html:24** — Empty `<th>` for action column, no `scope` / aria label.
- **egg_list.html:35-41** — Quality badge logic in template; belongs on model.
- **egg_list.html:49** — `colspan="5"` hardcoded.

#### E.7 `egg_form.html`

- **egg_form.html:23-114** — Entire form hand-rendered field-by-field, 90 lines. Use `{{ form.as_div }}` or `django-widget-tweaks`.
- **egg_form.html:41-47, 60-75** — Manual iteration over `form.chicken.field.choices`.
- **egg_form.html:44, 67** — `{% if form.chicken.value|stringformat:"s" == pk|stringformat:"s" %}` — classic template-logic smell.
- **egg_form.html:93-102** — Radio quality choices hand-rendered.

#### E.8 `egg_confirm_delete.html`

- Missing `shadow-sm` class despite other cards having it. Visual inconsistency.
- Submit buttons swapped in order vs `egg_form.html` — inconsistent UX.
- Duplicates the `dl.row` pattern from `chicken_detail.html:39-60`.
- No breadcrumb.

#### E.9 `metrics.html`

- **metrics.html:4-32** — 29 lines of CSS inlined.
- **metrics.html:322-612** — **290-line inline `<script>` block**. Should be in `static/web_app/metrics.js`.
- **metrics.html:63-68, 135-148** — Inline `onclick` on 7+ buttons.
- **metrics.html:74-83** — `onchange="submitForm()"` on every input.
- **metrics.html:136-148** — Quick-filter buttons pass `{% now "Y" %}, {% now "m" %}, {% now "d" %}` three times each — 21 template tag calls where `new Date()` in JS would do it.
- **metrics.html:367** — `const SHOW_MEAN = {{ show_mean|yesno:"true,false" }}`. Use `{{ show_mean|json_script }}`.
- **metrics.html:82** — `🪓` emoji for "deceased" with no accessible label (screen readers say "axe").
- **metrics.html:192, 212, 294** — `role="button"` on `<div>` — use real `<button>`.

#### E.10 `timeline.html`

- **timeline.html:7-15** — Inline `<style>` duplicates `chicken_detail.html:15`.
- **timeline.html:45-263** — **218-line inline `<script>` block**.
- **timeline.html:49-52** — Django `{% for %}` loop injects JS object literals directly. Chicken names containing `'`, `\`, or `</script>` will break the page or allow XSS. Use `{{ chickens|json_script }}`.
- **timeline.html:37** — `<img id="dashboard-image" src="">` — same ID as `_latest_image.html`. Empty `src` triggers re-request to current doc.
- **timeline.html:256-262** — `setInterval` with `window.start` shadowing the global `window`.

#### E.11 `_timeline_assets.html`

- **_timeline_assets.html:1-2** — `vis-timeline` loaded from `@latest`. Ticking bomb.
- **_timeline_assets.html:3-73** — 70 lines of CSS inlined.
- **_timeline_assets.html:42-60** — Four-way per-sensor colour rules hard-coded.
- **_timeline_assets.html:74-95** — `todayWindow` + `debounce` utilities inlined.

#### E.12 Partials

- **`_latest_presence.html:9`** — `<thead class="table-light">` no `<th scope="col">`.
- **`_sensors.html:11-13`** — Badge colour logic inlined; should be a model property.
- **`_sensors.html:16, 24`** — Inline `style="font-size: 0.8em"`.
- **`_latest_image.html:6-8`** — `<img src="">` in the "no image" case.
- **`_latest_image.html`** — ID `dashboard-image` referenced by both HTMX polling and raw `fetch`.
- **`_eggs_today.html:7`** — `<a href="..." class="stretched-link"></a>` — empty anchor, screen readers announce unlabelled link.

#### E.13 Cross-cutting

**Duplication patterns that should become partials / tags:**
1. **Sortable table header** (2 templates, diverging) → `{% sort_header %}` custom tag.
2. **Breadcrumb** (2 copies, missing from 1) → `_breadcrumb.html` partial.
3. **"Collapsible card"** (3× in metrics) → partial.
4. **"Chart card"** (8× in metrics) → partial.
5. **Status badge** (quality + connectivity) → move to model methods.
6. **`dl.row` definition list** → partial.
7. **HTMX polling panel** (5× in dashboard) → inclusion tag `{% htmx_poll url interval %}`.
8. **Timeline loader JS** (2 templates) → shared JS module.
9. **`<select>` option loop** (2 templates) → form widget / partial.

**Accessibility summary:**

| File | Issue |
|---|---|
| base.html:17-42 | No `<main>` landmark; no active-page indicator in nav. |
| chicken_list.html:33 | `<tr onclick>` not keyboard accessible. |
| chicken_list.html:16-24, egg_list.html:17-21 | `<th>` without `scope="col"`. |
| egg_list.html:24 | Empty `<th>` for action column. |
| metrics.html:192, 212, 294 | `<div role="button">` instead of real `<button>`. |
| metrics.html:82 | `🪓` emoji with no aria-label. |
| _laid_chickens.html:16, _eggs_today.html:7 | Emoji / stretched link without labels. |
| _latest_image.html:6-8 | Non-descriptive `alt` attribute. |
| _sensors.html:11-13 | Status conveyed primarily by colour. |
| chicken_detail.html:96 | `vis-timeline` chart has no accessible label. |

**Template testing gaps:**
1. No tests for `egg_form.html` rendering — hand-rolled field logic is fragile and untested.
2. No tests for metrics.html sidebar form rendering.
3. No tests for `_latest_image.html` rendering both states.
4. No tests for `_sensors.html` — status badge colour logic.
5. No tests for `_latest_events.html` fallback strings.
6. No tests for `chicken_list.html` / `egg_list.html` sort header rendering.
7. No tests for `egg_confirm_delete.html`.
8. No tests for breadcrumb rendering consistency.
9. No snapshot-style test for the base template's nav bar markup.

---

## Outside-of-LAN Security Changes

**These items are intentionally out of scope under the current deployment model** (trusted LAN + VPN). They are recorded here so that if the app is ever exposed beyond the LAN — on the public internet, on a shared/untrusted network, or to users other than the owner — they can be picked up as a checklist. None of them need to be done today.

### S1. Authentication and authorization
- Add `LoginRequiredMixin` (or `@login_required`) to all views — at minimum the write views: `EggCreateView`, `EggUpdateView`, `EggDeleteView` (`views/eggs.py`).
- Consider `PermissionRequiredMixin` if multi-user access is wanted (e.g. read-only guests vs. coop keepers).
- Add a login page and a logout route; wire `LOGIN_URL` and `LOGIN_REDIRECT_URL` in settings.
- Bootstrap an admin user at container start (`createsuperuser --noinput` wrapper or a `manage.py bootstrap_admin` command), since there's no other way in.
- Django admin is currently reachable anonymously via the lack of auth on other routes; double-check `admin.site.urls` is login-gated (it is by default, but worth confirming once auth is added).

### S2. HTTPS / transport security
- Put a TLS-terminating reverse proxy (Caddy, nginx, Traefik) in front of the app. Caddy is easiest on a Pi with Let's Encrypt if the box ever has a public hostname.
- Once behind HTTPS, enable in `prod.py`:
  - `SECURE_SSL_REDIRECT = True`
  - `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` (if behind a proxy)
  - `SECURE_HSTS_SECONDS = 31536000`
  - `SECURE_HSTS_INCLUDE_SUBDOMAINS = True`
  - `SECURE_HSTS_PRELOAD = True` (only once confident)
  - `SESSION_COOKIE_SECURE = True`
  - `CSRF_COOKIE_SECURE = True`
  - `SECURE_CONTENT_TYPE_NOSNIFF = True` (default on; be explicit)
- Set `CSRF_TRUSTED_ORIGINS = ["https://coop.example.com"]` — required in Django 4+ when behind an HTTPS proxy.

### S3. `ALLOWED_HOSTS` hardening
- Replace `ALLOWED_HOSTS = ["*"]` in `base.py` with an env-driven, explicit list in `prod.py`:
  ```python
  ALLOWED_HOSTS = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")
  ```
- Keep `["*"]` only in `dev.py`.

### S4. Rate limiting
- HTMX partials poll every 1–5 seconds × 6 panels × no auth = trivially hammer-able. Add `django-ratelimit` or a reverse-proxy rate limit on the `/partials/*` prefix.
- The `timeline_images` endpoint accepts `n` as a query param with no upper bound; clamp to something sane (e.g. 500) to prevent resource-exhaustion requests.

### S5. Input hardening
- Audit every query-string parse for unbounded/untrusted values: `metrics.py` window/bandwidth params, `timeline.py` `n`, `partial_image_at_time` timestamps.
- Fix the XSS risk at `timeline.html:50` — chicken names are interpolated unescaped into a JS literal. Use `{{ chickens|json_script }}`. (This is worth doing anyway for robustness against unusual names; under the current threat model it's a low-severity correctness issue rather than a vulnerability.)
- Tighten `EggForm.clean_quality` so invalid input raises instead of silently normalising.

### S6. CSRF / cookies
- Once HTTPS is in play, set `CSRF_COOKIE_SECURE = True` and `SESSION_COOKIE_SECURE = True`.
- Consider `SESSION_COOKIE_HTTPONLY = True` (default), `SESSION_COOKIE_SAMESITE = "Lax"` (default — fine).
- Review any HTMX POST endpoints (none today, but likely once write forms go HTMX) — they'll need the CSRF token passed via `hx-headers` or the `{% csrf_token %}` meta trick.

### S7. Security headers
- Add a `Content-Security-Policy` (via `django-csp` or reverse proxy). **This will require eliminating all inline `<script>` and `<style>` blocks first** (see Tier 3 items #29–#32 for the prerequisite work).
- Headers to set at the proxy layer: `X-Frame-Options: DENY` (Django default), `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` as appropriate.
- Consider subresource integrity (SRI) hashes on any remaining CDN `<link>`/`<script>` tags — ideally by vendoring them locally (Tier 3 #30).

### S8. Secrets management
- `SECRET_KEY` fail-fast is already in Tier 1 for ops reasons, but it becomes a genuine security requirement here — a leaked or default `SECRET_KEY` allows session-cookie forgery.
- Rotate `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` before exposing externally.
- Ensure `.env` is not baked into the Docker image.

### S9. Container hardening
- Run as non-root (`USER app` in the runtime Dockerfile stage) — defence in depth for any future RCE-class CVE in Django/uvicorn/OpenCV. Cheap, basically free.
- Add a `HEALTHCHECK` so Docker can restart on unhealthy. (Also valuable on-LAN.)
- Drop capabilities the container doesn't need (`--cap-drop=ALL`, add back specifically).
- Consider a read-only root filesystem with `/tmp` and the media volume writable.

### S10. Audit logging
- Log authentication attempts, admin actions, and destructive operations (egg delete, chicken delete) to a separate, non-rotating audit log.
- On a public-facing deployment, ship logs off the Pi (the SD card is a single point of failure).

### S11. Backups
- Automate Postgres backups to a mounted volume or off-box location. A `manage.py backup_db` command + cron entry, or `pg_dump` from a sidecar.
- Same for media (`nesting_box_images/`) — though the prune job keeps this small, it's still irreplaceable if SD card dies.

### S12. Dependency scanning
- Add `pip-audit` (or equivalent) in CI. On a LAN this matters less; exposed externally it matters more.
- Track CVEs for Django, uvicorn, psycopg, and (especially) opencv-python.

### S13. `manage.py check --deploy`
- Run this against prod settings in CI once HTTPS is set up. It will flag most of the `SECURE_*` items in one go.

---

*End of review.*
