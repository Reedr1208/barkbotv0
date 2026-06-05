with open("jobs/07_scrape_nycacc_profiles.py", "r") as f:
    content = f.read()
import re
match = re.search(r"async def main_async.*", content, re.DOTALL)
if match:
    print(match.group(0))
