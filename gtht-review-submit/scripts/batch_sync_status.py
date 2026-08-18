#!/usr/bin/env python3
"""
从需求大宽表(OnlineGrid)查询需求真实状态，自动同步到文库。
步骤: 打开大宽表 → 搜索需求 → 一键展开 → 向右滚动 → 读取"需求状态"列
"""
import asyncio, json, re
from pathlib import Path
from playwright.async_api import async_playwright

import config

VAULT_ROOT = config.get_vault_root()
DEMAND_DIR = VAULT_ROOT / "10-需求"
_TABLE_ID, _ = config.get_table_sheet()
GRID_URL = (f"{config.get_base_url()}/OnlineGrid?tableId={_TABLE_ID}"
            f"&tableName=%E4%BA%A4%E6%98%93%E7%BB%93%E7%AE%97%E6%A0%B8%E5%BF%83%E7%B3%BB%E7%BB%9F%E9%9C%80%E6%B1%82%E9%9B%86%E5%90%88")
LOGIN_URL = config.get_login_url()

TERMINAL_STATUSES = ["已上线", "终止", "已终止", "已关闭"]

# 大宽表列顺序(关键列): ...需求编号 | Story编号 | 计划生产排期 | 版本排期 | 需求名称 | Story系统 | Story状态 | 需求状态 | Story业务验收结果...
# 每搜索一个req_id, 展开后按此顺序提取 需求状态 列


async def get_real_status(page, req_id: str) -> str:
    """在大宽表中搜索req_id, 返回需求状态"""
    await page.fill('#filter-text-box', req_id)
    await page.wait_for_timeout(1500)

    # 展开分组(如果折叠)
    expand_btn = page.locator('button.ant-btn.ant-btn-round.ant-btn-text:has-text("一键展开")')
    if await expand_btn.count() > 0:
        await expand_btn.first.click()
        await page.wait_for_timeout(1000)

    # 向右滚动到"需求状态"列
    for _ in range(8):
        await page.evaluate("""() => {
            const vp = document.querySelector('.ag-body-viewport, .ag-body-horizontal-scroll-viewport');
            if (vp) vp.scrollLeft += 400;
        }""")
        await page.wait_for_timeout(200)

    text = await page.evaluate("() => document.body.innerText")

    # 在文本中找这个需求的"需求状态"列值
    # 数据格式(展开后): ...需求名称 | Story系统 | Story状态 | 需求状态 | Story业务验收结果...
    # 找到Story系统名之后的第二个状态关键词
    idx = text.find(req_id)
    if idx < 0:
        return ""

    # 取需求行数据(从req_id开始到下一个分组或表尾)
    chunk = text[idx:idx+2000]

    # 提取列值——在文本中按顺序出现的字段
    # 找到"Story状态"后的status和"需求状态"后的status
    # 更可靠: 找到业务验收结果文字前的最后一个状态关键词
    # 格式: Story系统名称\n状态A\n状态B\n业务验收结果
    # 状态A=Story状态, 状态B=需求状态

    # 拆分行
    lines = chunk.split('\n')
    # 在Story系统名称行后, 找连续的状态行
    status_values = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if any(kw in stripped for kw in ["开发中", "UAT测试中", "技术评估中", "方案设计中",
                                          "分析中", "已上线", "已终止", "待SIT", "待UAT",
                                          "SIT测试中", "SIT生产测试中", "已受理", "待确认",
                                          "已评审"]):
            status_values.append((i, stripped))

        # 将原始大宽表状态映射为看板列状态
    GRID_TO_KANBAN = {
        "开发中": "开发中", "待开发": "开发中", "开发待排期": "开发中",
        "SIT测试中": "集成测试中(SIT)", "SIT生产测试中": "集成测试中(SIT)",
        "待SIT测试": "集成测试中(SIT)", "待SIT": "集成测试中(SIT)",
        "待SIT大远期自测": "集成测试中(SIT)", "待SIT大远期打包": "集成测试中(SIT)",
        "SIT大远期打包": "集成测试中(SIT)", "SIT大远期自测中": "集成测试中(SIT)",
        "UAT测试中": "UAT测试中", "待UAT自测": "UAT测试中",
        "UAT小远期自测中": "UAT测试中", "UAT自测中": "UAT测试中",
        "UAT小远期自测待排期": "UAT测试中",
        "技术评估中": "技术评估中", "技术评估": "技术评估中",
        "方案设计中": "方案设计中", "待确认": "方案设计中",
        "分析中": "分析中", "已受理": "分析中", "待受理": "分析中",
        "已上线": "已上线", "结束": "已上线",
    }

    # 找"业务验收"关键词来定位列位置
    biz_idx = text.find("业务验收", idx) if idx >= 0 else -1
    if biz_idx < 0:
        biz_idx = idx + 500

    # 在req_id行到业务验收之间的所有状态值中, 取最后一个(因为列顺序: Story状态在前, 需求状态在后)
    relevant = [s for pos, s in status_values if pos < biz_idx - idx + 5]
    if relevant:
        raw_status = relevant[-1]  # 最后一个状态 = 需求状态
        # 映射为看板状态
        for raw, mapped in GRID_TO_KANBAN.items():
            if raw in raw_status:
                return mapped
        return raw_status  # 无法映射就返回原始值

    return ""


async def batch_sync():
    req_files = list(DEMAND_DIR.glob("REQ-R*.md"))
    print(f"共找到 {len(req_files)} 个需求文件", flush=True)

    to_query = []
    for f in req_files:
        content = f.read_text(encoding="utf-8")
        lines = content.split("\n")
        fm = {}
        if lines and lines[0].strip() == "---":
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    break
                m = re.match(r'^(\w[\w-]*)\s*:\s*(.*)', lines[i])
                if m:
                    fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
        req_id = fm.get("req_id", "")
        status = fm.get("status", "")
        if not req_id or status in TERMINAL_STATUSES:
            if req_id and status in TERMINAL_STATUSES:
                print(f"  ⏭️  {req_id}: 已终态({status})，跳过", flush=True)
            continue
        to_query.append((f, req_id, status))

    if not to_query:
        print("没有需要查询的需求", flush=True)
        return
    print(f"需查询 {len(to_query)} 个需求", flush=True)

    import session as SESSION
    page, ctx, pw = await SESSION.open_page_async()
    try:
        # 打开大宽表(指定tab)
        await page.goto(GRID_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2500)

        updates = []
        for fpath, req_id, current_status in to_query:
            try:
                real_stage = await get_real_status(page, req_id)
                if real_stage and real_stage != current_status:
                    content = fpath.read_text(encoding="utf-8")
                    new_content = re.sub(r'^status:\s*\S+', f'status: {real_stage}', content, count=1, flags=re.MULTILINE)
                    fpath.write_text(new_content, encoding="utf-8")
                    updates.append({"req_id": req_id, "from": current_status, "to": real_stage})
                    print(f"  🔄 {req_id}: {current_status} → {real_stage} ✅", flush=True)
                else:
                    note = "（无变化）" if real_stage else "（未识别）"
                    print(f"  ✅ {req_id}: {current_status}{note}", flush=True)
            except Exception as e:
                print(f"  ❌ {req_id}: 查询失败 - {e}", flush=True)
    finally:
        await SESSION.close_page(ctx, pw)

    if updates:
        print(f"\n共 {len(updates)} 个需求已自动更新：")
        for u in updates:
            print(f"  ✅ {u['req_id']}: {u['from']} → {u['to']}")
    else:
        print("\n所有需求状态已是最新，无需更新。")


if __name__ == "__main__":
    asyncio.run(batch_sync())
