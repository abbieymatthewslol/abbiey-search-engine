"""Optional Vercel serverless entry: import the Flask app.

Production deploys use ``vercel.json`` with ``builds`` → ``app.py`` and a catch-all route.
This file remains valid if a project is pointed at ``api/index.py`` instead.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app  # noqa: F401
