# Paste this into your PythonAnywhere WSGI configuration file
# (Web tab > "WSGI configuration file" link), replacing everything in it.
# Change YOURUSERNAME to your PythonAnywhere username.
import sys

path = "/home/YOURUSERNAME/discover-pakistan-tourism/backend"
if path not in sys.path:
    sys.path.insert(0, path)

from app import create_app  # noqa: E402

application = create_app()
