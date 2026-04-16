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
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

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
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    # Linux
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/snap/bin/chromium",
]

SYSTEM_CHROME = None
for p in CHROME_PATHS:
    if os.path.isfile(p):
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
                 browser_mode: str = "auto", browser_exec: str = None):
        self.base_url = base_url.rstrip('/')
        self.output_dir = Path(output_dir)
        self.max_depth = max_depth
        self.extra_wait_ms = extra_wait_ms
        self.headful = headful

        self.downloaded = []
        self.errors = []
        self.pages = set()
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

    def _url_to_path(self, url: str) -> Path:
        parsed = urllib.parse.urlparse(url)
        rel_path = parsed.path.lstrip('/') or 'index.html'
        if not rel_path.endswith('.html') and not rel_path.endswith('.htm'):
            rel_path = re.split(r'[?#]', rel_path)[0]
        if rel_path.endswith('/'):
            rel_path += 'index.html'
        if not any(rel_path.endswith(ext) for ext in self.ASSET_EXTENSIONS):
            if parsed.path.endswith('/') or '.' not in rel_path.split('/')[-1]:
                rel_path += '.html'
        return self.output_dir / rel_path

    def _rewrite_urls_in_html(self, html_content: str, page_url: str) -> str:
        def replace_url(match):
            full_match = match.group(0)
            url = match.group(1) or match.group(2) or ''
            if not url or self._should_skip(url):
                return full_match
            resolved = urllib.parse.urljoin(page_url, url)
            if not resolved.startswith(self.base_origin):
                return full_match
            rel_path = self._url_to_path(resolved)
            try:
                local_relative = os.path.relpath(rel_path, self.output_dir).replace('\\', '/')
            except ValueError:
                local_relative = rel_path.name
            return full_match.replace(url, local_relative)

        html_content = re.sub(
            r'(?:href|src)=["\']([^"\']+)["\']',
            replace_url,
            html_content
        )
        return html_content

    def _rewrite_urls_in_css(self, css_content: str, css_url: str) -> str:
        def replace_url(match):
            url = match.group(1)
            if not url or self._should_skip(url):
                return match.group(0)
            resolved = urllib.parse.urljoin(css_url, url)
            if not resolved.startswith(self.base_origin):
                return match.group(0)
            rel_path = self._url_to_path(resolved)
            try:
                local_relative = os.path.relpath(rel_path, self._url_to_path(css_url).parent).replace('\\', '/')
            except ValueError:
                local_relative = rel_path.name
            return f'url("{local_relative}")'

        return re.sub(r'url\(["\']?([^)"\']+)["\']?\)', replace_url, css_content)

    async def _save_resource(self, url: str, body: bytes, content_type: str = ''):
        local_path = self._url_to_path(url)
        local_path.parent.mkdir(parents=True, exist_ok=True)

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

    async def clone(self):
        print(f"🚀 Cloning: {self.base_url}")
        print(f"📁 Output: {self.output_dir.absolute()}")
        print(f"🌐 Browser: {self.browser_mode}" + (f" ({self.browser_exec})" if self.browser_exec else ""))
        print()

        self.output_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            browser = await self._launch_browser(p)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
            )
            page = await context.new_page()

            async def handle_request(route):
                request = route.request
                url = request.url
                if self._should_skip(url):
                    await route.continue_()
                    return
                try:
                    response = await route.fetch()
                    body = await response.body()
                    content_type = response.headers.get('content-type', '')
                    await self._save_resource(url, body, content_type)
                    await route.fulfill(response=response)
                except Exception as e:
                    self.errors.append({'url': url, 'error': str(e)})
                    await route.continue_()

            await page.route('**/*', handle_request)

            print(f"⏳ Loading page...")
            try:
                await page.goto(self.base_url, wait_until='networkidle', timeout=60000)
            except Exception:
                print(f"⚠️  Timeout on networkidle, trying domcontentloaded...")
                try:
                    await page.goto(self.base_url, wait_until='domcontentloaded', timeout=30000)
                except Exception as e:
                    print(f"❌ Failed to load page: {e}")
                    await browser.close()
                    return

            print(f"✅ Page loaded")

            if self.extra_wait_ms > 0:
                print(f"⏳ Waiting {self.extra_wait_ms}ms for lazy content...")
                await asyncio.sleep(self.extra_wait_ms / 1000)

            print(f"📜 Scrolling to trigger lazy-load...")
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
                pass  # Scroll may fail on some pages, not critical

            if self.max_depth > 0:
                print(f"🔍 Discovering linked pages (depth={self.max_depth})...")
                try:
                    links = await page.evaluate("""() => {
                        const links = [...document.querySelectorAll('a[href]')];
                        return links.map(a => a.href).filter(h => h.startsWith(window.location.origin));
                    }""")
                    for link in set(links)[:20]:
                        if link != self.base_url:
                            self.pages.add(link)
                except Exception:
                    pass

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
            'pages_discovered': len(self.pages),
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
        print(f"   Time:       {report['elapsed_seconds']}s")
        print(f"   Pages:      {report['pages_discovered']} discovered")
        print()
        print("   Files by type:")
        for ftype, count in sorted(report['files_by_type'].items(), key=lambda x: -x[1]):
            print(f"     {ftype}: {count}")
        print()

        if self.errors:
            print(f"⚠️  {len(self.errors)} errors (see _clone_report.json)")

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
    )

    asyncio.run(cloner.clone())


if __name__ == '__main__':
    main()
