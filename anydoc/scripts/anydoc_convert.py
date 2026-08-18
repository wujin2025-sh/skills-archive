#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AnyDoc Converter Helper Script
Powered by Firecrawl anydoc engine.
"""

import argparse
import os
import sys
import tempfile
import urllib.request
import anydoc


def convert_document(input_source: str, is_url: bool = False, format_hint: str = None, output_path: str = None):
    temp_file = None
    try:
        target_path = input_source
        if is_url or input_source.startswith("http://") or input_source.startswith("https://"):
            print(f"[*] Downloading file from: {input_source}", file=sys.stderr)
            req = urllib.request.Request(
                input_source,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
            )
            suffix = os.path.splitext(input_source.split("?")[0])[-1] or ".tmp"
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            with urllib.request.urlopen(req) as resp, open(temp_file.name, "wb") as out_f:
                out_f.write(resp.read())
            target_path = temp_file.name

        if not os.path.exists(target_path):
            print(f"[Error] File not found: {target_path}", file=sys.stderr)
            sys.exit(1)

        # Convert
        if format_hint:
            with open(target_path, "rb") as f:
                content = f.read()
            md_text = anydoc.to_markdown_bytes(content, format=format_hint)
        else:
            md_text = anydoc.to_markdown(target_path)

        if output_path:
            out_dir = os.path.dirname(os.path.abspath(output_path))
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(md_text)
            print(f"[+] Successfully converted to: {output_path}", file=sys.stderr)
        else:
            print(md_text)

    except Exception as e:
        print(f"[Error] Conversion failed: {str(e)}", file=sys.stderr)
        sys.exit(1)
    finally:
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="AnyDoc document to Markdown converter")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-i", "--input", help="Local file path to convert")
    group.add_argument("-u", "--url", help="Remote document URL to download and convert")
    parser.add_argument("-o", "--output", help="Output markdown file path (default: stdout)")
    parser.add_argument("-f", "--format", help="Force format hint (e.g. docx, xlsx, pptx, pdf, csv, epub)")

    args = parser.parse_args()

    if args.input:
        convert_document(args.input, is_url=False, format_hint=args.format, output_path=args.output)
    elif args.url:
        convert_document(args.url, is_url=True, format_hint=args.format, output_path=args.output)


if __name__ == "__main__":
    main()
