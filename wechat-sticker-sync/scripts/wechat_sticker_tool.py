#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号贴图（小绿书/图片消息）全自动工具箱
提供两大核心能力：
1. make-cover: 自动生成 3:4 (1080x1440) 暖调极简大字封面海报；
2. sync: 自动解析贴图 Markdown 文件，一键免扫码直达微信后台草稿箱，完成图片批量上传、标题/正文注入并保存。
"""

import os
import sys
import re
import time
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

SESSION_DIR = os.path.expanduser("~/.wechat_mp_playwright_profile")

def generate_cover(title_html: str, output_path: str):
    """根据给定的标题 HTML 与高亮词，渲染生成 3:4 高清大字封面海报"""
    html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
  * {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }}
  body {{
    width: 1080px;
    height: 1440px;
    background-color: #FFF7F6;
    display: flex;
    justify-content: center;
    align-items: center;
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Noto Sans SC", sans-serif;
    position: relative;
    overflow: hidden;
  }}
  .card {{
    width: 880px;
    height: 1180px;
    position: relative;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 60px 40px;
  }}
  .quote-icon {{
    width: 68px;
    height: 56px;
    fill: #F76544;
  }}
  .quote-left {{
    position: absolute;
    top: 70px;
    left: 30px;
  }}
  .quote-right {{
    position: absolute;
    bottom: 70px;
    right: 30px;
  }}
  .title {{
    font-size: 86px;
    line-height: 1.42;
    font-weight: 900;
    color: #1A1816;
    letter-spacing: 2px;
    margin-left: 20px;
    margin-top: 10px;
  }}
  .highlight {{
    color: #F76544;
  }}
</style>
</head>
<body>
  <div class="card">
    <div class="quote-left">
      <svg class="quote-icon" viewBox="0 0 24 24">
        <path d="M9.983 3v7.391c0 5.704-3.731 9.57-8.983 10.609l-.995-2.151c2.432-.917 3.995-3.638 3.995-5.849h-4v-10h9.983zm14.017 0v7.391c0 5.704-3.748 9.571-9 10.609l-.996-2.151c2.433-.917 3.996-3.638 3.996-5.849h-3.983v-10h9.983z"/>
      </svg>
    </div>
    <div class="title">
      {title_html}
    </div>
    <div class="quote-right">
      <svg class="quote-icon" viewBox="0 0 24 24" style="transform: rotate(180deg);">
        <path d="M9.983 3v7.391c0 5.704-3.731 9.57-8.983 10.609l-.995-2.151c2.432-.917 3.995-3.638 3.995-5.849h-4v-10h9.983zm14.017 0v7.391c0 5.704-3.748 9.571-9 10.609l-.996-2.151c2.433-.917 3.996-3.638 3.996-5.849h-3.983v-10h9.983z"/>
      </svg>
    </div>
  </div>
</body>
</html>"""

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1440})
        page.set_content(html_template)
        page.screenshot(path=output_path)
        browser.close()
    print(f"✅ 封面海报生成成功: {output_path}")

def parse_sticker_md(md_path: str):
    """解析贴图 Markdown 文档"""
    if not os.path.exists(md_path):
        raise FileNotFoundError(f"找不到指定的 Markdown 文件: {md_path}")

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. 提取标题 (微信贴图标题限制 20 字符以内)
    title_m = re.search(r"^#\s*(.+)$", content, re.MULTILINE)
    raw_title = title_m.group(1).strip() if title_m else ""
    if len(raw_title) > 20:
        # 优先提取主标题部分
        title = raw_title.split("：")[0].split("与")[0].strip()
        if len(title) > 20:
            title = title[:20]
    else:
        title = raw_title

    # 2. 提取贴图正文文案 (提取“贴图正文文案”章节到分割线之间的内容)
    body_match = re.search(r"##\s*.*?贴图正文文案.*?\n\n(.*?)\n\n---", content, re.DOTALL)
    if not body_match:
        # 兼容备用格式
        body_match = re.search(r"##\s*.*?正文文案.*?\n\n(.*?)\n\n---", content, re.DOTALL)
    
    if body_match:
        body_text = body_match.group(1).strip()
    else:
        raise ValueError("未能匹配到正文文案章节，请确保包含 '## 贴图正文文案' 与 '---' 分割线")

    # 3. 提取配图路径
    base_dir = os.path.dirname(os.path.abspath(md_path))
    raw_img_matches = re.findall(r"!\[.*?\]\(([^)]+)\)", content)
    
    seen = set()
    img_paths = []
    for rel_path in raw_img_matches:
        if rel_path not in seen:
            seen.add(rel_path)
            abs_path = os.path.normpath(os.path.join(base_dir, rel_path))
            if os.path.exists(abs_path):
                img_paths.append(abs_path)
            else:
                print(f"⚠️ 引用图片不存在已跳过: {abs_path}")

    if not img_paths:
        raise ValueError("未在文档中找到任何存在的本地图片路径！")

    return title, body_text, img_paths

