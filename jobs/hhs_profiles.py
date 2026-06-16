"""Legacy entrypoint — delegates to jobs.shelters.hhs.profiles."""
import logging
import sys

from jobs.shelters.hhs.profiles import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    raise SystemExit(main())
