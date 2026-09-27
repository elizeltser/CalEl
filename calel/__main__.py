"""CLI entry point: ``python -m calel`` / ``calel``."""

import sys

from calel.cli.parser import main

if __name__ == "__main__":
    sys.exit(main())
