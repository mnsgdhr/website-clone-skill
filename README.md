# 🌐 Website Clone Skill

> Download any website's complete source code, analyze it, and refactor into a clean project. Built for AI agents.

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Playwright](https://img.shields.io/badge/Powered%20by-Playwright-green.svg)](https://playwright.dev)

---

## ✨ Features

- **🎯 Complete asset capture** — HTML, CSS, JS, images, fonts, XHR/fetch responses
- **🤖 SPA-friendly** — Uses Playwright to execute JS, capturing fully-rendered content
- **🔄 URL rewriting** — Automatically rewrites links in HTML/CSS to work offline
- **📊 Clone report** — Generates structured JSON report of all captured resources
- ** Refactoring workflow** — Step-by-step guide to rebuild cloned sites into clean code
- ** AI Agent ready** — SKILL.md format for direct installation by AI agents

---

## 🚀 Quick Start

### Install

```bash
# Clone this repo
git clone https://github.com/mnsgdhr/website-clone-skill.git
cd website-clone-skill

# Install dependencies
pip install -r requirements.txt

# Browser: auto-detected!
#   1. System Chrome/Edge (if installed) — no extra setup needed
#   2. Playwright Chromium (fallback): python -m playwright install chromium
```

### Clone a Website

```bash
# Basic: single page
python scripts/clone.py https://example.com

# Custom output directory
python scripts/clone.py https://example.com --output ./my-clone

# Wait longer for lazy-loaded content
python scripts/clone.py https://example.com --wait 5000

# Recursive: discover and download linked pages
python scripts/clone.py https://example.com --depth 2

# Debug: see the browser window
python scripts/clone.py https://example.com --headful
```

### Serve Locally

```bash
python -m http.server 8000 --directory cloned_example.com
# Open http://localhost:8000
```

---

## 📋 Workflow

This skill implements a **3-step workflow** optimized for AI agents:

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Step 1      │    │  Step 2      │    │  Step 3      │
│  Download    │───>│  Analyze     │───>│  Refactor    │
│              │    │              │    │              │
│ • Playwright │    │ • Tech stack │    │ • Clean code │
│ • All assets │    │ • Structure  │    │ • Fix paths  │
│ • URL rewrite│    │ • Missing    │    │ • Rebuild    │
└──────────────┘    └──────────────┘    └──────────────┘
```

### Step 1: Download

Choose the right tool based on site type:

| Site Type | Tool | Why |
|-----------|------|-----|
| **SPA / JS-rendered** (React, Vue, Next.js) | `clone.py` (Playwright) | Executes JS, captures dynamic content |
| **Static site** (WordPress, docs) | `wget` or `httrack` | Fast, no browser needed |

### Step 2: Analyze

After download, the agent reads `_clone_report.json` and key files to identify:

- **Framework**: React, Vue, Next.js, Nuxt.js, etc.
- **CSS approach**: Tailwind, Bootstrap, CSS Modules, styled-components
- **Animation libs**: GSAP, Framer Motion, Locomotive Scroll
- **Build setup**: webpack, Vite, esbuild
- **Missing resources**: CDN assets, API data

### Step 3: Refactor

Rebuild the site with clean architecture:

1. Create new project scaffold (Next.js + Tailwind recommended)
2. Extract and organize assets (images, fonts, SVGs)
3. Rebuild components from minified source
4. Rewrite styles with clean CSS/Tailwind
5. Handle missing data with mock content
6. Verify build passes

---

## 📁 Project Structure

```
website-clone-skill/
├── SKILL.md                  # AI agent skill definition
├── README.md                 # This file
├── LICENSE                   # MIT License
├── requirements.txt          # Python dependencies
├── scripts/
│   ├── clone.py              # Main download script (Playwright)
│   └── path_rewriter.py      # URL rewriting utility
└── examples/                 # Example clone reports (optional)
```

---

## 🛠️ Script Reference

### clone.py

```
Usage: python scripts/clone.py <url> [options]

Required:
  url                     URL to clone

Options:
  -o, --output DIR        Output directory (default: ./cloned_<hostname>)
  -d, --depth N           Max depth for page discovery (0 = single page)
  -w, --wait MS           Extra wait time after load in ms (default: 3000)
  -f, --full              Full recursive clone (sets depth=2)
  --headful               Run browser in visible mode
  -h, --help              Show help
```

### Output

```
cloned_example.com/
├── index.html              # Main page (URLs rewritten)
├── about.html              # Additional pages (if --depth > 0)
├── static/
│   ├── css/
│   ├── js/
│   └── images/
├── fonts/
└── _clone_report.json      # Structured clone metadata
```

---

## 🤖 AI Agent Integration

### Install as Skill

For AI agents that support SKILL.md format:

```bash
# Install to agent's skills directory
cp -r website-clone-skill ~/.agents/skills/website-clone
```

### Usage in Agent Prompt

```
Use the website-clone skill to download https://example.com:

1. Run: python scripts/clone.py https://example.com --output ./target-site
2. Read: ./target-site/_clone_report.json for resource summary
3. Analyze the tech stack from downloaded files
4. Refactor into a clean project
```

### Token Optimization

When using with LLM agents:

1. **Download first, read second** — Files are cheaper to read than extracting via browser MCP
2. **Use clone report** — `_clone_report.json` gives structured summary without reading hundreds of files
3. **Read selectively** — grep for framework indicators before reading full files
4. **Rebuild, don't patch** — For complex sites, rebuilding from scratch is cheaper than patching minified code

---

##  Browser Detection

The script **auto-detects** an available browser (no config needed):

| Priority | Browser | Notes |
|----------|---------|-------|
| 1 | **System Chrome** | `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| 2 | **System Edge** | `C:\Program Files\Microsoft\Edge\Application\msedge.exe` |
| 3 | **Playwright Chromium** | Fallback if system browser not found |

**Most users have Chrome or Edge installed — no extra download needed!**

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| `No browser found` | Install Chrome or Edge, or run `python -m playwright install chromium` |
| Page is blank after download | Site needs JS — `clone.py` handles this automatically |
| Images broken | Increase `--wait` time for lazy-loaded images |
| CSS minified | Refactoring step rebuilds styles from scratch |
| API calls return 404 | Expected — use mock data in refactored version |

---

## 📝 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Credits

Inspired by and built upon:
- [zebbern/website-clone](https://github.com/zebbern/website-clone) — Python web cloning approach
- [GorvGoyl/Clone-Wars](https://github.com/GorvGoyl/Clone-Wars) — Clone project curation
- [JCodesMore/ai-website-cloner-template](https://github.com/JCodesMore/ai-website-cloner-template) — AI agent cloning workflow

---

## 🤝 Contributing

Contributions welcome! Areas for improvement:

- [ ] Better CSS URL rewriting for complex cases
- [ ] Support for service workers / PWA resources
- [ ] Automatic framework detection from downloaded files
- [ ] Built-in refactoring templates
- [ ] Multi-page recursive download with queue management
