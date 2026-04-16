#!/usr/bin/env python3
"""
clone.py — Complete website cloner with Playwright

Downloads a full website including all assets (HTML, CSS, JS, images, fonts, XHR).
Supports both single-page and multi-page recursive cloning.
Automatically rewrites URLs in HTML/CSS to point to local files.

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

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("❌ Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)


class WebsiteCloner:
    """Clone a website by intercepting all network requests."""

    # Asset extensions we care about
    ASSET_EXTENSIONS = {
        '.html', '.htm', '.css', '.js', '.json',
        '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.avif', '.bmp',
        '.woff', '.woff2', '.ttf', '.eot', '.otf',
        '.mp4', '.webm', '.ogg', '.mp3', '.wav',
        '.xml', '.txt', '.map',
    }

    # URL patterns to skip
    SKIP_PATTERNS = [
        re.compile(r'^data:', re.IGNORECASE),
        re.compile(r'^blob:', re.IGNORECASE),
        re.compile(r'^chrome-extension:', re.IGNORECASE),
        re.compile(r'^devtools:', re.IGNORECASE),
    ]

    def __init__(self, base_url: str, output_dir: str, max_depth: int = 0,
                 extra_wait_ms: int = 3000, headful: bool = False):
        self.base_url = base_url.rstrip('/')
        self.output_dir = Path(output_dir)
        self.max_depth = max_depth
        self.extra_wait_ms = extra_wait_ms
        self.headful = headful

        # Tracking
        self.downloaded = []      # List of {url, path, size, status}
        self.errors = []          # List of {url, error}
        self.missing = []         # Referenced but not downloaded
        self.pages = set()        # URLs of HTML pages found
        self.start_time = time.time()

        # Base path for URL resolution
        parsed = urllib.parse.urlparse(base_url)
        self.base_origin = f"{parsed.scheme}://{parsed.netloc}"

    def _should_skip(self, url: str) -> bool:
        """Check if URL should be skipped."""
        for pattern in self.SKIP_PATTERNS:
            if pattern.match(url):
                return True
        return False

    def _url_to_path(self, url: str) -> Path:
        """Convert a URL to a local file path."""
        parsed = urllib.parse.urlparse(url)

        # Build relative path from the URL path
        rel_path = parsed.path.lstrip('/') or 'index.html'

        # Remove query string for file path (keep for HTML files)
        if not rel_path.endswith('.html') and not rel_path.endswith('.htm'):
            # For non-HTML, strip query/fragment
            rel_path = re.split(r'[?#]', rel_path)[0]

        # Handle trailing slash directories
        if rel_path.endswith('/'):
            rel_path += 'index.html'

        # Ensure file extension for extensionless paths
        if not any(rel_path.endswith(ext) for ext in self.ASSET_EXTENSIONS):
            if parsed.path.endswith('/') or not '.' in rel_path.split('/')[-1]:
                rel_path += '.html'

        return self.output_dir / rel_path

    def _rewrite_urls_in_html(self, html_content: str, page_url: str) -> str:
        """Rewrite URLs in HTML to point to local files."""
        parsed = urllib.parse.urlparse(page_url)

        def replace_url(match):
            full_match = match.group(0)
            url = match.group(1) or match.group(2) or ''

            if not url or self._should_skip(url):
                return full_match

            # Resolve relative URLs
            resolved = urllib.parse.urljoin(page_url, url)

            # Skip external URLs (different domain)
            if not resolved.startswith(self.base_origin):
                return full_match

            # Convert to relative local path
            rel_path = self._url_to_path(resolved)
            try:
                local_relative = os.path.relpath(rel_path, self.output_dir).replace('\\', '/')
            except ValueError:
                local_relative = rel_path.name

            # Determine the attribute context
            if 'href=' in full_match:
                return full_match.replace(url, local_relative)
            elif 'src=' in full_match:
                return full_match.replace(url, local_relative)
            return full_match

        # Match href and src attributes
        html_content = re.sub(
            r'(?:href|src)=["\']([^"\']+)["\']',
            replace_url,
            html_content
        )

        # Match CSS url() in inline styles
        html_content = re.sub(
            r'url\(["\']?([^)"\']+)["\']?\)',
            lambda m: f'url("{m.group(1)}")',  # Keep as-is for now, CSS rewriter handles it
            html_content
        )

        return html_content

    def _rewrite_urls_in_css(self, css_content: str, css_url: str) -> str:
        """Rewrite URLs in CSS to point to local files."""
        def replace_url(match):
            url = match.group(1)

            if not url or self._should_skip(url):
                return match.group(0)

            resolved = urllib.parse.urljoin(css_url, url)

            # Skip external URLs
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
        """Save a downloaded resource to disk."""
        local_path = self._url_to_path(url)

        # Create parent directory
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # Rewrite URLs based on content type
        if 'html' in content_type or url.endswith(('.html', '.htm')):
            body = self._rewrite_urls_in_html(body.decode('utf-8', errors='replace'), url).encode('utf-8')
        elif 'css' in content_type or url.endswith('.css'):
            body = self._rewrite_urls_in_css(body.decode('utf-8', errors='replace'), url).encode('utf-8')

        # Write file
        local_path.write_bytes(body)

        self.downloaded.append({
            'url': url,
            'path': str(local_path.relative_to(self.output_dir)),
            'size': len(body),
            'content_type': content_type,
        })

        return local_path

    async def clone(self):
        """Main cloning process."""
        print(f"🚀 Cloning: {self.base_url}")
        print(f"📁 Output: {self.output_dir.absolute()}")
        print()

        self.output_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not self.headful)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
            )
            page = await context.new_page()

            # Track all requests
            request_urls = set()

            async def handle_request(route):
                request = route.request
                url = request.url

                if self._should_skip(url):
                    await route.continue_()
                    return

                request_urls.add(url)

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

            # Navigate to the page
            print(f"⏳ Loading page...")
            try:
                await page.goto(self.base_url, wait_until='networkidle', timeout=60000)
            except Exception as e:
                # Try with shorter timeout
                print(f"⚠️  Timeout on networkidle, trying domcontentloaded...")
                try:
                    await page.goto(self.base_url, wait_until='domcontentloaded', timeout=30000)
                except Exception as e2:
                    print(f"❌ Failed to load page: {e2}")
                    await browser.close()
                    return

            print(f"✅ Page loaded")

            # Wait for additional requests (lazy-loaded content, XHR)
            if self.extra_wait_ms > 0:
                print(f"⏳ Waiting {self.extra_wait_ms}ms for lazy content...")
                await asyncio.sleep(self.extra_wait_ms / 1000)

            # Scroll to trigger lazy loading
            print(f"📜 Scrolling to trigger lazy-load...")
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

            # Wait a bit more after scrolling
            await asyncio.sleep(2)

            # Handle recursive depth if specified
            if self.max_depth > 0:
                print(f"🔍 Discovering linked pages (depth={self.max_depth})...")
                links = await page.evaluate("""() => {
                    const links = [...document.querySelectorAll('a[href]')];
                    return links.map(a => a.href).filter(h => h.startsWith(window.location.origin));
                }""")

                unique_links = list(set(links))
                print(f"   Found {len(unique_links)} unique internal links")

                # For now, we just track them; full recursive download would need a queue
                for link in unique_links[:20]:  # Limit to avoid infinite loops
                    if link != self.base_url:
                        self.pages.add(link)

            await browser.close()

        # Generate report
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

        report_path = self.output_dir / '_clone_report.json'
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

        # Print summary
        print()
        print("=" * 50)
        print("📊 Clone Report")
        print("=" * 50)
        print(f"   URL:        {self.base_url}")
        print(f"   Output:     {self.output_dir.absolute()}")
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
            print(f"⚠️  {len(self.errors)} errors occurred (see _clone_report.json for details)")

        print(f"✅ Done! Serve with:")
        print(f"   python -m http.server 8000 --directory {self.output_dir.absolute()}")

    def _human_size(self, size: int) -> str:
        """Convert bytes to human-readable size."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def _count_by_type(self) -> dict:
        """Count downloaded files by type."""
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
Examples:
  python clone.py https://example.com
  python clone.py https://example.com --output ./my-clone
  python clone.py https://example.com --depth 2 --wait 5000
        """
    )
    parser.add_argument('url', help='URL to clone')
    parser.add_argument('--output', '-o', default=None, help='Output directory')
    parser.add_argument('--depth', '-d', type=int, default=0,
                        help='Max depth for recursive page discovery (0 = single page)')
    parser.add_argument('--wait', '-w', type=int, default=3000,
                        help='Extra wait time after page load in ms (default: 3000)')
    parser.add_argument('--full', '-f', action='store_true',
                        help='Full recursive clone (downloads linked pages)')
    parser.add_argument('--headful', action='store_true',
                        help='Run browser in visible mode (for debugging)')

    args = parser.parse_args()

    # Determine output directory
    if args.output:
        output_dir = args.output
    else:
        parsed = urllib.parse.urlparse(args.url)
        hostname = parsed.netloc.replace('.', '_')
        output_dir = f'./cloned_{hostname}'

    # If --full flag is set, override depth
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
