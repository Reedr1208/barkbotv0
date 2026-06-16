"""Legacy entrypoint — delegates to jobs.shelters.pawsch.profiles."""
from jobs.shelters.pawsch.profiles import main

if __name__ == "__main__":
    raise SystemExit(main())
