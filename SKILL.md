---
name: website-clone
description: >
  Download any website's full source code (HTML/CSS/JS/images/fonts) and refactor it into a clean project.
  Use when the user wants to clone, mirror, copy, or replicate a website.
  Supports both static sites (via wget/httrack) and SPA/JS-rendered sites (via Playwright).
  Workflow: 1) Download assets → 2) Analyze → 3) Refactor → 4) Fix missing parts.
user-invocable: true
argument-hint: "<url> [options: --output <dir> --depth <n> --download-cdn]"
---

# Website Clone Skill

Download any website's complete source code and refactor it into a clean, working project.

## Overview

This skill provides a **3-step workflow** for cloning websites:

```
Step 1: Download    →  Fetch all assets (HTML/CSS/JS/images/fonts)
Step 2: Analyze     →  Identify tech stack, framework, and structure
Step 3: Refactor    →  Rebuild into clean code, fix missing parts
```

## Prerequisites

**Required tools:**

| Tool | Purpose | Install |
|------|---------|---------|
| **Python 3.9+** | Run download scripts | `python --version` |
| **Browser** | Chrome, Edge, or Playwright Chromium | See below |
| **wget** (optional) | Static site download | Built-in on Linux/macOS |
| **httrack** (optional) | Static site download (advanced) | `choco install httrack` |

**Browser auto-detection** (in order):
1. **System Chrome** — if installed, used automatically (most common)
2. **System Edge** — fallback if Chrome not found
3. **Playwright Chromium** — `pip install playwright && python -m playwright install chromium`

> **Most users already have Chrome or Edge — no extra setup needed!**

## Workflow

### Step 1: Download Assets

**Choose the right tool based on site type:**

| Site Type | Tool | Command |
|-----------|------|---------|
| Static site (WordPress, docs, blogs) | wget or httrack | See below |
| SPA/JS-rendered (React, Vue, Next.js) | Playwright script | See below |
| Unsure | Let the agent decide | Agent checks first |

#### Option A: Playwright (for SPA/JS-rendered sites)

```bash
python scripts/clone.py <url> [--output <dir>]
```

**What it does:**
1. Launches headless Chromium
2. Navigates to the URL, waits for full render
3. Intercepts ALL network requests (HTML, CSS, JS, images, fonts, XHR)
4. Saves everything to `output/` with original directory structure
5. Rewrites URLs in HTML/CSS to point to local files
6. Scrolls page to trigger lazy-loaded content
7. Optionally discovers and downloads linked pages (--depth)

**Example:**
```bash
python scripts/clone.py https://example.com --output ./cloned-site
```

#### Option B: wget (for static sites)

```bash
wget --mirror --convert-links --adjust-extension --page-requisites --no-parent -P <output-dir> <url>
```

**Flags explained:**
- `--mirror` — Recursive download
- `--convert-links` — Rewrite links for offline viewing
- `--page-requisites` — Download CSS, images, etc. needed to display the page
- `--no-parent` — Don't ascend to parent directories

#### Option C: httrack (for static sites, most thorough)

```bash
httrack <url> -O <output-dir> -%v --depth=5
```

### Step 2: Analyze Downloaded Content

After download, the agent reads the downloaded files to identify:

1. **Tech Stack** — Framework (React/Vue/Next.js/Nuxt.js), bundler (webpack/vite), CSS framework (Tailwind/Bootstrap)
2. **Structure** — Component files, page directories, asset directories
3. **Third-party libs** — GSAP, Locomotive Scroll, Framer Motion, etc.
4. **Build artifacts** — Minified JS/CSS that needs cleanup
5. **Missing resources** — CDN-loaded assets that weren't captured

**Analysis commands:**
```bash
# Check for framework indicators
grep -r "react" output/ --include="*.js" | head -5
grep -r "next" output/ --include="*.js" | head -5
grep -r "vue" output/ --include="*.js" | head -5

# Check for CSS framework
ls output/static/css/  # Tailwind, Bootstrap, etc.
grep -r "tailwind" output/ --include="*.css" | head -3

# Check for animation libraries
grep -r "gsap\|framer\|locomotive" output/ --include="*.js" | head -5
```

### Step 3: Refactor

Based on the analysis, the agent:

1. **Creates a clean project structure** (e.g., Next.js + Tailwind)
2. **Extracts and organizes assets** (images, fonts, SVGs)
3. **Rewrites CSS** — Convert to Tailwind or clean CSS modules
4. **Rebuilds components** — Convert minified JS to readable React components
5. **Fixes paths** — Ensure all relative paths work correctly
6. **Handles missing parts** — Generate placeholder content for uncaptured resources
7. **Verifies build** — `npm run build` must pass

