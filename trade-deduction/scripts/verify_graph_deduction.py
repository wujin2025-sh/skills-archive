#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_graph_deduction.py — 交易推演代码图谱 DB 自动核验辅助脚本

连接集中交易(jzjy)/集中清算(jzqs)/参数中心(cszx)代码图谱数据库(graph.db)，
根据输入的推演关键字（如 datasum, 维保比, 代扣税, F500122, fundavl），
提取对应代码 Node、C++ 函数签名、物理文件路径(file://)及源码片段，
输出交易推算的第一权威代码事实对比表。

用法：
  python3 verify_graph_deduction.py --query "datasum" [--system jzjy|jzqs|cszx|all] [--snippet]
"""
import os, sys, sqlite3, argparse, json
from pathlib import Path

GRAPH_DBS = {
    "jzjy": Path("/Volumes/Macintosh HD_Data/Project/jzjy/spbsrc/.code-review-graph/graph.db"),
    "jzqs": Path("/Volumes/Macintosh HD_Data/Project/jzqs/src/.code-review-graph/graph.db"),
    "cszx": Path("/Volumes/Macintosh HD_Data/Project/jygl/jygl_sys/.code-review-graph/graph.db"),
}

def query_system_graph(sys_key: str, db_path: Path, query_term: str, fetch_snippet: bool = False, max_results: int = 10):
    if not db_path.exists():
        return []
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 模糊匹配 name / qualified_name / extra / signature
    pattern = f"%{query_term}%"
    sql = """
        SELECT id, kind, name, qualified_name, file_path, line_start, line_end, signature, extra
        FROM nodes
        WHERE name LIKE ? OR qualified_name LIKE ? OR signature LIKE ? OR extra LIKE ?
        ORDER BY CASE WHEN kind IN ('Function', 'Method', 'Class') THEN 0 ELSE 1 END, id ASC
        LIMIT ?
    """
    
    results = []
    try:
        cursor.execute(sql, (pattern, pattern, pattern, pattern, max_results))
        rows = cursor.fetchall()
        for r in rows:
            fp = r["file_path"]
            abs_fp = fp if fp.startswith("/") else str(db_path.parent.parent / fp)
            file_url = f"file://{abs_fp}"
            
            snippet_text = ""
            if fetch_snippet and os.path.exists(abs_fp) and r["line_start"] and r["line_end"]:
                try:
                    with open(abs_fp, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        start = max(0, r["line_start"] - 1)
                        end = min(len(lines), r["line_end"])
                        snippet_text = "".join(lines[start:end])
                except Exception:
                    pass
            
            results.append({
                "system": sys_key,
                "id": r["id"],
                "kind": r["kind"],
                "name": r["name"],
                "qualified_name": r["qualified_name"],
                "file_path": abs_fp,
                "file_url": file_url,
                "line_start": r["line_start"],
                "line_end": r["line_end"],
                "signature": r["signature"] or "",
                "snippet": snippet_text
            })
    except Exception as e:
        print(f"⚠️ 查询 {sys_key} 图谱出错: {e}", file=sys.stderr)
    finally:
        conn.close()
        
    return results

def main():
    parser = argparse.ArgumentParser(description="交易推演代码图谱 DB 自动核验脚本")
    parser.add_argument("--query", "-q", required=True, help="推演查询关键字，如 datasum / 维保比 / F500122")
    parser.add_argument("--system", "-s", default="jzjy", choices=["jzjy", "jzqs", "cszx", "all"], help="目标图谱系统")
    parser.add_argument("--snippet", action="store_true", help="提取源码片段")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--limit", type=int, default=10, help="最多返回条目数量")
    
    args = parser.parse_args()
    
    systems_to_check = [args.system] if args.system != "all" else ["jzjy", "jzqs", "cszx"]
    all_results = []
    
    for sys_key in systems_to_check:
        db_p = GRAPH_DBS.get(sys_key)
        if db_p:
            res = query_system_graph(sys_key, db_p, args.query, fetch_snippet=args.snippet, max_results=args.limit)
            all_results.extend(res)
            
    if args.json:
        print(json.dumps(all_results, ensure_ascii=False, indent=2))
        return
        
    print(f"\n🔍 === 交易推演代码图谱 DB 核验结果 (关键字: '{args.query}') ===\n")
    if not all_results:
        print("⚠️ 未在图谱 DB 中查找到直接匹配的代码节点。建议扩大关键字检索。")
        return

    print("| 系统 | 类型 | 名称 / 函数签名 | 物理源码路径 (file://) | 行号 |")
    print("| :--- | :--- | :--- | :--- | :--- |")
    for r in all_results:
        disp_name = r["signature"] if r["signature"] else r["name"]
        lines_str = f"L{r['line_start']}-L{r['line_end']}" if r['line_start'] else "-"
        print(f"| {r['system']} | {r['kind']} | `{disp_name}` | [{r['file_path'].split('/')[-1]}]({r['file_url']}) | {lines_str} |")

    if args.snippet:
        print("\n📝 === 提取的代码事实片段 ===")
        for r in all_results:
            if r["snippet"]:
                print(f"\n#### [{r['system']}] {r['qualified_name']} ({r['file_url']})")
                print("```cpp")
                print(r["snippet"].strip()[:1000])  # 展示前1000字符
                print("```")

if __name__ == "__main__":
    main()
