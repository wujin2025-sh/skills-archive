import os
import sys
import argparse
import tempfile
import requests
from urllib.parse import urlparse
from markitdown import MarkItDown
from openai import OpenAI

def convert_document_to_markdown(file_source: str, enable_vision: bool = False) -> str:
    """
    Convert document or web URL to Markdown format using MarkItDown.
    """
    try:
        # 1. Initialize MarkItDown
        if enable_vision:
            client = OpenAI()
            md = MarkItDown(llm_client=client, llm_model="gpt-4o")
        else:
            md = MarkItDown()

        # 2. Determine if file_source is a URL or local path
        parsed_url = urlparse(file_source)
        is_url = all([parsed_url.scheme, parsed_url.netloc])

        if is_url:
            # Extract path and extension
            path = parsed_url.path
            ext = os.path.splitext(path)[1]
            if not ext:
                # Default to .html for URLs without file extensions
                ext = ".html"

            if ext.lower() in ('.html', '.htm'):
                # Convert URL directly (MarkItDown uses requests internally for HTML)
                result = md.convert(file_source)
            else:
                # Download to a temporary file retaining the original extension
                response = requests.get(file_source, timeout=30)
                response.raise_for_status()
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp_file:
                    temp_file.write(response.content)
                    temp_path = temp_file.name

                try:
                    result = md.convert(temp_path)
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
        else:
            # Local file path
            # Standardize path by removing potential "file://" protocol
            if file_source.startswith("file://"):
                file_source = file_source[7:]
            if not os.path.exists(file_source):
                return f"错误：未在路径 {file_source} 找到文件，请检查路径是否正确。"
            result = md.convert(file_source)

        return result.text_content

    except Exception as e:
        return f"文件读取/转换失败，系统错误信息: {str(e)}"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert local file or web URL to Markdown.")
    parser.add_argument("--file_source", required=True, help="Local file path or URL.")
    parser.add_argument("--enable_vision", action="store_true", help="Enable vision parsing using OpenAI LLM (requires OPENAI_API_KEY).")
    args = parser.parse_args()

    output = convert_document_to_markdown(args.file_source, args.enable_vision)
    # Ensure output is printed using utf-8 encoding
    sys.stdout.buffer.write(output.encode('utf-8'))
