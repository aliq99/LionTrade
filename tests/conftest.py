import os
import sys

# Add the project's root directory (the parent of 'tests') to the Python path
# This allows tests to import modules from trading/, strategies/, etc.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
