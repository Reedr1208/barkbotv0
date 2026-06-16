"""Legacy entrypoint — delegates to jobs.shelters.nycacc.inventory."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from jobs.shelters.nycacc.inventory import main_async, build_arg_parser

def main():
    parsed_args = build_arg_parser().parse_args()
    return asyncio.run(main_async(parsed_args))

if __name__ == "__main__":
    raise SystemExit(main())
