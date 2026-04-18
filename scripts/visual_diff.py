#!/usr/bin/env python3
"""
Visual Comparison Script
Compares original and cloned websites visually.
"""

import argparse
import os
import difflib
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image
import numpy as np


def capture_screenshot(url: str, output: str, fullpage: bool = False, breakpoint: str = "desktop") -> str:
    """Capture screenshot of a URL."""
    viewports = {
        "mobile": {"width": 375, "height": 667},
        "tablet": {"width": 768, "height": 1024},
        "desktop": {"width": 1920, "height": 1080},
    }
    
    vp = viewports.get(breakpoint, viewports["desktop"])
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_viewport(size=vp)
        page = context.new_page()
        
        if fullpage:
            page.set_viewport_size({"width": vp["width"], "height": 10000})
        
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.screenshot(full_page=fullpage, path=output)
        browser.close()
    
    return output


def compare_images(img1_path: str, img2_path: str) -> dict:
    """Compare two images and return diff metrics."""
    img1 = Image.open(img1_path).convert("RGB")
    img2 = Image.open(img2_path).convert("RGB")
    
    # Resize to match
    if img1.size != img2.size:
        img2 = img2.resize(img1.size)
    
    # Calculate difference
    arr1 = np.array(img1)
    arr2 = np.array(img2)
    
    diff = np.abs(arr1.astype(float) - arr2.astype(float))
    diff_pct = (diff.sum() / (arr1.size * 255)) * 100
    
    # Similarity
    similarity = 100 - diff_pct
    
    return {
        "similarity_percent": round(similarity, 2),
        "diff_percent": round(diff_pct, 2),
        "passed": similarity >= 95,
    }


def visual_diff(original_url: str, cloned_dir: str, output: str = "./diff", 
             breakpoints: list = None, fullpage: bool = False, threshold: float = 95) -> dict:
    """Run visual comparison."""
    breakpoints = breakpoints or ["mobile", "tablet", "desktop"]
    
    os.makedirs(output, exist_ok=True)
    
    results = {}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        for bp in breakpoints:
            print(f"Comparing {bp}...")
            
            vp = {"mobile": 375, "tablet": 768, "desktop": 1920}[bp]
            
            # Screenshot original
            page = browser.new_page()
            page.set_viewport_size({"width": vp, "height": 800})
            page.goto(original_url, wait_until="networkidle", timeout=30000)
            orig_path = f"{output}/{bp}_original.png"
            page.screenshot(path=orig_path)
            
            # Screenshot cloned (local file)
            cloned_path = f"{cloned_dir}/index.html"
            if os.path.exists(cloned_path):
                page.goto(f"file://{os.path.abspath(cloned_path)}", wait_until="networkidle")
                cloned_img_path = f"{output}/{bp}_cloned.png"
                page.screenshot(path=cloned_img_path)
                
                # Compare
                cmp_result = compare_images(orig_path, cloned_img_path)
                results[bp] = cmp_result
                
                print(f"  {bp}: {cmp_result['similarity_percent']}% match")
            else:
                results[bp] = {"error": "Cloned index.html not found"}
        
        browser.close()
    
    # Summary
    passed = all(r.get("passed", False) for r in results.values())
    avg_similarity = sum(r.get("similarity_percent", 0) for r in results.values()) / len(results)
    
    summary = {
        "results": results,
        "average_similarity": round(avg_similarity, 2),
        "passed": passed,
    }
    
    # Save report
    import json
    with open(f"{output}/diff_report.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n✓ Visual diff complete: {avg_similarity}% match")
    print(f"  {'✅ PASSED' if passed else '❌ FAILED'}")
    print(f"  Report: {output}/diff_report.json")
    
    return summary


def main():
    parser = argparse.ArgumentParser(description="Visual comparison of original and cloned sites")
    parser.add_argument("original_url", help="Original site URL")
    parser.add_argument("cloned_dir", help="Cloned site directory")
    parser.add_argument("--output", "-o", default="./diff", help="Output directory")
    parser.add_argument("--breakpoints", "-b", nargs="+", 
                       default=["mobile", "tablet", "desktop"],
                       help="Breakpoints to test")
    parser.add_argument("--fullpage", "-f", action="store_true", help="Compare full page")
    parser.add_argument("--threshold", "-t", type=float, default=95, 
                       help="Match threshold %")
    args = parser.parse_args()
    
    visual_diff(args.original_url, args.cloned_dir, args.output, 
              args.breakpoints, args.fullpage, args.threshold)


if __name__ == "__main__":
    main()