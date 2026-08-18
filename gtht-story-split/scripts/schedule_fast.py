#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
schedule_fast.py — 直连 WebSocket 写入大宽表「计划生产排期」（免浏览器，秒级）

原理：大宽表保存走 WebSocket（type=2 消息带完整行数据）。本脚本：
  1. 本地缓存 getSheetContent 行数据（`.sheet_rows_cache.pkl`，默认 TTL 30 分钟），
     避免每次 17-20s 全量拉取；
  2. 从缓存取目标行完整数据 → 改 planProdLineDate → 直连 WS 发送；
  3. 以 WS 服务端回包（code=1 且 planProdLineDate=目标值）作为落库确认。

用法:
  python3 schedule_fast.py <req_id> <YYYYMMDD> [--verify] [--refresh]   # 需求号
  python3 schedule_fast.py <epic_id> <YYYYMMDD> [--verify] [--refresh]  # 史诗（E/PG 开头，批量更新其下所有 Story）
  python3 schedule_fast.py --row <rowId> <YYYYMMDD> [--verify] [--refresh]  # 单行
  python3 schedule_fast.py --prewarm   # 仅拉取 getSheetContent 写缓存后退出（后台并行预热，隐藏 17-20s）
  # --force: 忽略缓存"已是目标值"判断，强制写入（幂等）；缓存可能陈旧时用
  # --refresh: 强制重新拉取 getSheetContent（新增 Story/行数据变化时用）

性能：
  - 冷缓存（首次）: ~20s（一次 getSheetContent 拉取 + WS 写入）→ 建议先 --prewarm 预热
  - 热缓存（TTL 内）: ~2-5s（纯 WS 写入，免全量拉取）
  - WS 写入失败自动重试：最多 3 次全新连接，退避 1s/2s（_ws_update 包装器，签名不变）；
    未确认行二次校验仅一次 refresh 全量刷新（原两次），最坏耗时 ~100s → ~25s。
