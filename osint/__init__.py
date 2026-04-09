"""Curated, on-demand OSINT helpers for abbiey.search (public sources only).

Import from ``osint.service`` in application code to avoid import cycles
(``python -c "import osint.service"`` is the supported entry).

``osint.kali_tools`` adds optional ``dig`` / ``whois`` facts when those binaries exist
on PATH (common on Kali/Linux dev machines); enable via ``ABBIEY_OSINT_MODULES``.
"""
