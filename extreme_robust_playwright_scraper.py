import asyncio
import re
import random
import time
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
import aiohttp
import logging

# ========== CONFIGURATION ==========

DISCORD_WEBHOOK_URL = "https://discordapp.com/api/webhooks/1404164923780628561/UwfDFCiS54yUzOP1rhiLvtp04Yh9-ImRQW-7MgNEvsbTnUk4YLRmokWYJm4c4dJOXGyO"
START_URL = "https://www.government.se/contact-information/"
MAX_DEPTH = 3  # crawl depth (0 = only start page)
MAX_PAGES = 200  # max total pages to crawl
CONCURRENT_PAGES = 3  # concurrency of browser pages
REQUEST_DELAY = (1.5, 3.5)  # random delay range between requests (seconds)
PROXIES = []  # list of proxies (http://user:pass@ip:port), leave empty for none
USER_AGENTS = [
    # Realistic user agent strings to rotate
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0"
]
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
SAVE_CHECKPOINT_EVERY = 30  # pages
CHECKPOINT_FILE = "scraper_checkpoint.json"
OUTPUT_EMAILS_FILE = "emails_found.json"
LOG_FILE = "scraper.log"
OBFUSCATE_KEYS = ['_a1b2', '_z9x8', '_r7s6']  # keys for very simple obfuscation

# ========== LOGGER SETUP ==========

logging.basicConfig(
    filename=LOG_FILE,
    filemode='a',
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    level=logging.DEBUG
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

# ========== HELPER FUNCTIONS ==========

def iso_utc_now():
    return datetime.now(timezone.utc).isoformat()

def obfuscate_string(s):
    # Very basic obfuscation by interleaving chars with random letters
    import string
    obfuscated = ''.join(c + random.choice(string.ascii_letters) for c in s)
    return obfuscated

def deobfuscate_string(s):
    # Reverse of above: take every second char
    return s[::2]

def normalize_url(base, link):
    # Normalize relative or absolute URLs
    if not link:
        return None
    if link.startswith('mailto:'):
        return None
    if link.startswith('#'):
        return None
    try:
        return urljoin(base, link)
    except Exception:
        return None

def is_same_domain(url1, url2):
    try:
        d1 = urlparse(url1).netloc.lower()
        d2 = urlparse(url2).netloc.lower()
        return d1 == d2
    except Exception:
        return False

async def send_to_discord(webhook_url, content):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json={"content": content}) as resp:
                if resp.status != 204:
                    logging.warning(f"Discord webhook failed with status {resp.status}")
    except Exception as e:
        logging.error(f"Exception sending to Discord: {e}")

def save_checkpoint(data):
    try:
        with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        logging.info(f"Checkpoint saved to {CHECKPOINT_FILE}")
    except Exception as e:
        logging.error(f"Failed to save checkpoint: {e}")

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logging.info(f"Checkpoint loaded from {CHECKPOINT_FILE}")
            return data
        except Exception as e:
            logging.error(f"Failed to load checkpoint: {e}")
    return None

def save_emails_to_file(emails):
    try:
        with open(OUTPUT_EMAILS_FILE, 'w', encoding='utf-8') as f:
            json.dump(sorted(list(emails)), f, indent=2)
        logging.info(f"Emails saved to {OUTPUT_EMAILS_FILE}")
    except Exception as e:
        logging.error(f"Failed to save emails: {e}")

# ========== SCRAPER CLASS ==========

