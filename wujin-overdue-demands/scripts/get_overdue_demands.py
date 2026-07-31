#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
get_overdue_demands.py — 统计我受理的逾期交付且未上线需求汇总 (高保真版)
===================================================================
用法:
    python get_overdue_demands.py [-o output.md] [--exclude-status 已上线]
"""

import os
import json
import argparse
import requests
import sys

SESSION_FILE = "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.fintech_session.json"
LIST_URL = "https://fintech.gtht.com.cn/api/demand-service/demandsub/list"

def load_session_credentials():
    cookies = {}
    token = None
    if not os.path.exists(SESSION_FILE):
        return cookies, token
    try:
        with open(SESSION_FILE, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        for c in session_data.get("cookies", []):
            if c.get("domain") in ("fintech.gtht.com.cn", ".gtht.com.cn"):
                cookies[c["name"]] = c["value"]
        for origin_data in session_data.get("origins", []):
            if origin_data.get("origin") == "https://fintech.gtht.com.cn":
                for item in origin_data.get("localStorage", []):
                    if item.get("name") == "GTJA_TOKEN":
                        token = item.get("value")
                        break
    except Exception:
        pass
    return cookies, token

def print_terminal_table(records):
    # Calculate column widths
    headers = ["序号", "需求编号", "需求名称", "级别", "提出人", "提出部门", "状态", "期望上线", "耗时(天)"]
    widths = [4, 11, 40, 4, 8, 12, 12, 10, 8]
    
    # Helper to calculate CJK display width
    def display_width(s):
        w = 0
        for ch in str(s):
            if ord(ch) >= 0x2E80:
                w += 2
            else:
                w += 1
        return w
        
    def pad_cjk(text, width):
        text = str(text)
        cur = display_width(text)
        if cur >= width:
            return text
        return text + " " * (width - cur)
        
    def truncate_cjk(text, width):
        text = str(text)
        if display_width(text) <= width:
            return text
        res = []
        w = 0
        limit = width - 2
        for ch in text:
            ch_w = 2 if ord(ch) >= 0x2E80 else 1
            if w + ch_w > limit:
                break
            res.append(ch)
            w += ch_w
        return "".join(res) + ".."

    # Print header
    header_row = " | ".join(pad_cjk(h, w) for h, w in zip(headers, widths))
    print(header_row)
    print("-+-".join("-" * w for w in widths))
    
    for idx, d in enumerate(records):
        d_id = d.get("demandId", "") or "--"
        summary = truncate_cjk(d.get("summary", "") or "--", widths[2])
        priority = d.get("priority", "") or "--"
        org_user = d.get("orgUserName", "") or "--"
        dept = truncate_cjk(d.get("deptName", "") or "--", widths[5])
        status = d.get("boardName", "") or "--"
        wish_date = d.get("wishDate", "") or "--"
        deliv_time = d.get("deliveryTime", "")
        try:
            deliv_time_str = f"{float(deliv_time):.2f}"
        except (ValueError, TypeError):
            deliv_time_str = str(deliv_time) if deliv_time is not None and deliv_time != "" else "--"
            
        row_fields = [
            str(idx + 1),
            d_id,
            summary,
            priority,
            org_user,
            dept,
            status,
            wish_date,
            deliv_time_str
        ]
        print(" | ".join(pad_cjk(f, w) for f, w in zip(row_fields, widths)))

def generate_html_table(records):
    html = []
    html.append('<div style="background-color: #121212; padding: 20px; border-radius: 12px; border: 1px solid #2a2a2a; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif; box-shadow: 0 10px 40px rgba(0,0,0,0.6); overflow-x: auto;">')
    html.append('  <table style="width: 100%; border-collapse: collapse; color: #e0e0e0; font-size: 14px; min-width: 900px;">')
    html.append('    <thead>')
    html.append('      <tr style="background-color: #1e1e1e; border-bottom: 2px solid #2d2d2d; color: #8c8c8c;">')
    html.append('        <th style="padding: 14px 12px; font-weight: 500; width: 60px; text-align: center; border: 1px solid #2d2d2d;">序号</th>')
    html.append('        <th style="padding: 14px 12px; font-weight: 500; width: 130px; border: 1px solid #2d2d2d; text-align: center;">需求编号</th>')
    html.append('        <th style="padding: 14px 12px; font-weight: 500; border: 1px solid #2d2d2d;">需求名称</th>')
    html.append('        <th style="padding: 14px 12px; font-weight: 500; width: 70px; text-align: center; border: 1px solid #2d2d2d;">级别</th>')
    html.append('        <th style="padding: 14px 12px; font-weight: 500; width: 90px; text-align: center; border: 1px solid #2d2d2d;">提出人</th>')
    html.append('        <th style="padding: 14px 12px; font-weight: 500; width: 120px; border: 1px solid #2d2d2d;">提出部门</th>')
    html.append('        <th style="padding: 14px 12px; font-weight: 500; width: 140px; border: 1px solid #2d2d2d;">状态</th>')
    html.append('        <th style="padding: 14px 12px; font-weight: 500; width: 120px; text-align: center; border: 1px solid #2d2d2d;">期望上线时间</th>')
    html.append('        <th style="padding: 14px 12px; font-weight: 500; width: 110px; text-align: center; border: 1px solid #2d2d2d;">交付耗时 (天)</th>')
    html.append('      </tr>')
    html.append('    </thead>')
    html.append('    <tbody>')
    
    for idx, d in enumerate(records):
        d_id = d.get("demandId", "")
        summary = d.get("summary", "")
        priority = d.get("priority", "")
        org_user = d.get("orgUserName", "") or "--"
        dept = d.get("deptName", "") or "--"
        status = d.get("boardName", "") or "--"
        wish_date = d.get("wishDate", "") or "--"
        deliv_time = d.get("deliveryTime", "")
        try:
            deliv_time_str = f"{float(deliv_time):.2f}"
        except (ValueError, TypeError):
            deliv_time_str = str(deliv_time) if deliv_time is not None and deliv_time != "" else "--"
            
        border_bottom = "border-bottom: none;" if idx == len(records) - 1 else "border-bottom: 1px solid #252525;"
        td_style = f"padding: 16px 12px; border: 1px solid #252525; {border_bottom}"
        td_style_center = f"padding: 16px 12px; text-align: center; border: 1px solid #252525; {border_bottom}"
        
        html.append('      <tr>')
        html.append(f'        <td style="{td_style_center} color: #8c8c8c;">{idx+1}</td>')
        html.append(f'        <td style="{td_style_center}"><a href="https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId={d_id}&templateId=8888&flag=1" style="color: #3b82f6; text-decoration: none; font-weight: 500;">{d_id}</a></td>')
        html.append(f'        <td style="{td_style} line-height: 1.5;">{summary}</td>')
        html.append(f'        <td style="{td_style_center}">{priority}</td>')
        html.append(f'        <td style="{td_style_center}">{org_user}</td>')
        html.append(f'        <td style="{td_style}">{dept}</td>')
        html.append(f'        <td style="{td_style}">{status}</td>')
        html.append(f'        <td style="{td_style_center}">{wish_date}</td>')
        html.append(f'        <td style="{td_style_center}">{deliv_time_str}</td>')
        html.append('      </tr>')
        
    html.append('    </tbody>')
    html.append('  </table>')
    html.append('</div>')
    return "\n".join(html)

def main():
    parser = argparse.ArgumentParser(description="Query overdue demands assigned to you.")
    parser.add_argument("-o", "--output", help="Path to write the Markdown report.")
    parser.add_argument("--exclude-status", default="已上线", help="Status to filter out (default is '已上线'). Specify 'None' to disable filtering.")
    args = parser.parse_args()
    
    cookies, token = load_session_credentials()
    if not cookies or not token:
        print("错误: 未在 .fintech_session.json 中找到有效的登录态，请先运行其他 headed 模式技能登录。", file=sys.stderr)
        sys.exit(1)
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "accept": "application/json",
        "content-type": "application/json",
        "token": token
    }
    
    # myPutForward = 21 (我受理的), isexceed = "是" (逾期交付)
    payload = {
        "currentPage": 1,
        "pageSize": 500,
        "myPutForward": 21,
        "companyId": "comp01",
        "isexceed": "是"
    }
    
    try:
        r = requests.post(LIST_URL, json=payload, cookies=cookies, headers=headers, timeout=30)
        if r.status_code != 200:
            print(f"API 请求失败，HTTP 状态码: {r.status_code}", file=sys.stderr)
            sys.exit(1)
            
        resp = r.json()
        if resp.get("code") != 200:
            print(f"API 返回错误: {resp.get('msg')}", file=sys.stderr)
            sys.exit(1)
            
        records = resp.get("data", {}).get("records", [])
        
        # Filter status
        if args.exclude_status and args.exclude_status.lower() != 'none':
            exclude_list = [s.strip() for s in args.exclude_status.split(",")]
            records = [r for r in records if r.get("boardName") not in exclude_list]
            
        # Sort by demandId descending
        records.sort(key=lambda x: x.get("demandId", ""), reverse=True)
        
        print(f"已过滤筛选出 {len(records)} 条符合条件的逾期未上线需求。")
        if not records:
            sys.exit(0)
            
        # Print terminal table
        print()
        print_terminal_table(records)
        print()
        
        # Write markdown if output specified
        if args.output:
            md_content = []
            md_content.append("# 我受理的「是否逾期交付：是」需求汇总报告\n")
            md_content.append(f"本报告根据金融科技平台「需求管理」数据自动生成。")
            md_content.append(f"- **统计口径**: 我受理的 且 是否逾期交付为「是」")
            if args.exclude_status and args.exclude_status.lower() != 'none':
                md_content.append(f"- **排除状态**: {args.exclude_status}")
            md_content.append(f"- **总计需求数**: {len(records)} 个\n")
            
            # Embed high-fidelity HTML table
            md_content.append("## 需求卡片汇总 (高保真 HTML 格式)\n")
            md_content.append(generate_html_table(records))
            md_content.append("\n---\n")
            
            # Standard markdown table fallback
            md_content.append("## 需求列表明细 (Markdown 格式)\n")
            md_content.append("| 序号 | 需求编号 | 需求名称 | 级别 | 提出人 | 提出部门 | 状态 | 期望上线时间 | 交付耗时 (天) |")
            md_content.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
            
            for idx, d in enumerate(records):
                d_id = d.get("demandId", "")
                summary = d.get("summary", "").replace("|", "\\|")
                priority = d.get("priority", "")
                org_user = d.get("orgUserName", "") or "--"
                dept = d.get("deptName", "") or "--"
                status = d.get("boardName", "") or "--"
                wish_date = d.get("wishDate", "") or "--"
                deliv_time = d.get("deliveryTime", "")
                try:
                    deliv_time_str = f"{float(deliv_time):.2f}"
                except (ValueError, TypeError):
                    deliv_time_str = str(deliv_time) if deliv_time is not None and deliv_time != "" else "--"
                    
                md_content.append(f"| {idx+1} | [{d_id}](https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId={d_id}&templateId=8888&flag=1) | {summary} | {priority} | {org_user} | {dept} | {status} | {wish_date} | {deliv_time_str} |")
                
            with open(args.output, "w", encoding="utf-8") as f:
                f.write("\n".join(md_content))
            print(f"已成功将高保真 Markdown 报告写入: {os.path.abspath(args.output)}")
            
    except Exception as e:
        print(f"执行异常: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
