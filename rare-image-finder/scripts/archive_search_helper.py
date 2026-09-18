#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
archive_search_helper.py - 珍贵图片与权威历史档案检索辅助工具
支持快速构建多源权威档案库检索矩阵、反向以图搜图直达链接，并可选通过公开 API 直接拉取图片元数据。
"""

import sys
import urllib.parse
import json
import argparse

ARCHIVE_TEMPLATES = {
    "Wikimedia Commons (维基共享高精档案)": "https://commons.wikimedia.org/w/index.php?search={query}&title=Special:MediaSearch&type=image",
    "Library of Congress (美国国会图书馆图档库)": "https://www.loc.gov/pictures/search/?q={query}",
    "Internet Archive (互联网档案馆图像库)": "https://archive.org/details/image?query={query}",
    "Newspaper Navigator (历史报纸AI图片库)": "https://news-navigator.labs.loc.gov/search?q={query}",
    "Europeana (欧洲数字文化遗产)": "https://www.europeana.eu/en/search?query={query}&type=IMAGE",
    "Yandex Images (全球最强老照片/人脸特征搜图)": "https://yandex.com/images/search?text={query}",
    "Google Images (高级档案检索)": "https://www.google.com/search?tbm=isch&q={query}+site%3Aloc.gov+OR+site%3Acommons.wikimedia.org+OR+site%3Axinhuanet.com",
    "新华网/新华社历史图集检索": "https://www.google.com/search?tbm=isch&q={query}+site%3Axinhuanet.com+OR+site%3Apeople.com.cn",
}

REVERSE_SEARCH_TEMPLATES = {
    "Yandex 以图搜图 (最强特征与无裁切母本)": "https://yandex.com/images/search?rpt=imageview&url={url}",
    "TinEye (溯源最早发布时间与最高分辨率)": "https://tineye.com/search?url={url}&sort=crawl_date&order=asc",
    "Google Lens 以图搜图": "https://lens.google.com/uploadbyurl?url={url}",
    "Baidu 识图 (中文地方志与国内网页覆盖)": "https://graph.baidu.com/details?isfromvs=1&sign=126_xxxx&picUrl={url}",
}

def generate_keyword_links(query: str):
    print(f"\n🔍 【珍贵图片 & 历史档案多源检索矩阵】")
    print(f"👉 检索关键词: {query}\n" + "="*70)
    encoded = urllib.parse.quote_plus(query)
    for name, tpl in ARCHIVE_TEMPLATES.items():
        url = tpl.format(query=encoded)
        print(f"📌 {name}:\n   {url}\n")

def generate_reverse_links(img_url: str):
    print(f"\n🔄 【反向以图搜图 & 母本溯源矩阵】")
    print(f"👉 目标图片 URL: {img_url}\n" + "="*70)
    encoded = urllib.parse.quote_plus(img_url)
    for name, tpl in REVERSE_SEARCH_TEMPLATES.items():
        url = tpl.format(url=encoded)
        print(f"📌 {name}:\n   {url}\n")

def main():
    parser = argparse.ArgumentParser(description="珍贵图片与权威历史档案检索辅助脚本")
    parser.add_argument("query", nargs="*", help="检索关键词（如：1990 上海证券交易所 开业 尉文渊）")
    parser.add_argument("--reverse", "-r", help="反向以图搜图的目标图片 URL")
    args = parser.parse_args()

    if args.reverse:
        generate_reverse_links(args.reverse)
    elif args.query:
        query_str = " ".join(args.query)
        generate_keyword_links(query_str)
    else:
        # 默认演示
        generate_keyword_links("1990 上海证券交易所 铜锣 开业")

if __name__ == "__main__":
    main()
