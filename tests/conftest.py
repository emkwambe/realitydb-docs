"""Pytest configuration for realitydb-docs tests."""
import os
import sys

import pytest

# Make the package importable without an editable install. pytest puts the
# test file's own directory on sys.path, not the repo root, so without this
# the suite only runs where `pip install -e .` has already been done.
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "consistency: cross-document consistency checks"
    )
    config.addinivalue_line(
        "markers",
        "rendering: PDF rendering checks"
    )
