"""Legacy entrypoint — delegates to jobs.shelters.hssa.inventory."""
from jobs.shelters.hssa.inventory import scrape_inventory

def main():
    scrape_inventory()

if __name__ == "__main__":
    main()
