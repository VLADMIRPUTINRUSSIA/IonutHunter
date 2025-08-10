#!/usr/bin/env python3
import re
import sys
import time
import json
import argparse
import requests
import socket
import concurrent.futures
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from urllib.parse import urlparse, urljoin

# -------- Constants --------

# Discord webhook URL (your provided)
DISCORD_WEBHOOK_URL = "https://discordapp.com/api/webhooks/1404164923780628561/UwfDFCiS54yUzOP1rhiLvtp04Yh9-ImRQW-7MgNEvsbTnUk4YLRmokWYJm4c4dJOXGyO"

# Heavy rotation of User Agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:116.0) Gecko/20100101 Firefox/116.0",
    "Mozilla/5.0 (Linux; Android 13; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36",
    # Add more as desired...
]

# Common HTTP/S ports to try
COMMON_PORTS = [80, 443, 8080, 8000, 8443]

# Regex patterns
EMAIL_REGEX = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+', re.UNICODE)
PHONE_REGEX = re.compile(r'(\+?\d{1,3}[-.\s]?(\(?\d+\)?[-.\s]?)+\d+)', re.UNICODE)
IP_REGEX = re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')

# -------- Utility Functions --------

def iso_timestamp(dt=None):
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.isoformat(timespec='seconds')

def utc_to_cest(dt):
    cest = timezone(timedelta(hours=2))
    return dt.astimezone(cest).isoformat(timespec='seconds')

def print_progress(message):
    print(f"[{iso_timestamp()}] {message}")

