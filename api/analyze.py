"""Vercel Function entrypoint for the Praline web interface."""

from praline.web import PralineWebHandler


class handler(PralineWebHandler):
    """Serve the landing page, analyzer, assets, and analysis API."""
