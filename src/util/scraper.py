import asyncio
import random
from typing import Optional, TypedDict

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async


class CaptchaDetected(Exception):
    """Custom exception for captcha detection."""

    pass


class RateLimited(Exception):
    """Custom exception for rate limiting."""

    pass


class ProxyConfig(TypedDict, total=False):
    """Proxy configuration for the scraper."""

    server: str
    username: Optional[str]
    password: Optional[str]


class Scraper:
    def __init__(self):
        raise NotImplementedError("Use Scraper.create() to initialize the class.")

    @classmethod
    async def create(cls, proxy: Optional[ProxyConfig] = None) -> "Scraper":
        """
        Asynchronous factory method to create and initialize the scraper.
        :param proxy: Proxy to use for this scraper (optional)
        :return: Fully initialized Scraper instance
        """
        # Create an instance of the class
        instance = object.__new__(cls)  # Bypass __init__

        # Different user agents for different browsers
        user_agents = {
            "chromium": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            ],
            "firefox": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; rv:89.0) Gecko/20100101 Firefox/89.0",
            ],
        }

        # Randomly select a browser type
        browser_type = random.choice(list(user_agents.keys()))

        # Randomly select a user agent for the chosen browser
        user_agent = random.choice(user_agents[browser_type])

        # Start Playwright and initialize the browser and context
        instance.playwright = await async_playwright().start()
        browser_launcher = getattr(instance.playwright, browser_type)
        instance.browser = await browser_launcher.launch(headless=False)

        instance.context = None
        # Create a new browser context with the selected user agent
        # and proxy settings if provided
        if proxy:
            instance.context = await instance.browser.new_context(
                proxy=proxy,
                user_agent=user_agent,
                java_script_enabled=True,
            )
        else:
            instance.context = await instance.browser.new_context(
                user_agent=user_agent,
                java_script_enabled=True,
            )

        # Give the context ninja-like stealth capabilities
        await stealth_async(instance.context)

        return instance

    async def quick_scrape(self, url: str) -> str:
        """
        Quick scrape method to navigate to a URL and return the page content.
        :param url: URL to scrape
        :return: Page content
        :raises RateLimited: If the server responds with a 429 status code.
        :raises CaptchaDetected: If a captcha page is detected.
        :raises Exception: For other unexpected errors.
        """
        page = await self.context.new_page()
        try:
            response = await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(4)
            # Check for rate limiting
            if response.status == 429:
                await page.close()
                raise RateLimited("Rate limit exceeded. (HTTP 429)")

            # Check for common captcha elements
            if await page.locator("text=I'm not a robot").is_visible():
                raise CaptchaDetected("Captcha detected on the page.")

            if await page.locator("text=Access Denied").is_visible():
                raise CaptchaDetected("Captcha detected on the page.")

            if await page.locator("text=Verify you are human").is_visible():
                raise CaptchaDetected("Captcha detected on the page.")

            # Check for captcha detection
            content = await page.content()
            return content

        except (RateLimited, CaptchaDetected):
            # Re-raise specific exceptions to be handled by the caller
            raise
        except Exception as e:
            # Handle unexpected errors
            print(f"Unexpected error occurred: {e}")
            raise Exception(f"An unexpected error occurred while scraping: {e}")
        finally:
            # Ensure the page is always closed
            await page.close()

    async def slow_scrape(self, url: str) -> str:
        """
        Slow scrape method to navigate to a URL with random delays/scrolls and return the page content.
        :param url: URL to scrape
        :return: Page content
        :raises RateLimited: If the server responds with a 429 status code.
        :raises CaptchaDetected: If a captcha page is detected.
        :raises Exception: For other unexpected errors.
        """
        page = await self.context.new_page()

        try:
            response = await page.goto(url, wait_until="networkidle")
            await page.wait_for_selector("body")
            await asyncio.sleep(4)
            # Check for rate limiting
            if response.status == 429:
                raise RateLimited("Rate limit exceeded. (HTTP 429)")

            # Check for common captcha elements
            if await page.locator("text=I'm not a robot").is_visible():
                raise CaptchaDetected("Captcha detected on the page.")

            # Perform random scrolling
            for _ in range(random.randint(3, 6)):  # Random number of scrolls
                scroll_distance = random.randint(100, 500)  # Random scroll distance
                await page.mouse.wheel(0, scroll_distance)
                await asyncio.sleep(
                    random.uniform(0.5, 1.5)
                )  # Random delay between scrolls

            # Check for captcha detection
            content = await page.content()
            return content

        except (RateLimited, CaptchaDetected):
            # Re-raise specific exceptions to be handled by the caller
            raise
        except Exception as e:
            # Handle unexpected errors
            print(f"Unexpected error occurred: {e}")
            raise Exception(f"An unexpected error occurred while scraping: {e}")
        finally:
            # Ensure the page is always closed
            await page.close()

    async def close(self):
        """
        Close the browser and Playwright instance.
        """
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()