def get_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[500,502,503,504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def rotate_user_agent(session):
    ua = USER_AGENTS[int(time.time()*1000) % len(USER_AGENTS)]
    session.headers.update({"User-Agent": ua})

def fetch_url(url, session):
    rotate_user_agent(session)
    try:
        response = session.get(url, timeout=15, allow_redirects=True)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print_progress(f"[WARN] Failed to fetch {url}: {e}")
        return None

def extract_entities(text):
    emails = set(EMAIL_REGEX.findall(text))
    phones = set(phone[0] if isinstance(phone, tuple) else phone for phone in PHONE_REGEX.findall(text))
    ips = set(IP_REGEX.findall(text))
    return emails, phones, ips

def is_valid_url(url):
    try:
        p = urlparse(url)
        return p.scheme in ['http', 'https'] and p.netloc != ''
    except:
        return False

def normalize_url(base_url, link):
    # join relative URLs properly
    return urljoin(base_url, link)

def get_links(html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for a in soup.find_all('a', href=True):
        link = normalize_url(base_url, a['href'])
        if is_valid_url(link):
            links.add(link)
    return links

# Simple port checker for HTTP service
def check_port(ip, port):
    try:
        with socket.create_connection((ip, port), timeout=2):
            return True
    except:
        return False

# Basic search engine scraping (DuckDuckGo & Bing for example)
def search_duckduckgo(query, max_results=10):
    print_progress("[INFO] Searching DuckDuckGo for URLs...")
    urls = set()
    url_template = "https://html.duckduckgo.com/html/?q={query}&s={offset}"
    session = get_session()
    offset = 0
    while len(urls) < max_results:
        url = url_template.format(query=query, offset=offset)
        html = fetch_url(url, session)
        if not html:
            break
        soup = BeautifulSoup(html, 'html.parser')
        results = soup.select('a.result__a')
        if not results:
            break
        for r in results:
            href = r.get('href')
            if href and is_valid_url(href):
                urls.add(href)
                if len(urls) >= max_results:
                    break
        offset += len(results)
    return list(urls)

def search_bing(query, max_results=10):
    print_progress("[INFO] Searching Bing for URLs...")
    urls = set()
    url_template = "https://www.bing.com/search?q={query}&first={offset}"
    session = get_session()
    offset = 1
    while len(urls) < max_results:
        url = url_template.format(query=query, offset=offset)
        html = fetch_url(url, session)
        if not html:
            break
        soup = BeautifulSoup(html, 'html.parser')
        results = soup.select('li.b_algo h2 a')
        if not results:
            break
        for r in results:
            href = r.get('href')
            if href and is_valid_url(href):
                urls.add(href)
                if len(urls) >= max_results:
                    break
        offset += 10
    return list(urls)

def send_to_discord(content):
    headers = {'Content-Type': 'application/json'}
    try:
        r = requests.post(DISCORD_WEBHOOK_URL, json=content, headers=headers, timeout=10)
        if r.status_code == 204:
            print_progress("[INFO] Sent results to Discord webhook successfully.")
        else:
            print_progress(f"[WARN] Discord webhook returned status {r.status_code}")
    except Exception as e:
        print_progress(f"[ERROR] Failed sending to Discord webhook: {e}")

# Main scrape function
def scrape_url(url, session):
    print_progress(f"[INFO] Scraping URL: {url}")
    html = fetch_url(url, session)
    if not html:
        return None

    emails, phones, ips = extract_entities(html)
    links = get_links(html, url)
    return {
        'url': url,
        'emails': list(emails),
        'phones': list(phones),
        'ips': list(ips),
        'links_found': list(links),
    }

def scrape_ip(ip):
    found_data = {'ip': ip, 'open_ports': [], 'data': []}
    print_progress(f"[INFO] Scanning IP {ip} on common HTTP ports...")
    for port in COMMON_PORTS:
        if check_port(ip, port):
            found_data['open_ports'].append(port)
    return found_data

def main():
    parser = argparse.ArgumentParser(description="EXTREME ROBUST CLI SCRAPER + SEARCH + DISCORD WEBHOOK")
    parser.add_argument("target", help="URL or IP to scrape")
    parser.add_argument("-k", "--keyword", help="Keyword for search engines (to find URLs)", default=None)
    parser.add_argument("-d", "--depth", type=int, default=1, help="Depth of crawling (default 1)")
    parser.add_argument("-m", "--maxsearch", type=int, default=5, help="Max search engine results to scrape per engine")
    args = parser.parse_args()

    start_time = datetime.now(timezone.utc)
    print_progress(f"=== Scraper started at {iso_timestamp(start_time)} UTC ===")

    session = get_session()

    all_results = {
        'start_time_utc': iso_timestamp(start_time),
        'targets': [],
        'summary': {},
    }

    targets_to_scrape = []

    if args.keyword:
        # Search engines queries to find URLs
        ddg_results = search_duckduckgo(args.keyword, max_results=args.maxsearch)
        bing_results = search_bing(args.keyword, max_results=args.maxsearch)
        combined = set(ddg_results + bing_results)
        print_progress(f"[INFO] Found {len(combined)} URLs from search engines")
        targets_to_scrape.extend(combined)

    # Add main target if URL or IP
    if is_valid_url(args.target):
        targets_to_scrape.append(args.target)
    else:
        # Could be IP? Basic validation
        try:
            socket.inet_aton(args.target)
            targets_to_scrape.append(f"http://{args.target}")
        except:
            print_progress("[ERROR] Target is neither valid URL nor IP.")
            sys.exit(1)

    # Crawl targets with limited depth
    scraped = set()
    to_crawl = set(targets_to_scrape)
    next_depth = set()

    for depth in range(args.depth):
        print_progress(f"[INFO] Crawl depth {depth+1} with {len(to_crawl)} URLs")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(scrape_url, url, session): url for url in to_crawl}
            for future in concurrent.futures.as_completed(futures):
                url = futures[future]
                try:
                    res = future.result()
                    if res:
                        all_results['targets'].append(res)
                        scraped.add(url)
                        # For next depth crawl add links
                        if depth + 1 < args.depth:
                            next_depth.update(res.get('links_found', []))
                except Exception as e:
                    print_progress(f"[ERROR] Scraping {url} failed: {e}")
        to_crawl = next_depth
        next_depth = set()

    # Scan IP if IP given (optional enhancement)
    ip = None
    try:
        ip = socket.gethostbyname(urlparse(args.target).netloc)
    except:
        ip = None

    if ip:
        ip_scan = scrape_ip(ip)
        all_results['ip_scan'] = ip_scan

    end_time = datetime.now(timezone.utc)
    duration = end_time - start_time

    # Summary
    total_emails = sum(len(t['emails']) for t in all_results['targets'])
    total_phones = sum(len(t['phones']) for t in all_results['targets'])
    total_ips = sum(len(t['ips']) for t in all_results['targets'])

    all_results['summary'] = {
        'total_urls_scraped': len(all_results['targets']),
        'total_emails_found': total_emails,
        'total_phones_found': total_phones,
        'total_ips_found': total_ips,
        'start_time_utc': iso_timestamp(start_time),
        'end_time_utc': iso_timestamp(end_time),
        'duration_seconds': int(duration.total_seconds())
    }

    # Prepare Discord message (simplified)
    discord_content = {
        "username": "ExtremeScraperBot",
        "embeds": [{
            "title": "Scraping Report",
            "description": f"Target: {args.target}\n"
                           f"Keyword: {args.keyword or 'N/A'}\n"
                           f"Depth: {args.depth}\n"
                           f"Duration: {str(duration)}\n"
                           f"Total URLs Scraped: {len(all_results['targets'])}\n"
                           f"Emails found: {total_emails}\n"
                           f"Phones found: {total_phones}\n"
                           f"IPs found: {total_ips}",
            "timestamp": iso_timestamp(end_time),
            "color": 0x00ff00
        }]
    }

    send_to_discord(discord_content)

    # Print summary
    print("\n=== Scraping summary ===")
    print(json.dumps(all_results['summary'], indent=2))
    print(f"Detailed results count: {len(all_results['targets'])}")
    print(f"Discord webhook sent at {iso_timestamp(end_time)}")

if __name__ == "__main__":
    main()
