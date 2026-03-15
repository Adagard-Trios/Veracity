"""
tests/conftest.py — pytest configuration and shared fixtures.
"""

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "llm_judge: marks tests as LLM-as-judge evaluation (uses real Firecrawl + Groq credits)"
    )
