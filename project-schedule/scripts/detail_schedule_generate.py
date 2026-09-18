#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detail_schedule_generate.py — 需求进度详细跟踪表生成器（多环节详细跟进与预警版）
=============================================================================
批量查询多个需求编号或史诗编号，提取开发、SIT测试、UAT自测等各个环节的负责人、
预计结束时间及计划交付时间，针对已逾期环节提示【🚨 已逾期】，临近到期（≤3天）提示【⚠️ 临近到期】，
自动生成带分组头和单元格合并的 HTML & Markdown 需求进度详细跟踪表。

用法:
  python detail_schedule_generate.py <需求ID_或_史诗ID_1> <需求ID_或_史诗ID_2> ... [--project 项目名称] [--output_html html路径] [--output_md md路径]
"""

import sys
import os
import re
import json
import asyncio
import argparse
from datetime import datetime

# 动态获取当前系统日期
CURRENT_DATE_TEMP = datetime.now()
CURRENT_DATE_STR = CURRENT_DATE_TEMP.strftime("%Y-%m-%d")
CURRENT_DATE_FILE_STR = CURRENT_DATE_TEMP.strftime("%Y%m%d")
CURRENT_DATE = datetime.strptime(CURRENT_DATE_STR, "%Y-%m-%d")

# 共享映射（shared_maps.json 单一数据源）：需求子标题 + Story 名称精炼，人工维护
def _load_shared_maps():
    """加载共享映射：DEMAND_SUBTITLE_MAP / STORY_NAME_MAP（人工精炼产物，单一数据源）"""
    maps_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared_maps.json")
    if os.path.exists(maps_path):
        try:
            with open(maps_path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("demand_subtitle", {}), data.get("story_name", {})
        except Exception:
            pass
    return {}, {}

DEMAND_SUBTITLE_MAP, STORY_NAME_MAP = _load_shared_maps()

# 动态流程节点解析映射（优先自动从 Live Scraper / Cache 载入，覆盖各阶段【经办人】多人显示）
LIVE_NODE_MAP = {}
LIVE_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_dynamic_node_results.json")
if os.path.exists(LIVE_CACHE_PATH):
    try:
        with open(LIVE_CACHE_PATH, "r", encoding="utf-8") as f:
            LIVE_NODE_MAP = json.load(f)
    except Exception:
        LIVE_NODE_MAP = {}

def clean_story_name(story_id, original_name):
    if story_id in STORY_NAME_MAP:
        return STORY_NAME_MAP[story_id]
    
    name = re.sub(r'^【.*?】', '', original_name)
    name = re.sub(r'^JY\d+\-', '', name)
    name = name.strip()
    name = name.replace("等接口从集中交易切换至清算", "切换配合")
    name = name.replace("从集中交易迁移到集中清算", "迁移配合")
    name = name.replace("从集中交易迁移到三方存管", "迁移配合")
    name = name.replace("历史数据及文件从集中交易迁移到集中清算", "历史数据迁移")
    name = name.replace("历史文件从集中交易迁移到集中清算", "历史文件迁移")
    return name

def parse_owner(text):
    """通用经办人解析：自动切分逗号/空格/换行/斜杠/顿号分隔的多人，及无分隔符连体中文姓名
    （如 刘志林金渤文 -> 刘志林, 金渤文）。返回 ", " 连接的字符串（保持顺序去重），无有效值返回 "/"。"""
    if not text or str(text).strip() in ("/", "--", "None", "", "null"):
        return "/"
    raw_items = re.split(r'[,，/\\;\n\t、\s]+', str(text).strip())
    names = []
    for item in raw_items:
        s_item = item.strip()
        if not s_item:
            continue
        match = re.search(r'^([\u4e00-\u9fa5]+)', s_item)
        if match:
            cn = match.group(1)
            if len(cn) > 4 and len(cn) <= 8:
                if len(cn) == 6:
                    parts = [cn[:3], cn[3:]]
                elif len(cn) == 4:
                    parts = [cn[:2], cn[2:]]
                elif len(cn) == 5:
                    parts = [cn[:3], cn[3:]]
                else:
                    parts = [cn]
            else:
                parts = [cn]
        else:
            parts = [s_item]
        for p in parts:
            p = p.strip()
            if p and p not in ("/", "--") and p not in names:
                names.append(p)
    return ", ".join(names) if names else "/"

def clean_date_str(date_str):
    if not date_str or date_str in ("--", "None", ""):
        return "--"
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(date_str))
    return match.group(0) if match else "--"

def compute_phase_status(end_date_str, is_done, is_terminated=False):
    """
    计算环节/总体预警状态:
    - 结束/终止: ✅ 已完成 / 🛑 已终止
    - 无排期: --
    - 逾期: 🚨 已逾期
    - 临近到期 (≤3天): ⚠️ 临近到期 (还剩X天) / ⚠️ 今天到期
    - 正常: 正常
    """
    if is_done:
        return "✅ 已完成"
    if is_terminated:
        return "🛑 已终止"
    
    clean_date = clean_date_str(end_date_str)
    if clean_date == "--":
        return "--"
    
    try:
        dt = datetime.strptime(clean_date, "%Y-%m-%d")
        delta_days = (dt.date() - CURRENT_DATE.date()).days
        if dt.date() < CURRENT_DATE.date():
            return "🚨 已逾期"
        elif 0 <= delta_days <= 3:
            if delta_days == 0:
                return "⚠️ 今天到期"
            else:
                return f"⚠️ 临近到期 ({delta_days}天)"
        else:
            return "正常"
    except Exception:
        return "正常"

def get_badge_class(status_str):
    if "已完成" in status_str:
        return "badge-done"
    elif "已终止" in status_str:
        return "badge-terminated"
    elif "已逾期" in status_str:
        return "badge-overdue"
    elif "临近" in status_str or "今天" in status_str:
        return "badge-warning"
    elif status_str == "正常":
        return "badge-normal"
    else:
        return "badge-muted"

def load_demand_data_from_cache(demand_ids, script_dir):
    """从本地 .table_cache.json 加载需求的 Story 明细数据"""
    possible_cache_paths = [
        os.path.join(os.getcwd(), ".table_cache.json"),
        os.path.join(script_dir, ".table_cache.json"),
        os.path.join(os.path.dirname(script_dir), ".table_cache.json"),
        "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.table_cache.json"
    ]
    
    cache_data = None
    for cp in possible_cache_paths:
        if os.path.exists(cp):
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                break
            except Exception:
                pass
                
    if not cache_data:
        return {}

    demands_dict = {}
    for d_id in demand_ids:
        rows = [r for r in cache_data if r.get("demandId") == d_id]
        if not rows:
            continue
            
        first_row = rows[0]
        title = first_row.get("demandTitle") or first_row.get("storyTitle") or ""
        subtitle = DEMAND_SUBTITLE_MAP.get(d_id, "")
        if not subtitle and title:
            subtitle = re.sub(r'^(JY\d+\-|【.*?】)', '', title).strip()
            if len(subtitle) > 15:
                subtitle = subtitle[:15] + "..."

        stories = []
        for r in rows:
            s_id = r.get("storyCode") or r.get("storyNo") or ""
            raw_s_name = r.get("storyTitle") or ""
            s_name = clean_story_name(s_id, raw_s_name)
            system = r.get("storySystemName") or ""
            status = r.get("storyStatusName") or r.get("demandStatus") or ""
            
            is_done = (status in ("结束", "SIT大远期自测完成", "UAT验收完成", "完成", "已发布"))
            is_terminated = (status == "终止")

            if s_id in LIVE_NODE_MAP and LIVE_NODE_MAP[s_id].get("dev"):
                dev_owner = ", ".join(LIVE_NODE_MAP[s_id]["dev"])
            else:
                dev_owner = parse_owner(r.get("devManagePerson"))
            dev_end = clean_date_str(r.get("devAssessDateEnd"))
            dev_status = compute_phase_status(dev_end, is_done, is_terminated)

            if s_id in LIVE_NODE_MAP and LIVE_NODE_MAP[s_id].get("sit"):
                sit_owner = ", ".join(LIVE_NODE_MAP[s_id]["sit"])
            else:
                sit_owner = parse_owner(r.get("sitTestManagePerson"))
            sit_end = clean_date_str(r.get("sitTestAssessDateEnd"))
            sit_status = compute_phase_status(sit_end, is_done, is_terminated)

            if s_id in LIVE_NODE_MAP and LIVE_NODE_MAP[s_id].get("uat"):
                uat_owner = ", ".join(LIVE_NODE_MAP[s_id]["uat"])
            else:
                uat_owner = parse_owner(r.get("uatTestManagePerson"))
            uat_end = clean_date_str(r.get("uatTestAssessDateEnd"))
            uat_status = compute_phase_status(uat_end, is_done, is_terminated)

            delivery_date = clean_date_str(r.get("storyPlanLineDate") or r.get("largeDeliverDate"))
            overall_status = compute_phase_status(delivery_date, is_done, is_terminated)

            # 综合风险判定（如果任意环节逾期，综合风险即为逾期；若无逾期但有临近到期，为预警）
            phase_statuses = [dev_status, sit_status, uat_status, overall_status]
            if "🚨 已逾期" in phase_statuses:
                overall_status = "🚨 已逾期"
            elif any("临近到期" in ps or "今天到期" in ps for ps in phase_statuses) and overall_status != "✅ 已完成":
                overall_status = "⚠️ 临近预警"

            stories.append({
                "id": s_id,
                "name": s_name,
                "system": system,
                "status": status,
                "dev_owner": dev_owner,
                "dev_end": dev_end,
                "dev_status": dev_status,
                "sit_owner": sit_owner,
                "sit_end": sit_end,
                "sit_status": sit_status,
                "uat_owner": uat_owner,
                "uat_end": uat_end,
                "uat_status": uat_status,
                "delivery_date": delivery_date,
                "overall_status": overall_status
            })

        demands_dict[d_id] = {
            "demand_id": d_id,
            "title": title,
            "subtitle": subtitle,
            "stories": stories
        }

    return demands_dict

def generate_html(data_list, output_path, project_name):
    rows_html = []
    
    for idx, item in enumerate(data_list):
        demand_id = item["demand_id"]
        subtitle = item["subtitle"]
        stories = item["stories"]
        story_count = len(stories)
        
        row_style = ' style="border-top: 2px solid #cbd5e1;"' if idx > 0 else ''
        
        if story_count == 0:
            rows_html.append(f"""
      <tr{row_style}>
        <td class="req-col">
          <a href="https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId={demand_id}&templateId=8888&flag=1" target="_blank" style="font-weight: bold; text-decoration: underline;">{demand_id}</a>
          <span class="req-sub">{subtitle}</span>
        </td>
        <td colspan="15" style="text-align: center; color: #64748b;">（无关联 Story）</td>
      </tr>""")
        else:
            for s_idx, story in enumerate(stories):
                dev_badge = f'<span class="badge {get_badge_class(story["dev_status"])}">{story["dev_status"]}</span>'
                sit_badge = f'<span class="badge {get_badge_class(story["sit_status"])}">{story["sit_status"]}</span>'
                uat_badge = f'<span class="badge {get_badge_class(story["uat_status"])}">{story["uat_status"]}</span>'
                overall_badge = f'<span class="badge {get_badge_class(story["overall_status"])}">{story["overall_status"]}</span>'

                system_td = f'<td class="system-highlight">{story["system"]}</td>' if "清算" in story["system"] else f'<td>{story["system"]}</td>'
                
                # 状态列着色
                status_style = ""
                if story["status"] in ("结束", "SIT大远期自测完成", "UAT验收完成"):
                    status_style = ' style="color: #166534; font-weight: 500;"'
                elif "SIT" in story["status"] or "开发" in story["status"]:
                    status_style = ' style="color: #b45309; font-weight: 500;"'

                if s_idx == 0:
                    rows_html.append(f"""
      <tr{row_style}>
        <td rowspan="{story_count}" class="req-col">
          <a href="https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId={demand_id}&templateId=8888&flag=1" target="_blank" style="font-weight: bold; text-decoration: underline;">{demand_id}</a>
          <span class="req-sub">{subtitle}</span>
        </td>
        <td><strong>{story["id"]}</strong></td>
        <td class="story-name-col">{story["name"]}</td>
        {system_td}
        <td{status_style}>{story["status"]}</td>
        <td>{story["dev_owner"]}</td>
        <td>{story["dev_end"]}</td>
        <td>{dev_badge}</td>
        <td>{story["sit_owner"]}</td>
        <td>{story["sit_end"]}</td>
        <td>{sit_badge}</td>
        <td>{story["uat_owner"]}</td>
        <td>{story["uat_end"]}</td>
        <td>{uat_badge}</td>
        <td><strong>{story["delivery_date"]}</strong></td>
        <td>{overall_badge}</td>
      </tr>""")
                else:
                    rows_html.append(f"""
      <tr>
        <td><strong>{story["id"]}</strong></td>
        <td class="story-name-col">{story["name"]}</td>
        {system_td}
        <td{status_style}>{story["status"]}</td>
        <td>{story["dev_owner"]}</td>
        <td>{story["dev_end"]}</td>
        <td>{dev_badge}</td>
        <td>{story["sit_owner"]}</td>
        <td>{story["sit_end"]}</td>
        <td>{sit_badge}</td>
        <td>{story["uat_owner"]}</td>
        <td>{story["uat_end"]}</td>
        <td>{uat_badge}</td>
        <td><strong>{story["delivery_date"]}</strong></td>
        <td>{overall_badge}</td>
      </tr>""")

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{project_name} - 需求进度详细跟踪表</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background-color: #f8fafc;
    color: #1e293b;
    padding: 24px 16px;
    margin: 0;
  }}
  .container {{
    max-width: 1680px;
    margin: 0 auto;
    background-color: #ffffff;
    padding: 24px 28px;
    border-radius: 16px;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01);
    border: 1px solid #e2e8f0;
  }}
  .header-banner {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 3px solid #2563eb;
    padding-bottom: 12px;
    margin-bottom: 20px;
  }}
  h2 {{
    font-size: 22px;
    font-weight: 700;
    color: #1e3a8a;
    margin: 0;
  }}
  .sub-date {{
    font-size: 13px;
    color: #64748b;
    font-weight: 500;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    font-size: 12px;
    text-align: left;
  }}
  thead tr.group-header th {{
    background-color: #1e40af;
    color: #ffffff;
    font-weight: 700;
    text-align: center;
    border: 1px solid #1d4ed8;
    padding: 8px 6px;
    font-size: 13px;
  }}
  thead tr.sub-header th {{
    background-color: #f1f5f9;
    color: #334155;
    font-weight: 700;
    padding: 10px 8px;
    border: 1px solid #cbd5e1;
    text-align: left;
  }}
  td {{
    padding: 10px 8px;
    border: 1px solid #cbd5e1;
    color: #334155;
    vertical-align: middle;
  }}
  tr:hover {{
    background-color: #f8fafc;
  }}
  .req-col {{
    font-weight: bold;
    background-color: #f8fafc;
    color: #1e40af;
    vertical-align: middle;
    text-align: center;
    min-width: 110px;
  }}
  .req-sub {{
    font-size: 11px;
    color: #64748b;
    font-weight: normal;
    display: block;
    margin-top: 4px;
  }}
  .story-name-col {{
    max-width: 180px;
    word-break: break-all;
  }}
  .badge {{
    display: inline-block;
    padding: 2px 7px;
    border-radius: 9999px;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
  }}
  .badge-done {{
    background-color: #dcfce7;
    color: #15803d;
  }}
  .badge-terminated {{
    background-color: #f1f5f9;
    color: #64748b;
  }}
  .badge-overdue {{
    background-color: #fee2e2;
    color: #b91c1c;
    border: 1px solid #fca5a5;
  }}
  .badge-warning {{
    background-color: #fef3c7;
    color: #b45309;
    border: 1px solid #fcd34d;
  }}
  .badge-normal {{
    background-color: #e0f2fe;
    color: #0369a1;
  }}
  .badge-muted {{
    color: #94a3b8;
  }}
  .system-highlight {{
    font-weight: 600;
    color: #1d4ed8;
  }}
  .legend-bar {{
    margin-top: 16px;
    font-size: 12px;
    color: #475569;
    display: flex;
    gap: 16px;
    align-items: center;
  }}
</style>
</head>
<body>

<div class="container">
  <div class="header-banner">
    <h2>📋 {project_name} - 需求进度详细跟踪表</h2>
    <span class="sub-date">跟踪日期：{CURRENT_DATE_STR}（评估标准：临近到期≤3天预警）</span>
  </div>

  <table>
    <thead>
      <tr class="group-header">
        <th colspan="5">📌 Story 基础与当前状态</th>
        <th colspan="3">💻 开发相关</th>
        <th colspan="3">🧪 SIT 测试</th>
        <th colspan="3">🔍 UAT 自测</th>
        <th colspan="2">🚀 交付与综合预警</th>
      </tr>
      <tr class="sub-header">
        <th>需求编号</th>
        <th>Story编号</th>
        <th>任务名称</th>
        <th>涉及系统</th>
        <th>当前状态</th>
        <th>开发负责人</th>
        <th>预计结束</th>
        <th>开发状态</th>
        <th>SIT负责人</th>
        <th>预计结束</th>
        <th>SIT状态</th>
        <th>UAT负责人</th>
        <th>预计结束</th>
        <th>UAT状态</th>
        <th>计划交付</th>
        <th>综合预警</th>
      </tr>
    </thead>
    <tbody>{"".join(rows_html)}
    </tbody>
  </table>

  <div class="legend-bar">
    <strong>图例说明：</strong>
    <span class="badge badge-done">✅ 已完成</span>
    <span class="badge badge-overdue">🚨 已逾期</span>
    <span class="badge badge-warning">⚠️ 临近到期 (≤3天)</span>
    <span class="badge badge-normal">正常</span>
    <span class="badge badge-muted">-- 未排期</span>
  </div>
</div>

</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[DetailedSchedule] 已成功生成 HTML 表格: {output_path}")

def generate_markdown(data_list, output_path, project_name):
    lines = []
    lines.append(f"# 📋 {project_name} - 需求进度详细跟踪表 ({CURRENT_DATE_STR})")
    lines.append("")
    lines.append("> **评估规则**：已结束标记为 `✅ 已完成`；逾期阶段标记为 `🚨 已逾期`；距预计结束时间 ≤3 天标记为 `⚠️ 临近到期`。")
    lines.append("")
    lines.append("| 需求编号 | Story编号 | 任务名称 | 涉及系统 | 当前状态 | 开发负责人 | 开发预计结束 | 开发状态 | SIT负责人 | SIT预计结束 | SIT状态 | UAT负责人 | UAT预计结束 | UAT状态 | 计划交付 | 综合预警 |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    all_stories = []
    for item in data_list:
        demand_id = item["demand_id"]
        subtitle = item["subtitle"]
        stories = item["stories"]
        demand_col = f"**{demand_id}**<br>({subtitle})"
        
        if len(stories) == 0:
            lines.append(f"| {demand_col} | - | (无关联 Story) | - | - | - | - | - | - | - | - | - | - | - | - | - |")
        else:
            for s_idx, story in enumerate(stories):
                s_copy = story.copy()
                s_copy["demand_id"] = demand_id
                s_copy["demand_subtitle"] = subtitle
                all_stories.append(s_copy)

                d_col = demand_col if s_idx == 0 else ""
                lines.append(
                    f"| {d_col} | **{story['id']}** | {story['name']} | {story['system']} | {story['status']} | "
                    f"{story['dev_owner']} | {story['dev_end']} | {story['dev_status']} | "
                    f"{story['sit_owner']} | {story['sit_end']} | {story['sit_status']} | "
                    f"{story['uat_owner']} | {story['uat_end']} | {story['uat_status']} | "
                    f"**{story['delivery_date']}** | {story['overall_status']} |"
                )

    # 统计与风险汇总部分
    lines.append("")
    lines.append("## 🚨 重点逾期与预警汇总")
    lines.append("")

    overdue_list = [s for s in all_stories if "已逾期" in s["overall_status"] or "已逾期" in s["dev_status"] or "已逾期" in s["sit_status"] or "已逾期" in s["uat_status"]]
    warning_list = [s for s in all_stories if "临近" in s["overall_status"] or "今天" in s["overall_status"] or "临近" in s["sit_status"] or "临近" in s["dev_status"] or "临近" in s["uat_status"]]

    if not overdue_list and not warning_list:
        lines.append("- **✅ 整体良好**：目前暂无已逾期或临近 3 天到期的 Story。")
    else:
        if overdue_list:
            lines.append(f"### 🚨 已逾期 Story (共 {len(overdue_list)} 个)")
            for s in overdue_list:
                overdue_phases = []
                if "已逾期" in s["dev_status"]: overdue_phases.append(f"开发(结束:{s['dev_end']}/人:{s['dev_owner']})")
                if "已逾期" in s["sit_status"]: overdue_phases.append(f"SIT(结束:{s['sit_end']}/人:{s['sit_owner']})")
                if "已逾期" in s["uat_status"]: overdue_phases.append(f"UAT(结束:{s['uat_end']}/人:{s['uat_owner']})")
                if "已逾期" in s["overall_status"] and not overdue_phases: overdue_phases.append(f"交付(计划:{s['delivery_date']})")
                lines.append(f"- **{s['id']}** ({s['name']}) — 需求: `{s['demand_id']}` | 系统: `{s['system']}` | 逾期环节: `{' / '.join(overdue_phases)}`")
            lines.append("")

        if warning_list:
            lines.append(f"### ⚠️ 临近到期预警 (≤3天, 共 {len(warning_list)} 个)")
            for s in warning_list:
                warn_phases = []
                if "临近" in s["dev_status"] or "今天" in s["dev_status"]: warn_phases.append(f"开发({s['dev_status']})")
                if "临近" in s["sit_status"] or "今天" in s["sit_status"]: warn_phases.append(f"SIT({s['sit_status']})")
                if "临近" in s["uat_status"] or "今天" in s["uat_status"]: warn_phases.append(f"UAT({s['uat_status']})")
                lines.append(f"- **{s['id']}** ({s['name']}) — 需求: `{s['demand_id']}` | 系统: `{s['system']}` | 预警环节: `{' / '.join(warn_phases)}`")
            lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")
    print(f"[DetailedSchedule] 已成功生成 Markdown 表格: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="生成需求进度详细跟踪表（含开发、SIT、UAT各环节预警）")
    parser.add_argument("demand_ids", nargs="+", help="需求编号列表（以空格分隔）")
    parser.add_argument("--output_html", default=None, help="生成的 HTML 表格路径")
    parser.add_argument("--output_md", default=None, help="生成的 Markdown 表格路径")
    parser.add_argument("--project", default="交易结算核心历史数据及接口迁移项目", help="项目名称")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    demands_dict = load_demand_data_from_cache(args.demand_ids, script_dir)
    
    data_list = []
    for d_id in args.demand_ids:
        if d_id in demands_dict:
            data_list.append(demands_dict[d_id])
        else:
            data_list.append({
                "demand_id": d_id,
                "title": "",
                "subtitle": DEMAND_SUBTITLE_MAP.get(d_id, ""),
                "stories": []
            })

    output_html = args.output_html or f"{CURRENT_DATE_FILE_STR}-详细进度-{args.project}.html"
    output_md = args.output_md or f"{CURRENT_DATE_FILE_STR}-详细进度-{args.project}.md"

    generate_html(data_list, output_html, args.project)
    generate_markdown(data_list, output_md, args.project)

    # 自动同步 Obsidian 进度跟踪目录（如果目录存在）
    obsidian_dir = "/Volumes/Macintosh HD_Data/obsidian/100_Projects/进度跟踪"
    if os.path.exists(obsidian_dir):
        obsidian_md_path = os.path.join(obsidian_dir, os.path.basename(output_md))
        try:
            with open(output_md, "r", encoding="utf-8") as src, open(obsidian_md_path, "w", encoding="utf-8") as dst:
                dst.write(src.read())
            print(f"[DetailedSchedule] 已同步写入 Obsidian 目录: {obsidian_md_path}")
        except Exception as e:
            print(f"[DetailedSchedule] 同步 Obsidian 目录失败: {e}")

if __name__ == "__main__":
    main()
