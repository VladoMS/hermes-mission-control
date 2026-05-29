#!/usr/bin/env python3
"""Mission Control — compatibility shim. Delegates to server.main."""
import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.main import main

if __name__ == "__main__":
    main()
