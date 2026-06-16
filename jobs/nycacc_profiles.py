"""Legacy entrypoint — delegates to jobs.shelters.nycacc.profiles."""
import asyncio
from jobs.shelters.nycacc.profiles import main_async, build_arg_parser

def main():
    return asyncio.run(main_async(build_arg_parser().parse_args()))

if __name__ == "__main__":
    raise SystemExit(main())
