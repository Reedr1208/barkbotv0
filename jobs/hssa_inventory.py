"""Legacy entrypoint — delegates to jobs.shelters.hssa.inventory."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobs.shelters.hssa.inventory import scrape_inventory

def main():
    scrape_inventory()

if __name__ == "__main__":
    main()
