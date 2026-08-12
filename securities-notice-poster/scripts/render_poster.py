#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render securities notice poster HTML to high-resolution PNG using Playwright.
Usage: python3 render_poster.py <path_to_html> [output_png_path]
"""

import sys
import os
import asyncio

async def capture_poster(html_path, output_png_path=None):
    if not output_png_path:
        base, _ = os.path.splitext(html_path)
        output_png_path = base + ".png"

    abs_html_path = os.path.abspath(html_path)
    file_url = f"file://{abs_html_path}"

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[ERROR] Playwright is not installed. Please run: pip install playwright && playwright install chromium")
        sys.exit(1)

    async with async_playwright() as p:
        # Launch chromium
        browser = await p.chromium.launch(headless=True)
        # Device scale factor 2 for high retina DPI resolution
        context = await browser.new_context(device_scale_factor=2, viewport={'width': 800, 'height': 1200})
        page = await context.new_page()

        await page.goto(file_url, wait_until='networkidle')

        # Get full document scroll height
        body_handle = await page.query_selector('.poster-container')
        if body_handle:
            bounding_box = await body_handle.bounding_box()
            height = int(bounding_box['height']) + 40
            width = int(bounding_box['width'])
            await page.set_viewport_size({'width': width, 'height': height})

        # Take screenshot of full page
        await page.screenshot(path=output_png_path, full_page=True)
        await browser.close()

        print(f"[SUCCESS] Poster image saved to: {output_png_path}")
        return output_png_path

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 render_poster.py <path_to_html> [output_png_path]")
        sys.exit(1)

    html_path = sys.argv[1]
    output_png_path = sys.argv[2] if len(sys.argv) > 2 else None

    asyncio.run(capture_poster(html_path, output_png_path))

if __name__ == "__main__":
    main()
