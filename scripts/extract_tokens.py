#!/usr/bin/env python3
"""
Design Token Extraction Script
Extracts colors, typography, spacing, and animation tokens from a website.
"""

import argparse
import json
import re
from playwright.sync_api import sync_playwright


def extract_tokens(url: str, wait: int = 3000, fullpage: bool = False) -> dict:
    """Extract design tokens from a URL."""
    tokens = {
        "colors": {},
        "typography": {},
        "spacing": {},
        "borders": {},
        "animations": {},
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(wait)

        if fullpage:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)

        # Extract computed styles
        styles = page.evaluate("""
            () => {
                const tokens = {
                    colors: {},
                    typography: {},
                    spacing: {},
                    borders: {},
                    animations: {}
                };
                const computed = getComputedStyle(document.body);
                
                // Colors
                const colorProps = ['color', 'backgroundColor', 'background', 'borderColor', 
                                 'outlineColor', 'textDecorationColor'];
                colorProps.forEach(prop => {
                    try {
                        const val = computed.getPropertyValue(prop).trim();
                        if (val && val !== 'rgba(0, 0, 0, 0)' && val !== 'transparent') {
                            tokens.colors[prop] = val;
                        }
                    } catch (e) {}
                });

                // Typography
                const fontProps = ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 
                               'letterSpacing', 'textTransform'];
                fontProps.forEach(prop => {
                    try {
                        const val = computed.getPropertyValue(prop).trim();
                        if (val) tokens.typography[prop] = val;
                    } catch (e) {}
                });

                // Spacing
                const spaceProps = ['margin', 'padding', 'gap', 'gridGap', 'rowGap', 'columnGap'];
                spaceProps.forEach(prop => {
                    try {
                        const val = computed.getPropertyValue(prop).trim();
                        if (val && val !== '0px') tokens.spacing[prop] = val;
                    } catch (e) {}
                });

                // Borders
                const borderProps = ['borderWidth', 'borderStyle', 'borderRadius', 
                                     'borderColor', 'outlineWidth', 'outlineStyle'];
                borderProps.forEach(prop => {
                    try {
                        const val = computed.getPropertyValue(prop).trim();
                        if (val && val !== 'none') tokens.borders[prop] = val;
                    } catch (e) {}
                });

                // Animation (from CSS rules)
                const sheets = document.styleSheets;
                try {
                    for (let i = 0; i < sheets.length; i++) {
                        try {
                            const rules = sheets[i].cssRules || sheets[i].rules;
                            for (let j = 0; j < rules.length; j++) {
                                const rule = rules[j];
                                if (rule.type === CSSRule.KEYFRAMES_RULE) {
                                    tokens.animations[rule.name] = rule.cssText;
                                }
                                if (rule.style && rule.style.transition) {
                                    tokens.animations['transition'] = rule.style.transition;
                                }
                            }
                        } catch (e) {}
                    }
                } catch (e) {}

                return tokens;
            }
        """)

        for key, val in styles.items():
            if val:
                tokens[key].update(val)

        browser.close()

    return tokens


def main():
    parser = argparse.ArgumentParser(description="Extract design tokens from a website")
    parser.add_argument("url", help="Target URL")
    parser.add_argument("--output", "-o", default="./tokens", help="Output directory")
    parser.add_argument("--wait", "-w", type=int, default=3000, help="Wait time (ms)")
    parser.add_argument("--fullpage", "-f", action="store_true", help="Scroll full page first")
    args = parser.parse_args()

    print(f"Extracting tokens from {args.url}...")
    tokens = extract_tokens(args.url, args.wait, args.fullpage)

    output_file = f"{args.output}/design-tokens.json"
    with open(output_file, "w") as f:
        json.dump(tokens, f, indent=2)

    print(f"✓ Tokens saved to {output_file}")
    print(f"  - {len(tokens.get('colors', {}))} colors")
    print(f"  - {len(tokens.get('typography', {}))} typography styles")
    print(f"  - {len(tokens.get('spacing', {}))} spacing values")


if __name__ == "__main__":
    main()