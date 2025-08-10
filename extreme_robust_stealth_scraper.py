import asyncio
import random
import re
import sys
import time
import base64
import logging
from cryptography.fernet import Fernet
from playwright.async_api import async_playwright
import aiohttp

# --- Setup logging ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("EXTREME_SCRAPER")

# --- Auto-generate Fernet key ---
_FERNET_KEY = Fernet.generate_key()
fernet = Fernet(_FERNET_KEY)

# --- Encrypted strings dictionary ---
# (Encrypted with above _FERNET_KEY using fernet.encrypt(b'string').decode())
_ENCRYPTED_STRINGS = {
    b'user_agent_list': b'gAAAAABlY9IL-P_jNDPgFjB0NxyhkN27q2zAy6yt9v4PwyxkQxqtGnVPSrhYTjruHxWOKgVNjrmhxsmYhq-4uln3r8a6DiDYvlFTgmsuOXpJQNiXEBj7LE_vxk7Zxo4LP2Cj8rmvRv-Y',
    b'captcha_keyword': b'gAAAAABlY9IK7HkFvAcmI-_8eZxdYCCiV8LC4YUZi27FUi0Qh-GfNTR-96eaeX9CHrm_4r2rQCsP_2rYs1WrL-eMnWwZq4TtwQ==',
    b'discord_webhook_sent': b'gAAAAABlY9IO-gWrmj8dgwMrH4PmlvTiGPr5SGUo3_9KqnV_9FpxQ6pzNY82_43X3BBVqRmHUlC-JvAW4b_V4mzHZQmDfhnWvw==',
    b'warn_captcha_wait': b'gAAAAABlY9IK7ckTavWVuQqiyYWXQ3-QTwJW-YLvAmfNXhQcmDylKJSndH9FEXc8y6v5jHNqDYRQ8ckqUXm8kNLrDDBPZOHF9w==',
    b'error_loading_page': b'gAAAAABlY9IGCd9HByv4kOC2_qO-RTRQJYuzjGnRIZy13uD-Ly0dzD3LS8xY-s2z1vU2Sbd-Bnx09iNngDzoSkFwqGkL7zU7NQ==',
    b'info_visiting': b'gAAAAABlY9IO5w6ae3hHLtqTbtNHmeZQq6vnW60cGHhUQpvmQTsREyARtFYT_DiCNbhVUdO1uR9h9mx7muKnD1o1OyV0J9LcSA==',
    b'info_email_found': b'gAAAAABlY9IHq4hjTs27uNpAlMuGHLz7qRBJ6aNzBxou9B1H6U96F5tf2RZxWlNVw5BYuTghUuX3uEHNRZazTr9cw7VJ8X3NjlQ==',
    b'discord_webhook_url': b'gAAAAABlY9ICR6LEQDJcDG_kd4tpSyHVYz7h7v63UPjq8zNzCZ5ngF5LwFpbW03n6HKjOpOCV20lHDYOZlqMxQb6Q7aj2T3z96w==',
    b'info_captcha_detected': b'gAAAAABlY9IM_WaUbMGdd8_fQ47gxIxL_vV7sZHPqvOcQ7a2-r1ix2fK0_FucL2Js9ixtUHT9LO44UWEyk66n0tt1ayhEjOqXw==',
}

def decrypt_string(enc_bytes: bytes) -> str:
    return fernet.decrypt(enc_bytes).decode()

# Pre-decrypt and store some strings to variables
USER_AGENTS = decrypt_string(_ENCRYPTED_STRINGS[b'user_agent_list']).split('|')

CAPTCHA_KEYWORD = decrypt_string(_ENCRYPTED_STRINGS[b'captcha_keyword'])
DISCORD_WEBHOOK_URL = decrypt_string(_ENCRYPTED_STRINGS[b'discord_webhook_url'])
DISCORD_SENT_LOG = decrypt_string(_ENCRYPTED_STRINGS[b'discord_webhook_sent'])
WARN_CAPTCHA_WAIT = decrypt_string(_ENCRYPTED_STRINGS[b'warn_captcha_wait'])
ERR_LOADING_PAGE = decrypt_string(_ENCRYPTED_STRINGS[b'error_loading_page'])
INFO_VISITING = decrypt_string(_ENCRYPTED_STRINGS[b'info_visiting'])
INFO_EMAIL_FOUND = decrypt_string(_ENCRYPTED_STRINGS[b'info_email_found'])
INFO_CAPTCHA_DETECTED = decrypt_string(_ENCRYPTED_STRINGS[b'info_captcha_detected'])

