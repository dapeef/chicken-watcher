"""Shared fixtures for the metrics view tests."""

import pytest
from django.utils import timezone


@pytest.fixture
def today():
    return timezone.localdate()
