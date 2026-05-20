"""Shared pytest fixtures and configuration."""
import os
import pytest
from pathlib import Path

# Ensure tests always run with the project root as CWD so relative
# path resolution in tools (excel, documents, sql) works correctly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def set_project_root_cwd(monkeypatch):
    """Change CWD to the project root for every test."""
    monkeypatch.chdir(PROJECT_ROOT)