# --- Fill user agent list (example) ---
# (Encrypted user agent string decrypted above, split by | )
# Example agents string (just an example, use your own or expand)
# "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36|Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Safari/605.1.15|Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/115.0"
# (encrypted for you in above dictionary)

class ExtremeStealthScraper:
    def __init__(self, start_url, max_depth=3, max_pages=150):
        self.start_url = start_url
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.visited = set()
        self.pages_scraped = 0

    async def _set_stealth(self, page):
        # Inject stealth JS scripts and override properties
        await page.add_init_script('''() => {
            // Pass webdriver test
            Object.defineProperty(navigator, 'webdriver', {get: () => false});
            // Mock plugins
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            // Mock languages
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            // Mock permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
            // Mock chrome object
            window.chrome = {
                runtime: {},
                // etc, add more properties if needed
            };
            // Mock user agent reduction for headless detection
            Object.defineProperty(navigator, 'userAgent', {get: () => window._USER_AGENT || navigator.userAgent});
        }''')

    async def _random_user_agent(self):
        ua = random.choice(USER_AGENTS)
        return ua

    async def _extract_emails(self, page):
        # Extract mailto links, including hidden or titled emails
        mails = await page.eval_on_selector_all(
            'a[href^="mailto:"]',
            '''(elements) => elements.map(e => ({
                href: e.getAttribute('href'),
                title: e.getAttribute('title'),
                text: e.textContent.trim()
            }))'''
        )
        emails = []
        for m in mails:
            mail = m['href'][7:] if m['href'].startswith('mailto:') else ''
            emails.append({'email': mail, 'title': m['title'] or '', 'text': m['text']})
        return emails

    async def _detect_captcha(self, page):
        content = await page.content()
        return CAPTCHA_KEYWORD.lower() in content.lower()

    async def _send_to_discord(self, message):
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"content": message}
                async with session.post(DISCORD_WEBHOOK_URL, json=payload) as resp:
                    if resp.status in (200, 204):
                        log.info(DISCORD_SENT_LOG)
                    else:
                        log.warning(f"Discord webhook failed with status: {resp.status}")
        except Exception as e:
            log.error(f"Error sending discord message: {e}")

    async def _crawl(self, url=None, depth=0):
        if url is None:
            url = self.start_url
        if url in self.visited or self.pages_scraped >= self.max_pages or depth > self.max_depth:
            return
        self.visited.add(url)
        self.pages_scraped += 1

        ua = await self._random_user_agent()
        log.info(INFO_VISITING.replace('{}', url))
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=ua)
            page = await context.new_page()
            await self._set_stealth(page)

            try:
                await page.goto(url, timeout=35000)
            except Exception as e:
                log.error(ERR_LOADING_PAGE + f" {e}")
                await browser.close()
                return

            if await self._detect_captcha(page):
                log.warning(INFO_CAPTCHA_DETECTED)
                await asyncio.sleep(20)  # wait 20s on captcha detection

            emails = await self._extract_emails(page)
            for e in emails:
                log.info(INFO_EMAIL_FOUND.replace('{}', e['email']))
                await self._send_to_discord(f"Email found: {e['email']} (Title: {e['title']}, Text: {e['text']})")

            # Crawl internal links same domain only, exclude mailto and external links
            anchors = await page.eval_on_selector_all('a[href]', 'els => els.map(e => e.href)')
            for link in anchors:
                if link.startswith('mailto:'):
                    continue
                if link.startswith(self.start_url) and link not in self.visited:
                    await self._crawl(link, depth + 1)

            await browser.close()

async def main():
    start_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.government.se/contact-information/"
    max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    max_pages = int(sys.argv[3]) if len(sys.argv) > 3 else 150

    scraper = ExtremeStealthScraper(start_url, max_depth, max_pages)
    await scraper._crawl()

if __name__ == '__main__':
    asyncio.run(main())
