import os

import dotenv
import requests

# Load environment variables from .env file
dotenv.load_dotenv()

api_key = os.getenv("proxycurl")
headers = {"Authorization": "Bearer " + api_key}
api_endpoint = "https://nubela.co/proxycurl/api/v2/linkedin"


async def get_linkedin_profile(url: str):
    """
    Get LinkedIn profile data using Proxycurl API.
    """
    response = requests.get(api_endpoint, params={"url": url}, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": "Failed to fetch data from Proxycurl API"}
