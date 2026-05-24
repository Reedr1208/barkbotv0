import os

env_file = "/Users/chayev/repos/Reedr1208/barkbotv0/.env.local"
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                # Determine value length or simple signature
                val_len = len(val.strip())
                print(f"Key: {key} (length: {val_len})")
else:
    print(".env.local not found")
