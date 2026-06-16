"""Legacy entrypoint — delegates to jobs.shelters.pacc.profiles."""
from jobs.shelters.pacc.profiles import main

if __name__ == "__main__":
    raise SystemExit(main())
