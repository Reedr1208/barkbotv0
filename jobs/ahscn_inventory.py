"""Legacy entrypoint — delegates to jobs.shelters.ahscn.inventory."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobs.shelters.ahscn.inventory import main

if __name__ == "__main__":
    main()
