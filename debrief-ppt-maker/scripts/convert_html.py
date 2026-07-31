#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
from playwright.sync_api import sync_playwright

def convert_html_to_pdf(html_path, pdf_path=None):
    if not os.path.exists(html_path):
        print(f"Error: HTML file not found at '{html_path}'")
        sys.exit(1)
        
    html_abs_path = os.path.abspath(html_path)
    base_dir = os.path.dirname(html_abs_path)
    base_name, _ = os.path.splitext(os.path.basename(html_abs_path))
    
    if not pdf_path:
        pdf_path = os.path.join(base_dir, f"{base_name}.pdf")
        
    print(f"Initializing PDF conversion for '{html_path}'...")
    print(f"Target PDF: {pdf_path}")
    
    with sync_playwright() as p:
        print("Launching headless Chromium...")
        browser = p.chromium.launch(headless=True)
        # 16:9 viewport aspect ratio (1280x720)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        
        # Load local HTML file via file:// protocol
        file_url = f"file://{html_abs_path}"
        page.goto(file_url)
        
        # Wait for fonts and network resources to be fully loaded
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000) # Give extra breathing room for rendering
        
        # Export PDF using Playwright's native PDF generation with print media style injection
        print("Generating vector PDF...")
        # Inject print styles to hide navigation and make clean page breaks
        print_style = """
        @media print {
            .nav { display: none !important; }
            .slides-wrapper { margin: 0 !important; padding: 0 !important; gap: 0 !important; display: block !important; }
            .slide { page-break-after: always !important; page-break-inside: avoid !important; box-shadow: none !important; border-radius: 0 !important; margin: 0 !important; }
        }
        """
        page.add_style_tag(content=print_style)
        
        try:
            page.pdf(
                path=pdf_path,
                width="1280px",
                height="720px",
                print_background=True,
                margin={"top": "0px", "right": "0px", "bottom": "0px", "left": "0px"}
            )
            print(f"Successfully generated PDF: {pdf_path}")
        except Exception as e:
            print(f"Error: Playwright PDF generation failed: {e}")
            browser.close()
            sys.exit(1)
            
        browser.close()
        
    print("Conversion completed successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Slide HTML to PDF.")
    parser.add_argument("html_path", help="Path to the source slide HTML file")
    parser.add_argument("--pdf", help="Output PDF path (default: same as HTML name in same directory)")
    
    args = parser.parse_args()
    convert_html_to_pdf(args.html_path, args.pdf)
