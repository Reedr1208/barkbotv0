"""Legacy entrypoint — delegates to jobs.shelters.hhs.profiles."""
import sys
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobs.shelters.hhs.profiles import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    raise SystemExit(main())