"""
import sys, json, time, ssl, pickle
from pathlib import Path
import websocket  # websocket-client

import session as SESSION
import config

TABLE_ID, SHEET_ID = config.get_table_sheet()
COL_KEY = "planProdLineDate"
WS_URL = f"{config.get_ws_base()}/ws/table-socket/table/websocket/{TABLE_ID}"
CACHE_FILE = config.get_state_file(".sheet_rows_cache.pkl")
CACHE_TTL = 2 * 60 * 60  # 2 小时（行数据结构稳定，写入只需 planProdLineDate；--refresh 可强制刷新）


def _fetch_all_rows(refresh=False):
    """从 getSheetContent 获取全部行；优先用本地缓存（TTL 内）"""
    now = time.time()
    if not refresh and CACHE_FILE.exists():
        try:
            data = pickle.loads(CACHE_FILE.read_bytes())
            if now - data["fetched_at"] < CACHE_TTL and data["rows"]:
                return data["rows"], data["fetched_at"]
        except Exception:
            pass
    print("[sheet] 拉取全量行数据（getSheetContent，约 17-20s）...", flush=True)
    t0 = time.time()
    rows = SESSION.api_get("/table-service/table/row/getSheetContent", {"sheetId": SHEET_ID}, timeout=60)
    if not isinstance(rows, list):
        rows = (rows or {}).get("data", []) if isinstance(rows, dict) else []
    CACHE_FILE.write_bytes(pickle.dumps({"fetched_at": now, "rows": rows}))
    print(f"[sheet] 已缓存 {len(rows)} 行（拉取 {time.time()-t0:.1f}s）", flush=True)
    return rows, now


def _is_epic(code: str) -> bool:
    """史诗编号识别：E 开头（史诗编号）或 PG 开头（公司信息技术项目编号）"""
    c = (code or "").strip()
    return c.startswith("E") or c.startswith("PG")


def _get_rows(req_id=None, row_id=None, refresh=False):
    rows, _ = _fetch_all_rows(refresh)
    out = []
    for r in rows:
        if row_id and str(r.get("rowId")) == str(row_id):
            out.append(r)
            continue
        if not req_id:
            continue
        if _is_epic(req_id):
            # 史诗匹配：epicCode 精确，或 epicConcat 以 "史诗+" 开头
            epic_code = str(r.get("epicCode") or "").strip()
            epic_concat = str(r.get("epicConcat") or "").strip()
            epic_id = epic_concat.split("+")[0].strip() if epic_concat else epic_code
            if epic_code == req_id or epic_id == req_id or epic_concat == req_id or epic_concat.startswith(req_id + "+"):
                out.append(r)
        elif str(r.get("demandId") or "").strip() == req_id:
            out.append(r)
    return out


def _find_col_value(rows: list, row_id, col: str) -> str:
    """在行列表中按 rowId 查找某列值（安全返回字符串，避免 next 默认值写法歧义）"""
    for x in rows:
        if str(x.get("rowId")) == str(row_id):
            return str(x.get(col) or "").strip()
    return ""


def _update_cache_row(row_data: dict):
    """写入成功后更新本地缓存的对应行（避免校验读到旧值）"""
    try:
        if CACHE_FILE.exists():
            data = pickle.loads(CACHE_FILE.read_bytes())
            for i, r in enumerate(data["rows"]):
                if str(r.get("rowId")) == str(row_data.get("rowId")):
                    data["rows"][i] = row_data
                    break
            CACHE_FILE.write_bytes(pickle.dumps(data))
    except Exception:
        pass


def _ws_update_once(token: str, row_data: dict, target_date: str, timeout: int = 30) -> dict:
    """单次直连 WebSocket 发送 type=2 更新消息，返回 (echo, ok)；超时不崩溃，标记 'timeout'"""
    payload = {"sheetId": SHEET_ID, **row_data}
    payload[COL_KEY] = target_date
    msg = {"token": token, "type": 2, "data": payload}

    try:
        ws = websocket.create_connection(WS_URL, timeout=timeout,
                                         origin=config.get_origin(),
                                         sslopt={"cert_reqs": ssl.CERT_NONE} if hasattr(ssl, "CERT_NONE") else {})
    except Exception as e:
        return None, f"conn_error:{str(e)[:80]}"
    try:
        try:
            ws.settimeout(5)  # 建连后尽早短超时，避免 30s 阻塞
            ws.recv()  # 握手
            ws.send(json.dumps({"type": 1, "clientId": TABLE_ID, "token": token, "data": {"msg": "心跳检测"}}, ensure_ascii=False))
            ws.recv()  # 心跳 ack
        except Exception:
            pass  # 握手/心跳异常不阻塞，仍尝试发送更新
        ws.send(json.dumps(msg, ensure_ascii=False))
        # 回包等待：短超时获取，超时则返回 'timeout'（写入可能已落库，由主流程二次校验）
        echo = None
        for _ in range(6):
            try:
                raw = ws.recv()
            except Exception:
                break  # 超时/断开 → 停止等待
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            if isinstance(obj, dict) and isinstance(obj.get("data"), dict):
                echo = obj
                break
        if not echo:
            return None, "timeout"
        d = echo.get("data") or {}
        ok = (echo.get("code") == 1) and str(d.get(COL_KEY) or "").strip() == target_date
        return echo, ok
    finally:
        try:
            ws.close()
        except Exception:
            pass


def _ws_update(token: str, row_data: dict, target_date: str, timeout: int = 30) -> dict:
    """_ws_update_once 的重试包装器（对外签名不变）：最多 3 次全新 WS 连接，退避 1s/2s。

    幂等：同值重写无副作用；以服务端回包 code=1 且 planProdLineDate=目标值为成功判定。
    main() 两处调用点零改动。
    """
    last = (None, "unknown")
    for attempt in range(3):
        if attempt:
            time.sleep(attempt)  # 退避 1s / 2s
        echo, ok = _ws_update_once(token, row_data, target_date, timeout)
        if ok is True:
            return echo, True
        last = (echo, ok)
        if attempt < 2:
            print(f"    [retry] WS 写入第 {attempt+1} 次未确认({ok})，{attempt}s 后重试...", flush=True)
    return last


def main():
    args = sys.argv[1:]
    verify = "--verify" in args
    refresh = "--refresh" in args
    force = "--force" in args
    prewarm = "--prewarm" in args
    args = [a for a in args if a not in ("--verify", "--refresh", "--force", "--prewarm")]

    # --prewarm：仅拉取 getSheetContent 写缓存后退出（后台并行预热，隐藏冷缓存 17-20s）
    if prewarm:
        t0 = time.time()
        rows, _ = _fetch_all_rows(refresh=True)
        print(f"[prewarm] 已拉取并缓存 {len(rows)} 行（{time.time()-t0:.1f}s）", flush=True)
        sys.exit(0)

    if not args or len(args) < 1:
        print("用法: python3 schedule_fast.py <req_id|epic_id> <YYYYMMDD> [--verify] [--refresh]\n"
              "      查询: python3 schedule_fast.py <req_id|epic_id>  (不带日期，列出当前排期)\n"
              "      单行: python3 schedule_fast.py --row <rowId> <YYYYMMDD>\n"
              "      预热: python3 schedule_fast.py --prewarm")
        sys.exit(1)

    if args[0] == "--row":
        row_id, target = args[1], args[2]
        req_id = None
    else:
        req_id = args[0]
        target = args[1] if len(args) > 1 else None
        row_id = None

    # 查询模式：只给编号不带日期 → 列出当前排期
    if target is None:
        rows = _get_rows(req_id=req_id, row_id=row_id, refresh=refresh)
        if not rows:
            rows = _get_rows(req_id=req_id, row_id=row_id, refresh=True)
        if not rows:
            print(f"❌ 未找到目标行 ({req_id})")
            sys.exit(1)
        print(f"{'史诗' if _is_epic(req_id) else '需求'} {req_id} 当前计划生产排期：")
        for r in rows:
            print(f"  {r.get('storyCode')}: {r.get(COL_KEY) or '(空)'}")
        sys.exit(0)

    target_date = f"{target[:4]}-{target[4:6]}-{target[6:8]}"
    rows = _get_rows(req_id=req_id, row_id=row_id, refresh=refresh)
    if not rows:
        # 缓存里没有 → 强制刷新一次
        print("[sheet] 缓存未命中，强制刷新...", flush=True)
        rows = _get_rows(req_id=req_id, row_id=row_id, refresh=True)
    if not rows:
        print(f"❌ 未找到目标行 (req={req_id}, row={row_id})")
        sys.exit(1)

    print(f"目标 {len(rows)} 行: {[(r.get('storyCode'), r.get('rowId')) for r in rows]}")
    sess = SESSION.get_session()
    token = sess["token"]
    t0 = time.time()

    ok = 0
    unconfirmed = []  # 已发送但回包超时/异常的，待二次校验
    for r in rows:
        story = r.get("storyCode") or r.get("rowId")
        before = (r.get(COL_KEY) or "").strip()
        if before == target_date and not force:
            print(f"  ⏭ {story}: 缓存显示已是 {target_date}，跳过（--force 可强制重写）")
            ok += 1
            continue
        print(f"  ✍ {story}: {before or '(空)'} → {target_date}{'（--force）' if force else ''}", flush=True)
        echo, ok_flag = _ws_update(token, r, target_date)
        if ok_flag is True:
            print(f"    ✅ WS 回包确认: {echo.get('data', {}).get(COL_KEY)}", flush=True)
            r[COL_KEY] = target_date
            _update_cache_row(r)
            ok += 1
        else:
            print(f"    ⏳ 回包未确认({ok_flag})，标记待二次校验", flush=True)
            unconfirmed.append(r)

    # 对未确认的行：一次 refresh 全量校验确认实际值（原两次）；仍未生效则 _ws_update（已含 3 次重试）
    if unconfirmed:
        print(f"\n=== 二次校验 {len(unconfirmed)} 行（一次全量刷新确认实际值）===", flush=True)
        time.sleep(2)
        rows_v = _get_rows(req_id=req_id, row_id=row_id, refresh=True)
        for r in unconfirmed[:]:
            story = r.get("storyCode") or r.get("rowId")
            actual = _find_col_value(rows_v, r.get("rowId"), COL_KEY)
            if actual == target_date:
                print(f"  ✅ {story} 已落库: {actual}", flush=True)
                r[COL_KEY] = target_date
                _update_cache_row(r)
                ok += 1
                unconfirmed.remove(r)
        # 仍未生效的行 → 重试写入（_ws_update 内置 3 次重试）
        for r in unconfirmed[:]:
            story = r.get("storyCode") or r.get("rowId")
            actual = _find_col_value(rows_v, r.get("rowId"), COL_KEY)
            print(f"  ⏳ {story} 未生效(当前={actual or '空'})，重试写入...", flush=True)
            echo2, ok2 = _ws_update(token, r, target_date)
            if ok2 is True:
                print(f"    ✅ 重试确认: {echo2.get('data', {}).get(COL_KEY)}", flush=True)
                r[COL_KEY] = target_date
                _update_cache_row(r)
                ok += 1
                unconfirmed.remove(r)
        if unconfirmed:
            print(f"  ⚠️ {len(unconfirmed)} 行仍未确认，可加 --force 兜底重写", flush=True)

    print(f"\n耗时 {time.time()-t0:.1f}s，成功 {ok}/{len(rows)}")

    if verify and ok > 0:
        print("=== 最终校验（缓存回读）===", flush=True)
        rows_v = _get_rows(req_id=req_id, row_id=row_id, refresh=False)
        all_ok = all(str(r.get(COL_KEY) or "").strip() == target_date for r in rows_v)
        for r in rows_v:
            print(f"  {r.get('storyCode')} = {r.get(COL_KEY)}", flush=True)
        print("  ✅ 校验通过" if all_ok else "  ⚠️ 有行未刷新", flush=True)

    sys.exit(0 if ok == len(rows) else 2)


if __name__ == "__main__":
    main()
