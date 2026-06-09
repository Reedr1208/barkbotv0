import os
import sys
from pathlib import Path
import subprocess

env_local = Path('.env.development.local')
if env_local.exists():
    with open(env_local) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k] = v.strip().strip('"').strip("'")

target_script = Path('jobs/wwla_all.py').resolve()
subprocess.run([sys.executable, str(target_script)], env=os.environ.copy())