class AdvancedScraper:

    def __init__(self, start_url, max_depth, max_pages, concurrency, proxies):
        self.start_url = start_url
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.concurrency = concurrency
        self.proxies = proxies or []
        self.emails = set()
        self.visited = set()
        self.to_visit = []
        self.total_pages = 0
        self.start_time = None
        self.end_time = None
        self.base_domain = urlparse(start_url).netloc.lower()
        self._lock = asyncio.Lock()
        self._checkpoint_counter = 0
        self._stop_requested = False

    async def _setup_browser(self):
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        return playwright, browser

    async def _close_browser(self, playwright, browser):
        try:
            await browser.close()
        except Exception:
            pass
        try:
            await playwright.stop()
        except Exception:
            pass

    async def _random_delay(self):
        delay = random.uniform(*REQUEST_DELAY)
        logging.debug(f"Delaying for {delay:.2f} seconds")
        await asyncio.sleep(delay)

    async def _fetch_page(self, browser, url, proxy=None):
        user_agent = random.choice(USER_AGENTS)
        context_args = {
            "user_agent": user_agent,
            "viewport": {
                "width": random.randint(1200, 1920),
                "height": random.randint(700, 1080)
            },
            "java_script_enabled": True,
            "locale": "en-US",
        }
        if proxy:
            context_args["proxy"] = {"server": proxy}

        context = await browser.new_context(**context_args)
        page = await context.new_page()

        # Anti-headless detection workaround:
        # - Override navigator.webdriver
        await page.add_init_script(
            """() => {
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.navigator.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            }"""
        )

        try:
            logging.info(f"[INFO] Loading page: {url} with UA: {user_agent}")
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(random.uniform(1.5, 3.5))  # post-load wait

            # Detect and handle possible JS captcha or challenge - just wait longer if suspected
            content = await page.content()
            if "captcha" in content.lower() or "challenge" in content.lower():
                logging.warning(f"[WARN] Captcha or challenge detected on {url}. Waiting extra 10s...")
                await asyncio.sleep(10)

            # Extract emails strictly from mailto links and those in title attrs
            mailto_hrefs = await page.eval_on_selector_all(
                "a[href^='mailto:']",
                "elements => elements.map(el => ({ href: el.getAttribute('href'), title: el.getAttribute('title'), text: el.textContent }))"
            )

            emails_found = set()
            for link in mailto_hrefs:
                href = link.get('href') or ''
                title = link.get('title') or ''
                text = link.get('text') or ''

                # Extract email from mailto:
                m = re.match(r'mailto:([^?]+)', href)
                if m:
                    email = m.group(1).strip()
                    if EMAIL_REGEX.fullmatch(email):
                        emails_found.add(email.lower())
                # Sometimes email might be in title attribute or text
                for s in (title, text):
                    if s and EMAIL_REGEX.search(s):
                        for em in EMAIL_REGEX.findall(s):
                            emails_found.add(em.lower())

            # Additionally extract any emails visible in page text (backup)
            all_text = await page.evaluate("() => document.body.innerText")
            if all_text:
                for em in EMAIL_REGEX.findall(all_text):
                    emails_found.add(em.lower())

            # Extract all same domain href links for crawling deeper
            anchors = await page.eval_on_selector_all("a[href]", "elements => elements.map(e => e.href)")
            new_links = []
            for href in anchors:
                href_norm = normalize_url(url, href)
                if href_norm and is_same_domain(self.start_url, href_norm):
                    new_links.append(href_norm)

            await context.close()
            return emails_found, new_links

        except PlaywrightTimeoutError:
            logging.error(f"[ERROR] Timeout loading page: {url}")
        except PlaywrightError as pe:
            logging.error(f"[ERROR] Playwright error on page {url}: {pe}")
        except Exception as e:
            logging.error(f"[ERROR] Exception on page {url}: {e}")

        await context.close()
        return set(), []

    async def _worker(self, browser):
        while True:
            if self._stop_requested:
                logging.info("[INFO] Stop requested, exiting worker")
                break
            async with self._lock:
                if not self.to_visit or self.total_pages >= self.max_pages:
                    break
                url, depth = self.to_visit.pop(0)
                if url in self.visited or depth > self.max_depth:
                    continue
                self.visited.add(url)
                self.total_pages += 1

            logging.info(f"[SCRAPE] Visiting {url} at depth {depth} (Page {self.total_pages}/{self.max_pages})")

            proxy = random.choice(self.proxies) if self.proxies else None
            emails_found, new_links = await self._fetch_page(browser, url, proxy)

            async with self._lock:
                self.emails.update(emails_found)
                # Queue new links
                for nl in new_links:
                    if nl not in self.visited and nl not in [u for u, _ in self.to_visit]:
                        self.to_visit.append((nl, depth + 1))

                self._checkpoint_counter += 1
                if self._checkpoint_counter >= SAVE_CHECKPOINT_EVERY:
                    self._checkpoint_counter = 0
                    self._save_checkpoint()

            await self._random_delay()

    def _save_checkpoint(self):
        data = {
            'visited': list(self.visited),
            'to_visit': self.to_visit,
            'emails': list(self.emails),
            'total_pages': self.total_pages,
            'start_time': self.start_time,
        }
        save_checkpoint(data)

    def _load_checkpoint(self):
        data = load_checkpoint()
        if data:
            self.visited = set(data.get('visited', []))
            self.to_visit = data.get('to_visit', [])
            self.emails = set(data.get('emails', []))
            self.total_pages = data.get('total_pages', 0)
            self.start_time = data.get('start_time', None)
            logging.info(f"[INFO] Resuming from checkpoint. Visited: {len(self.visited)}, Queue: {len(self.to_visit)}, Emails: {len(self.emails)}, Pages: {self.total_pages}")
            return True
        return False

    async def run(self):
        self.start_time = iso_utc_now()

        # Load checkpoint if available, else start fresh
        if not self._load_checkpoint():
            self.to_visit = [(self.start_url, 0)]

        playwright, browser = await self._setup_browser()

        try:
            workers = [asyncio.create_task(self._worker(browser)) for _ in range(self.concurrency)]
            await asyncio.gather(*workers)
        except Exception as e:
            logging.error(f"[ERROR] Unexpected error during scraping: {e}")
        finally:
            await self._close_browser(playwright, browser)

        self.end_time = iso_utc_now()
        duration = (datetime.fromisoformat(self.end_time) - datetime.fromisoformat(self.start_time)).total_seconds()
        logging.info(f"[INFO] Scraping finished. Duration: {duration:.2f} seconds. Pages scraped: {self.total_pages}. Emails found: {len(self.emails)}")

        # Save final checkpoint & emails
        self._save_checkpoint()
        save_emails_to_file(self.emails)

        # Send summary and emails to Discord in chunks
        await self._send_results_to_discord(duration)

    async def _send_results_to_discord(self, duration):
        summary = (
            f"**Scraping Summary**\n"
            f"Start URL: {self.start_url}\n"
            f"Pages Scraped: {self.total_pages}\n"
            f"Emails Found: {len(self.emails)}\n"
            f"Start Time (UTC): {self.start_time}\n"
            f"End Time (UTC): {self.end_time}\n"
            f"Duration (seconds): {duration:.2f}\n"
        )
        await send_to_discord(DISCORD_WEBHOOK_URL, summary)

        if not self.emails:
            await send_to_discord(DISCORD_WEBHOOK_URL, "No emails found.")
            return

        # Send emails in chunks to avoid Discord message limits
        emails_sorted = sorted(self.emails)
        chunk_size = 1900
        chunk = ""
        for email in emails_sorted:
            if len(chunk) + len(email) + 2 > chunk_size:
                await send_to_discord(DISCORD_WEBHOOK_URL, f"```\n{chunk}```")
                chunk = ""
            chunk += email + "\n"
        if chunk:
            await send_to_discord(DISCORD_WEBHOOK_URL, f"```\n{chunk}```")

    def request_stop(self):
        self._stop_requested = True

# ========== MAIN RUN ==========

async def main():
    scraper = AdvancedScraper(
        start_url=START_URL,
        max_depth=MAX_DEPTH,
        max_pages=MAX_PAGES,
        concurrency=CONCURRENT_PAGES,
        proxies=PROXIES
    )
    await scraper.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("KeyboardInterrupt caught, exiting gracefully.")
