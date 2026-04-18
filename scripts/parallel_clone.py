#!/usr/bin/env python3
"""
Parallel Worktree Clone Script
Clones a website using parallel worktrees for faster processing.
"""

import argparse
import os
import json
import subprocess
import concurrent.futures
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright


def discover_pages(url: str, max_depth: int = 2) -> list:
    """Discover all pages in a website."""
    discovered = set()
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        def crawl(current_url: str, depth: int = 0):
            if depth > max_depth:
                return
            if current_url in discovered:
                return
            
            discovered.add(current_url)
            
            try:
                page.goto(current_url, wait_until="networkidle", timeout=10000)
                links = page.query_selector_all("a[href]")
                
                for link in links:
                    try:
                        href = link.get_attribute("href")
                        if not href:
                            continue
                        if href.startswith("#"):
                            continue
                        if href.startswith("mailto:") or href.startswith("tel:"):
                            continue
                        if href.startswith("http") and parsed.netloc not in href:
                            continue
                        
                        full_url = urljoin(current_url, href)
                        if parsed.netloc in full_url and full_url not in discovered:
                            crawl(full_url, depth + 1)
                    except Exception:
                        continue
            except Exception:
                pass
        
        crawl(url)
        browser.close()
    
    return list(discovered)


def clone_single_page(url: str, output_dir: str) -> bool:
    """Clone a single page."""
    import subprocess
    
    try:
        cmd = [
            "python", "-c",
            f"""
import sys
sys.path.insert(0, '.')
from clone import clone_page
clone_page('{url}', '{output_dir}')
"""
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        return True
    except Exception as e:
        print(f"Error cloning {url}: {e}")
        return False


def parallel_clone(url: str, workers: int = 4, output: str = None, depth: int = 2) -> dict:
    """Clone website using parallel worktrees."""
    
    print(f"Discovering pages from {url}...")
    pages = discover_pages(url, depth)
    print(f"Found {len(pages)} pages")
    
    if not output:
        parsed = urlparse(url)
        output = f"cloned_{parsed.netloc}"
    
    os.makedirs(output, exist_ok=True)
    
    # Split pages into chunks for workers
    chunk_size = max(1, len(pages) // workers)
    chunks = [pages[i:i + chunk_size] for i in range(0, len(pages), chunk_size)]
    
    print(f"Processing with {workers} workers...")
    
    results = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        
        for i, chunk in enumerate(chunks):
            worktree_dir = f"{output}/worktree_{i}"
            os.makedirs(worktree_dir, exist_ok=True)
            
            future = executor.submit(clone_batch, chunk, worktree_dir)
            futures[future] = i
        
        for future in concurrent.futures.as_completed(futures):
            i = futures[future]
            try:
                results[i] = future.result()
            except Exception as e:
                results[i] = {"error": str(e)}
    
    # Merge results
    merge_results(output, workers)
    
    return {
        "total_pages": len(pages),
        "workers": workers,
        "output": output,
        "results": results,
    }


def clone_batch(pages: list, output_dir: str) -> dict:
    """Clone a batch of pages."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        for page_url in pages:
            try:
                page = browser.new_page()
                page.goto(page_url, wait_until="networkidle", timeout=30000)
                
                # Save HTML
                from urllib.parse import urlparse, unquote
                path = unquote(urlparse(page_url).path)
                if path == "/" or path == "":
                    path = "/index.html"
                elif not path.endswith(".html"):
                    path = path.rstrip("/") + "/index.html"
                
                out_path = os.path.join(output_dir, path.lstrip("/"))
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                
                html = page.content()
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(html)
                
                page.close()
            except Exception as e:
                print(f"Error: {e}")
                continue
        
        browser.close()
    
    return {"pages": len(pages)}


def merge_results(base_dir: str, num_workers: int):
    """Merge worktree results into unified output."""
    import shutil
    
    for i in range(num_workers):
        worktree = f"{base_dir}/worktree_{i}"
        if not os.path.exists(worktree):
            continue
        
        for root, dirs, files in os.walk(worktree):
            for f in files:
                src = os.path.join(root, f)
                rel = os.path.relpath(src, worktree)
                dst = os.path.join(base_dir, rel)
                
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
    
    # Cleanup worktrees
    for i in range(num_workers):
        worktree = f"{base_dir}/worktree_{i}"
        if os.path.exists(worktree):
            shutil.rmtree(worktree)
    
    print(f"✓ Merged into {base_dir}")


def main():
    parser = argparse.ArgumentParser(description="Parallel website cloning")
    parser.add_argument("url", help="Target URL")
    parser.add_argument("--workers", "-w", type=int, default=4, help="Number of workers")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--depth", "-d", type=int, default=2, help="Max recursion depth")
    args = parser.parse_args()
    
    result = parallel_clone(args.url, args.workers, args.output, args.depth)
    
    print(f"\n✓ Clone complete!")
    print(f"  Pages: {result['total_pages']}")
    print(f"  Workers: {result['workers']}")
    print(f"  Output: {result['output']}")


if __name__ == "__main__":
    main()