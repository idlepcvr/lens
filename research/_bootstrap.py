"""Make this directory's scripts behave as if they were still at the repo root.

They import `app`, and some open `lens.db` by its relative path. Both only work
from the repo root: `import app` needs it on `sys.path`, and `DB_PATH` is the
bare string "lens.db". These files used to live at the root and got both for
free — after the 2026-07-24 reorganisation they have to ask for them.

Import this FIRST, before anything from `app`, or the app import runs before
`sys.path` is fixed and still fails:

    import _bootstrap  # noqa: F401
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)
