import asyncio as A0
import re as A1
import json as A2
import random as A3
import logging as A4
from datetime import datetime as A5, timezone as A6
from urllib.parse import urlparse as A7
import httpx as A8
from playwright.async_api import async_playwright as A9
from cryptography.fernet import Fernet as A10

# --- ENCRYPTED STRINGS & KEY ---
# Key to decrypt strings at runtime, change to re-encrypt
_K = b'Ms3vWcDgqQtHZG8D2RyS6Gv9y3MW6AY--2u4-i0Cp6M='

def _D(x):  # Decrypt string
    return A10(_K).decrypt(x).decode()

# Encrypted literals:
_E = {
    'navigator': b'gAAAAABlYOKDPjzMq70RWjwQNy3aGCrkKRaGvyy-iZmIZXoSNJSc_m6Nfh_cH1uTwXf2uJ1kZH5Lcd10X9ziVlVUqEGO6o9F7Q==',
    'webdriver': b'gAAAAABlYOKDZdWqbFTEYGQR7jFVKjzR5r1Mr4gFGcT_Nxqu7jxV0kH_TGAsJoK7mN6uSQ1-e33UMbb9w8tczRSsz63T8Xt7Dw==',
    'plugins': b'gAAAAABlYOKDLi9f_06uXILsqrUXYqGKGn4tSRrYPxPcF7k4gtQk5k2mn1vhq6V-i1x6r-Vny4gZrfm2GyU84By3hCnAZMroQA==',
    'languages': b'gAAAAABlYOKD0xTWkJpWyswnXmIQMKK42DRjlU4uh9JXj-dvlJ8PpTg-cyxOXORLuHyZ1hM9l0ZcrzUO0ZDR8VWVLzNkcnfLvg==',
    'captcha': b'gAAAAABlYOKDQ3kM_xazk4bhjp_R1MwovC_5NckP9Rpb0CgxQDwN1wMMbYyqJb1wwbBBEPFkX_5vM6jGPrDp2fZz0Dw0LV2pm_w==',
    'mailto': b'gAAAAABlYOKDaVf0F7LsP60c1f7aJvTvdg5fNmw8swvy3CGOPsN1YucTyzc1d97MvIzHegw-5YFqlxaO_Zx08Y1IrQ5GqvWNs0w==',
    'discord_webhook_sent': b'gAAAAABlYOKDKRriYB-tDFYtOm6l3JoWdqcgxZps0_q4W42F8qqlcJGLc9rgrcS5vlD4fB4p4D2cH9qxiZcsALXOqd3ijhDrrA==',
    'warn_captcha_wait': b'gAAAAABlYOKDW2OxqNnyc31gY4RugUBouoTYUJQk3xj15VNLrVnV3CYJUcXz4mU0rmA53egOSRQIeHw_YKymVJly_iFz3YJhJg==',
    'error_exception': b'gAAAAABlYOKDDTKSpc8IvlNVF67ur0bjzljCgti6uOHVPZK-QkDOD5xkpNNRzudVxA4Rkc7vgG8sX0XrfyEy9VQ6dFEbfMTgu-w==',
    'info_scrape_visiting': b'gAAAAABlYOKD_l-EytwhtZxRRMZFaHbZDX4qKqGTloIm1CZk7evCmOKGvf_qTpzYRDpxRlSlavpQbZDjSejWM3Zq3DcXbYZmww==',
    'info_scrape_captcha': b'gAAAAABlYOKDcnE94bh8zXGr2KZmfkj5HwOBBpBjFlICr3TpL4vwhRYhzH5tYW91MZYb_T05H8b4ihHd4_MpWKGzYO5_z0P8bJQ==',
    'info_scrape_captcha_wait': b'gAAAAABlYOKDwrwJnFidUxVh-xoiSSh25H11sFmnvOHFXo7JbLWW9c2NBY2v32v6NoDglq1xmNMmuTFjNdP89GkSx2D5ppqOH5Q==',
    'info_scrape_loaded': b'gAAAAABlYOKDcOb6p-A1W1wWPT87YjJHPqavkq28EtNpxPocXHx5qxqkXE-HC-_2Sbh06npBk9Tvk1RGXOKa72t_6iH0WzA2h9A==',
    'content_captcha': b'gAAAAABlYOKDBE9pDdThnGJJKAmF_Q-GI2xb3pyoeM8wiSrS4chxsyYv1dxJ8H7XspDyyGnH9N5uTG9DYTNX9Jc3wu2iChDOaHw==',
}

def _S(key):  # String decrypt helper
    return _D(_E[key])

# Logging setup
A4.basicConfig(
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    level=A4.INFO,
    datefmt='%Y-%m-%dT%H:%M:%S%z'
)

# Regexes
_R_EMAIL = A1.compile(r'([a-zA-Z0-9._%+-]+@(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,})', A1.I)
_R_MAILTO = A1.compile(r'^mailto:(.+)$', A1.I)

# User agents (obfuscated list)
_UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 13; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
]

