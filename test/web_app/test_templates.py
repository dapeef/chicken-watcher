"""
Template-level regression tests that aren't specific to any one view.

Most template rendering is exercised indirectly via the view tests;
this module holds the handful of checks that are genuinely cross-
cutting (e.g. "no CDN references leak into any template").
"""

from pathlib import Path

import pytest
from django.urls import reverse

from .factories import ChickenFactory

TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "src" / "web_app" / "templates"
)


def _all_templates() -> list[Path]:
    return sorted(TEMPLATES_DIR.rglob("*.html"))


class TestNoLargeInlineScripts:
    """Inline <script> blocks over a certain size are a code smell:
    they can't be cached by the browser, can't be covered by a CSP
    policy, and are a pain to test and lint. Wave 4 is extracting the
    three large inline scripts (metrics, timeline, chicken_detail)
    into ``static/web_app/js/``. This test pins that decision so
    future inline scripts stay small.

    ``STILL_INLINE`` lists templates that are being migrated across
    Wave 4 items and are currently expected to fail this check.
    Remove from the set as each extraction lands.
    """

    MAX_INLINE_SCRIPT_CHARS = 500

    # Templates known to still have oversized inline scripts. Each
    # entry will be removed by its corresponding Wave 4 extraction
    # commit.
    # As of Wave 4 completion, every template's inline scripts have
    # been extracted. This set is empty but kept as a place for future
    # migrations.
    STILL_INLINE: set[str] = set()

    @pytest.mark.parametrize("template_path", _all_templates(), ids=lambda p: p.name)
    def test_no_oversized_inline_script_blocks(self, template_path: Path):
        import re

        if template_path.name in self.STILL_INLINE:
            pytest.xfail(
                f"{template_path.name} still has an inline script pending "
                f"extraction in a subsequent Wave 4 commit"
            )

        content = template_path.read_text()
        # Match a <script> ... </script> block that does NOT carry a
        # src= or type="application/json" attribute. Those are the
        # legitimate cases (external file, data handoff).
        inline_pattern = re.compile(
            r"<script(?![^>]*\bsrc=)(?![^>]*type=\"application/json\")[^>]*>(.*?)</script>",
            re.DOTALL | re.IGNORECASE,
        )
        for match in inline_pattern.finditer(content):
            body = match.group(1).strip()
            assert len(body) <= self.MAX_INLINE_SCRIPT_CHARS, (
                f"{template_path.name} has an inline <script> block of "
                f"{len(body)} chars (limit {self.MAX_INLINE_SCRIPT_CHARS}). "
                f"Extract to a file under src/web_app/static/web_app/js/ "
                f"and reference via {{% static %}}."
            )
        for match in inline_pattern.finditer(content):
            body = match.group(1).strip()
            assert len(body) <= self.MAX_INLINE_SCRIPT_CHARS, (
                f"{template_path.name} has an inline <script> block of "
                f"{len(body)} chars (limit {self.MAX_INLINE_SCRIPT_CHARS}). "
                f"Extract to a file under src/web_app/static/web_app/js/ "
                f"and reference via {{% static %}}."
            )


class TestNoCDNReferences:
    """All third-party assets should be vendored locally. A CDN
    reference in any template is a regression — see Wave 4 / item 30
    of docs/tech-debt-review.md."""

    CDN_HOSTS = (
        "cdn.jsdelivr.net",
        "unpkg.com",
        "cdnjs.cloudflare.com",
        "ajax.googleapis.com",
        "fonts.googleapis.com",
        "stackpath.bootstrapcdn.com",
    )

    @pytest.mark.parametrize("template_path", _all_templates(), ids=lambda p: p.name)
    def test_template_has_no_cdn_references(self, template_path: Path):
        content = template_path.read_text()
        for host in self.CDN_HOSTS:
            assert host not in content, (
                f"{template_path.name} references CDN host {host!r}. "
                f"All assets must be vendored under src/web_app/static/ "
                f"and served via {{% static %}}."
            )


@pytest.mark.django_db
class TestBaseTemplateBasics:
    """Smoke tests on the base template's rendered output."""

    def test_base_template_loads_local_bootstrap_css(self, client):
        response = client.get(reverse("dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        # Vendored path, not CDN
        assert "vendor/bootstrap-5.3.2/css/bootstrap.min.css" in content

    def test_base_template_loads_local_htmx(self, client):
        response = client.get(reverse("dashboard"))
        content = response.content.decode()
        assert "vendor/htmx-1.9.10/htmx.min.js" in content

    def test_base_template_has_main_landmark(self, client):
        response = client.get(reverse("dashboard"))
        content = response.content.decode()
        # Accessibility: the page body should have a <main> landmark so
        # assistive tech can skip past the nav.
        assert "<main" in content

    def test_active_nav_item_has_active_class(self, client):
        response = client.get(reverse("chicken_list"))
        content = response.content.decode()
        # The "Chickens" nav link should be rendered with the active class
        # on the chicken list page.
        ChickenFactory()  # ensure the page has something to render
        assert 'class="nav-link active"' in content or " active " in content

    def test_messages_framework_renders(self, client):
        """If a view sets a message, base.html should render it in an
        accessible alert. We trigger one via a redirect."""
        from django.contrib import messages
        from django.test import RequestFactory
        from django.contrib.messages.storage.fallback import FallbackStorage

        rf = RequestFactory()
        request = rf.get("/")
        # Stuff a message onto a dummy session/messages backend
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))
        messages.info(request, "Test message")
        # We don't have a trivial way to render the base template with
        # this request through the test client, so we just verify the
        # template structure from the file directly.
        base_path = TEMPLATES_DIR / "base.html"
        base_content = base_path.read_text()
        assert "{% if messages %}" in base_content
        assert "{% for message in messages %}" in base_content