def sync_to_wechat(md_path: str, headless: bool = True):
    """一键同步至微信公众号后台草稿箱"""
    print("=" * 60)
    print("🚀 微信公众号【贴图】一键存入草稿箱")
    print("=" * 60)

    title, body_text, img_paths = parse_sticker_md(md_path)
    print(f"📖 文件: {os.path.basename(md_path)}")
    print(f"📌 标题: {title} ({len(title)}/20 字)")
    print(f"📝 正文: {len(body_text)} 字")
    print(f"🖼️ 配图: {len(img_paths)} 张")
    for idx, p in enumerate(img_paths, 1):
        print(f"   [{idx}] {os.path.basename(p)}")
    print("-" * 60)

    os.makedirs(SESSION_DIR, exist_ok=True)

    with sync_playwright() as p:
        print("🌐 启动浏览器...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=headless,
            viewport={"width": 1280, "height": 900},
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://mp.weixin.qq.com/", wait_until="domcontentloaded")
        time.sleep(1)

        token = None
        if "token=" in page.url:
            match = re.search(r"token=(\d+)", page.url)
            if match:
                token = match.group(1)

        if not token:
            print("\n🔔 登录 Session 已过期，等待扫码登录...")
            try:
                page.wait_for_url(lambda u: "token=" in u, timeout=180000)
                match = re.search(r"token=(\d+)", page.url)
                if match:
                    token = match.group(1)
                    print(f"✅ 登录成功！Token: {token}")
            except Exception:
                print("❌ 扫码超时，任务退出。")
                context.close()
                return False

        print(f"🔑 登录态有效，Token: {token}")

        # 2. 点击首页【贴图】按钮
        print("🎯 定位并点击首页【贴图】创作入口...")
        sticker_btn = page.locator("text=贴图").first
        with context.expect_page() as new_page_info:
            sticker_btn.click()
        new_page = new_page_info.value
        new_page.wait_for_load_state("domcontentloaded")
        time.sleep(2)

        # 3. 批量上传图片 (使用 input[type='file'].nth(1))
        print(f"📤 正在上传 {len(img_paths)} 张贴图高清图片...")
        new_page.locator("input[type='file']").nth(1).set_input_files(img_paths)
        time.sleep(8)
        print("✅ 图片上传与渲染完成！")

        # 4. 定位并填写标题
        print(f"✍️ 正在填写标题: {title}")
        counter_box = new_page.locator("*:has-text('0/20')").last.bounding_box()
        if counter_box:
            new_page.mouse.click(counter_box['x'] - 100, counter_box['y'] + 10)
            time.sleep(0.5)
            new_page.keyboard.type(title)
            print("✅ 标题输入完成！")
        else:
            title_input = new_page.locator("textarea[placeholder*='标题'], input[placeholder*='标题']").first
            title_input.fill(title)

        time.sleep(1)

        # 5. 定位并填写正文
        print("📝 正在注入正文描述...")
        if counter_box:
            new_page.mouse.click(counter_box['x'] - 100, counter_box['y'] + 60)
            time.sleep(0.5)
            new_page.keyboard.insert_text(body_text)
            print("✅ 正文描述注入完成！")
        else:
            desc_el = new_page.locator("div.ProseMirror").first
            desc_el.click()
            new_page.keyboard.insert_text(body_text)

        time.sleep(2)

        # 6. 保存草稿
        print("💾 点击【保存为草稿】...")
        save_btn = new_page.locator("button:has-text('保存为草稿')").first
        save_btn.click()
        print("🎯 保存指令已提交！")
        time.sleep(5)

        # 截图留存
        out_dir = os.path.join(os.path.dirname(os.path.abspath(md_path)), "images")
        os.makedirs(out_dir, exist_ok=True)
        screenshot_path = os.path.join(out_dir, "draft_sync_result.png")
        new_page.screenshot(path=screenshot_path)
        print(f"📸 存盘结果截图已保存至: {screenshot_path}")

        print("\n" + "=" * 60)
        print("🎉 贴图已成功存入微信公众号草稿箱！")
        print("=" * 60 + "\n")

        time.sleep(2)
        context.close()
        return True

def main():
    parser = argparse.ArgumentParser(description="微信公众号贴图自动化工具箱")
    subparsers = parser.add_subparsers(dest="subcommand", help="子命令")

    # 子命令 1: make-cover
    p_cover = subparsers.add_parser("make-cover", help="生成 3:4 高清大字封面海报")
    p_cover.add_argument("--html", "-t", required=True, help="标题 HTML (支持 <br> 和 <span class=\"highlight\">)")
    p_cover.add_argument("--output", "-o", required=True, help="图片输出路径 (.png)")

    # 子命令 2: sync
    p_sync = subparsers.add_parser("sync", help="同步贴图 Markdown 到公众号草稿箱")
    p_sync.add_argument("--file", "-f", required=True, help="贴图 Markdown 文件路径")
    p_sync.add_argument("--headed", action="store_true", help="显示浏览器窗口（默认无头静默运行）")

    args = parser.parse_args()

    if args.subcommand == "make-cover":
        generate_cover(args.html, args.output)
    elif args.subcommand == "sync":
        sync_to_wechat(args.file, headless=not args.headed)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