## Script Reference

### scripts/clone.py — Main download script

```
Usage: python scripts/clone.py <url> [options]

Options:
  --output <dir>   Output directory (default: ./cloned_<hostname>)
  --depth <n>      Max click depth for recursive pages (default: 0 = single page only)
  --wait <ms>      Extra wait time after page load in ms (default: 3000)
  --full           Download all linked pages recursively (uses BFS, depth=2)
  --headful        Run browser in visible mode (for debugging)
  --download-cdn   Also download CDN resources (fonts, libs, etc.)
```

**Example usage:**
```bash
# Single page clone
python scripts/clone.py https://example.com

# Custom output directory
python scripts/clone.py https://example.com --output ./my-clone

# Wait longer for slow sites
python scripts/clone.py https://example.com --wait 5000

# Recursive clone (download linked pages too, BFS traversal)
python scripts/clone.py https://example.com --depth 2

# Include CDN resources
python scripts/clone.py https://example.com --download-cdn
```

### scripts/path_rewriter.py — Path rewriting utility

Standalone tool to rewrite URLs in existing cloned files.

```
Usage: python scripts/path_rewriter.py <directory> <base-url>

Options:
  --cdn-dir <dir>  Directory name for CDN resources (default: _cdn)
  --keep-cdn       Keep CDN URLs as-is instead of rewriting

Example:
python scripts/path_rewriter.py ./cloned-site https://example.com
python scripts/path_rewriter.py ./cloned-site https://example.com --keep-cdn
```

## Output Structure

After cloning, the output directory looks like:

```
cloned_example.com/
├── index.html              # Main page (URLs rewritten to local)
├── about.html              # Additional pages (if --depth > 0)
├── static/
│   ├── css/
│   │   ├── main.a1b2c3.css
│   │   └── vendor.d4e5f6.css
│   ├── js/
│   │   ├── main.g7h8i9.js
│   │   └── vendor.j0k1l2.js
│   └── images/
│       ├── hero.webp
│       └── logo.svg
├── fonts/
│   └── inter-var.woff2
├── _cdn/                   # CDN resources (if --download-cdn)
│   ├── fonts_googleapis_com/
│   └── cdn_jsdelivr_net/
└── _clone_report.json      # Metadata about the clone
```

## Common Issues & Solutions

### Issue: "No browser found" error
**Cause:** No Chrome, Edge, or Playwright Chromium detected.
**Solution:** Install Google Chrome or Microsoft Edge. Or run `pip install playwright && python -m playwright install chromium`. Note: Python 3.14+ is not yet fully supported by Playwright; use Python 3.9–3.13 for best results.

### Issue: Images are broken
**Cause:** Images loaded from CDN or lazy-loaded after scroll.
**Solution:** Increase `--wait` time, or use `--download-cdn` to include CDN resources.

### Issue: CSS is minified and unreadable
**Cause:** Production build output.
**Solution:** Use a CSS beautifier, or the refactoring step will rebuild styles from scratch.

### Issue: Fonts not loading
**Cause:** Google Fonts or self-hosted fonts not captured.
**Solution:** Check `_clone_report.json` for missing font URLs, use `--download-cdn` flag, or download manually.

### Issue: API calls return 404
**Cause:** Dynamic data from backend API.
**Solution:** This is expected — API responses can't be cloned. Use mock data in the refactored version.

### Issue: Multi-page clone seems stuck
**Cause:** Site has many internal links.
**Solution:** Use `--depth 1` instead of `--full` to limit recursion. The script uses BFS so it won't infinite-loop.

## Best Practices

1. **Always use Playwright for modern sites** — wget/httrack miss JS-rendered content
2. **Check the clone report** — `_clone_report.json` lists all captured and missing resources
3. **Start with single page** — Test with one page before doing full recursive clone
4. **Refactor incrementally** — Build section by section, verify each step
5. **Preserve animations** — Note which animation libraries are used before rebuilding
6. **Use --download-cdn sparingly** — Only when you need specific CDN fonts/libs locally

## Token Optimization Tips

When using this skill with an AI agent:

1. **Download first, analyze second** — Don't try to extract info via browser MCP; download the files and read them directly
2. **Read only what's needed** — Don't read all JS files; grep for framework indicators first
3. **Use the clone report** — `_clone_report.json` gives you a structured summary without reading hundreds of files
4. **Refactor from scratch** — For complex sites, it's cheaper to rebuild with clean code than to patch minified output
5. **Python Version** — Ensure you are using Python 3.9–3.13. Python 3.14+ may have compatibility issues with Playwright dependencies.
