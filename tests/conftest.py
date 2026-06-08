"""Pytest configuration: make the backend and ml packages importable.

Adds the ``backend`` and ``ml`` directories to ``sys.path`` so tests can import
modules directly (``import risk_engine``) without packaging boilerplate.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("backend", "ml"):
    path = os.path.join(_ROOT, sub)
    if path not in sys.path:
        sys.path.insert(0, path)
