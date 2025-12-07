"""
HTML Scraper for Grokipedia - Fetches full HTML content of Grokipedia.com article pages from a list of URLs.

Usage:
    python html_scraper.py --input-file urls.txt
    python html_scraper.py "https://grokipedia.com/page/Elon_Musk" "https://grokipedia.com/page/Tesla"
    
Examples:
    python html_scraper.py --input-file urls.txt
    python html_scraper.py "https://grokipedia.com/page/Elon_Musk" "https://grokipedia.com/page/Tesla"

This scrapes multiple URLs in parallel, inlines CSS (Tailwind/styles) by default for self-contained display,
and saves all HTML files to the 'pages' folder. Each file is named based on the URL slug.
"""

import argparse
import sys

import requests

try:
    from bs4 import BeautifulSoup
    BS_AVAILABLE = True
except ImportError:
    BeautifulSoup = None
    BS_AVAILABLE = False

import concurrent.futures
import os
from pathlib import Path
from urllib.parse import urlparse


def _fetch_page(url: str) -> str:
    """Fetch the full HTML content of a page."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def scrape_single(url: str, base_dir: Path, filename: str = None, do_inline: bool = True) -> Path | None:
    """Scrape a single URL, optionally inline CSS, and save to file."""
    if "grokipedia.com" not in url:
        print(f"Warning: Skipping non-Grokipedia URL: {url}", file=sys.stderr)
        return None
    
    print(f"Scraping: {url}", file=sys.stderr)
    
    html = _fetch_page(url)
    if not html:
        print(f"Failed to fetch content for {url}", file=sys.stderr)
        return None
    
    if do_inline and BS_AVAILABLE:
        print("Inlining CSS (Tailwind/styles)...", file=sys.stderr)
        soup = BeautifulSoup(html, 'html.parser')
        
        css_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/css,*/*;q=0.1",
            "Accept-Language": "en-US,en;q=0.5",
        }
        
        inlined_count = 0
        for link in soup.find_all('link', rel='stylesheet'):
            href = link.get('href')
            if href and '/_next/static/css/' in href:
                css_url = f"https://grokipedia.com{href}" if href.startswith('/') else href
                try:
                    css_resp = requests.get(css_url, headers=css_headers, timeout=10)
                    css_resp.raise_for_status()
                    style_tag = soup.new_tag('style')
                    if link.get('media'):
                        style_tag['media'] = link.get('media')
                    if link.get('nonce'):
                        style_tag['nonce'] = link.get('nonce')
                    style_tag.string = css_resp.text
                    link.replace_with(style_tag)
                    inlined_count += 1
                except Exception as e:
                    print(f"Failed to inline {href}: {e}", file=sys.stderr)
        
        html = str(soup)
        print(f"Inlined {inlined_count} CSS files for self-contained display.", file=sys.stderr)
    elif do_inline:
        print("Inline requested but BeautifulSoup unavailable; saving without inlining.", file=sys.stderr)
    
    if filename:
        out_file = base_dir / filename
        out_file.parent.mkdir(parents=True, exist_ok=True)
    else:
        parsed = urlparse(url)
        slug = os.path.basename(parsed.path.rstrip('/'))
        if not slug or slug == 'page':
            slug = 'index'
        if not slug.endswith('.html'):
            slug += '.html'
        out_file = base_dir / slug
    
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"Saved styled HTML: {out_file}", file=sys.stderr)
    return out_file


def main():
    parser = argparse.ArgumentParser(
        description="Scrape full HTML content from multiple Grokipedia pages in parallel, with default CSS inlining (Tailwind/styles) for exact, self-contained display. All pages are saved to the 'pages' folder."
    )
    parser.add_argument("urls", nargs='*', help="Grokipedia URLs to scrape in parallel (optional if using --input-file).")
    parser.add_argument(
        "--input-file", "-i",
        help="Text file with one URL per line for batch scraping (overrides positional URLs; lines must be valid HTTP URLs)."
    )
    parser.add_argument(
        "--output-dir",
        default="data/pages",
        help="Directory to save HTML files (default: pages/; created if missing). Each file is named based on the URL slug (e.g., Elon_Musk.html)."
    )
    parser.add_argument(
        "--no-inline-css",
        action="store_true",
        help="Disable default CSS inlining (results in smaller file with external Tailwind/CSS loads; may not style in local browser due to security blocks)."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Max parallel workers for scraping (default: 5; increase for speed, but avoid high to prevent rate-limiting)."
    )
    
    args = parser.parse_args()
    
    do_inline_css = not args.no_inline_css
    
    # Load URLs from input file if provided
    if args.input_file:
        try:
            with open(args.input_file, 'r', encoding='utf-8') as f:
                file_urls = [line.strip() for line in f if line.strip() and line.strip().startswith('http')]
            if file_urls:
                args.urls = file_urls
                print(f"Loaded {len(file_urls)} URLs from {args.input_file}", file=sys.stderr)
            else:
                print("No valid URLs (starting with http) found in input file.", file=sys.stderr)
                sys.exit(1)
        except FileNotFoundError:
            print(f"Input file not found: {args.input_file}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error reading input file: {e}", file=sys.stderr)
            sys.exit(1)
    
    if not args.urls:
        print("No URLs provided. Use positional arguments or --input-file.", file=sys.stderr)
        parser.print_help()
        sys.exit(1)
    
    # Always save to pages folder
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Scrape all URLs in parallel
    print(f"Scraping {len(args.urls)} URLs in parallel to {out_dir} (workers={args.workers}, inline-css={'enabled' if do_inline_css else 'disabled'})", file=sys.stderr)
    saved_files = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(scrape_single, url, out_dir, None, do_inline_css)
            for url in args.urls
        ]
        for future in concurrent.futures.as_completed(futures):
            try:
                file_path = future.result()
                if file_path:
                    saved_files.append(file_path)
            except Exception as e:
                print(f"Parallel scrape error: {e}", file=sys.stderr)
    
    if saved_files:
        print(f"Successfully scraped and saved {len(saved_files)} styled HTML pages to {out_dir}.")
        print("Open the .html files in a browser for exact display (Tailwind/CSS inlined by default for offline styling).")
    else:
        print("No pages saved (all failed). Check logs above.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
