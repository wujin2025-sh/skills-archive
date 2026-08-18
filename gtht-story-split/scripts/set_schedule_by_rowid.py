#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
set_schedule_by_rowid.py — 按 rowId 直接写入大宽表「计划生产排期」

背景：plan-schedule-edit 按需求号搜索失败（R2608070025 行存在但搜索逻辑未命中），
本脚本用 API 获取到的 rowId 直接定位 ag-grid 行并更新 planProdLineDate，走 WebSocket 落库。

用法:
  python3 set_schedule_by_rowid.py <req_id> <YYYYMMDD> [--story-code "Sxxx=rowId" ...]
  或直接用内置的 rowId 映射（从 getSheetContent API 自动获取）
"""
import sys, json, asyncio, time
import session as SESSION
import config

TABLE_ID, SHEET_ID = config.get_table_sheet()
COL_KEY = "planProdLineDate"


async def get_rowids(req_id: str) -> list:
    """从 getSheetContent API 获取该需求在目标 sheet 中的行 (rowId, storyCode)"""
    rows = SESSION.api_get("/table-service/table/row/getSheetContent", {"sheetId": SHEET_ID})
    if not isinstance(rows, list):
        rows = (rows or {}).get("data", []) if isinstance(rows, dict) else []
    result = []
    for r in rows:
        if str(r.get("demandId") or "").strip() == req_id and r.get("rowId"):
            result.append({"rowId": str(r["rowId"]), "storyCode": str(r.get("storyCode") or "")})
    return result


async def main():
    if len(sys.argv) < 3:
        print("用法: python3 set_schedule_by_rowid.py <req_id> <YYYYMMDD>")
        sys.exit(1)
    req_id = sys.argv[1]
    target_date = f"{sys.argv[2][:4]}-{sys.argv[2][4:6]}-{sys.argv[2][6:8]}"

    # 1. 从 API 获取 rowId
    rows = await get_rowids(req_id)
    if not rows:
        print(f"❌ 未在 sheet {SHEET_ID} 中找到需求 {req_id} 的行")
        sys.exit(1)
    print(f"找到 {len(rows)} 行: {[(r['storyCode'], r['rowId']) for r in rows]}")

    # 2. 打开大宽表
    page, ctx, pw = await SESSION.open_page_async()
    try:
        url = f"{config.get_base_url()}/OnlineGrid?tableId={TABLE_ID}&sheetId={SHEET_ID}"
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # 等待 ag-grid 加载出数据行
        for _ in range(60):
            await page.wait_for_timeout(500)
            ready = await page.evaluate("""() => {
                const el = document.querySelector('.ag-root-wrapper');
                const rows = document.querySelectorAll('.ag-center-cols-container .ag-row');
                return !!(el && rows.length > 0);
            }""")
            if ready:
                break
        print("ag-grid 已加载", flush=True)
        await page.wait_for_timeout(2000)

        # 允许只更新指定 rowId（用 --row-id 过滤）
        only_row = None
        if "--row-id" in sys.argv:
            only_row = sys.argv[sys.argv.index("--row-id") + 1]

        for row in rows:
            row_id = row["rowId"]
            story = row["storyCode"] or row_id
            if only_row and row_id != only_row:
                continue
            print(f"\n===== 更新 Story [{story}] rowId={row_id} → {target_date} =====", flush=True)
            # 每个 row 独立等待更久，确保 WebSocket 落库完成
            res = await page.evaluate("""({ rowId, colKey, targetVal }) => {
                const el = document.querySelector('.ag-root-wrapper');
                if (!el) return { error: 'no ag-root-wrapper' };
                const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber'));
                let current = el[fiberKey];
                let api = null, gridOptions = null, reactComp = null;
                while (current) {
                    const node = current.stateNode;
                    if (node && (node.sendRowData || node.gridApi || node.api || node.gridOptions)) {
                        api = api || node.gridApi || node.api || (node.gridOptions && node.gridOptions.api);
                        gridOptions = gridOptions || node.gridOptions || (api && api.gridOptions);
                        if (node.sendRowData) reactComp = node;
                        if (api && reactComp) break;
                    }
                    current = current.return;
                }
                if (!api) return { error: 'no ag-grid api' };
                const rowNode = api.getRowNode(rowId);
                if (!rowNode) return { error: 'rowNode not found: ' + rowId };
                const oldVal = rowNode.data ? (rowNode.data[colKey] || '') : '';
                if (oldVal === targetVal) {
                    return { ok: true, beforeVal: oldVal, afterVal: targetVal, skipped: true };
                }
                if (rowNode.data) { rowNode.data[colKey] = targetVal; }
                if (reactComp && typeof reactComp.sendRowData === 'function') {
                    const payload = Object.assign({ sheetId: '""" + SHEET_ID + """' }, rowNode.data);
                    reactComp.sendRowData(payload);
                } else if (gridOptions && typeof gridOptions.onCellValueChanged === 'function') {
                    gridOptions.onCellValueChanged({
                        node: rowNode, data: rowNode.data, oldValue: oldVal,
                        newValue: targetVal, value: targetVal, source: 'paste',
                        colDef: { field: colKey },
                        column: api.getColumn ? api.getColumn(colKey) : null,
                        api: api, columnApi: api.columnModel || api.columnApi
                    });
                }
                if (api.refreshCells) { api.refreshCells({ rowNodes: [rowNode], columns: [colKey], force: true }); }
                return { ok: true, beforeVal: oldVal, afterVal: targetVal, skipped: false };
            }""", {"rowId": row_id, "colKey": COL_KEY, "targetVal": target_date})
            print("更新结果:", json.dumps(res, ensure_ascii=False), flush=True)
            await page.wait_for_timeout(4000)

        # 3. 重新查询 API 验证持久化
        await SESSION.close_page(ctx, pw)
        time.sleep(1)
        verify = await get_rowids(req_id)
        print("\n=== 验证（重新查 API）===", flush=True)
        for v in verify:
            # 重新查该行内容
            rows_all = SESSION.api_get("/table-service/table/row/getSheetContent", {"sheetId": SHEET_ID})
            if not isinstance(rows_all, list):
                rows_all = (rows_all or {}).get("data", []) if isinstance(rows_all, dict) else []
            for r in rows_all:
                if str(r.get("rowId")) == v["rowId"]:
                    print(f"  {v['storyCode']}: planProdLineDate = {r.get('planProdLineDate')}", flush=True)
                    break
    finally:
        await SESSION.close_page(ctx, pw)

asyncio.run(main())
