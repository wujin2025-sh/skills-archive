#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_story_meta.py — Story 元信息自动抓取工具
=============================================================================
从平台 Story 详情页批量抓取三类元信息：
    原始需求提出人（基本信息区）
    业务验收人（业务与设计区）
    各阶段预计结束时间（IT 评估与排期卡片：开发/SIT/UAT）
输出到 story_meta_cache.json（与 project_schedule_generate.py 同目录），
生成排期表时自动加载合并，替代手工维护 STORY_ORIGINAL_REQUESTER_MAP /
STORY_BUSINESS_ACCEPTOR_MAP / STORY_PLAN_END_MAP 硬编码。

用法:
    python3 fetch_story_meta.py --epic E2603040001
    python3 fetch_story_meta.py --demand R2609080068 R2607090114
    python3 fetch_story_meta.py --epic E2603040001 --force   # 全量刷新所有 Story

字段取数规则（与平台 Story 详情页一致，innerText 键值以 \\t 分隔）:
    原始需求提出人  -> 基本信息区「原始需求提出人」
    业务验收人      -> 业务与设计区「业务验收人」（非验收动态消息中的提及）
    开发预计结束    -> IT 评估与排期「开发预计结束时间」
    SIT预计结束     -> 「SIT测试预计结束时间」
    UAT预计结束     -> 「UAT 自测预计结束时间」
关键 URL: /kjpt/StoryManage/storyDetail?storyNo={R格式storyNo}（storyNo 取大宽表缓存 storyNo/dataUniqueNo 字段，非 S 编号）
"""
import asyncio, sys, os, re, json, argparse

sys.path.append('/Volumes/Macintosh HD_Data/WorkBuddy/需求管理')
from req_query import ensure_login
from playwright.async_api import async_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_OUT = os.path.join(SCRIPT_DIR, "story_meta_cache.json")

# 大宽表缓存候选路径（与 fetch_story_actual_end.py / project_schedule_generate.py 保持一致）
TABLE_CACHE_CANDIDATES = [
    os.path.join(os.getcwd(), ".table_cache.json"),
    os.path.join(SCRIPT_DIR, ".table_cache.json"),
    os.path.join(os.path.dirname(SCRIPT_DIR), ".table_cache.json"),
    "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.table_cache.json",
]

# 键值以 tab 分隔：`原始需求提出人\t杨思明`；验收动态消息无 tab 跟随，天然排除
PATTERNS = {
    "requester": [r"原始需求提出人\s*\t\s*([\u4e00-\u9fa5]{2,8})"],
    "acceptor": [r"业务验收人\s*\t\s*([\u4e00-\u9fa5]{2,8})"],
    "plan_dev": [r"开发预计结束时间\s*\t\s*(\d{4}-\d{2}-\d{2})"],
    "plan_sit": [r"SIT测试预计结束时间\s*\t\s*(\d{4}-\d{2}-\d{2})"],
    "plan_uat": [r"UAT\s*自测预计结束时间\s*\t\s*(\d{4}-\d{2}-\d{2})"],
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
    """抓取所有 Story 元信息，返回 {storyCode: {requester/acceptor/plan_*}}"""
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
                print(f"[{sc}] {sno} {sysname} [{status}] -> "
                      f"提出人={found.get('requester','--')} 验收人={found.get('acceptor','--')} "
                      f"计划dev/sit/uat={found.get('plan_dev','--')}/{found.get('plan_sit','--')}/{found.get('plan_uat','--')}")
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
        for k in ("requester", "acceptor", "plan_dev", "plan_sit", "plan_uat"):
            if k in info["found"]:
                if entry.get(k) != info["found"][k]:
                    updated += 1
                entry[k] = info["found"][k]
        entry["storyNo"] = info.get("storyNo", entry.get("storyNo", ""))
        entry["demandId"] = info.get("demandId", entry.get("demandId", ""))
        cache[sc] = entry
    with open(CACHE_OUT, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    print(f"\n[fetch] 缓存已写入: {CACHE_OUT}（本批更新 {updated} 个字段）")
    return cache


def main():
    ap = argparse.ArgumentParser(description="Story 元信息（提出人/业务验收人/计划结束）抓取工具")
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
        print(f"{sc}: 提出人={e.get('requester','--')} 验收人={e.get('acceptor','--')} "
              f"计划dev/sit/uat={e.get('plan_dev','--')}/{e.get('plan_sit','--')}/{e.get('plan_uat','--')}")


if __name__ == "__main__":
    main()
