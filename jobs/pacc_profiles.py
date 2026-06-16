"""Legacy entrypoint — delegates to jobs.shelters.pacc.profiles."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobs.shelters.pacc.profiles import main

if __name__ == "__main__":
    raise SystemExit(main())
