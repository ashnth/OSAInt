import os

import dotenv
import requests

dotenv.load_dotenv()


async def check_breaches(account):
    """
    Check if an account has been breached using the Have I Been Pwned API.
    """
    url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{account}"
    headers = {"hibp-api-key": os.getenv("haveibeenpwned")}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 404:
        return None
    else:
        raise Exception(f"Error checking breaches: {response.status_code}")
