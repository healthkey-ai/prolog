"""Development/test settings: the standalone settings with DEBUG on by default.

Used by pytest (see pyproject) and by `manage.py` when DEBUG is not set in
the environment, so local commands work without exporting anything. A
deployment sets DEBUG explicitly (the container image sets DEBUG=false) and
never imports this module.
"""

import os

os.environ.setdefault("DEBUG", "true")

from .settings import *  # noqa: E402, F403
