"""Vercel WSGI entry point for abbiey.search."""
import sys
import os

# Ensure the project root is on the path so `app` and `entity_parser` resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app  # noqa: F401 — Vercel picks up `app` as the WSGI handler
