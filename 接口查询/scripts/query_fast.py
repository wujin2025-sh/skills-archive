#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
极速接口毫秒级查询工具 (基于 SQLite 结构化接口知识库)
支持:
1. 单个或多个功能号/文件编号 (如: query_fast.py z59 s03 s04)
2. 关键字/表名模糊搜索 (如: query_fast.py credittargetstk)
3. 纯 Markdown 结构化输出
耗时: < 0.001 秒 (1毫秒)
"""

import sys
import os
import sqlite3
import time
from pathlib import Path

# 数据源（外置盘）：可被环境变量 INTERFACE_BASE_DIR 覆盖
BASE_DIR = Path(os.environ.get(
    "INTERFACE_BASE_DIR", "/Volumes/Macintosh HD_Data/WorkBuddy/需求分析"))
DB_PATH = BASE_DIR / "rules-raw" / ".interface_store.db"

def format_markdown(iface, fields):
    lines = []
    lines.append(f"### 📌 接口: `{iface['code']}` - {iface['name']} ({iface['system_name']})")
    lines.append("")
    lines.append("| 属性 | 内容 |")
    lines.append("| --- | --- |")
    lines.append(f"| **系统分类** | {iface['system_type']} ({iface['system_name']} / {iface['category']}) |")
    lines.append(f"| **功能/文件号** | `{iface['code']}` |")
    lines.append(f"| **名称** | {iface['name']} |")
    if iface['table_name']:
        lines.append(f"| **数据库表名** | `{iface['table_name']}` |")
    if iface['version']:
        lines.append(f"| **版本号** | `{iface['version']}` |")
    if iface['manager']:
        lines.append(f"| **负责人** | `{iface['manager']}` |")
    if iface['description']:
        lines.append(f"| **描述** | {iface['description']} |")
    lines.append("")
    
    # Check sections
    sections = {}
    for f in fields:
        sec = f['section']
        sections.setdefault(sec, []).append(f)
        
    for sec_name, sec_fields in sections.items():
        title = "📥 输入参数" if sec_name == "input" else "📤 输出参数" if sec_name == "output" else "📑 字段列表"
        lines.append(f"#### {title} (共 {len(sec_fields)} 项)")
        lines.append("")
        if iface['system_type'] == '文件接口':
            lines.append("| 序号 | 字段 ID | 数据类型 | 中文含义 | 主键 | 缺省/格式 | 字典代码 |")
            lines.append("| :---: | --- | --- | --- | :---: | --- | :---: |")
            for idx, f in enumerate(sec_fields, 1):
                pk = "**Y**" if f['is_pk'] == 'Y' else '-'
                lines.append(f"| {idx} | `{f['field_name']}` | `{f['field_type']}` | {f['field_label']} | {pk} | {f['remark'] or '-'} | {f['dict_code'] or '-'} |")
        else:
            lines.append("| 序号 | 字段名 | 数据类型 | 业务说明 | 必须 | 缺省值 / 说明 | 字典代码 |")
            lines.append("| :---: | --- | --- | --- | :---: | --- | :---: |")
            for idx, f in enumerate(sec_fields, 1):
                req = "**Y**" if f['is_required'] == 'Y' else '-'
                lines.append(f"| {idx} | `{f['field_name']}` | `{f['field_type']}` | {f['field_label']} | {req} | {f['default_val'] or '-'} | {f['dict_code'] or '-'} |")
        lines.append("")
        
    return "\n".join(lines)

def query(keywords):
    if not DB_PATH.exists():
        print(f"❌ 数据库不存在，请先执行 build_interface_cache.py 初始化: {DB_PATH}")
        sys.exit(1)
        
    t0 = time.perf_counter()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    results = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        
        # 1. Exact match code or table_name
        cursor.execute("""
        SELECT * FROM interfaces 
        WHERE UPPER(code) = UPPER(?) OR UPPER(table_name) = UPPER(?)
        ORDER BY id
        """, (kw, kw))
        rows = cursor.fetchall()
        
        # 2. If not found, fuzzy match name or code
        if not rows:
            cursor.execute("""
            SELECT * FROM interfaces 
            WHERE code LIKE ? OR name LIKE ? OR table_name LIKE ?
            ORDER BY id
            """, (f"%{kw}%", f"%{kw}%", f"%{kw}%"))
            rows = cursor.fetchall()
            
        for iface in rows:
            if iface['id'] not in [r[0]['id'] for r in results]:
                cursor.execute("""
                SELECT * FROM interface_fields 
                WHERE interface_id = ? 
                ORDER BY id
                """, (iface['id'],))
                fields = cursor.fetchall()
                results.append((iface, fields))
                
    elapsed = (time.perf_counter() - t0) * 1000
    conn.close()
    
    if not results:
        print(f"❌ 未查询到匹配的接口记录 (耗时 {elapsed:.2f} ms)")
        return
        
    print(f"> ⚡ 查询耗时: **{elapsed:.2f} ms** | 命中 **{len(results)}** 个接口定义\n")
    for iface, fields in results:
        print(format_markdown(iface, fields))
        print("---\n")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python query_fast.py <功能号/文件编号/表名/关键字...> [支持多关键字，如: z59 s03 s04]")
        sys.exit(0)
    query(sys.argv[1:])