class _X:
    def __init__(self, s, d=2, m=100, w=None, p=None):
        self.s = s
        self.d = d
        self.m = m
        self.w = w
        self.p = p
        self.v = set()
        self.e = set()
        self.cnt = 0
        self.st = A5.now(A6.utc)

    async def _L(self, p, u, depth):
        A4.info(_S('info_scrape_visiting').replace('{}', u))
        await A0.sleep(A3.uniform(1.5, 3.5))
        await self._stealth(p)
        ua = A3.choice(_UA)
        await p.set_user_agent(ua)
        try:
            r = await p.goto(u, timeout=60000)
            r = await r
            if r is None:
                A4.warning(f"[WARN] No response from {u}")
                return set()
            if r.status >= 400:
                A4.warning(f"[WARN] HTTP {r.status} at {u}")
                return set()
            c = await p.content()
            if _S('captcha') in c.lower():
                A4.warning(_S('warn_captcha_wait'))
                await A0.sleep(15)
            await self._human(p)
            c = await p.content()
            emails = self._extract(c)
            links = await p.query_selector_all('a[href^="mailto:"]')
            for l in links:
                href = await l.get_attribute('href')
                if href:
                    mail = href.split(':', 1)[1].split('?')[0]
                    emails.add(mail)
            self.cnt += 1
            self.v.add(u)
            self.e.update(emails)
            base = A7(self.s).netloc
            newu = set()
            anchors = await p.query_selector_all('a[href]')
            for a in anchors:
                href = await a.get_attribute('href')
                if not href:
                    continue
                parsed = A7(href)
                if parsed.scheme in ['http', 'https']:
                    if parsed.netloc == base and href not in self.v:
                        newu.add(href)
                elif href.startswith('/'):
                    nu = f"{A7(u).scheme}://{base}{href}"
                    if nu not in self.v:
                        newu.add(nu)
            return newu
        except Exception as ex:
            A4.error(f"{_S('error_exception')}: {ex}")
            return set()

    async def _human(self, p):
        try:
            for _ in range(A3.randint(1, 3)):
                await p.mouse.wheel(0, A3.randint(100, 400))
                await A0.sleep(A3.uniform(0.2, 0.6))
            for _ in range(A3.randint(1, 3)):
                x = A3.randint(100, 1000)
                y = A3.randint(100, 600)
                await p.mouse.move(x, y, steps=A3.randint(5, 15))
                await A0.sleep(A3.uniform(0.2, 0.6))
        except Exception as ex:
            A4.debug(f"Human interaction error: {ex}")

    def _extract(self, text):
        m = set(_R_EMAIL.findall(text))
        for mt in _R_MAILTO.findall(text):
            m.add(mt.split('?')[0])
        return m

    async def _stealth(self, p):
        await p.add_init_script(f"""
        Object.defineProperty(navigator, 'webdriver', {{get: () => false}});
        Object.defineProperty(navigator, 'plugins', {{get: () => [1,2,3,4,5]}});
        Object.defineProperty(navigator, 'languages', {{get: () => ['en-US', 'en']}});
        """)

    async def _send_d(self):
        if not self.w:
            return
        S = {
            "total_urls_scraped": len(self.v),
            "total_emails_found": len(self.e),
            "start_time_utc": self.st.isoformat(),
            "end_time_utc": A5.now(A6.utc).isoformat(),
            "duration_seconds": (A5.now(A6.utc) - self.st).total_seconds(),
            "emails": list(self.e)[:50],
        }
        c = f"**Scraping Summary:**\n```json\n{A2.dumps(S, indent=2)}\n```"
        async with A8.AsyncClient() as cl:
            r = await cl.post(self.w, json={"content": c})
            if r.status_code == 204:
                A4.info(_S('discord_webhook_sent'))
            else:
                A4.warning(f"Webhook failed: {r.status_code} {r.text}")

    async def crawl(self):
        async with A9() as p:
            br = await p.chromium.launch(headless=True)
            ctx_arg = {}
            if self.p:
                ctx_arg["proxy"] = {"server": self.p}
            ctx = await br.new_context(**ctx_arg)
            pg = await ctx.new_page()
            todo = {self.s}
            cd = 0
            while todo and cd <= self.d and self.cnt < self.m:
                nxt = set()
                for u in todo:
                    if self.cnt >= self.m:
                        break
                    if u in self.v:
                        continue
                    nu = await self._L(pg, u, cd)
                    nxt.update(nu)
                todo = nxt
                cd += 1
            await br.close()
        await self._send_d()
        self._print_sum()

    def _print_sum(self):
        et = A5.now(A6.utc)
        dur = (et - self.st).total_seconds()
        print("\n=== Scraping summary ===")
        print(A2.dumps({
            "total_urls_scraped": len(self.v),
            "total_emails_found": len(self.e),
            "start_time_utc": self.st.isoformat(),
            "end_time_utc": et.isoformat(),
            "duration_seconds": dur
        }, indent=2))

def _M():
    import argparse as ag
    p = ag.ArgumentParser(description="Extreme Robust Playwright Scraper")
    p.add_argument("start_url", help="Starting URL to scrape")
    p.add_argument("-d", "--depth", type=int, default=2, help="Max crawl depth")
    p.add_argument("-m", "--maxpages", type=int, default=100, help="Max pages to scrape")
    p.add_argument("-w", "--webhook", type=str, default=None, help="Discord webhook URL")
    p.add_argument("-p", "--proxy", type=str, default=None, help="Proxy server (e.g. http://proxy:port)")
    a = p.parse_args()
    x = _X(a.start_url, a.depth, a.maxpages, a.webhook, a.proxy)
    A0.run(x.crawl())

if __name__ == "__main__":
    _M()
