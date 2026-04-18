"""
Service-layer modules for the web_app package.

Services are the place for business logic that:

  * Doesn't belong in models (too view-specific, or spans multiple models
    in ways that would bloat any single one).
  * Doesn't belong in views (not HTTP-shaped — called from the hardware
    agent, management commands, etc.).

Each service module should:

  * Expose a small, named set of public callables.
  * Import from ``web_app.models`` freely.
  * **Not** depend on the request/response cycle (no ``request`` args,
    no ``django.http``, no ``reverse()``).

Current modules:

  * :mod:`hardware_events` — persists the events emitted by the hardware
    agent (RFID tag reads, beam breaks, camera frames, sensor status).
"""
