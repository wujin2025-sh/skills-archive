#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
project_schedule_generate.py — 项目进度表生成器（参考 demand-detail-schedule 输出要素）
=============================================================================
支持输入需求编号或史诗编号（如 PG202204-0236），输出包含【Story基础】、【开发环节】、
【SIT测试】、【UAT自测】、【交付与综合预警】16大要素的精美 HTML & Markdown 进度跟踪表。
"""

import sys
import os
import re
import json
import asyncio
import argparse
from datetime import datetime
from collections import defaultdict

# 动态获取当前系统日期
CURRENT_DATE_TEMP = datetime.now()
CURRENT_DATE_STR = CURRENT_DATE_TEMP.strftime("%Y-%m-%d")
CURRENT_DATE_FILE_STR = CURRENT_DATE_TEMP.strftime("%Y%m%d")
CURRENT_DATE = datetime.strptime(CURRENT_DATE_STR, "%Y-%m-%d")

# 预编译正则提高字符串处理性能
RE_BRACKETS = re.compile(r'^【.*?】')
RE_JY = re.compile(r'^JY\d+\-')
RE_DATE = re.compile(r'\d{4}-\d{2}-\d{2}')
RE_SUBTITLE = re.compile(r'^(JY\d+\-|【.*?】)')

# 全局内存缓存单例
_CACHE_DATA_SINGLETON = None
_CACHE_INDEX_BY_DEMAND = None

# 需求编号子标题映射
DEMAND_SUBTITLE_MAP = {
    "R2603130062": "富易网络投票切换清算",
    "R2603110056": "历史文件迁移到清算",
    "R2602120019": "银证转账历史文件迁移",
    "R2602120009": "交易历史文件迁移",
    "R2602120017": "担保费率等迁移参数后台",
    "R2604300028": "融资仓单偿还数量优化",
    "R2606170151": "买券还券增加风险警示板权限",
}

# 已知 Story ID 到任务名称硬编码映射（优先匹配）
STORY_NAME_MAP = {
    "S2603160070": "富易网络投票切换清算配合",
    "S2603160083": "移动端网络投票切换封装配合",
    "S2603190133": "JY977-富易投票切换清算",
    "S2603190136": "富易投票接口切换测试配合",
    "S2603110132": "配合测试-历史文件迁移",
    "S2603110133": "委托和沪港通委托历史文件迁移",
    "S2603190060": "历史文件迁移非现场配合",
    "S2603190061": "历史文件迁移反洗钱配合",
    "S2603190062": "历史文件迁移信用业务配合",
    "S2605290172": "历史文件迁移大数据配合",
    "S2606080286": "配合历史数据迁移监控",
    "S2602120030": "银证转账迁移配合测试",
    "S2602120031": "银证转账迁移集中交易配合",
    "S2603110087": "银证转账迁移大数据模块",
    "S2603180160": "银证转账配合(BDNEW_3.1)",
    "S2603180162": "银证转账迁移反洗钱配合",
    "S2603180163": "银证转账迁移非现场配合",
    "S2602120011": "集中交易历史数据文件迁移",
    "S2602120012": "集中交易历史数据迁移配合",
    "S2603190066": "历史数据迁移非现场监控配合",
    "S2603190067": "历史文件迁移反洗钱监控配合",
    "S2603190068": "历史文件迁移信用业务配合",
    "S2602120027": "两融担保费率迁移至参数后台",
    "S2602120029": "两融历史文件迁移配合测试",
    "S2605290171": "两融历史文件迁移信用配合",
    "S2605290177": "两融历史文件迁移非现场配合"
}

def clean_story_name(story_id, original_name):
    if story_id in STORY_NAME_MAP:
        return STORY_NAME_MAP[story_id]
    name = RE_BRACKETS.sub('', original_name)
    name = RE_JY.sub('', name).strip()
    name = name.replace("等接口从集中交易切换至清算", "切换配合")
    name = name.replace("从集中交易迁移到集中清算", "迁移配合")
    name = name.replace("从集中交易迁移到三方存管", "迁移配合")
    name = name.replace("历史数据及文件从集中交易迁移到集中清算", "历史数据迁移")
    name = name.replace("历史文件从集中交易迁移到集中清算", "历史文件迁移")
    return name

def parse_owner(text):
    if not text or text.strip() in ("/", "--", "None", ""):
        return "/"
    return text.split('-')[0].strip()

def clean_date_str(date_str):
    if not date_str or date_str in ("--", "None", ""):
        return "--"
    match = RE_DATE.search(str(date_str))
    return match.group(0) if match else "--"

def determine_story_phase_level(status_name):
    """
    根据 Story 当前状态判定流程层级:
    Level 4: 全流程/验收/生产测试完成 -> 开发、SIT、UAT 均已完成!
    Level 3: 进入 UAT 阶段 -> 开发与 SIT 均已完成!
    Level 2: 进入 SIT 阶段 / 开发完成 -> 开发已完成!
    Level 1: 处于开发/分析阶段
    Level -1: 终止
    """
    if not status_name:
        return 1
    status = status_name.strip()
    if status == '终止':
        return -1
    if status in (
        '结束', '已结束', '完成', '已发布', '已上线', '业务验收/设计走查', 
        'SIT生产测试中', 'SIT生产测试待排期', '待SIT生产测试',
        'UAT生产自测中', 'UAT生产自测完成', 'UAT生产自测待排期', '待UAT生产自测',
        'UAT小远期自测完成', 'UAT验收完成', 
        'SIT大远期自测完成', 'SIT大远期测试完成', 'SIT测试完成'
    ):
        return 4
    if 'UAT' in status:
        return 3
    if 'SIT' in status or status == '开发完成':
        return 2
    return 1

def compute_phase_status_by_date(end_date_str):
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

def compute_phase_status(phase_name, end_date_str, phase_level):
    if phase_level == -1:
        return "🛑 已终止"
    if phase_level == 4:
        return "✅ 已完成"
    res = compute_phase_status_by_date(end_date_str)
    if phase_name == 'dev':
        return "✅ 已完成" if phase_level > 1 else ("⚠️ 未排期" if res == "--" else res)
    elif phase_name == 'sit':
        if phase_level > 2:
            return "✅ 已完成"
        elif phase_level == 2:
            return "⚠️ 未排期" if res == "--" else res
        else:
            return "--"
    elif phase_name == 'uat':
        if phase_level > 3:
            return "✅ 已完成"
        elif phase_level == 3:
            return "⚠️ 未排期" if res == "--" else res
        else:
            return "--"
    elif phase_name == 'delivery':
        return "⚠️ 未排期" if res == "--" else res
    return res

def is_risk_story(story):
    phases = [story["dev_status"], story["sit_status"], story["uat_status"], story["overall_status"]]
    for ps in phases:
        if "已逾期" in ps or "临近" in ps or "今天" in ps or "未排期" in ps:
            return True
    return False

def get_badge_class(status_str):
    if "已完成" in status_str:
        return "badge-done"
    elif "已终止" in status_str:
        return "badge-terminated"
    elif "已逾期" in status_str:
        return "badge-overdue"
    elif "临近" in status_str or "今天" in status_str or "未排期" in status_str:
        return "badge-warning"
    elif status_str == "正常":
        return "badge-normal"
    else:
        return "badge-muted"

def get_indexed_cache(script_dir):
    global _CACHE_DATA_SINGLETON, _CACHE_INDEX_BY_DEMAND
    if _CACHE_DATA_SINGLETON is not None:
        return _CACHE_DATA_SINGLETON, _CACHE_INDEX_BY_DEMAND

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
        _CACHE_DATA_SINGLETON = []
        _CACHE_INDEX_BY_DEMAND = defaultdict(list)
        return _CACHE_DATA_SINGLETON, _CACHE_INDEX_BY_DEMAND

    by_demand = defaultdict(list)
    for r in cache_data:
        d_id = r.get("demandId")
        if d_id:
            by_demand[d_id].append(r)

    _CACHE_DATA_SINGLETON = cache_data
    _CACHE_INDEX_BY_DEMAND = by_demand
    return _CACHE_DATA_SINGLETON, _CACHE_INDEX_BY_DEMAND

def load_demand_data_from_cache(demand_ids, script_dir):
    cache_data, by_demand = get_indexed_cache(script_dir)
    if not cache_data:
        return {}

    demands_dict = {}
    for d_id in demand_ids:
        rows = by_demand.get(d_id, [])
        if not rows:
            continue
        first_row = rows[0]
        title = first_row.get("demandTitle") or first_row.get("storyTitle") or ""
        subtitle = DEMAND_SUBTITLE_MAP.get(d_id, "")
        if not subtitle and title:
            subtitle = RE_SUBTITLE.sub('', title).strip()
            if len(subtitle) > 15:
                subtitle = subtitle[:15] + "..."

        stories = []
        for r in rows:
            s_id = r.get("storyCode") or r.get("storyNo") or ""
            raw_s_name = r.get("storyTitle") or ""
            s_name = clean_story_name(s_id, raw_s_name)
            system = r.get("storySystemName") or ""
            status = r.get("storyStatusName") or r.get("demandStatus") or ""
            
            phase_level = determine_story_phase_level(status)

            dev_owner = parse_owner(r.get("devManagePerson"))
            dev_end = clean_date_str(r.get("devAssessDateEnd"))
            dev_status = compute_phase_status('dev', dev_end, phase_level)

            sit_owner = parse_owner(r.get("sitTestManagePerson"))
            sit_end = clean_date_str(r.get("sitTestAssessDateEnd"))
            sit_status = compute_phase_status('sit', sit_end, phase_level)

            uat_owner = parse_owner(r.get("uatTestManagePerson"))
            uat_end = clean_date_str(r.get("uatTestAssessDateEnd"))
            uat_status = compute_phase_status('uat', uat_end, phase_level)

            delivery_date = clean_date_str(r.get("demandEsDuedate"))
            overall_status = compute_phase_status('delivery', delivery_date, phase_level)

            phase_statuses = [dev_status, sit_status, uat_status, overall_status]
            if "🚨 已逾期" in phase_statuses:
                overall_status = "🚨 已逾期"
            elif any("未排期" in ps for ps in phase_statuses) and overall_status != "🚨 已逾期":
                overall_status = "⚠️ 存在未排期"
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

def parse_result_file(file_path, demand_id):
    if not os.path.exists(file_path):
        return None
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    title_match = re.search(r"^\s*　　\*\*标题\*\*：(.*)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""
    
    subtitle = DEMAND_SUBTITLE_MAP.get(demand_id, "")
    if not subtitle and title:
        subtitle = RE_SUBTITLE.sub('', title).strip()
        if len(subtitle) > 15:
            subtitle = subtitle[:15] + "..."
            
    stories = []
    story_blocks = re.split(r"^\s*　　　　\*\*\d+\.\s*(S\d+)\*\*\s*—\s*(.*)$", content, flags=re.MULTILINE)
    
    if len(story_blocks) > 2:
        for idx in range(1, len(story_blocks), 3):
            story_id = story_blocks[idx].strip()
            raw_story_name = story_blocks[idx+1].strip()
            block_body = story_blocks[idx+2]
            
            status_match = re.search(r"状态：([^\s|]*)\s*\|", block_body)
            status = status_match.group(1).strip() if status_match else ""
            
            system_match = re.search(r"系统：([^\n|]*)", block_body)
            system = system_match.group(1).strip() if system_match else ""
            
            dev_match = re.search(r"开发负责人：([^\s|]*)", block_body)
            sit_match = re.search(r"SIT负责人：([^\s|]*)", block_body)
            uat_match = re.search(r"UAT负责人：([^\n|]*)", block_body)
            
            dev_owner = parse_owner(dev_match.group(1)) if dev_match else "/"
            sit_owner = parse_owner(sit_match.group(1)) if sit_match else "/"
            uat_owner = parse_owner(uat_match.group(1)) if uat_match else "/"
            
            deliv_match = re.search(r"计划交付：([^\s|]*)", block_body)
            delivery_date = clean_date_str(deliv_match.group(1).strip()) if deliv_match else "--"
            
            phase_level = determine_story_phase_level(status)

            dev_end = "--"
            dev_status = compute_phase_status('dev', dev_end, phase_level)
            sit_end = "--"
            sit_status = compute_phase_status('sit', sit_end, phase_level)
            uat_end = "--"
            uat_status = compute_phase_status('uat', uat_end, phase_level)
            overall_status = compute_phase_status('delivery', delivery_date, phase_level)

            story_name = clean_story_name(story_id, raw_story_name)
            
            stories.append({
                "id": story_id,
                "name": story_name,
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
            
    return {
        "demand_id": demand_id,
        "title": title,
        "subtitle": subtitle,
        "stories": stories
    }

async def run_single_query(req_id, script_dir):
    req_query_path = os.path.join(script_dir, "req_query.py")
    temp_output = os.path.join(script_dir, f"temp_{req_id}.md")
    print(f"[Orchestrator] 开始查询需求: {req_id}...")
    
    cmd = [sys.executable, req_query_path, req_id, "-o", temp_output]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    await process.communicate()
    
    if process.returncode == 0:
        print(f"[Orchestrator] 需求 {req_id} 查询成功。")
        return temp_output
    else:
        print(f"[Orchestrator] 需求 {req_id} 查询失败。")
        return None

def generate_html(data_list, output_path, project_name, only_risk=False):
    rows_html = []
    
    total_stories = 0
    rendered_demands_count = 0
    for idx, item in enumerate(data_list):
        demand_id = item["demand_id"]
        subtitle = item.get("subtitle", "")
        stories = item.get("stories", [])

        if only_risk:
            stories = [s for s in stories if is_risk_story(s)]
            if len(stories) == 0:
                continue

        story_count = len(stories)
        total_stories += story_count
        rendered_demands_count += 1
        row_style = ' style="border-top: 2px solid #cbd5e1;"' if rendered_demands_count > 1 else ''
        
        if story_count == 0:
            rows_html.append(f"""
      <tr{row_style}>
        <td class="req-col">
          <strong>{demand_id}</strong>
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
                
                status_style = ""
                if story["status"] in ("结束", "SIT大远期自测完成", "UAT验收完成"):
                    status_style = ' style="color: #166534; font-weight: 500;"'
                elif "SIT" in story["status"] or "开发" in story["status"] or "UAT" in story["status"]:
                    status_style = ' style="color: #b45309; font-weight: 500;"'

                if s_idx == 0:
                    rows_html.append(f"""
      <tr{row_style}>
        <td rowspan="{story_count}" class="req-col">
          <strong>{demand_id}</strong>
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
<title>{project_name} 进度跟踪表</title>
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
    <h2>📋 {project_name} 进度跟踪表</h2>
    <span class="sub-date">跟踪日期：{CURRENT_DATE_STR}（评估标准：结合阶段推进，仅评估活跃阶段与交付排期；包含未排期预警）</span>
  </div>

  <table>
    <thead>
      <tr class="group-header">
        <th colspan="5">📌 Story 基础与当前状态</th>
        <th colspan="3">💻 开发相关</th>
        <th colspan="3">🧪 SIT 测试</th>
        <th colspan="3">🔍 UAT 自测</th>
        <th colspan="2">🚀 交付验收与综合预警</th>
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
        <th>预计交付验收时间</th>
        <th>综合预警</th>
      </tr>
    </thead>
    <tbody>{"".join(rows_html)}
    </tbody>
  </table>

  <div class="legend-bar">
    <strong>图例说明：</strong>
    <span class="badge badge-overdue">🚨 已逾期</span>
    <span class="badge badge-warning">⚠️ 临近到期 (≤3天) / 未排期</span>
    <span class="badge badge-done">✅ 已完成</span>
    <span class="badge badge-normal">正常</span>
    <span class="badge badge-muted">-- 未排期</span>
  </div>
</div>

</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[Orchestrator] 已成功生成 HTML 表格: {output_path}")

def generate_markdown(data_list, output_path, project_name, only_risk=False):
    lines = []
    filter_desc = "全量 Story 跟踪" if not only_risk else "仅显示逾期/预警 Story"
    lines.append(f"# 📋 {project_name} 进度跟踪表 ({CURRENT_DATE_STR})")
    lines.append("")
    lines.append(f"> **跟踪规则**：`{filter_desc}` | 结合 Story 状态推进，已通过阶段自动标记 `✅ 已完成`；仅评估活跃阶段与交付排期，已过预计结束时间为 `🚨 已逾期`；距预计结束时间 ≤3 天或活跃阶段缺失时间为 `⚠️ 临近到期 / ⚠️ 未排期`。")
    lines.append("")
    lines.append("| 需求编号 | Story编号 | 任务名称 | 涉及系统 | 当前状态 | 开发负责人 | 开发预计结束 | 开发状态 | SIT负责人 | SIT预计结束 | SIT状态 | UAT负责人 | UAT预计结束 | UAT状态 | 预计交付验收时间 | 综合预警 |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    all_filtered_stories = []
    rendered_count = 0
    for item in data_list:
        demand_id = item["demand_id"]
        subtitle = item.get("subtitle", "")
        stories = item.get("stories", [])

        if only_risk:
            stories = [s for s in stories if is_risk_story(s)]
            if len(stories) == 0:
                continue

        demand_col = f"**{demand_id}**<br>({subtitle})" if subtitle else f"**{demand_id}**"
        
        if len(stories) == 0:
            lines.append(f"| {demand_col} | - | (无关联 Story) | - | - | - | - | - | - | - | - | - | - | - | - | - |")
        else:
            rendered_count += 1
            for s_idx, story in enumerate(stories):
                s_copy = story.copy()
                s_copy["demand_id"] = demand_id
                s_copy["demand_subtitle"] = subtitle
                all_filtered_stories.append(s_copy)

                d_col = demand_col if s_idx == 0 else ""
                lines.append(
                    f"| {d_col} | **{story['id']}** | {story['name']} | {story['system']} | {story['status']} | "
                    f"{story['dev_owner']} | {story['dev_end']} | {story['dev_status']} | "
                    f"{story['sit_owner']} | {story['sit_end']} | {story['sit_status']} | "
                    f"{story['uat_owner']} | {story['uat_end']} | {story['uat_status']} | "
                    f"**{story['delivery_date']}** | {story['overall_status']} |"
                )

    lines.append("")
    lines.append("## 🚨 重点逾期与预警汇总（按负责人提醒）")
    lines.append("")

    overdue_list = [s for s in all_filtered_stories if "已逾期" in s["overall_status"] or "已逾期" in s["dev_status"] or "已逾期" in s["sit_status"] or "已逾期" in s["uat_status"]]
    warning_list = [s for s in all_filtered_stories if "临近" in s["overall_status"] or "今天" in s["overall_status"] or "未排期" in s["overall_status"] or "未排期" in s["sit_status"] or "未排期" in s["dev_status"] or "未排期" in s["uat_status"] or "临近" in s["sit_status"] or "临近" in s["dev_status"] or "临近" in s["uat_status"]]

    if not overdue_list and not warning_list:
        lines.append("- **✅ 整体良好**：目前暂无已逾期、临近 3 天到期或未排期的 Story。")
    else:
        if overdue_list:
            lines.append(f"### 🚨 已逾期 Story 提醒 (共 {len(overdue_list)} 个)")
            for s in overdue_list:
                overdue_phases = []
                if "已逾期" in s["dev_status"]: overdue_phases.append(f"开发负责人 @{s['dev_owner']}(结束:{s['dev_end']})")
                if "已逾期" in s["sit_status"]: overdue_phases.append(f"SIT负责人 @{s['sit_owner']}(结束:{s['sit_end']})")
                if "已逾期" in s["uat_status"]: overdue_phases.append(f"UAT负责人 @{s['uat_owner']}(结束:{s['uat_end']})")
                if "已逾期" in s["overall_status"] and not overdue_phases: overdue_phases.append(f"预计交付验收时间(计划:{s['delivery_date']})")
                lines.append(f"- **{s['id']}** ({s['name']}) — 需求: `{s['demand_id']}` | 系统: `{s['system']}` | 需关注负责人: `{' / '.join(overdue_phases)}`")
            lines.append("")

        if warning_list:
            lines.append(f"### ⚠️ 临近到期与未排期预警提醒 (共 {len(warning_list)} 个)")
            for s in warning_list:
                warn_phases = []
                if "临近" in s["dev_status"] or "今天" in s["dev_status"] or "未排期" in s["dev_status"]: warn_phases.append(f"开发负责人 @{s['dev_owner']}({s['dev_status']})")
                if "临近" in s["sit_status"] or "今天" in s["sit_status"] or "未排期" in s["sit_status"]: warn_phases.append(f"SIT负责人 @{s['sit_owner']}({s['sit_status']})")
                if "临近" in s["uat_status"] or "今天" in s["uat_status"] or "未排期" in s["uat_status"]: warn_phases.append(f"UAT负责人 @{s['uat_owner']}({s['uat_status']})")
                lines.append(f"- **{s['id']}** ({s['name']}) — 需求: `{s['demand_id']}` | 系统: `{s['system']}` | 需提醒负责人: `{' / '.join(warn_phases)}`")
            lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")
    print(f"[Orchestrator] 已成功生成 Markdown 表格: {output_path}")

async def resolve_epic_id(epic_id, script_dir):
    req_query_path = os.path.join(script_dir, "req_query.py")
    print(f"[Orchestrator] 检测到史诗编号 {epic_id}，正在解析关联的需求编号列表...")
    
    cmd = [sys.executable, req_query_path, epic_id, "--epic"]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    resolved_demands = []
    if process.returncode == 0:
        out_str = stdout.decode('utf-8', errors='ignore')
        for line in out_str.splitlines():
            if line.startswith("EPIC_DEMANDS:"):
                demands_part = line[len("EPIC_DEMANDS:"):].strip()
                if demands_part:
                    resolved_demands = [d.strip().upper() for d in demands_part.split() if d.strip()]
                break
    else:
        err_msg = stderr.decode('utf-8', errors='ignore')
        print(f"[Orchestrator] 史诗编号 {epic_id} 解析失败: {err_msg}", file=sys.stderr)
        
    print(f"[Orchestrator] 史诗 {epic_id} 关联需求解析结果: {resolved_demands}")
    return resolved_demands

async def main_async():
    parser = argparse.ArgumentParser(description="批量生成项目进度跟踪表（HTML & Markdown）")
    parser.add_argument("demand_ids", nargs="+", help="需求编号或史诗编号列表（以空格分隔）")
    parser.add_argument("--output_html", default=None, help="生成的 HTML 表格路径")
    parser.add_argument("--output_md", default=None, help="生成的 Markdown 表格路径")
    parser.add_argument("--project", default="交易结算核心历史数据及接口迁移项目", help="项目名称")
    parser.add_argument("--only_risk", action="store_true", help="仅显示高风险或逾期 Story")
    args = parser.parse_args()

    project_name = args.project.strip()
    html_path = args.output_html if args.output_html else f"{CURRENT_DATE_FILE_STR}-进度-{project_name}.html"
    md_path = args.output_md if args.output_md else f"{CURRENT_DATE_FILE_STR}-进度-{project_name}.md"

    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 扫描输入参数，如果是史诗编号则解析它
    resolved_demand_ids = []
    for item in args.demand_ids:
        item_upper = item.strip().upper()
        if not item_upper:
            continue
        if item_upper.startswith("PG") or item_upper.startswith("E"):
            demands = await resolve_epic_id(item_upper, script_dir)
            resolved_demand_ids.extend(demands)
        else:
            resolved_demand_ids.append(item_upper)
            
    # 去重并保持顺序
    seen = set()
    demand_ids = []
    for d in resolved_demand_ids:
        if d not in seen:
            seen.add(d)
            demand_ids.append(d)
            
    if not demand_ids:
        print("[Orchestrator] 错误: 未获取到任何有效的需求编号。")
        sys.exit(1)

    # 优先从缓存获取需求与 Story 详情
    cached_demands = load_demand_data_from_cache(demand_ids, script_dir)
    missing_demands = [d for d in demand_ids if d not in cached_demands or len(cached_demands[d]["stories"]) == 0]
    
    live_parsed_dict = {}
    if missing_demands:
        print(f"[Orchestrator] 正在对 {len(missing_demands)} 个未缓存需求执行实时查询: {missing_demands}...")
        tasks = [run_single_query(req_id, script_dir) for req_id in missing_demands]
        temp_files = await asyncio.gather(*tasks)
        
        for req_id, temp_file in zip(missing_demands, temp_files):
            if temp_file and os.path.exists(temp_file):
                print(f"[Orchestrator] 解析中间结果: {temp_file}")
                data = parse_result_file(temp_file, req_id)
                if data:
                    live_parsed_dict[req_id] = data
                try:
                    os.remove(temp_file)
                except Exception as e:
                    print(f"[Orchestrator] 无法删除临时文件 {temp_file}: {e}")
            else:
                print(f"[Orchestrator] 警告: 未能获取需求 {req_id} 的数据，跳过该需求。")

    parsed_data = []
    for d_id in demand_ids:
        if d_id in cached_demands and len(cached_demands[d_id]["stories"]) > 0:
            parsed_data.append(cached_demands[d_id])
        elif d_id in live_parsed_dict:
            parsed_data.append(live_parsed_dict[d_id])
        else:
            parsed_data.append({
                "demand_id": d_id,
                "title": "",
                "subtitle": DEMAND_SUBTITLE_MAP.get(d_id, ""),
                "stories": []
            })

    if not parsed_data:
        print("[Orchestrator] 错误: 没有成功获取到任何需求数据。")
        sys.exit(1)

    # 生成文件
    generate_html(parsed_data, html_path, project_name, only_risk=args.only_risk)
    generate_markdown(parsed_data, md_path, project_name, only_risk=args.only_risk)

    # 自动同步到 Obsidian 目录
    obsidian_dir = "/Volumes/Macintosh HD_Data/obsidian/100_Projects/进度跟踪"
    try:
        os.makedirs(obsidian_dir, exist_ok=True)
        obsidian_md_path = os.path.join(obsidian_dir, f"{CURRENT_DATE_FILE_STR}-进度-{project_name}.md")
        generate_markdown(parsed_data, obsidian_md_path, project_name, only_risk=args.only_risk)
        print(f"[Orchestrator] 已成功同步写入 Obsidian 目录: {obsidian_md_path}")
    except Exception as e:
        print(f"[Orchestrator] 警告: 无法同步到 Obsidian 目录: {e}")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
