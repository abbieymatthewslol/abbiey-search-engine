# Vercel Python entrypoint ? expose Flask app

import os
import sys

# Ensure project root is importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Import the Flask app instance from your main file
from app import app as app

# Optional: alias for some runtimes (harmless)
handler = app
