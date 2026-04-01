"""Vercel WSGI entry point for abbiey.search."""
import sys
import os

# Ensure the project root is on the path so `app` and `entity_parser` resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app  # noqa: F401 — Vercel picks up `app` as the WSGI handler

# ---- AUTO HEALTH PATCH ----
try:
    from flask import jsonify
except:
    pass

def _health_response():
    try:
        return jsonify({"status": "ok"})
    except:
        return {"status": "ok"}

try:
    app.route("/api/health")(_health_response)
except:
    pass
# ---- END PATCH ----

