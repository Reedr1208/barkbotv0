from playwright.sync_api import sync_playwright

USER_AGENT = "Mozilla/5.0"

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        
        # Test ?speciesId=1
        page.goto("https://www.adoptapet.com/shelter/76010-humane-society-of-southern-arizona-tucson-arizona?speciesId=1#available-pets")
        page.wait_for_timeout(4000)
        
        cards = page.locator('a[data-testid="pet-card-link"][href*="/pet/"]')
        names = []
        for i in range(cards.count()):
            names.append(cards.nth(i).inner_text().split('\n')[0])
            
        print(f"?speciesId=1 NIMBUS present: {'NIMBUS' in names}")

        # Test ?petSpeciesId=1
        page.goto("https://www.adoptapet.com/shelter/76010-humane-society-of-southern-arizona-tucson-arizona?petSpeciesId=1#available-pets")
        page.wait_for_timeout(4000)
        
        cards = page.locator('a[data-testid="pet-card-link"][href*="/pet/"]')
        names = []
        for i in range(cards.count()):
            names.append(cards.nth(i).inner_text().split('\n')[0])
            
        print(f"?petSpeciesId=1 NIMBUS present: {'NIMBUS' in names}")

        browser.close()

if __name__ == "__main__":
    run()
