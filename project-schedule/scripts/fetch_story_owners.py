#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_story_owners.py — Story 各环节 Task 经办人抓取工具
=============================================================================
从平台 Story 详情页「所属 Task」表格批量抓取开发/SIT/UAT 各环节的 Task 经办人，
与 Story 详情页的「开发负责人/SIT测试负责人/UAT自测负责人」合并，即可得到
每个环节的完整经办人列表（负责人 + 经办人，可能多人）。

输出到 story_owners_cache.json（与 project_schedule_generate.py 同目录），
结构: {storyCode: {"dev": ["石雪军","许曼莉"], "sit": [...], "uat": [...], "storyNo": "...", "demandId": "..."}}

用法:
    python3 fetch_story_owners.py --epic E2603040001
    python3 fetch_story_owners.py --demand R2604160080
    python3 fetch_story_owners.py --demand R2604160080 --force   # 全量重抓

取数规则（Story 详情页「所属 Task」表格，列：Task编号|标题|类型|状态|经办人|...）:
    类型列含「开发」    -> dev 经办人
    类型列含「SIT测试」 -> sit 经办人
    类型列含「UAT自测」 -> uat 经办人
关键 URL: /kjpt/StoryManage/storyDetail?storyNo={R格式storyNo}
"""
import asyncio, sys, os, re, json, argparse

sys.path.append('/Volumes/Macintosh HD_Data/WorkBuddy/需求管理')
from req_query import ensure_login
from playwright.async_api import async_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_OUT = os.path.join(SCRIPT_DIR, "story_owners_cache.json")

TABLE_CACHE_CANDIDATES = [
    os.path.join(os.getcwd(), ".table_cache.json"),
    os.path.join(SCRIPT_DIR, ".table_cache.json"),
    os.path.join(os.path.dirname(SCRIPT_DIR), ".table_cache.json"),
    "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.table_cache.json",
]

# 环节类型关键词（按优先级匹配 Task 类型列）
PHASE_KEYWORDS = {
    "dev": ["开发"],
    "sit": ["SIT测试", "SIT 测试"],
    "uat": ["UAT自测", "UAT 自测"],
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
    demands = set()
    for r in items:
        ec = r.get("epicConcat") or ""
        if ec.startswith(epic_id) or ec.startswith(epic_id + "+"):
            d = r.get("demandId")
            if d:
                demands.add(d)
    return sorted(demands)


def resolve_stories(items, demand_ids):
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


def load_existing_cache():
    if os.path.exists(CACHE_OUT):
        try:
            with open(CACHE_OUT, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


async def fetch_stories(stories):
    """抓取每个 Story 所属 Task 表格中开发/SIT/UAT 环节的经办人"""
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
                # 点击「所属 Task」tab 以激活表格
                try:
                    await page.click('text=所属 Task', timeout=5000)
                    await page.wait_for_timeout(1500)
                except Exception:
                    pass
                rows = await page.evaluate("""() => {
                    const out = [];
                    const trs = Array.from(document.querySelectorAll('.ant-table-tbody .ant-table-row'));
                    for (const tr of trs) {
                        const tds = tr.querySelectorAll('td');
                        const cells = Array.from(tds).map(td => (td.innerText||'').replace(/\\s+/g,' ').trim());
                        if (cells.length >= 5) out.push(cells);
                    }
                    return out;
                }""")
                owners = {"dev": [], "sit": [], "uat": []}
                for cells in rows:
                    # 类型列=第3个单元格(index2)，经办人列=第5个单元格(index4)
                    if len(cells) < 5:
                        continue
                    task_type = cells[2] or ""
                    task_owner = cells[4] or ""
                    if not task_owner:
                        continue
                    for phase, kws in PHASE_KEYWORDS.items():
                        if any(kw in task_type for kw in kws):
                            if task_owner not in owners[phase]:
                                owners[phase].append(task_owner)
                results[sc] = {"storyNo": sno, "demandId": did, "system": sysname,
                               "status": status, "owners": owners}
                print(f"[{sc}] {sno} [{status}] -> "
                      f"开发={owners['dev'] or '--'} SIT={owners['sit'] or '--'} UAT={owners['uat'] or '--'}")
            except Exception as e:
                results[sc] = {"storyNo": sno, "demandId": did, "system": sysname,
                               "status": status, "error": str(e)}
                print(f"[{sc}] {sno} ERROR: {e}")
        await browser.close()
        return results


def merge_and_save(fetched, force=False):
    cache = {} if force else load_existing_cache()
    updated = 0
    for sc, info in fetched.items():
        if "error" in info:
            continue
        owners = info.get("owners") or {}
        # 仅当本环节有实际经办人时才更新
        for k in ("dev", "sit", "uat"):
            if owners.get(k):
                new_val = sorted(set(owners[k]))
                if cache.get(sc, {}).get(k) != new_val:
                    updated += 1
                cache.setdefault(sc, {})[k] = new_val
        cache.setdefault(sc, {})["storyNo"] = info.get("storyNo", cache.get(sc, {}).get("storyNo", ""))
        cache.setdefault(sc, {})["demandId"] = info.get("demandId", cache.get(sc, {}).get("demandId", ""))
    with open(CACHE_OUT, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    print(f"\n[fetch] 缓存已写入: {CACHE_OUT}（本批更新 {updated} 个字段）")
    return cache


def main():
    ap = argparse.ArgumentParser(description="Story 各环节 Task 经办人抓取工具")
    ap.add_argument("--epic", help="史诗编号，如 E2603040001")
    ap.add_argument("--demand", nargs="*", help="需求编号列表")
    ap.add_argument("--force", action="store_true", help="全量重抓（覆盖已有条目）")
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
        print(f"{sc}: 开发={e.get('dev','--')} SIT={e.get('sit','--')} UAT={e.get('uat','--')}")


if __name__ == "__main__":
    main()