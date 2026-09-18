#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_story_actual_end.py — Story 实际结束时间自动抓取工具
=============================================================================
从平台 Story 详情页「Story 一生」卡片批量抓取实际结束时间，
输出到 story_actual_end_cache.json（与 project_schedule_generate.py 同目录），
生成排期表时自动加载合并，无需再手动维护硬编码 STORY_ACTUAL_END_MAP。

用法:
    python3 fetch_story_actual_end.py --epic E2603040001
    python3 fetch_story_actual_end.py --demand R2609080068 R2607090114
    python3 fetch_story_actual_end.py --epic E2603040001 --force   # 全量刷新所有 Story

实际结束字段取数规则（与平台「Story 一生」卡片一致）:
    开发实际结束  -> 开发实际结束时间
    SIT实际结束   -> SIT自测实际结束时间
    UAT实际结束   -> UAT自测实际结束时间
关键 URL: /kjpt/StoryManage/storyDetail?storyNo={R格式storyNo}（storyNo 取大宽表缓存 storyNo/dataUniqueNo 字段，非 S 编号）
"""
import asyncio, sys, os, re, json, argparse
from datetime import datetime
from collections import defaultdict

sys.path.append('/Volumes/Macintosh HD_Data/WorkBuddy/需求管理')
from req_query import ensure_login
from playwright.async_api import async_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_OUT = os.path.join(SCRIPT_DIR, "story_actual_end_cache.json")

# 大宽表缓存候选路径（与 project_schedule_generate.py get_indexed_cache 保持一致）
TABLE_CACHE_CANDIDATES = [
    os.path.join(os.getcwd(), ".table_cache.json"),
    os.path.join(SCRIPT_DIR, ".table_cache.json"),
    os.path.join(os.path.dirname(SCRIPT_DIR), ".table_cache.json"),
    "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.table_cache.json",
]

PATTERNS = {
    "dev": [r"开发实际结束时间\s*[:：]?\s*(\d{4}-\d{2}-\d{2})",
            r"devFactEndDate['\"]?\s*[:：]\s*['\"]?(\d{4}-\d{2}-\d{2})"],
    "sit": [r"SIT自测实际结束时间\s*[:：]?\s*(\d{4}-\d{2}-\d{2})",
            r"SIT实际结束时间\s*[:：]?\s*(\d{4}-\d{2}-\d{2})",
            r"sitFactEndDate['\"]?\s*[:：]\s*['\"]?(\d{4}-\d{2}-\d{2})"],
    "uat": [r"UAT自测实际结束时间\s*[:：]?\s*(\d{4}-\d{2}-\d{2})",
            r"UAT实际结束时间\s*[:：]?\s*(\d{4}-\d{2}-\d{2})",
            r"uatFactEndDate['\"]?\s*[:：]\s*['\"]?(\d{4}-\d{2}-\d{2})"],
}


def find_table_cache():
    for p in TABLE_CACHE_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def load_table_cache():
    p = find_table_cache()
    if not p:
        print("[fetch] 未找到 .table_cache.json，无法解析 Story 列表")
        return []
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return data.get("data") or data.get("records") or data.get("list") or []


def resolve_epic_demands(items, epic_id):
    """根据史诗编号从大宽表解析关联需求编号"""
    demands = set()
    for r in items:
        ec = r.get("epicConcat") or ""
        if ec.startswith(epic_id) or ec.startswith(epic_id + "+"):
            d = r.get("demandId")
            if d:
                demands.add(d)
    return sorted(demands)


def resolve_stories(items, demand_ids):
    """解析需求下 Story 列表: storyCode -> (storyNo, demandId, systemName, status)"""
    seen = {}
    for r in items:
        d = r.get("demandId")
        if d not in demand_ids:
            continue
        sc = r.get("storyCode") or ""
        if not sc:
            continue
        sno = r.get("storyNo") or r.get("dataUniqueNo") or ""
        status = r.get("storyStatusName") or ""
        # 过滤已终止 Story
        if "终止" in status:
            continue
        if sc not in seen:
            seen[sc] = (sno, d, r.get("storySystemName") or "", status)
    return [(sc, sno, d, sysname, status) for sc, (sno, d, sysname, status) in sorted(seen.items())]


def extract(text):
    out = {}
    for k, pats in PATTERNS.items():
        for p in pats:
            m = re.search(p, text)
            if m:
                out[k] = m.group(1)
                break
    return out


def load_existing_cache():
    if os.path.exists(CACHE_OUT):
        try:
            with open(CACHE_OUT, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


async def fetch_stories(stories):
    """抓取所有 Story 实际结束时间，返回 {storyCode: {dev/sit/uat}}"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await ensure_login(context, page)

        results = {}
        for sc, sno, did, sysname, status in stories:
            url = f'https://fintech.gtht.com.cn/kjpt/StoryManage/storyDetail?storyNo={sno}'
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(3500)
                text = await page.evaluate("() => document.body ? document.body.innerText : ''")
                found = extract(text)
                results[sc] = {"storyNo": sno, "demandId": did, "system": sysname,
                               "status": status, "found": found,
                               "page_len": len(text)}
                print(f"[{sc}] {sno} {sysname} [{status}] -> dev={found.get('dev','--')} sit={found.get('sit','--')} uat={found.get('uat','--')}")
                if len(text) < 60:
                    print(f"    ⚠️ 页面异常(空白/跳转登录): {text[:120]!r}")
            except Exception as e:
                results[sc] = {"storyNo": sno, "demandId": did, "system": sysname,
                               "status": status, "error": str(e)}
                print(f"[{sc}] {sno} ERROR: {e}")
        await browser.close()
        return results


