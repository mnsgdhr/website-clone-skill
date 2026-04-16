#!/usr/bin/env python3
"""
path_rewriter.py — URL rewriting utility for cloned websites

Rewrites URLs in HTML and CSS files to point to local paths.
Can be used standalone to fix a downloaded website, or imported as a module.

Usage:
    python path_rewriter.py <directory> <base-url>

Example:
    python path_rewriter.py ./cloned-site https://example.com
    python path_rewriter.py ./cloned-site https://example.com --cdn-dir _cdn --keep-cdn
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path


# Common CDN domains
CDN_DOMAINS = {
    'fonts.googleapis.com', 'fonts.gstatic.com',
    'cdn.jsdelivr.net', 'unpkg.com', 'cdnjs.cloudflare.com',
    'ajax.googleapis.com', 'code.jquery.com',
    'stackpath.bootstrapcdn.com', 'cdn.bootcss.com',
}


class PathRewriter:
    """Rewrite URLs in HTML/CSS files to point to local paths."""

    SKIP_PATTERNS = [
        re.compile(r'^data:', re.IGNORECASE),
        re.compile(r'^blob:', re.IGNORECASE),
        re.compile(r'^chrome-extension:', re.IGNORECASE),
        re.compile(r'^devtools:', re.IGNORECASE),
    ]

    def __init__(self, directory: str, base_url: str,
                 cdn_dir: str = "_cdn", keep_cdn: bool = False):
        self.directory = Path(directory)
        self.base_url = base_url.rstrip('/')
        self.cdn_dir = cdn_dir
        self.keep_cdn = keep_cdn

        parsed = urllib.parse.urlparse(base_url)
        self.base_origin = f"{parsed.scheme}://{parsed.netloc}"

        self.rewritten_files = []
        self.errors = []

    def _should_skip(self, url: str) -> bool:
        for pattern in self.SKIP_PATTERNS:
            if pattern.match(url):
                return True
        return False

    def _is_cdn(self, url: str) -> bool:
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.netloc in CDN_DOMAINS
        except Exception:
            return False

    def _is_same_origin(self, url: str) -> bool:
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.scheme + "://" + parsed.netloc == self.base_origin
        except Exception:
            return False

    def _url_to_local_path(self, url: str) -> str:
        """Convert a URL to a relative local path."""
        parsed = urllib.parse.urlparse(url)

        if not self._is_same_origin(url):
            safe_host = parsed.netloc.replace('.', '_')
            rel_path = f"{self.cdn_dir}/{safe_host}{parsed.path}"
        else:
            rel_path = parsed.path.lstrip('/') or 'index.html'

        # Clean up
        if not rel_path.endswith(('.html', '.htm')):
            rel_path = re.split(r'[?#]', rel_path)[0]
        if rel_path.endswith('/'):
            rel_path += 'index.html'

        return rel_path

    def rewrite_html(self, html_content: str, page_url: str) -> str:
        """Rewrite all URLs in HTML content."""
        # href and src
        def replace_url(match):
            full = match.group(0)
            url = match.group(1) or match.group(2) or ''
            if not url or self._should_skip(url):
                return full
            resolved = urllib.parse.urljoin(page_url, url)
            if not self._is_same_origin(resolved):
                if self._is_cdn(resolved) and self.keep_cdn:
                    return full
                local = self._url_to_local_path(resolved)
                return full.replace(url, local)
            local = self._url_to_local_path(resolved)
            return full.replace(url, local)

        html_content = re.sub(
            r'(?:href|src)=["\']([^"\']+)["\']',
            replace_url,
            html_content
        )

        # srcset
        def replace_srcset(match):
            full = match.group(0)
            urls = re.findall(r'([^\s,]+)(?:\s+\d+[wx])?', full)
            new_parts = []
            for url in urls:
                if self._should_skip(url):
                    new_parts.append(url)
                    continue
                resolved = urllib.parse.urljoin(page_url, url)
                if not self._is_same_origin(resolved) and self.keep_cdn and self._is_cdn(resolved):
                    new_parts.append(url)
                else:
                    local = self._url_to_local_path(resolved)
                    new_parts.append(local)
            return 'srcset="' + ', '.join(new_parts) + '"'

        html_content = re.sub(r'srcset=["\']([^"\']+)["\']', replace_srcset, html_content)

        # style url()
        def replace_style_url(match):
            full = match.group(0)
            url = match.group(1)
            if not url or self._should_skip(url):
                return full
            resolved = urllib.parse.urljoin(page_url, url)
            if not self._is_same_origin(resolved) and self.keep_cdn and self._is_cdn(resolved):
                return full
            local = self._url_to_local_path(resolved)
            return f'url("{local}")'

        html_content = re.sub(r'url\(["\']?([^)"\']+)["\']?\)', replace_style_url, html_content)

        return html_content

    def rewrite_css(self, css_content: str, css_url: str) -> str:
        """Rewrite all URLs in CSS content."""
        def replace_url(match):
            url = match.group(1)
            if not url or self._should_skip(url):
                return match.group(0)
            resolved = urllib.parse.urljoin(css_url, url)
            if not self._is_same_origin(resolved):
                if self._is_cdn(resolved) and self.keep_cdn:
                    return match.group(0)
                local = self._url_to_local_path(resolved)
                return f'url("{local}")'
            local = self._url_to_local_path(resolved)
            return f'url("{local}")'

        css_content = re.sub(r'url\(["\']?([^)"\']+)["\']?\)', replace_url, css_content)

        # @import
        def replace_import(match):
            full = match.group(0)
            url = match.group(1) or match.group(2)
            if not url or self._should_skip(url):
                return full
            resolved = urllib.parse.urljoin(css_url, url)
            if not self._is_same_origin(resolved) and self.keep_cdn and self._is_cdn(resolved):
                return full
            local = self._url_to_local_path(resolved)
            return f'@import url("{local}");'

        css_content = re.sub(
            r'@import\s+(?:url\(["\']?([^)"\']+)["\']?\)|["\']([^"\']+)["\'])',
            replace_import,
            css_content
        )

        return css_content

    def run(self):
        """Rewrite all HTML/CSS files in the directory."""
        print(f"🔄 Rewriting URLs in: {self.directory.absolute()}")
        print(f"🌐 Base URL: {self.base_url}")
        print(f"📦 CDN handling: {'keep remote' if self.keep_cdn else 'rewrite to local'}")
        print()

        for html_file in self.directory.rglob('*.html'):
            try:
                content = html_file.read_text(encoding='utf-8', errors='replace')
                # Use file path as pseudo-URL for resolution
                pseudo_url = self.base_url + str(html_file.relative_to(self.directory)).replace('\\', '/')
                if not pseudo_url.endswith('.html'):
                    pseudo_url += '.html'

                new_content = self.rewrite_html(content, pseudo_url)
                if new_content != content:
                    html_file.write_text(new_content, encoding='utf-8')
                    self.rewritten_files.append(str(html_file.relative_to(self.directory)))
                    print(f"   ✏️  {html_file.relative_to(self.directory)}")
            except Exception as e:
                self.errors.append({'file': str(html_file), 'error': str(e)})

        for css_file in self.directory.rglob('*.css'):
            try:
                content = css_file.read_text(encoding='utf-8', errors='replace')
                pseudo_url = self.base_url + str(css_file.relative_to(self.directory)).replace('\\', '/')
                new_content = self.rewrite_css(content, pseudo_url)
                if new_content != content:
                    css_file.write_text(new_content, encoding='utf-8')
                    self.rewritten_files.append(str(css_file.relative_to(self.directory)))
                    print(f"   ✏️  {css_file.relative_to(self.directory)}")
            except Exception as e:
                self.errors.append({'file': str(css_file), 'error': str(e)})

        print()
        print(f"✅ Rewrote {len(self.rewritten_files)} files")
        if self.errors:
            print(f"⚠️  {len(self.errors)} errors")


def main():
    parser = argparse.ArgumentParser(
        description='Rewrite URLs in cloned website files to local paths'
    )
    parser.add_argument('directory', help='Directory containing cloned files')
    parser.add_argument('base_url', help='Original base URL of the website')
    parser.add_argument('--cdn-dir', default='_cdn',
                        help='Directory name for CDN resources (default: _cdn)')
    parser.add_argument('--keep-cdn', action='store_true',
                        help='Keep CDN URLs as-is instead of rewriting')

    args = parser.parse_args()

    rewriter = PathRewriter(
        directory=args.directory,
        base_url=args.base_url,
        cdn_dir=args.cdn_dir,
        keep_cdn=args.keep_cdn,
    )
    rewriter.run()


if __name__ == '__main__':
    main()
