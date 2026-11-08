#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_flow.py —— query_requirement_flow 大响应一键精炼解析（gtht-accept-review 专用）

背景：query_requirement_flow 返回 53KB 嵌套 JSON 大响应（demand/flow/availableActions/stories/
requirement/operatorStaffId 六部分），人工翻阅或手写临时脚本都耗时。本脚本一键把持久化的
flow 响应解析为「决策所需最小摘要」，直接支持受理/评审/纪要判断。

数据形态（两种都兼容）：
  1. 结构化：resp.result.structuredContent 或其 .data -> {demand, flow, availableActions, stories, ...}
  2. 文本版：resp.result.content[0].text 为 "## Requirement flow query completed\n```json\n{...}\n```"
     （从 text 定位第一个 '{' 与最后一个 '}' 截取 json.loads）

用法：
  python parse_flow.py <flow响应文件>      # 最常用：传 .chat/tool-results/*.txt
  cat <文件> | python parse_flow.py        # stdin 模式
  python parse_flow.py --json '<JSON>'     # 直接传 MCP 返回 JSON 文本

退出码：0=解析成功；1=未提取到 flow 内容（此时打印原始文本前 2000 字符便于排查）
"""
import argparse
import json
import re
import sys


def load_text(path=None, stdin_text=None):
    if stdin_text is not None:
        return stdin_text
    with open(path, encoding="utf-8") as f:
        return f.read()


def _unwrap(text):
    """把外层包装逐层剥开：(1) 外层 success/result 包装 (2) MCP result.content 包装，返回 text 字段或 None"""
    # 先尝试整体 JSON
    try:
        obj = json.loads(text)
    except Exception:
        obj = None

    if isinstance(obj, dict):
        # 形态1：外层 {"success": true, "result": {"success": true, ...}}（工具持久化形态）
        res = obj.get("result")
        if isinstance(res, dict):
            res = res.get("result", res)
            if isinstance(res, dict) and isinstance(res.get("content"), list):
                for c in res["content"]:
                    if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                        return c["text"]
                # 无 text 则给 structuredContent 原样，交给 extract_data 复用
                if res.get("structuredContent"):
                    return json.dumps(res["structuredContent"], ensure_ascii=False)
        # 形态2：直接 MCP 响应 {"result": {"content": [...], "structuredContent": {...}}}
        content = res.get("content") if isinstance(res, dict) else None
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                    return c["text"]
            if isinstance(res, dict) and res.get("structuredContent"):
                return json.dumps(res["structuredContent"], ensure_ascii=False)
        # 形态3：已经是 flow 数据本身（有 demand/flow 键）
        if "demand" in obj or "flow" in obj or "stories" in obj:
            return json.dumps(obj, ensure_ascii=False)
    return text


def extract_data(text):
    """从文本提取 flow 数据字典。优先结构化 JSON，其次 text 内嵌 ```json 代码块"""
    # 尝试直接 json.loads（含 unwrap 后的 structuredContent 字符串）
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and ("demand" in obj or "data" in obj):
            return obj
    except Exception:
        pass

    # 定位 ```json ... ``` 代码块
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # 兜底：找第一个 '{' 与最后一个 '}' 截取
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    return None


def _get(obj, *keys, default=None):
    """按键链取值（dict 或 list of dict）"""
    cur = obj
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        elif isinstance(cur, list) and cur:
            cur = cur[0].get(k) if isinstance(cur[0], dict) else None
        else:
            return default
    return cur if cur is not None else default


def summarize(data):
    """打印 flow 精炼摘要（决策所需最小信息）"""
    demand = _get(data, "demand") or _get(data, "requirement") or {}
    flow = _get(data, "flow") or {}
    actions = _get(data, "availableActions") or []
    stories = _get(data, "stories") or []
    operator = _get(data, "operatorStaffId")

    lines = []
    lines.append("== flow 精炼摘要 ==")
    lines.append(f"  需求编号   : {_get(demand, 'demandId') or _get(demand, 'reqId')}")
    lines.append(f"  需求标题   : {_get(demand, 'summary') or _get(demand, 'title')}")
    lines.append(f"  当前状态   : {_get(demand, 'boardName') or _get(flow, 'statusName') or _get(flow, 'flowName')}")
    lines.append(f"  更新时间   : {_get(demand, 'updateTime')}")
    lines.append(f"  受理人     : {_get(demand, 'receiverNew') or _get(demand, 'receiver')}  ({_get(demand, 'receiver')})")
    co = _get(demand, 'commonReceiver')
    lines.append(f"  共同受理人 : {co if co else '无'}")
    lines.append(f"  归属部门   : {_get(demand, 'deptName')} / 审批人 {_get(demand, 'gmName')}")
    lines.append(f"  期望上线   : {_get(demand, 'wishDate')}")
    lines.append(f"  操作员     : {operator}")

    if isinstance(actions, list) and actions:
        lines.append("  可执行操作 :")
        for act in actions:
            name = _get(act, 'buttonName') or _get(act, 'name')
            code = _get(act, 'buttonCode') or _get(act, 'code')
            st = _get(act, 'buttonStatusName')
            extra = f"（{st}）" if st and st not in (name, "启用") else ""
            lines.append(f"    - {name} {code} {extra}".rstrip())
    else:
        lines.append("  可执行操作 : 无 / 未知")

    if stories:
        lines.append(f"  存量 Story : {len(stories)} 个")
        for s in stories[:20]:
            no = _get(s, 'storyNo') or _get(s, 'storyCode') or _get(s, 'storyId')
            title = _get(s, 'storyName') or _get(s, 'summary')
            st = _get(s, 'statusName') or _get(s, 'boardName')
            lines.append(f"    - {no}  {title}  [{st}]")
        if len(stories) > 20:
            lines.append(f"    ... 共 {len(stories)} 个")
    else:
        lines.append("  存量 Story : 无（未拆分）")

    summary = _get(demand, 'summary') or _get(demand, 'title')
    if summary:
        lines.append(f"  需求摘要   : {summary}")

    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description="query_requirement_flow 大响应一键精炼解析")
    ap.add_argument("path", nargs="?", help="flow 响应持久化文件路径")
    ap.add_argument("--json", dest="json_text", help="直接传入 MCP 返回 JSON 文本")
    a = ap.parse_args()

    if a.json_text:
        text = a.json_text
    elif a.path:
        text = load_text(a.path)
    else:
        # stdin 模式
        text = sys.stdin.read()

    inner = _unwrap(text)
    data = extract_data(inner)
    if data is None:
        print("== ERROR: 未提取到 flow 内容（解析失败）==", file=sys.stderr)
        print(text[:2000], file=sys.stderr)
        sys.exit(1)

    summarize(data)
    sys.exit(0)


if __name__ == "__main__":
    main()
