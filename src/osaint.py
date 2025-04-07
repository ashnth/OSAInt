import asyncio

import matplotlib.pyplot as plt
import networkx as nx
from bs4 import BeautifulSoup

from util.scraper import CaptchaDetected, RateLimited, Scraper


async def main(target: str):
    # Initialization step
    graph = nx.Graph()
    central_node = graph.add_node(target, type="person")

    # Scraper initialization
    scraper = await Scraper.create()

    # Scrape google for links then scrape each of those links
    # Do this for the first 3 pages (30 results)
    total_pages = 3
    results_per_page = 10

    for page in range(total_pages):
        start = (page * results_per_page) + 1
        try:
            google_query = target.replace(" ", "+")
            url = f'https://www.google.com/search?q="{google_query}"&start={start}'
            response = await scraper.slow_scrape(url)
            soup = BeautifulSoup(response, "lxml")
            # Extract links
            links = [
                result.select_one("a")["href"]
                for result in soup.select(".tF2Cxc")
                if result.select_one("a") and "href" in result.select_one("a").attrs
            ]

        # Handle later
        except RateLimited:
            print("Rate limit exceeded. Exiting.")
            break
        # Handle later
        except CaptchaDetected:
            print("Captcha detected. Exiting.")
            break


if __name__ == "__main__":
    target = input("Who is your target? ")
    asyncio.run(main(target))