def merge_and_save(fetched, force=False):
    """合并抓取结果到缓存文件。force=True 时全量覆盖；否则仅更新成功抓取到的条目"""
    cache = {} if force else load_existing_cache()
    updated = 0
    for sc, info in fetched.items():
        if "error" in info or not info.get("found"):
            continue
        entry = cache.get(sc, {})
        for k in ("dev", "sit", "uat"):
            if k in info["found"]:
                if entry.get(k) != info["found"][k]:
                    updated += 1
                entry[k] = info["found"][k]
        cache[sc] = entry
    with open(CACHE_OUT, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    print(f"\n[fetch] 缓存已写入: {CACHE_OUT}（本批更新 {updated} 个字段）")
    return cache


def main():
    ap = argparse.ArgumentParser(description="Story 实际结束时间抓取工具")
    ap.add_argument("--epic", help="史诗编号，如 E2603040001")
    ap.add_argument("--demand", nargs="*", help="需求编号列表，如 R2609080068 R2607090114")
    ap.add_argument("--force", action="store_true", help="全量刷新（覆盖缓存中已有条目）")
    args = ap.parse_args()

    if not args.epic and not args.demand:
        ap.print_help()
        sys.exit(1)

    items = load_table_cache()
    if not items:
        print("[fetch] 大宽表缓存为空，请先确认 .table_cache.json 存在")
        sys.exit(1)

    demand_ids = set(args.demand or [])
    if args.epic:
        epic_demands = resolve_epic_demands(items, args.epic)
        if not epic_demands:
            print(f"[fetch] 史诗 {args.epic} 未在大宽表缓存中找到关联需求")
            sys.exit(1)
        print(f"[fetch] 史诗 {args.epic} 关联需求: {epic_demands}")
        demand_ids |= set(epic_demands)

    stories = resolve_stories(items, demand_ids)
    if not stories:
        print("[fetch] 未解析到任何 Story")
        sys.exit(1)
    print(f"[fetch] 共 {len(stories)} 个 Story 待抓取...\n")

    fetched = asyncio.run(fetch_stories(stories))
    cache = merge_and_save(fetched, force=args.force)

    print("\n=== 汇总（当前缓存全部条目） ===")
    for sc in sorted(cache.keys()):
        e = cache[sc]
        print(f"{sc}: dev={e.get('dev','--')} sit={e.get('sit','--')} uat={e.get('uat','--')}")


if __name__ == "__main__":
    main()
