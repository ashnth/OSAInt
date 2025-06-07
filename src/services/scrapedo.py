import os
import random
import urllib.parse

import dotenv
import requests

dotenv.load_dotenv()


def get_random_scrapedo_key():
    """
    Randomly get one of 5 Scrape.do keys from the environment variables.
    """
    key = random.choice([1])
    return os.getenv(f"scrapedo_{key}")


async def scrape_do(url: str):
    """
    Scrape a URL using the Scrape.do API.
    """
    token = get_random_scrapedo_key()

    encoded_url = urllib.parse.quote(url)

    # Normal Mode first
    url = "http://api.scrape.do/?token={}&url={}&output=markdown".format(
        token, encoded_url
    )
    response = requests.request("GET", url)

    # If that doesn't work and you get 400, try with super
    if response.status_code == 400:
        url = "http://api.scrape.do/?token={}&url={}&super=true&output=markdown".format(
            token, encoded_url
        )
        response = requests.request("GET", url)
    return response.text


async def scrape_do_no_md(url: str):
    """
    Scrape a URL using the Scrape.do API.
    """
    token = get_random_scrapedo_key()

    encoded_url = urllib.parse.quote(url)

    # Normal Mode first
    url = "http://api.scrape.do/?token={}&url={}".format(token, encoded_url)
    response = requests.request("GET", url)

    # If that doesn't work and you get 400, try with super
    if response.status_code == 400:
        url = "http://api.scrape.do/?token={}&url={}&super=true".format(
            token, encoded_url
        )
        response = requests.request("GET", url)
    return response.text
