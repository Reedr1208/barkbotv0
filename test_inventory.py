import sys
import json
import logging
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)

def test_pawsch():
    print("Testing PAWSCH")
    from jobs import pawsch_inventory
    session = pawsch_inventory.make_session()
    html = pawsch_inventory.fetch(session, pawsch_inventory.START_URL)
    soup = BeautifulSoup(html, "html.parser")
    dogs = pawsch_inventory.parse_dogs(soup)
    print("PAWSCH Dog 0:", json.dumps(dogs[0], indent=2) if dogs else "No dogs")

def test_nycacc():
    print("Testing NYCACC")
    from jobs import nycacc_inventory
    payload = nycacc_inventory.fetch_animals()
    dogs = nycacc_inventory.parse_animals(payload)
    print("NYCACC Dog 0:", json.dumps(dogs[0], indent=2) if dogs else "No dogs")

if __name__ == "__main__":
    test_pawsch()
    test_nycacc()
