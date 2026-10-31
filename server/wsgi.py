"""Production WSGI entry point with fail-fast database initialization."""

from . import db
from .app import app  # noqa: F401 - exported for Gunicorn


db.init_db()
