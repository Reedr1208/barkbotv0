import requests
from bs4 import BeautifulSoup

for param in ["?speciesId=1", "?petSpeciesId=1", "?species=dog"]:
    url = f"https://www.adoptapet.com/shelter/76010-humane-society-of-southern-arizona-tucson-arizona{param}#available-pets"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")
    cards = soup.select('a[data-testid="pet-card-link"][href*="/pet/"]')
    
    names = []
    for c in cards:
        name_el = c.select_one(".name")
        names.append(name_el.get_text(" ", strip=True) if name_el else "")
    
    print(f"{param}: {'NIMBUS' in names} (NIMBUS is a cat)")
