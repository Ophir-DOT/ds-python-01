"""`python -m ds_tool.gui` entry point.

Uses an absolute import so the same module works as the PyInstaller entry
script, where it runs as top-level `__main__` with no package context.
"""

import sys

from ds_tool.gui.app import main

sys.exit(main())
