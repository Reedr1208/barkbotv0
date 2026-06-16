"""Legacy entrypoint — delegates to jobs.shelters.hssa.profiles."""
from jobs.shelters.hssa.profiles import main

if __name__ == "__main__":
    raise SystemExit(main())
