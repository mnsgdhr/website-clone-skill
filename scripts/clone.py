#!/usr/bin/env python3
"""
clone.py — Complete website cloner

Downloads a full website including all assets (HTML, CSS, JS, images, fonts, XHR).
Supports both single-page and multi-page recursive cloning.
Automatically rewrites URLs in HTML/CSS to point to local files.

Browser detection (auto, in order):
  1. System Chrome/Chromium (if installed)
  2. Playwright's bundled Chromium (if playwright installed)
  3. Fails with helpful instructions if neither available

Usage:
    python clone.py <url> [--output <dir>] [--depth <n>] [--wait <ms>] [--full] [--headful]

Examples:
    python clone.py https://example.com
    python clone.py https://example.com --output ./my-clone
    python clone.py https://example.com --depth 2 --wait 5000
"""

import asyncio
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from collections import deque
from pathlib import Path

# Python version check
if sys.version_info < (3, 9):
    print("⚠️ Warning: Python 3.9+ is recommended for this script.")
elif sys.version_info >= (3, 14):
    print("⚠️ Warning: Python 3.14+ may have compatibility issues with Playwright. Consider using Python 3.9–3.13.")

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Browser detection
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

# Find system Chrome/Chromium
CHROME_PATHS = [
    # Windows
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    # WSL2 Windows paths
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/mnt/c/Users/*/AppData/Local/Google/Chrome/Application/chrome.exe",
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    # Linux
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/snap/bin/chromium",
]

SYSTEM_CHROME = None
for p in CHROME_PATHS:
    # Handle glob patterns for WSL paths
    if '*' in p:
        import glob
        matches = glob.glob(p)
        if matches:
            SYSTEM_CHROME = matches[0]
            break
    elif os.path.isfile(p):
        SYSTEM_CHROME = p
        break


def find_browser():
    """Detect available browser. Returns (mode, executable_or_none)."""
    # Priority 1: System Chrome/Edge
    if SYSTEM_CHROME:
        return ("system", SYSTEM_CHROME)
    # Priority 2: Playwright's bundled Chromium
    if PLAYWRIGHT_AVAILABLE:
        return ("playwright", None)
    return (None, None)


# Common CDN domains that may be expensive/unnecessary to download
CDN_DOMAINS = {
    'fonts.googleapis.com', 'fonts.gstatic.com',
    'cdn.jsdelivr.net', 'unpkg.com', 'cdnjs.cloudflare.com',
    'ajax.googleapis.com', 'code.jquery.com',
    'stackpath.bootstrapcdn.com', 'cdn.bootcss.com',
}


class WebsiteCloner:
    """Clone a website by intercepting all network requests."""

    ASSET_EXTENSIONS = {
        '.html', '.htm', '.css', '.js', '.json',
        '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.avif', '.bmp',
        '.woff', '.woff2', '.ttf', '.eot', '.otf',
        '.mp4', '.webm', '.ogg', '.mp3', '.wav',
        '.xml', '.txt', '.map',
    }

    SKIP_PATTERNS = [
        re.compile(r'^data:', re.IGNORECASE),
        re.compile(r'^blob:', re.IGNORECASE),
        re.compile(r'^chrome-extension:', re.IGNORECASE),
        re.compile(r'^devtools:', re.IGNORECASE),
        re.compile(r'^chrome:', re.IGNORECASE),
        re.compile(r'^edge:', re.IGNORECASE),
    ]

    def __init__(self, base_url: str, output_dir: str, max_depth: int = 0,
                 extra_wait_ms: int = 3000, headful: bool = False,
                 browser_mode: str = "auto", browser_exec: str = None,
                 download_cdn: bool = False):
        self.base_url = base_url.rstrip('/')
        self.output_dir = Path(output_dir)
        self.max_depth = max_depth
        self.extra_wait_ms = extra_wait_ms
        self.headful = headful
        self.download_cdn = download_cdn

        self.downloaded = []
        self.errors = []
        self.cdn_resources = []
        self.visited_urls = set()
        self.start_time = time.time()

        parsed = urllib.parse.urlparse(base_url)
        self.base_origin = f"{parsed.scheme}://{parsed.netloc}"

        # Resolve browser
        if browser_mode == "auto":
            mode, exec_path = find_browser()
            if mode is None:
                print("❌ No browser found!")
                print()
                print("Install one of the following:")
                print("  1. Google Chrome: https://www.google.com/chrome/")
                print("  2. Microsoft Edge: https://www.microsoft.com/edge")
                print("  3. Playwright Chromium: pip install playwright && python -m playwright install chromium")
                sys.exit(1)
            self.browser_mode = mode
            self.browser_exec = exec_path
        else:
            self.browser_mode = browser_mode
            self.browser_exec = browser_exec

    def _should_skip(self, url: str) -> bool:
        for pattern in self.SKIP_PATTERNS:
            if pattern.match(url):
                return True
        return False

    def _is_cdn_resource(self, url: str) -> bool:
        """Check if URL is from a known CDN domain."""
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.netloc in CDN_DOMAINS
        except Exception:
            return False

    def _is_same_origin(self, url: str) -> bool:
        """Check if URL belongs to the same origin as the base URL."""
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.scheme + "://" + parsed.netloc == self.base_origin
        except Exception:
            return False

    def _url_to_path(self, url: str) -> Path:
        """Convert a URL to a local file path."""
        parsed = urllib.parse.urlparse(url)

        # For CDN/external resources, store under _cdn/ directory
        if not self._is_same_origin(url):
            safe_host = parsed.netloc.replace('.', '_')
            rel_path = f"_cdn/{safe_host}{parsed.path}"
        else:
            rel_path = parsed.path.lstrip('/') or 'index.html'

        # Clean up query strings and fragments for filename
        if not rel_path.endswith('.html') and not rel_path.endswith('.htm'):
            rel_path = re.split(r'[?#]', rel_path)[0]

        # Handle directory URLs
        if rel_path.endswith('/'):
            rel_path += 'index.html'

        # Add .html extension if missing for page-like URLs
        if not any(rel_path.endswith(ext) for ext in self.ASSET_EXTENSIONS):
            if parsed.path.endswith('/') or '.' not in rel_path.split('/')[-1]:
                rel_path += '.html'

        # Handle URLs with query strings that look like API endpoints
        if parsed.query and not rel_path.endswith(('.html', '.htm')):
            # Create a directory for query-based URLs
            query_hash = hashlib.md5(parsed.query.encode()).hexdigest()[:8]
            rel_path = rel_path.rstrip('/') + f'_{query_hash}.json'

        return self.output_dir / rel_path

    def _rewrite_urls_in_html(self, html_content: str, page_url: str) -> str:
        """Rewrite all URLs in HTML to point to local files."""
        def replace_url(match):
            full_match = match.group(0)
            url = match.group(1) or match.group(2) or ''
            if not url or self._should_skip(url):
                return full_match
            resolved = urllib.parse.urljoin(page_url, url)
            if not resolved.startswith(self.base_origin):
                # For CDN resources, either keep original or point to _cdn/ path
                if self.download_cdn:
                    local_path = self._url_to_path(resolved)
                    try:
                        local_relative = os.path.relpath(local_path, self.output_dir).replace('\\', '/')
                    except ValueError:
                        local_relative = local_path.name
                    return full_match.replace(url, local_relative)
                else:
                    return full_match  # Keep CDN URLs as-is
            rel_path = self._url_to_path(resolved)
            try:
                local_relative = os.path.relpath(rel_path, self.output_dir).replace('\\', '/')
            except ValueError:
                local_relative = rel_path.name
            return full_match.replace(url, local_relative)

        # Handle href and src attributes
        html_content = re.sub(
            r'(?:href|src)=["\']([^"\']+)["\']',
            replace_url,
            html_content
        )

        # Handle srcset attributes (responsive images)
        def replace_srcset(match):
            full_match = match.group(0)
            parts = re.findall(r'([^\s,]+)(?:\s+\d+[wx])?', full_match)
            new_parts = []
            for url in parts:
                if self._should_skip(url):
                    new_parts.append(url)
                    continue
                resolved = urllib.parse.urljoin(page_url, url)
                if not resolved.startswith(self.base_origin):
                    if self.download_cdn:
                        local_path = self._url_to_path(resolved)
                        try:
                            local_relative = os.path.relpath(local_path, self.output_dir).replace('\\', '/')
                        except ValueError:
                            local_relative = local_path.name
                        new_parts.append(local_relative)
                    else:
                        new_parts.append(url)
                else:
                    rel_path = self._url_to_path(resolved)
                    try:
                        local_relative = os.path.relpath(rel_path, self.output_dir).replace('\\', '/')
                    except ValueError:
                        local_relative = rel_path.name
                    new_parts.append(local_relative)
            return 'srcset="' + ', '.join(new_parts) + '"'

        html_content = re.sub(
            r'srcset=["\']([^"\']+)["\']',
            replace_srcset,
            html_content
        )

        # Handle style attributes with url()
        def replace_style_url(match):
            full_match = match.group(0)
            url = match.group(1)
            if not url or self._should_skip(url):
                return full_match
            resolved = urllib.parse.urljoin(page_url, url)
            if not resolved.startswith(self.base_origin):
                if self.download_cdn:
                    local_path = self._url_to_path(resolved)
                    try:
                        local_relative = os.path.relpath(local_path, self.output_dir).replace('\\', '/')
                    except ValueError:
                        local_relative = local_path.name
                    return f'url("{local_relative}")'
                else:
                    return full_match
            rel_path = self._url_to_path(resolved)
            try:
                local_relative = os.path.relpath(rel_path, self.output_dir).replace('\\', '/')
            except ValueError:
                local_relative = rel_path.name
            return f'url("{local_relative}")'

        html_content = re.sub(
            r'url\(["\']?([^)"\']+)["\']?\)',
            replace_style_url,
            html_content
        )

        return html_content

    def _rewrite_urls_in_css(self, css_content: str, css_url: str) -> str:
        """Rewrite all URLs in CSS to point to local files."""
        def replace_url(match):
            url = match.group(1)
            if not url or self._should_skip(url):
                return match.group(0)
            resolved = urllib.parse.urljoin(css_url, url)
            if not resolved.startswith(self.base_origin):
                if self.download_cdn:
                    local_path = self._url_to_path(resolved)
                    try:
                        local_relative = os.path.relpath(local_path, self._url_to_path(css_url).parent).replace('\\', '/')
                    except ValueError:
                        local_relative = local_path.name
                    return f'url("{local_relative}")'
                else:
                    return match.group(0)  # Keep CDN URLs as-is
            rel_path = self._url_to_path(resolved)
            try:
                local_relative = os.path.relpath(rel_path, self._url_to_path(css_url).parent).replace('\\', '/')
            except ValueError:
                local_relative = rel_path.name
            return f'url("{local_relative}")'

        # Handle url() in CSS
        css_content = re.sub(r'url\(["\']?([^)"\']+)["\']?\)', replace_url, css_content)

        # Handle @import statements
        def replace_import(match):
            full_match = match.group(0)
            url = match.group(1) or match.group(2)
            if not url or self._should_skip(url):
                return full_match
            resolved = urllib.parse.urljoin(css_url, url)
            if not resolved.startswith(self.base_origin):
                if self.download_cdn:
                    local_path = self._url_to_path(resolved)
                    try:
                        local_relative = os.path.relpath(local_path, self._url_to_path(css_url).parent).replace('\\', '/')
                    except ValueError:
                        local_relative = local_path.name
                    return f'@import url("{local_relative}");'
                else:
                    return full_match
            rel_path = self._url_to_path(resolved)
            try:
                local_relative = os.path.relpath(rel_path, self._url_to_path(css_url).parent).replace('\\', '/')
            except ValueError:
                local_relative = rel_path.name
            return f'@import url("{local_relative}");'

        css_content = re.sub(
            r'@import\s+(?:url\(["\']?([^)"\']+)["\']?\)|["\']([^"\']+)["\'])',
            replace_import,
            css_content
        )

        return css_content

    async def _save_resource(self, url: str, body: bytes, content_type: str = ''):
        """Save a resource to local disk."""
        local_path = self._url_to_path(url)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # Rewrite URLs in HTML and CSS
        if 'html' in content_type or url.endswith(('.html', '.htm')):
            body = self._rewrite_urls_in_html(body.decode('utf-8', errors='replace'), url).encode('utf-8')
        elif 'css' in content_type or url.endswith('.css'):
            body = self._rewrite_urls_in_css(body.decode('utf-8', errors='replace'), url).encode('utf-8')

        local_path.write_bytes(body)
        self.downloaded.append({
            'url': url,
            'path': str(local_path.relative_to(self.output_dir)),
            'size': len(body),
            'content_type': content_type,
        })

    async def _launch_browser(self, p):
        """Launch browser based on detected mode."""
        if self.browser_mode == "system":
            return await p.chromium.launch(
                headless=not self.headful,
                executable_path=self.browser_exec,
                args=['--no-sandbox', '--disable-setuid-sandbox'],
            )
        else:
            # Playwright bundled Chromium
            return await p.chromium.launch(headless=not self.headful)

    async def _collect_page_links(self, page) -> list:
        """Extract all same-origin links from the current page."""
        try:
            links = await page.evaluate("""() => {
                const links = [...document.querySelectorAll('a[href]')];
                return links.map(a => {
                    try {
                        const url = new URL(a.href, window.location.href);
                        return url.href;
                    } catch { return null; }
                }).filter(h => h && h.startsWith(window.location.origin) && !h.includes('#'));
            }""")
            return [l for l in links if l]
        except Exception:
            return []

    async def _clone_single_page(self, browser, url: str) -> list:
        """Clone a single page and return discovered links."""
        if url in self.visited_urls:
            return []
        self.visited_urls.add(url)

        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
        )
        page = await context.new_page()

        async def handle_request(route):
            request = route.request
            req_url = request.url
            if self._should_skip(req_url):
                await route.continue_()
                return

            # Handle CDN resources
            if self._is_cdn_resource(req_url) and not self.download_cdn:
                self.cdn_resources.append(req_url)
                await route.continue_()
                return

            try:
                response = await route.fetch()
                body = await response.body()
                content_type = response.headers.get('content-type', '')
                await self._save_resource(req_url, body, content_type)
                await route.fulfill(response=response)
            except Exception as e:
                self.errors.append({'url': req_url, 'error': str(e)})
                await route.continue_()

        await page.route('**/*', handle_request)

        print(f"   📄 Loading: {url}")
        try:
            await page.goto(url, wait_until='networkidle', timeout=60000)
        except Exception:
            print(f"   ⚠️  Timeout on networkidle, trying domcontentloaded...")
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            except Exception as e:
                print(f"   ❌ Failed to load page: {e}")
                await context.close()
                return []

        print(f"   ✅ Page loaded")

        if self.extra_wait_ms > 0:
            print(f"   ⏳ Waiting {self.extra_wait_ms}ms for lazy content...")
            await asyncio.sleep(self.extra_wait_ms / 1000)

        # Scroll to trigger lazy-load
        print(f"   📜 Scrolling to trigger lazy-load...")
        try:
            await page.evaluate("""() => {
                return new Promise(resolve => {
                    let totalHeight = 0;
                    const distance = 300;
                    const timer = setInterval(() => {
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        if (totalHeight >= document.body.scrollHeight - window.innerHeight) {
                            clearInterval(timer);
                            resolve();
                        }
                    }, 200);
                });
            }""")
            await asyncio.sleep(2)
        except Exception:
            pass

        # Collect links for recursive crawling
        discovered_links = await self._collect_page_links(page)

        await context.close()
        return discovered_links

    async def clone(self):
        """Main clone workflow with BFS for multi-page support."""
        print(f"🚀 Cloning: {self.base_url}")
        print(f"📁 Output: {self.output_dir.absolute()}")
        print(f"🌐 Browser: {self.browser_mode}" + (f" ({self.browser_exec})" if self.browser_exec else ""))
        print(f"📏 Max depth: {self.max_depth}")
        print(f"📦 Download CDN: {self.download_cdn}")
        print()

        self.output_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            browser = await self._launch_browser(p)

            # BFS queue: (url, depth)
            queue = deque()
            queue.append((self.base_url, 0))

            while queue:
                url, depth = queue.popleft()

                if depth > self.max_depth:
                    continue

                discovered = await self._clone_single_page(browser, url)

                # Add discovered links to queue for next level
                if depth < self.max_depth:
                    for link in discovered:
                        if link not in self.visited_urls and link.startswith(self.base_origin):
                            queue.append((link, depth + 1))

            await browser.close()

        # Report
        elapsed = time.time() - self.start_time
        total_size = sum(d['size'] for d in self.downloaded)
        report = {
            'base_url': self.base_url,
            'output_dir': str(self.output_dir),
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'elapsed_seconds': round(elapsed, 2),
            'total_files': len(self.downloaded),
            'total_size_bytes': total_size,
            'total_size_human': self._human_size(total_size),
            'errors': len(self.errors),
            'cdn_resources_skipped': len(self.cdn_resources),
            'pages_visited': len(self.visited_urls),
            'files_by_type': self._count_by_type(),
        }

        (self.output_dir / '_clone_report.json').write_text(
            json.dumps(report, indent=2, ensure_ascii=False))

        print()
        print("=" * 50)
        print("📊 Clone Report")
        print("=" * 50)
        print(f"   URL:        {self.base_url}")
        print(f"   Output:     {self.output_dir.absolute()}")
        print(f"   Browser:    {self.browser_mode}")
        print(f"   Files:      {report['total_files']}")
        print(f"   Size:       {report['total_size_human']}")
        print(f"   Errors:     {report['errors']}")
        print(f"   Pages:      {report['pages_visited']} visited")
        print(f"   CDN skipped:{report['cdn_resources_skipped']}")
        print(f"   Time:       {report['elapsed_seconds']}s")
        print()
        print("   Files by type:")
        for ftype, count in sorted(report['files_by_type'].items(), key=lambda x: -x[1]):
            print(f"     {ftype}: {count}")
        print()

        if self.errors:
            print(f"⚠️  {len(self.errors)} errors (see _clone_report.json)")
        if self.cdn_resources:
            print(f"ℹ️  {len(self.cdn_resources)} CDN resources skipped (use --download-cdn to include)")

        print(f"✅ Done! Serve with:")
        print(f"   python -m http.server 8000 --directory {self.output_dir.absolute()}")

    def _human_size(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def _count_by_type(self) -> dict:
        counts = {}
        for d in self.downloaded:
            ct = d.get('content_type', '')
            if 'html' in ct:
                t = 'html'
            elif 'css' in ct:
                t = 'css'
            elif 'javascript' in ct:
                t = 'js'
            elif 'image' in ct:
                t = 'images'
            elif 'font' in ct:
                t = 'fonts'
            elif 'json' in ct:
                t = 'json'
            elif 'video' in ct or 'audio' in ct:
                t = 'media'
            else:
                t = 'other'
            counts[t] = counts.get(t, 0) + 1
        return counts


def main():
    parser = argparse.ArgumentParser(
        description='Clone a complete website with all assets',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Browser Detection (automatic):
  1. System Chrome/Edge (if installed)
  2. Playwright's bundled Chromium (if playwright installed)

Examples:
  python clone.py https://example.com
  python clone.py https://example.com --output ./my-clone
  python clone.py https://example.com --depth 2 --wait 5000
  python clone.py https://example.com --download-cdn
        """
    )
    parser.add_argument('url', help='URL to clone')
    parser.add_argument('--output', '-o', default=None, help='Output directory')
    parser.add_argument('--depth', '-d', type=int, default=0,
                        help='Max depth for page discovery (0 = single page)')
    parser.add_argument('--wait', '-w', type=int, default=3000,
                        help='Extra wait time after page load in ms (default: 3000)')
    parser.add_argument('--full', '-f', action='store_true',
                        help='Full recursive clone (sets depth=2)')
    parser.add_argument('--headful', action='store_true',
                        help='Run browser in visible mode (for debugging)')
    parser.add_argument('--download-cdn', action='store_true',
                        help='Also download CDN resources (fonts, libs, etc.)')

    args = parser.parse_args()

    if args.output:
        output_dir = args.output
    else:
        parsed = urllib.parse.urlparse(args.url)
        hostname = parsed.netloc.replace('.', '_')
        output_dir = f'./cloned_{hostname}'

    max_depth = 2 if args.full else args.depth

    cloner = WebsiteCloner(
        base_url=args.url,
        output_dir=output_dir,
        max_depth=max_depth,
        extra_wait_ms=args.wait,
        headful=args.headful,
        download_cdn=args.download_cdn,
    )

    asyncio.run(cloner.clone())


if __name__ == '__main__':
    main()
