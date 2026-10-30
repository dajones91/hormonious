"""Entry point for running Hormonious online (PythonAnywhere).

PythonAnywhere's own WSGI file adds this folder to the path and does:

    from wsgi import application

`production=True` refuses to start without a real SECRET_KEY and FAMILY_PASSWORD in .env,
turns the login on, and only sends the login cookie over https.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_app  # noqa: E402  (needs the path above)

application = create_app(production=True)
