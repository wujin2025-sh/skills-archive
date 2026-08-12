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
import subprocess
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
}

# 明确从 Story 节点/平台抓取的各阶段【经办人】覆盖
LIVE_NODE_MAP = {
    "S2606030085": {"dev": ["邢航源"]},
}

# 明确从 Story 一生 / 平台节点确认的实际完成日期
STORY_ACTUAL_END_MAP = {
    "S2604070091": {"dev": "2026-05-15", "sit": "2026-08-07"},
    "S2604070092": {"dev": "2026-06-15", "sit": "2026-08-10"},
    "S2604130029": {"dev": "2026-04-20", "sit": "2026-08-07"},
    "S2604130030": {"dev": "2026-06-15", "sit": "2026-08-10"},
    "S2606030083": {"dev": "2026-07-14"},
    "S2605070090": {"dev": "2026-06-15", "sit": "2026-07-24"},
    "S2605070105": {"dev": "2026-06-15", "sit": "2026-07-24"},
    "S2605070103": {"dev": "2026-05-27", "sit": "2026-08-10"},
    "S2605070104": {"dev": "2026-06-15"},
    "S2606030085": {"dev": "2026-07-14"},
}

# 明确从 Story 详情 -> 基本信息 确认的【原始需求提出人】映射
STORY_ORIGINAL_REQUESTER_MAP = {
    "S2604070091": "匡正祥",
    "S2604070092": "匡正祥",
    "S2604130029": "匡正祥",
    "S2604130030": "匡正祥",
    "S2606030083": "匡正祥",
    "S2605070090": "刘志林",
    "S2605070105": "刘志林",
    "S2605070104": "刘志林",
    "S2605070103": "刘志林",
    "S2606030085": "刘志林",
    "R2603250074": "匡正祥",
    "R2603250136": "匡正祥",
    "R2604220006": "刘志林",
    "R2604220009": "刘志林",
    "R2604220010": "刘志林",
}

# 明确从 Story 详情 -> 业务与设计 确认的【业务验收人】映射（严格独立 Story 级别）
STORY_BUSINESS_ACCEPTOR_MAP = {
    "S2604070091": "金渤文",
    "S2604070092": "金渤文",
    "S2604130029": "金渤文",
    "S2604130030": "金渤文",
    "S2606030083": "匡正祥",
    "S2605070090": "金渤文",
    "S2605070105": "金渤文",
    "S2605070104": "金渤文",
    "S2605070103": "金渤文",
    "S2606030085": "刘志林",
}

# 明确从 Story 评估卡片解析确认的各自阶段【预计结束时间】
STORY_PLAN_END_MAP = {
    "S2604070091": {"dev": "2026-05-22", "sit": "2026-08-07"},
    "S2604070092": {"dev": "2026-06-05", "sit": "2026-08-14", "uat": "2026-08-21"},
    "S2604130029": {"dev": "2026-05-16", "sit": "2026-08-07"},
    "S2604130030": {"dev": "2026-06-05", "sit": "2026-08-14", "uat": "2026-08-21"},
    "S2606030083": {"dev": "2026-07-24"},
    "S2605070090": {"dev": "2026-07-06", "sit": "2026-05-20"},
    "S2605070105": {"dev": "2026-07-21", "sit": "2026-05-20"},
    "S2605070103": {"dev": "2026-05-30", "sit": "2026-06-26"},
    "S2605070104": {"dev": "2026-06-05", "sit": "2026-08-14"},
    "S2606030085": {"dev": "2026-07-24"},
}

# 明确针对 Epic 同批上线的【计划生产排期】Override（史诗全体统一上线批次）
STORY_DELIVERY_DATE_MAP = {
    "PG202204-0263": "2026-09-04",
    "R2603250074": "2026-09-04",
    "R2603250136": "2026-09-04",
    "R2604220006": "2026-09-04",
    "R2604220009": "2026-09-04",
    "R2604220010": "2026-09-04",
    "S2604070091": "2026-09-04",
    "S2604070092": "2026-09-04",
    "S2604130029": "2026-09-04",
    "S2604130030": "2026-09-04",
    "S2606030083": "2026-09-04",
    "S2605070090": "2026-09-04",
    "S2605070105": "2026-09-04",
    "S2605070104": "2026-09-04",
    "S2605070103": "2026-09-04",
    "S2606030085": "2026-09-04",
}

# 动态流程节点解析映射（优先自动从 Live Scraper / Cache 载入，绝无硬编码列举）
LIVE_NODE_MAP = {}
LIVE_CACHE_PATH = "/Users/wujin/.gemini/antigravity/brain/219cca84-5e4b-4f93-ad72-4827f20dba66/scratch/live_dynamic_node_results.json"
if os.path.exists(LIVE_CACHE_PATH):
    try:
        with open(LIVE_CACHE_PATH, "r", encoding="utf-8") as f:
            LIVE_NODE_MAP = json.load(f)
    except Exception:
        LIVE_NODE_MAP = {}

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
    if not text or str(text).strip() in ("/", "--", "None", "", "null"):
        return "/"
    s_text = str(text).strip()
    match = re.search(r'^([\u4e00-\u9fa5]+)', s_text)
    if match:
        cn = match.group(1)
        if len(cn) > 4 and len(cn) <= 8:
            if len(cn) == 6:
                return f"{cn[:3]}, {cn[3:]}"
            elif len(cn) == 4:
                return f"{cn[:2]}, {cn[2:]}"
            elif len(cn) == 5:
                return f"{cn[:3]}, {cn[3:]}"
        return cn
    parts = s_text.split('-')
    name = parts[0].strip()
    return name if name else "/"

def parse_owner_list(input_val):
    """
    通用解析函数：将任何经办人输入（字符串、逗号/斜杠/换行分隔、多节点拼接、列表）
    通用处理为干净名字列表，保持出现顺序并去重。自动切分无分隔符连体中文姓名（如 刘志林金渤文 -> 刘志林, 金渤文）。
    """
    if not input_val:
        return []
    
    if isinstance(input_val, list):
        raw_items = input_val
    else:
        raw_items = re.split(r'[,，/\\;\n\t、\s]+', str(input_val))
        
    items = []
    for item in raw_items:
        s_item = str(item).strip()
        if not s_item: continue
        match = re.search(r'^([\u4e00-\u9fa5]+)', s_item)
        if match:
            cn = match.group(1)
            if len(cn) > 4 and len(cn) <= 8:
                if len(cn) == 6:
                    items.extend([cn[:3], cn[3:]])
                elif len(cn) == 4:
                    items.extend([cn[:2], cn[2:]])
                elif len(cn) == 5:
                    items.extend([cn[:3], cn[3:]])
                else:
                    items.append(cn)
            else:
                items.append(cn)
        else:
            items.append(s_item)

    names = []
    for item in items:
        cleaned = parse_owner(item)
        if cleaned != "/" and cleaned not in names:
            names.append(cleaned)
    return names

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

def compute_overdue_days(planned_end, actual_end=None):
    """
    根据用户规则 2：各自阶段，当 实际结束日期 > 预计结束日期，计算并填写逾期天数 (实际结束 - 预计结束)；
    若未填写实际结束日期 (未完成) 或 实际结束日期 <= 预计结束日期 (按期完成)，则不填写逾期天数 (返回 0)。
    """
    clean_plan = clean_date_str(planned_end)
    clean_act = clean_date_str(actual_end) if actual_end else "--"
    
    if clean_plan == "--" or clean_act == "--":
        return 0
    try:
        dt_plan = datetime.strptime(clean_plan, "%Y-%m-%d").date()
        dt_act = datetime.strptime(clean_act, "%Y-%m-%d").date()
        delta = (dt_act - dt_plan).days
        return delta if delta > 0 else 0
    except Exception:
        return 0

BADGE_INLINE_STYLES = {
    "badge-done": "display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; white-space: nowrap; background-color: #dcfce7; color: #15803d;",
    "badge-terminated": "display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; white-space: nowrap; background-color: #f1f5f9; color: #64748b;",
    "badge-overdue": "display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; white-space: nowrap; background-color: #fee2e2; color: #b91c1c;",
    "badge-warning": "display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; white-space: nowrap; background-color: #fef3c7; color: #b45309; border: 1px solid #fcd34d;",
    "badge-normal": "display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; white-space: nowrap; background-color: #e0f2fe; color: #0369a1;",
    "badge-muted": "display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; white-space: nowrap; color: #94a3b8;"
}

def format_phase_status_html(status_str, planned_end, actual_end=None):
    b_cls = get_badge_class(status_str)
    b_style = BADGE_INLINE_STYLES.get(b_cls, BADGE_INLINE_STYLES["badge-muted"])
    badge = f'<span class="badge {b_cls}" style="{b_style}">{status_str}</span>'
    days = compute_overdue_days(planned_end, actual_end)
    if days > 0:
        badge += f'<br><span style="font-size: 11px; color: #b91c1c; font-weight: 500; display: block; margin-top: 2px;">逾期{days}天</span>'
    return badge

def format_phase_status_md(status_str, planned_end, actual_end=None):
    days = compute_overdue_days(planned_end, actual_end)
    if days > 0:
        return f"{status_str}<br><span style='color:#b91c1c;'>逾期{days}天</span>"
    return status_str

def compute_phase_status(phase_name, planned_end_str, actual_end_str, phase_level, story_status=""):
    """
    根据用户规则 1：各阶段的标准状态为：待排期、待开发、已完成、自测待排期、待自测、自测中。
    """
    clean_plan = clean_date_str(planned_end_str)
    clean_act = clean_date_str(actual_end_str) if actual_end_str else "--"
    
    if phase_level == -1 or "终止" in story_status:
        return "🛑 已终止"
        
    if phase_name == 'dev':
        if clean_act != "--" or phase_level > 1 or "开发完成" in story_status or story_status in ("结束", "SIT大远期自测完成", "UAT验收完成"):
            return "✅ 已完成"
        if clean_plan == "--":
            return "待排期"
        if "开发中" in story_status:
            return "开发中"
        return "待开发"
        
    elif phase_name == 'sit':
        if clean_act != "--" or phase_level > 2 or "SIT测试完成" in story_status or story_status in ("结束", "UAT验收完成"):
            return "✅ 已完成"
        if phase_level < 1 and clean_plan == "--":
            return "--"
        if clean_plan == "--":
            return "自测待排期"
        if "自测中" in story_status or "SIT测试中" in story_status or "SIT大远期自测中" in story_status:
            return "自测中"
        return "待自测"
        
    elif phase_name == 'uat':
        if clean_act != "--" or phase_level > 3 or "UAT验收完成" in story_status or story_status in ("结束",):
            return "✅ 已完成"
        if phase_level < 2 and clean_plan == "--":
            return "--"
        if clean_plan == "--":
            return "自测待排期"
        if "自测中" in story_status or "UAT测试中" in story_status or "UAT小远期自测中" in story_status:
            return "自测中"
        return "待自测"
        
    elif phase_name == 'delivery':
        if phase_level >= 4 or story_status == "结束":
            return "✅ 已完成"
        if clean_plan == "--":
            return "⚠️ 未排期"
        return "待交付"
        
    return "待排期"

def is_risk_story(story):
    for p_end, p_act in [
        (story["dev_end"], story.get("dev_act")),
        (story["sit_end"], story.get("sit_act")),
        (story["uat_end"], story.get("uat_act"))
    ]:
        if compute_overdue_days(p_end, p_act) > 0:
            return True
    for ps in [story["dev_status"], story["sit_status"], story["uat_status"]]:
        if "待排期" in ps or "未排期" in ps or "自测待排期" in ps:
            return True
    return False

def get_badge_class(status_str):
    if "已完成" in status_str:
        return "badge-done"
    elif "终止" in status_str:
        return "badge-terminated"
    elif "开发中" in status_str or "自测中" in status_str or "待交付" in status_str:
        return "badge-normal"
    elif "待" in status_str or "未排期" in status_str:
        return "badge-warning"
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

def get_valid_date(r, *keys):
    for k in keys:
        val = r.get(k)
        cleaned = clean_date_str(val)
        if cleaned != "--":
            return cleaned
    return "--"

def get_valid_owner(r, *keys):
    for k in keys:
        val = r.get(k)
        if val and str(val).strip() not in ("/", "--", "None", "", "null"):
            owners = parse_owner_list(val)
            if owners and owners != ["/"]:
                return owners
    return []

def load_demand_data_from_cache(demand_ids, script_dir, demand_to_epic=None):
    cache_data, by_demand = get_indexed_cache(script_dir)
    if not cache_data:
        return {}

    demands_dict = {}
    for d_id in demand_ids:
        rows = by_demand.get(d_id, [])
        if not rows:
            continue
        
        # 若需求下存在真实的 Story 记录，自动过滤掉由无关联 Story 生成的空白占位行
        real_story_rows = [r for r in rows if r.get("storyCode") or (r.get("storyTitle") and r.get("storyTitle") != "(无关联 Story)")]
        target_rows = real_story_rows if real_story_rows else rows
        
        first_row = target_rows[0]
        title = first_row.get("demandTitle") or first_row.get("storyTitle") or ""
        subtitle = DEMAND_SUBTITLE_MAP.get(d_id, "")
        if not subtitle and title:
            subtitle = RE_SUBTITLE.sub('', title).strip()
            if len(subtitle) > 15:
                subtitle = subtitle[:15] + "..."

        requester = parse_owner(first_row.get("originalRequester") or first_row.get("demandCreatePerson"))
        if not requester:
            requester = "/"

        stories = []
        for r in target_rows:
            s_id = r.get("storyCode") or r.get("storyNo") or ""
            raw_s_name = r.get("storyTitle") or ""
            s_name = clean_story_name(s_id, raw_s_name)
            system = r.get("storySystemName") or ""
            status = r.get("storyStatusName") or r.get("demandStatus") or ""
            
            phase_level = determine_story_phase_level(status)

            # Extract Epic ID from the row
            epic_id = r.get("epicCode") or r.get("epicNo") or ""
            if not epic_id and r.get("epicConcat"):
                match = re.search(r'(PG\d+-\d+|E\d+-\d+)', str(r.get("epicConcat")), re.IGNORECASE)
                if match:
                    epic_id = match.group(1).upper()
            if (not epic_id or epic_id == "--") and demand_to_epic and d_id in demand_to_epic:
                e_info = demand_to_epic[d_id]
                epic_id = e_info.get("epic_code", "") if isinstance(e_info, dict) else str(e_info)
            if not epic_id:
                epic_id = "--"

            if s_id in LIVE_NODE_MAP and LIVE_NODE_MAP[s_id].get("dev"):
                dev_owners = LIVE_NODE_MAP[s_id]["dev"]
            else:
                dev_owners = get_valid_owner(r, "devManagePerson", "dev_owner")

            dev_owner = ", ".join(dev_owners) if dev_owners else "/"
            dev_owner_html = "<br>".join(dev_owners) if dev_owners else "/"

            dev_end = clean_date_str(r.get("devAssessDateEnd"))
            if dev_end == "--" and s_id in STORY_PLAN_END_MAP and "dev" in STORY_PLAN_END_MAP[s_id]:
                dev_end = STORY_PLAN_END_MAP[s_id]["dev"]

            dev_fact = get_valid_date(r, "devFactEndDate", "devActualDate", "devFinishTime")
            if s_id in STORY_ACTUAL_END_MAP and "dev" in STORY_ACTUAL_END_MAP[s_id]:
                dev_act = STORY_ACTUAL_END_MAP[s_id]["dev"]
            elif dev_fact != "--":
                dev_act = dev_fact
            else:
                dev_act = "--"
            dev_status = compute_phase_status('dev', dev_end, dev_act, phase_level, status)

            if s_id in LIVE_NODE_MAP and LIVE_NODE_MAP[s_id].get("sit"):
                sit_owners = LIVE_NODE_MAP[s_id]["sit"]
            else:
                sit_owners = get_valid_owner(r, "sitTestManagePerson", "sit_owner")

            if s_id in LIVE_NODE_MAP and LIVE_NODE_MAP[s_id].get("uat"):
                uat_owners = LIVE_NODE_MAP[s_id]["uat"]
            else:
                uat_owners = get_valid_owner(r, "uatTestManagePerson", "uat_owner")

            sit_owner = ", ".join(sit_owners) if sit_owners else "/"
            sit_owner_html = "<br>".join(sit_owners) if sit_owners else "/"

            uat_owner = ", ".join(uat_owners) if uat_owners else "/"
            uat_owner_html = "<br>".join(uat_owners) if uat_owners else "/"

            sit_end = clean_date_str(r.get("sitTestAssessDateEnd"))
            if sit_end == "--" and s_id in STORY_PLAN_END_MAP and "sit" in STORY_PLAN_END_MAP[s_id]:
                sit_end = STORY_PLAN_END_MAP[s_id]["sit"]

            sit_fact = get_valid_date(r, "sitFactEndDate", "sitActualDate", "sitFinishTime", "sitTestFinishTime")
            if s_id in STORY_ACTUAL_END_MAP and "sit" in STORY_ACTUAL_END_MAP[s_id]:
                sit_act = STORY_ACTUAL_END_MAP[s_id]["sit"]
            elif sit_fact != "--":
                sit_act = sit_fact
            else:
                sit_act = "--"
            sit_status = compute_phase_status('sit', sit_end, sit_act, phase_level, status)

            uat_end = clean_date_str(r.get("uatTestAssessDateEnd"))
            if uat_end == "--" and s_id in STORY_PLAN_END_MAP and "uat" in STORY_PLAN_END_MAP[s_id]:
                uat_end = STORY_PLAN_END_MAP[s_id]["uat"]
            uat_fact = get_valid_date(r, "uatFactEndDate", "uatActualDate", "uatFinishTime")
            if s_id in STORY_ACTUAL_END_MAP and "uat" in STORY_ACTUAL_END_MAP[s_id]:
                uat_act = STORY_ACTUAL_END_MAP[s_id]["uat"]
            elif uat_fact != "--":
                uat_act = uat_fact
            else:
                uat_act = "--"
            uat_status = compute_phase_status('uat', uat_end, uat_act, phase_level, status)

            delivery_date = STORY_DELIVERY_DATE_MAP.get(s_id) or STORY_DELIVERY_DATE_MAP.get(d_id) or get_valid_date(r, "planProdLineDate", "demandEsDuedate", "demandWishDate")
            overall_status = compute_phase_status('delivery', delivery_date, None, phase_level, status)

            overdue_days_list = [
                compute_overdue_days(dev_end, dev_act),
                compute_overdue_days(sit_end, sit_act),
                compute_overdue_days(uat_end, uat_act)
            ]
            max_overdue = max([d for d in overdue_days_list if d > 0] + [0])
            if max_overdue > 0:
                overall_status = f"🚨 存在逾期 ({max_overdue}天)"
            elif any("待排期" in ps or "未排期" in ps for ps in [dev_status, sit_status, uat_status]):
                overall_status = "⚠️ 存在未排期"
            elif all(ps in ("✅ 已完成", "--") for ps in [dev_status, sit_status, uat_status]):
                overall_status = "✅ 已完成"
            else:
                overall_status = "按计划推进"

            # 1. 原始需求提出人：取 Story 详情 - 基本信息 : 原始需求提出人
            requester = STORY_ORIGINAL_REQUESTER_MAP.get(s_id) or STORY_ORIGINAL_REQUESTER_MAP.get(d_id) or parse_owner(r.get("originalRequester") or r.get("demandCreatePerson") or r.get("cUserName") or r.get("userName") or first_row.get("originalRequester"))
            if not requester:
                requester = "/"

            # 2. 业务验收人：取 Story 详情 - 业务与设计 : 业务验收人 (Story 独立级优先)
            raw_acceptor = r.get("businessAcceptorName") or r.get("storyBusAcceptor") or r.get("busAcceptor") or r.get("businessAcceptor")
            business_acceptor = STORY_BUSINESS_ACCEPTOR_MAP.get(s_id) or parse_owner(raw_acceptor)
            if not business_acceptor:
                business_acceptor = "/"

            # 3. 验收状态：取 Story 详情 - 业务与设计 : 业务验收结果
            business_result = r.get("storyBusName") or r.get("storyResult") or r.get("storyBusResult")
            if not business_result or str(business_result).strip() in ("/", "--", "None", ""):
                if str(r.get("isHaveBus")) == "0":
                    business_result = "无需业务验收"
                else:
                    business_result = "待业务验收"

            stories.append({
                "id": s_id,
                "name": s_name,
                "system": system,
                "status": status,
                "dev_owner": dev_owner,
                "dev_owner_html": dev_owner_html,
                "dev_end": dev_end,
                "dev_act": dev_act,
                "dev_status": dev_status,
                "sit_owner": sit_owner,
                "sit_owner_html": sit_owner_html,
                "sit_end": sit_end,
                "sit_act": sit_act,
                "sit_status": sit_status,
                "uat_owner": uat_owner,
                "uat_owner_html": uat_owner_html,
                "uat_end": uat_end,
                "uat_act": uat_act,
                "uat_status": uat_status,
                "delivery_date": delivery_date,
                "overall_status": overall_status,
                "epic_id": epic_id,
                "business_acceptor": business_acceptor,
                "business_result": business_result,
                "requester": requester,
                "raw_dev_owner": r.get("devManagePerson"),
                "raw_sit_owner": r.get("sitTestManagePerson"),
                "raw_uat_owner": r.get("uatTestManagePerson"),
            })

        demands_dict[d_id] = {
            "demand_id": d_id,
            "title": title,
            "subtitle": subtitle,
            "stories": stories
        }

    return demands_dict

def parse_result_file(file_path, demand_id, demand_to_epic=None):
    if not os.path.exists(file_path):
        return None
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    title_match = re.search(r"^\s*　　\*\*标题\*\*：(.*)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""
    
    requester_match = re.search(r"^\s*　　\*\*提出人\*\*：(.*)$", content, re.MULTILINE)
    requester = parse_owner(requester_match.group(1).strip()) if requester_match else "/"
    if not requester:
        requester = "/"

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
            sit_match = re.search(r"(?:SIT负责人|SIT经办人)：([^\s|]*)", block_body)
            uat_match = re.search(r"(?:UAT负责人|UAT经办人)：([^\n|]*)", block_body)
            
            if story_id in LIVE_NODE_MAP and LIVE_NODE_MAP[story_id].get("dev"):
                dev_owners = LIVE_NODE_MAP[story_id]["dev"]
            else:
                d_o = parse_owner(dev_match.group(1)) if dev_match else "/"
                dev_owners = [d_o] if d_o != "/" else []

            if story_id in LIVE_NODE_MAP and LIVE_NODE_MAP[story_id].get("sit"):
                sit_owners = LIVE_NODE_MAP[story_id]["sit"]
            else:
                s_o = parse_owner(sit_match.group(1)) if sit_match else "/"
                sit_owners = [s_o] if s_o != "/" else []

            if story_id in LIVE_NODE_MAP and LIVE_NODE_MAP[story_id].get("uat"):
                uat_owners = LIVE_NODE_MAP[story_id]["uat"]
            else:
                u_o = parse_owner(uat_match.group(1)) if uat_match else "/"
                uat_owners = [u_o] if u_o != "/" else []

            dev_owner = ", ".join(dev_owners) if dev_owners else "/"
            dev_owner_html = "<br>".join(dev_owners) if dev_owners else "/"
            sit_owner = ", ".join(sit_owners) if sit_owners else "/"
            sit_owner_html = "<br>".join(sit_owners) if sit_owners else "/"
            uat_owner = ", ".join(uat_owners) if uat_owners else "/"
            uat_owner_html = "<br>".join(uat_owners) if uat_owners else "/"
            
            prod_match = re.search(r"计划生产排期：([^\s||\n]*)", block_body)
            if not prod_match:
                prod_match = re.search(r"计划生产排期：([^\s||\n]*)", content)
            p_val = prod_match.group(1).strip() if prod_match else ""
            if p_val and p_val != "--":
                delivery_date = clean_date_str(p_val)
            else:
                deliv_match = re.search(r"计划交付：([^\s|]*)", block_body)
                delivery_date = clean_date_str(deliv_match.group(1).strip()) if deliv_match else "--"
            
            epic_match = re.search(r"史诗编号：([^\s|]*)", block_body)
            epic_id = epic_match.group(1).strip() if epic_match else (demand_to_epic.get(demand_id, "--") if demand_to_epic else "--")
            if not epic_id:
                epic_id = "--"
            
            phase_level = determine_story_phase_level(status)

            dev_end_match = re.search(r"开发预计结束：([^\s|]*)", block_body)
            dev_end = clean_date_str(dev_end_match.group(1).strip()) if dev_end_match else "--"

            sit_end_match = re.search(r"SIT预计结束：([^\s|]*)", block_body)
            sit_end = clean_date_str(sit_end_match.group(1).strip()) if sit_end_match else "--"

            uat_end_match = re.search(r"UAT预计结束：([^\s|]*)", block_body)
            uat_end = clean_date_str(uat_end_match.group(1).strip()) if uat_end_match else "--"

            dev_fact = clean_date_str(re.search(r"开发实际结束：([^\s|]*)", block_body).group(1)) if re.search(r"开发实际结束：([^\s|]*)", block_body) else "--"
            sit_fact = clean_date_str(re.search(r"SIT实际结束：([^\s|]*)", block_body).group(1)) if re.search(r"SIT实际结束：([^\s|]*)", block_body) else "--"
            uat_fact = clean_date_str(re.search(r"UAT实际结束：([^\s|]*)", block_body).group(1)) if re.search(r"UAT实际结束：([^\s|]*)", block_body) else "--"

            dev_act = STORY_ACTUAL_END_MAP.get(story_id, {}).get("dev", dev_fact)
            sit_act = STORY_ACTUAL_END_MAP.get(story_id, {}).get("sit", sit_fact)
            uat_act = STORY_ACTUAL_END_MAP.get(story_id, {}).get("uat", uat_fact)

            dev_status = compute_phase_status('dev', dev_end, dev_act, phase_level, status)
            sit_status = compute_phase_status('sit', sit_end, sit_act, phase_level, status)
            uat_status = compute_phase_status('uat', uat_end, uat_act, phase_level, status)
            overall_status = compute_phase_status('delivery', delivery_date, None, phase_level, status)

            story_name = clean_story_name(story_id, raw_story_name)
            
            acceptor_match = re.search(r"业务验收人：([^\s|]*)", block_body)
            bus_result_match = re.search(r"业务验收结果：([^\s|]*)", block_body)
            
            business_acceptor = parse_owner(acceptor_match.group(1).strip()) if acceptor_match else "/"
            business_result = bus_result_match.group(1).strip() if bus_result_match else "--"
            if not business_acceptor:
                business_acceptor = "/"
            if not business_result:
                business_result = "--"

            requester_match = re.search(r"(?:原始需求提出人|需求提出人)：([^\s|]*)", block_body)
            requester = parse_owner(requester_match.group(1).strip()) if requester_match else "/"

            stories.append({
                "id": story_id,
                "name": story_name,
                "system": system,
                "status": status,
                "dev_owner": dev_owner,
                "dev_owner_html": dev_owner_html,
                "dev_end": dev_end,
                "dev_act": dev_act,
                "dev_status": dev_status,
                "sit_owner": sit_owner,
                "sit_owner_html": sit_owner_html,
                "sit_end": sit_end,
                "sit_act": sit_act,
                "sit_status": sit_status,
                "uat_owner": uat_owner,
                "uat_owner_html": uat_owner_html,
                "uat_end": uat_end,
                "uat_act": uat_act,
                "uat_status": uat_status,
                "delivery_date": delivery_date,
                "overall_status": overall_status,
                "epic_id": epic_id,
                "business_acceptor": business_acceptor,
                "business_result": business_result,
                "requester": requester
            })
            
    epic_info = (demand_to_epic or {}).get(demand_id, "")
    if isinstance(epic_info, dict):
        epic_code = epic_info.get("epic_code", "")
        epic_name = epic_info.get("epic_name", "")
    else:
        epic_code = str(epic_info) if epic_info else ""
        epic_name = ""

    return {
        "demand_id": demand_id,
        "title": title,
        "subtitle": subtitle,
        "epic_code": epic_code,
        "epic_name": epic_name,
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
    
    # 1. 过滤数据，得到计算 rowspan 的真实列表
    filtered_data = []
    for item in data_list:
        stories = item.get("stories", [])
        if only_risk:
            stories = [s for s in stories if is_risk_story(s)]
            if len(stories) == 0:
                continue
        item_copy = item.copy()
        item_copy["stories"] = stories
        filtered_data.append(item_copy)

    # 2. 计算每个史诗块的 rowspan
    demand_rows = []
    for item in filtered_data:
        stories = item.get("stories", [])
        epic_id = (stories[0].get("epic_id") if stories else None) or item.get("epic_id") or item.get("epic_code") or "--"
        story_count = len(stories)
        rows_occupied = story_count if story_count > 0 else 1
        demand_rows.append({
            "epic_id": epic_id,
            "rows_occupied": rows_occupied
        })

    epic_rowspans = {}
    i = 0
    while i < len(demand_rows):
        current_epic = demand_rows[i]["epic_id"]
        total_rows = 0
        j = i
        while j < len(demand_rows) and demand_rows[j]["epic_id"] == current_epic:
            total_rows += demand_rows[j]["rows_occupied"]
            j += 1
        epic_rowspans[i] = total_rows
        for k in range(i + 1, j):
            epic_rowspans[k] = 0
        i = j

    # 3. 渲染每一行
    total_stories = 0
    rendered_demands_count = 0
    for idx, item in enumerate(filtered_data):
        demand_id = item["demand_id"]
        subtitle = item.get("subtitle", "")
        stories = item.get("stories", [])

        story_count = len(stories)
        total_stories += story_count
        rendered_demands_count += 1
        row_style = ' style="border-top: 2px solid #cbd5e1;"' if rendered_demands_count > 1 else ''
        
        epic_id = (stories[0].get("epic_id") if stories else None) or item.get("epic_id") or item.get("epic_code") or "--"
        epic_show = f'<code style="background-color: #f1f5f9; padding: 2px 6px; border-radius: 4px; color: #475569; font-size: 11px;">{epic_id}</code>' if epic_id and epic_id != "--" else "--"
        
        epic_rowspan = epic_rowspans.get(idx, 0)
        epic_td = ""
        if epic_rowspan > 0:
            epic_td = f"""
        <td rowspan="{epic_rowspan}" class="req-col" style="font-weight: bold; background-color: #f8fafc; color: #1e40af; vertical-align: middle; text-align: center; border: 1px solid #cbd5e1; font-family: ui-monospace, monospace; padding: 10px 8px;">
          {epic_show}
        </td>"""
        
        td_style = 'style="padding: 10px 8px; border: 1px solid #cbd5e1; color: #334155; vertical-align: middle;"'
        
        if story_count == 0:
            rows_html.append(f"""
      <tr{row_style}>
        {epic_td}
        <td class="req-col" style="font-weight: bold; background-color: #f8fafc; color: #1d4ed8; vertical-align: middle; text-align: center; min-width: 110px; border: 1px solid #cbd5e1; padding: 10px 8px;">
          <strong style="color: #1d4ed8;">{demand_id}</strong>
          <span class="req-sub" style="font-size: 11px; color: #64748b; font-weight: normal; display: block; margin-top: 4px;">{subtitle}</span>
        </td>
        <td colspan="18" style="text-align: center; color: #64748b; padding: 10px 8px; border: 1px solid #cbd5e1; vertical-align: middle;">（无关联 Story）</td>
      </tr>""")
        else:
            for s_idx, story in enumerate(stories):
                dev_badge = format_phase_status_html(story["dev_status"], story["dev_end"], story.get("dev_act"))
                sit_badge = format_phase_status_html(story["sit_status"], story["sit_end"], story.get("sit_act"))
                uat_badge = format_phase_status_html(story["uat_status"], story["uat_end"], story.get("uat_act"))
                overall_badge = format_phase_status_html(story["overall_status"], story["delivery_date"])

                system_td = f'<td class="system-highlight" style="font-weight: 600; color: #1d4ed8; padding: 10px 8px; border: 1px solid #cbd5e1; vertical-align: middle;">{story["system"]}</td>' if "清算" in story["system"] else f'<td style="padding: 10px 8px; border: 1px solid #cbd5e1; color: #334155; vertical-align: middle;">{story["system"]}</td>'
                
                status_style = f' style="padding: 10px 8px; border: 1px solid #cbd5e1; color: #334155; vertical-align: middle;"'
                if story["status"] in ("结束", "SIT大远期自测完成", "UAT验收完成"):
                    status_style = ' style="color: #166534; font-weight: 500; padding: 10px 8px; border: 1px solid #cbd5e1; vertical-align: middle;"'
                elif "SIT" in story["status"] or "开发" in story["status"] or "UAT" in story["status"]:
                    status_style = ' style="color: #b45309; font-weight: 500; padding: 10px 8px; border: 1px solid #cbd5e1; vertical-align: middle;"'

                bus_result_style = f' style="padding: 10px 8px; border: 1px solid #cbd5e1; color: #334155; vertical-align: middle;"'
                if "通过" in story["business_result"]:
                    bus_result_style = ' style="color: #166534; font-weight: 500; padding: 10px 8px; border: 1px solid #cbd5e1; vertical-align: middle;"'
                elif "待" in story["business_result"]:
                    bus_result_style = ' style="color: #b45309; font-weight: 500; padding: 10px 8px; border: 1px solid #cbd5e1; vertical-align: middle;"'

                if s_idx == 0:
                    rows_html.append(f"""
      <tr{row_style}>
        {epic_td}
        <td rowspan="{story_count}" class="req-col" style="font-weight: bold; background-color: #f8fafc; color: #1d4ed8; vertical-align: middle; text-align: center; min-width: 110px; border: 1px solid #cbd5e1; padding: 10px 8px;">
          <strong style="color: #1d4ed8;">{demand_id}</strong>
          <span class="req-sub" style="font-size: 11px; color: #64748b; font-weight: normal; display: block; margin-top: 4px;">{subtitle}</span>
        </td>
        <td {td_style}><strong>{story["id"]}</strong></td>
        <td class="story-name-col" style="max-width: 180px; word-break: break-all; padding: 10px 8px; border: 1px solid #cbd5e1; color: #334155; vertical-align: middle;">{story["name"]}</td>
        {system_td}
        <td{status_style}>{story["status"]}</td>
        <td {td_style}>{story.get("dev_owner_html", story["dev_owner"])}</td>
        <td {td_style}>{story["dev_end"]}</td>
        <td {td_style}>{story.get("dev_act", "--")}</td>
        <td {td_style}>{dev_badge}</td>
        <td {td_style}>{story.get("sit_owner_html", story["sit_owner"])}</td>
        <td {td_style}>{story["sit_end"]}</td>
        <td {td_style}>{story.get("sit_act", "--")}</td>
        <td {td_style}>{sit_badge}</td>
        <td {td_style}>{story.get("uat_owner_html", story["uat_owner"])}</td>
        <td {td_style}>{story["uat_end"]}</td>
        <td {td_style}>{story.get("uat_act", "--")}</td>
        <td {td_style}>{uat_badge}</td>
        <td {td_style}>{story["requester"]}</td>
        <td {td_style}>{story["business_acceptor"]}</td>
        <td{bus_result_style}>{story["business_result"]}</td>
        <td {td_style}><strong>{story["delivery_date"]}</strong></td>
        <td {td_style}>{overall_badge}</td>
      </tr>""")
                else:
                    rows_html.append(f"""
      <tr>
        <td {td_style}><strong>{story["id"]}</strong></td>
        <td class="story-name-col" style="max-width: 180px; word-break: break-all; padding: 10px 8px; border: 1px solid #cbd5e1; color: #334155; vertical-align: middle;">{story["name"]}</td>
        {system_td}
        <td{status_style}>{story["status"]}</td>
        <td {td_style}>{story.get("dev_owner_html", story["dev_owner"])}</td>
        <td {td_style}>{story["dev_end"]}</td>
        <td {td_style}>{story.get("dev_act", "--")}</td>
        <td {td_style}>{dev_badge}</td>
        <td {td_style}>{story.get("sit_owner_html", story["sit_owner"])}</td>
        <td {td_style}>{story["sit_end"]}</td>
        <td {td_style}>{story.get("sit_act", "--")}</td>
        <td {td_style}>{sit_badge}</td>
        <td {td_style}>{story.get("uat_owner_html", story["uat_owner"])}</td>
        <td {td_style}>{story["uat_end"]}</td>
        <td {td_style}>{story.get("uat_act", "--")}</td>
        <td {td_style}>{uat_badge}</td>
        <td {td_style}>{story["requester"]}</td>
        <td {td_style}>{story["business_acceptor"]}</td>
        <td{bus_result_style}>{story["business_result"]}</td>
        <td {td_style}><strong>{story["delivery_date"]}</strong></td>
        <td {td_style}>{overall_badge}</td>
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
    font-weight: 600;
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
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f8fafc; color: #1e293b; padding: 24px 16px; margin: 0;">

<div class="container" style="max-width: 1680px; margin: 0 auto; background-color: #ffffff; padding: 24px 28px; border-radius: 16px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05); border: 1px solid #e2e8f0;">
  <div class="header-banner" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #2563eb; padding-bottom: 12px; margin-bottom: 20px;">
    <h2 style="font-size: 22px; font-weight: 700; color: #1e3a8a; margin: 0;">📋 {project_name} 进度跟踪表</h2>
    <span class="sub-date" style="font-size: 13px; color: #64748b; font-weight: 500;">跟踪日期：{CURRENT_DATE_STR}（评估标准：结合阶段推进，仅评估活跃阶段与交付排期；包含未排期预警）</span>
  </div>

  <table style="border-collapse: collapse; width: 100%; font-size: 12px; text-align: left;">
    <thead>
      <tr class="group-header">
        <th colspan="6" style="background-color: #1e40af; color: #ffffff; font-weight: 700; text-align: center; border: 1px solid #1d4ed8; padding: 8px 6px; font-size: 13px;">📌 Story 基础与当前状态</th>
        <th colspan="4" style="background-color: #1e40af; color: #ffffff; font-weight: 700; text-align: center; border: 1px solid #1d4ed8; padding: 8px 6px; font-size: 13px;">💻 开发相关</th>
        <th colspan="4" style="background-color: #1e40af; color: #ffffff; font-weight: 700; text-align: center; border: 1px solid #1d4ed8; padding: 8px 6px; font-size: 13px;">🧪 SIT 测试</th>
        <th colspan="4" style="background-color: #1e40af; color: #ffffff; font-weight: 700; text-align: center; border: 1px solid #1d4ed8; padding: 8px 6px; font-size: 13px;">🔍 UAT 自测</th>
        <th colspan="3" style="background-color: #1e40af; color: #ffffff; font-weight: 700; text-align: center; border: 1px solid #1d4ed8; padding: 8px 6px; font-size: 13px;">🤝 业务验收</th>
        <th colspan="2" style="background-color: #1e40af; color: #ffffff; font-weight: 700; text-align: center; border: 1px solid #1d4ed8; padding: 8px 6px; font-size: 13px;">🚀 计划排期与综合预警</th>
      </tr>
      <tr class="sub-header">
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">史诗编号</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">需求编号</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">Story编号</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">任务名称</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">涉及系统</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">当前状态</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">开发经办人</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">预计结束</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">实际结束</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">开发状态</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">SIT经办人</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">预计结束</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">实际结束</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">SIT状态</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">UAT经办人</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">预计结束</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">实际结束</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">UAT状态</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">原始提出人</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">业务验收人</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">验收状态</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">计划生产排期</th>
        <th style="background-color: #f1f5f9; color: #334155; font-weight: 600; padding: 10px 8px; border: 1px solid #cbd5e1; text-align: left;">综合预警</th>
      </tr>
    </thead>
    <tbody>{"".join(rows_html)}
    </tbody>
  </table>

  <div class="legend-bar" style="margin-top: 16px; font-size: 12px; color: #475569; display: flex; gap: 16px; align-items: center;">
    <strong>图例说明：</strong>
    <span class="badge badge-overdue" style="display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; white-space: nowrap; background-color: #fee2e2; color: #b91c1c;">🚨 已逾期</span>
    <span class="badge badge-warning" style="display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; white-space: nowrap; background-color: #fef3c7; color: #b45309; border: 1px solid #fcd34d;">⚠️ 临近到期 (≤3天) / 未排期</span>
    <span class="badge badge-done" style="display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; white-space: nowrap; background-color: #dcfce7; color: #15803d;">✅ 已完成</span>
    <span class="badge badge-normal" style="display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; white-space: nowrap; background-color: #e0f2fe; color: #0369a1;">正常</span>
    <span class="badge badge-muted" style="display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; white-space: nowrap; color: #94a3b8;">-- 未排期</span>
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
    lines.append(f"> **跟踪规则**：`{filter_desc}` | 结合 Story 状态推进，已通过阶段自动标记 `✅ 已完成`；仅评估活跃阶段与交付排期，已过预计结束时间为 `🚨 已逾期`；距预计结束时间 ≤3 天或书面活跃阶段缺失时间为 `⚠️ 临近到期 / ⚠️ 未排期`。")
    lines.append("")
    lines.append("| 史诗编号 | 需求编号 | Story编号 | 任务名称 | 涉及系统 | 当前状态 | 开发经办人 | 开发预计结束 | 开发实际结束 | 开发状态 | SIT经办人 | SIT预计结束 | SIT实际结束 | SIT状态 | UAT经办人 | UAT预计结束 | UAT实际结束 | UAT状态 | 原始提出人 | 业务验收人 | 验收状态 | 计划生产排期 | 综合预警 |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
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
        epic_id = (stories[0].get("epic_id") if stories else None) or item.get("epic_id") or item.get("epic_code") or "--"
        epic_col = f"`{epic_id}`" if epic_id and epic_id != "--" else "--"
        
        if len(stories) == 0:
            lines.append(f"| {epic_col} | {demand_col} | - | (无关联 Story) | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |")
        else:
            rendered_count += 1
            for s_idx, story in enumerate(stories):
                s_copy = story.copy()
                s_copy["demand_id"] = demand_id
                s_copy["demand_subtitle"] = subtitle
                all_filtered_stories.append(s_copy)

                d_col = demand_col if s_idx == 0 else ""
                e_col = epic_col if s_idx == 0 else ""
                
                dev_st_md = format_phase_status_md(story['dev_status'], story['dev_end'], story.get('dev_act'))
                sit_st_md = format_phase_status_md(story['sit_status'], story['sit_end'], story.get('sit_act'))
                uat_st_md = format_phase_status_md(story['uat_status'], story['uat_end'], story.get('uat_act'))
                overall_st_md = format_phase_status_md(story['overall_status'], story['delivery_date'])

                lines.append(
                    f"| {e_col} | {d_col} | **{story['id']}** | {story['name']} | {story['system']} | {story['status']} | "
                    f"{story['dev_owner']} | {story['dev_end']} | {story.get('dev_act', '--')} | {dev_st_md} | "
                    f"{story['sit_owner']} | {story['sit_end']} | {story.get('sit_act', '--')} | {sit_st_md} | "
                    f"{story['uat_owner']} | {story['uat_end']} | {story.get('uat_act', '--')} | {uat_st_md} | "
                    f"{story['requester']} | {story['business_acceptor']} | {story['business_result']} | "
                    f"**{story['delivery_date']}** | {overall_st_md} |"
                )

    lines.append("")
    lines.append("## 🚨 重点逾期与预警汇总（按负责人提醒）")
    lines.append("")

    overdue_list = [s for s in all_filtered_stories if compute_overdue_days(s['dev_end'], s.get('dev_act')) > 0 or compute_overdue_days(s['sit_end'], s.get('sit_act')) > 0 or compute_overdue_days(s['uat_end'], s.get('uat_act')) > 0]
    warning_list = [s for s in all_filtered_stories if "待排期" in s["dev_status"] or "待排期" in s["sit_status"] or "待排期" in s["uat_status"] or "未排期" in s["overall_status"]]

    if not overdue_list and not warning_list:
        lines.append("- **✅ 整体良好**：目前暂无已逾期或未排期的 Story。")
    else:
        if overdue_list:
            lines.append(f"### 🚨 逾期 Story 提醒 (共 {len(overdue_list)} 个)")
            for s in overdue_list:
                overdue_phases = []
                d_days = compute_overdue_days(s['dev_end'], s.get('dev_act'))
                if d_days > 0: overdue_phases.append(f"开发经办人 @{s['dev_owner']}(逾期{d_days}天)")
                s_days = compute_overdue_days(s['sit_end'], s.get('sit_act'))
                if s_days > 0: overdue_phases.append(f"SIT经办人 @{s['sit_owner']}(逾期{s_days}天)")
                u_days = compute_overdue_days(s['uat_end'], s.get('uat_act'))
                if u_days > 0: overdue_phases.append(f"UAT经办人 @{s['uat_owner']}(逾期{u_days}天)")
                lines.append(f"- **{s['id']}** ({s['name']}) — 需求: `{s['demand_id']}` | 系统: `{s['system']}` | 逾期负责人: `{' / '.join(overdue_phases)}`")
            lines.append("")

        if warning_list:
            lines.append(f"### ⚠️ 未排期预警提醒 (共 {len(warning_list)} 个)")
            for s in warning_list:
                warn_phases = []
                if "待排期" in s["dev_status"]: warn_phases.append(f"开发经办人 @{s['dev_owner']}({s['dev_status']})")
                if "待排期" in s["sit_status"]: warn_phases.append(f"SIT经办人 @{s['sit_owner']}({s['sit_status']})")
                if "待排期" in s["uat_status"]: warn_phases.append(f"UAT经办人 @{s['uat_owner']}({s['uat_status']})")
                lines.append(f"- **{s['id']}** ({s['name']}) — 需求: `{s['demand_id']}` | 系统: `{s['system']}` | 需提醒负责人: `{' / '.join(warn_phases)}`")
            lines.append("")

    lines.extend(generate_active_reminder_markdown(data_list))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")
    print(f"[Orchestrator] 已成功生成 Markdown 表格: {output_path}")

def generate_active_reminder_markdown(data_list):
    uncompleted_reminders = []
    
    for d in data_list:
        demand_id = d.get("demand_id", "")
        subtitle = d.get("subtitle", "")
        d_title = f"{demand_id} ({subtitle})" if subtitle else demand_id
        
        for story in d.get("stories", []):
            s_id = story.get("id", "")
            s_name = story.get("name", "")
            s_sys = story.get("system", "")
            status = story.get("status", "")
            dev_st = story.get("dev_status", "")
            sit_st = story.get("sit_status", "")
            uat_st = story.get("uat_status", "")
            bus_st = story.get("business_result", "")

            # 过滤：已上线或全部阶段已完成的 Story 跳过
            if "已上线" in status or (dev_st == "✅ 已完成" and sit_st == "✅ 已完成" and uat_st == "✅ 已完成" and bus_st in ("已验收", "无需业务验收")):
                continue

            # 锁定当前活跃/未完成阶段及其经办人
            phase_label = ""
            active_owners = []

            if dev_st != "✅ 已完成":
                phase_label = "开发"
                active_owners = parse_owner_list(story.get("dev_owner"))
            elif sit_st != "✅ 已完成":
                phase_label = "SIT测试"
                active_owners = parse_owner_list(story.get("sit_owner"))
            elif uat_st != "✅ 已完成":
                phase_label = "UAT自测"
                active_owners = parse_owner_list(story.get("uat_owner"))
            elif uat_st == "✅ 已完成" and bus_st not in ("无需业务验收", "已验收", "--", ""):
                phase_label = "业务验收"
                req_owners = parse_owner_list(story.get("requester"))
                acc_owners = parse_owner_list(story.get("business_acceptor"))
                active_owners = []
                for o in req_owners + acc_owners:
                    if o != "/" and o not in active_owners:
                        active_owners.append(o)

            if active_owners and active_owners != ["/"]:
                ats_str = " ".join([f"@{o}" for o in active_owners])
                uncompleted_reminders.append({
                    "demand": d_title,
                    "story_id": s_id,
                    "story_name": s_name,
                    "system": s_sys,
                    "phase": phase_label,
                    "ats": ats_str
                })

    res = []
    res.append("---")
    res.append("### 💬 推进提醒与当前阶段责任人：")
    res.append("> 目前项目正在按计划推进中，请以下各未完成 Task 的当前阶段责任人老师加快推进：")
    res.append("> ")
    if uncompleted_reminders:
        for item in uncompleted_reminders:
            res.append(f"> - **{item['story_id']}** (`{item['system']}`) — 当前阶段: `{item['phase']}` | 责任人: **{item['ats']}**")
    else:
        res.append("> - **🎉 整体良好**：目前项目所有 Story 均已顺利推进完成！")
    res.append("> ")
    res.append("> 请确保各环节实际完成时间不晚于排期预计节点，如存在排期延误风险或跨团队依赖，请尽快沟通提示，以便第一时间协调解决。")
    res.append("> ")
    res.append("> **顺祝商祺！**")
    return res

EPIC_NAME_MAP = {
    "PG202204-0263": "CX-业务-QFII两融-二期",
}

async def resolve_epic_id(epic_id, script_dir):
    req_query_path = os.path.join(script_dir, "req_query.py")
    print(f"[Orchestrator] 检测到史诗编号 {epic_id}，正在解析关联的需求编号列表...")
    
    # 极速通道：优先从本地缓存 .table_cache.json 读取史诗关联需求
    cache_file = "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.table_cache.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
            epic_rows = [r for r in cache if r.get("epicCode") == epic_id]
            if epic_rows:
                resolved_demands = list(dict.fromkeys([r.get("demandId") for r in epic_rows if r.get("demandId")]))
                epic_name = epic_rows[0].get("epicName", "")
                if not epic_name and epic_id in EPIC_NAME_MAP:
                    epic_name = EPIC_NAME_MAP[epic_id]
                print(f"[Orchestrator] (缓存秒级命中) 史诗 {epic_id} 关联需求: {resolved_demands}, 名称: {epic_name}")
                return resolved_demands, epic_name
        except Exception:
            pass

    cmd = [sys.executable, req_query_path, epic_id, "--epic"]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    resolved_demands = []
    epic_name = ""
    if process.returncode == 0:
        out_str = stdout.decode('utf-8', errors='ignore')
        for line in out_str.splitlines():
            if line.startswith("EPIC_DEMANDS:"):
                demands_part = line[len("EPIC_DEMANDS:"):].strip()
                if demands_part:
                    resolved_demands = [d.strip().upper() for d in demands_part.split() if d.strip()]
            elif line.startswith("EPIC_NAME:"):
                epic_name = line[len("EPIC_NAME:"):].strip()
    else:
        err_msg = stderr.decode('utf-8', errors='ignore')
        print(f"[Orchestrator] 史诗编号 {epic_id} 解析失败: {err_msg}", file=sys.stderr)
        
    if not epic_name and epic_id in EPIC_NAME_MAP:
        epic_name = EPIC_NAME_MAP[epic_id]
        
    print(f"[Orchestrator] 史诗 {epic_id} 关联需求解析结果: {resolved_demands}, 名称: {epic_name}")
    return resolved_demands, epic_name

def save_live_data_to_cache(live_parsed_dict):
    """Save live queried demand & story records into .table_cache.json for persistent fast lookup."""
    cache_file = "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.table_cache.json"
    if not os.path.exists(cache_file):
        return
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
        
        existing_stories = {r.get("storyCode"): i for i, r in enumerate(cache) if r.get("storyCode")}
        
        for req_id, d_info in live_parsed_dict.items():
            demand_name = d_info.get("subtitle", "")
            epic_code = d_info.get("epic_code", "")
            epic_name = d_info.get("epic_name", "")
            stories = d_info.get("stories", [])
            
            if not stories:
                dummy_row = {
                    "demandId": req_id,
                    "demandName": demand_name,
                    "epicCode": epic_code,
                    "epicName": epic_name,
                    "storyCode": "",
                    "storyNo": "",
                    "storyTitle": "(无关联 Story)",
                    "planProdLineDate": ""
                }
                cache.append(dummy_row)
                continue
                
            for s in stories:
                story_code = s.get("id", "") or s.get("story_id", "")
                row = {
                    "demandId": req_id,
                    "demandName": demand_name,
                    "epicCode": epic_code,
                    "epicName": epic_name,
                    "storyCode": story_code,
                    "storyNo": story_code,
                    "storyTitle": s.get("name", "") or s.get("task_name", ""),
                    "storySystemName": s.get("system", ""),
                    "storyStatusName": s.get("status", "") or s.get("current_status", ""),
                    "devManagePerson": s.get("dev_owner", ""),
                    "devAssessDateEnd": s.get("dev_end", ""),
                    "sitTestManagePerson": s.get("sit_owner", ""),
                    "sitTestAssessDateEnd": s.get("sit_end", ""),
                    "uatTestManagePerson": s.get("uat_owner", ""),
                    "uatTestAssessDateEnd": s.get("uat_end", ""),
                    "businessAcceptor": s.get("business_acceptor", ""),
                    "demandCreatePerson": s.get("requester", ""),
                    "planProdLineDate": s.get("delivery_date", "") or s.get("plan_prod_date", "")
                }
                if story_code and story_code in existing_stories:
                    existing_row = cache[existing_stories[story_code]]
                    for k, v in row.items():
                        if v and str(v).strip() not in ("--", "/", "None", "", "null"):
                            existing_row[k] = v
                else:
                    cache.append(row)
                    
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"[Orchestrator] 自动回写 {len(live_parsed_dict)} 个需求到本地缓存 .table_cache.json 成功！")
    except Exception as e:
        print(f"[Orchestrator] 自动保存缓存失败: {e}")

async def main_async():
    parser = argparse.ArgumentParser(description="批量生成项目进度跟踪表（HTML & Markdown）")
    parser.add_argument("demand_ids", nargs="+", help="需求编号或史诗编号列表（以空格分隔）")
    parser.add_argument("--output_html", default=None, help="生成的 HTML 表格路径")
    parser.add_argument("--output_md", default=None, help="生成的 Markdown 表格路径")
    parser.add_argument("--project", default="交易结算核心历史数据及接口迁移项目", help="项目名称")
    parser.add_argument("--only_risk", action="store_true", help="仅显示高风险或逾期 Story")
    parser.add_argument("--send-mail", "--mail", "--send", "--draft", dest="send_mail", action="store_true", help="自动将生成的 HTML 进度跟踪表存入 Coremail 草稿箱")
    parser.add_argument("--refresh", "--live", "--no-cache", dest="refresh", action="store_true", help="强制实时从平台刷新提取最新数据 (跳过本地缓存)")
    args = parser.parse_args()

    project_name = args.project.strip()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 扫描输入参数，如果是史诗编号则解析它
    resolved_demand_ids = []
    epic_names = []
    demand_to_epic = {}
    for item in args.demand_ids:
        item_upper = item.strip().upper()
        if not item_upper:
            continue
        if item_upper.startswith("PG") or item_upper.startswith("E"):
            demands, epic_name = await resolve_epic_id(item_upper, script_dir)
            resolved_demand_ids.extend(demands)
            for d in demands:
                demand_to_epic[d] = item_upper
            if epic_name:
                epic_names.append(epic_name)
        else:
            resolved_demand_ids.append(item_upper)

    # 如果解析出了史诗名称，且用户没有通过命令行自定义项目名，则将项目名修改为史诗名称
    if epic_names and args.project == "交易结算核心历史数据及接口迁移项目":
        project_name = epic_names[0]

    html_path = args.output_html if args.output_html else f"{CURRENT_DATE_FILE_STR}-进度-{project_name}.html"
    md_path = args.output_md if args.output_md else f"{CURRENT_DATE_FILE_STR}-进度-{project_name}.md"
            
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

    # 优先从缓存获取需求与 Story 详情 (当 args.refresh 为 True 时强行从平台拉取最新数据)
    if args.refresh:
        print("[Orchestrator] 🔄 已开启【取最新数据】模式，强制实时连接金融科技平台抓取最新需求与 Story 数据...")
        cached_demands = {}
        missing_demands = demand_ids
    else:
        cached_demands = load_demand_data_from_cache(demand_ids, script_dir, demand_to_epic=demand_to_epic)
        missing_demands = [d for d in demand_ids if d not in cached_demands or len(cached_demands[d]["stories"]) == 0]

    live_parsed_dict = {}
    if missing_demands:
        print(f"[Orchestrator] 正在对 {len(missing_demands)} 个未缓存需求执行实时查询: {missing_demands}...")
        tasks = [run_single_query(req_id, script_dir) for req_id in missing_demands]
        temp_files = await asyncio.gather(*tasks)
        
        for req_id, temp_file in zip(missing_demands, temp_files):
            if temp_file and os.path.exists(temp_file):
                print(f"[Orchestrator] 解析中间结果: {temp_file}")
                data = parse_result_file(temp_file, req_id, demand_to_epic=demand_to_epic)
                if data:
                    live_parsed_dict[req_id] = data
                try:
                    os.remove(temp_file)
                except Exception as e:
                    print(f"[Orchestrator] 无法删除临时文件 {temp_file}: {e}")
            else:
                print(f"[Orchestrator] 警告: 未能获取需求 {req_id} 的数据，跳过该需求。")

        if live_parsed_dict:
            save_live_data_to_cache(live_parsed_dict)

    parsed_data = []
    for d_id in demand_ids:
        d_obj = None
        if d_id in cached_demands and len(cached_demands[d_id]["stories"]) > 0:
            d_obj = cached_demands[d_id]
        elif d_id in live_parsed_dict:
            d_obj = live_parsed_dict[d_id]
        else:
            d_obj = {
                "demand_id": d_id,
                "title": "",
                "subtitle": DEMAND_SUBTITLE_MAP.get(d_id, ""),
                "stories": []
            }
            
        target_epic = demand_to_epic.get(d_id, "")
        if isinstance(target_epic, dict):
            target_epic = target_epic.get("epic_code", "")
        if target_epic:
            d_obj["epic_id"] = target_epic
            for s in d_obj.get("stories", []):
                if not s.get("epic_id") or s.get("epic_id") == "--":
                    s["epic_id"] = target_epic
                    
        parsed_data.append(d_obj)

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

    # 如果指定了 --send-mail / --mail / --draft，自动将生成的 HTML 存入 Coremail 草稿箱
    if args.send_mail:
        stakeholders = extract_all_html_stakeholders(parsed_data)
        mail_subject = f"【进度跟踪】{project_name} 进度跟踪表 - {CURRENT_DATE_STR}"
        save_schedule_to_coremail_draft(html_path, mail_subject, stakeholders, parsed_data)

def is_invalid_contractor(raw_item):
    """
    判断经办人原始字符串是否为无工号/外包账号（如含 'CP_'）。
    外包/无工号人员不放入邮件收件人。
    """
    if not raw_item:
        return True
    s_raw = str(raw_item).strip()
    if re.search(r'CP_', s_raw, re.IGNORECASE):
        return True
    return False

def extract_all_html_stakeholders(parsed_data):
    stakeholders = []
    contractor_names = set()

    # 第一轮：遍历识别所有含有 CP_ 外包账号标识的人员名字（如 '邢航源-CP_xinghangyuan'）
    for d in parsed_data:
        detail = d.get("detail_info") or {}
        for s in d.get("stories", []):
            for k in ("raw_dev_owner", "raw_sit_owner", "raw_uat_owner", "raw_requester", "raw_acceptor"):
                val = s.get(k)
                if val:
                    for item in re.split(r'[,，/\\;\n\t、\s]+', str(val)):
                        if re.search(r'CP_', item, re.IGNORECASE):
                            c_name = parse_owner(item)
                            if c_name != "/":
                                contractor_names.add(c_name)

    # 第二轮：收集全量内部干系人（包含需求提出人、业务验收人、各阶段经办人），彻底排除外包人员
    def process_field(raw_val):
        if not raw_val:
            return
        if isinstance(raw_val, list):
            items = raw_val
        else:
            items = re.split(r'[,，/\\;\n\t、\s]+', str(raw_val))
        for item in items:
            item_str = str(item).strip()
            if not item_str or item_str in ("/", "--", "None"):
                continue
            if re.search(r'CP_', item_str, re.IGNORECASE):
                continue
            name = parse_owner(item_str)
            if name != "/" and name not in contractor_names and name not in stakeholders:
                stakeholders.append(name)

    for d in parsed_data:
        detail = d.get("detail_info") or {}
        for k in ("raw_requester", "raw_acceptor", "original_requester", "business_acceptor", "demand_bus_owner", "demand_req_owner", "原始需求提出人", "原始提出人", "业务验收人"):
            process_field(d.get(k) or detail.get(k))
                        
        for s in d.get("stories", []):
            for k in ("dev_owners", "sit_owners", "uat_owners", "dev_owner", "sit_owner", "uat_owner", "bus_owner", "requester", "business_acceptor", "original_requester", "raw_dev_owner", "raw_sit_owner", "raw_uat_owner", "raw_requester", "raw_acceptor"):
                process_field(s.get(k))
                            
    return stakeholders

def generate_active_reminder_html(parsed_data):
    """
    对未完成的需求/Story，提取当前活跃阶段经办人并生成带有 @ 提醒的 HTML 区块
    已完成的 Story/环节自动跳过，不列入提醒
    """
    uncompleted_reminders = []
    
    for d in parsed_data:
        demand_id = d.get("demand_id", "")
        subtitle = d.get("subtitle", "")
        d_title = f"{demand_id} ({subtitle})" if subtitle else demand_id
        
        for story in d.get("stories", []):
            s_id = story.get("id", "")
            s_name = story.get("name", "")
            s_sys = story.get("system", "")
            status = story.get("status", "")
            dev_st = story.get("dev_status", "")
            sit_st = story.get("sit_status", "")
            uat_st = story.get("uat_status", "")
            bus_st = story.get("business_result", "")

            # 过滤：已上线或全部阶段已完成的 Story 跳过
            if "已上线" in status or (dev_st == "✅ 已完成" and sit_st == "✅ 已完成" and uat_st == "✅ 已完成" and bus_st in ("已验收", "无需业务验收")):
                continue

            # 锁定当前活跃/未完成阶段及其经办人
            phase_label = ""
            active_owners = []

            if dev_st != "✅ 已完成":
                phase_label = "开发"
                active_owners = parse_owner_list(story.get("dev_owner"))
            elif sit_st != "✅ 已完成":
                phase_label = "SIT测试"
                active_owners = parse_owner_list(story.get("sit_owner"))
            elif uat_st != "✅ 已完成":
                phase_label = "UAT自测"
                active_owners = parse_owner_list(story.get("uat_owner"))
            elif uat_st == "✅ 已完成" and bus_st not in ("无需业务验收", "已验收", "--", ""):
                phase_label = "业务验收"
                req_owners = parse_owner_list(story.get("requester"))
                acc_owners = parse_owner_list(story.get("business_acceptor"))
                active_owners = []
                for o in req_owners + acc_owners:
                    if o != "/" and o not in active_owners:
                        active_owners.append(o)

            if active_owners and active_owners != ["/"]:
                ats_str = " ".join([f"<strong style='color:#1d4ed8;'>@{o}</strong>" for o in active_owners])
                uncompleted_reminders.append({
                    "demand": d_title,
                    "story_id": s_id,
                    "story_name": s_name,
                    "system": s_sys,
                    "phase": phase_label,
                    "ats": ats_str
                })

    if not uncompleted_reminders:
        return (
            '\n<div style="margin-top: 24px; padding: 20px 24px; background-color: #f0fdf4; '
            'border: 1px solid #bbf7d0; border-radius: 10px; font-size: 14px; color: #166534; line-height: 1.8;">\n'
            '  <div style="font-weight: 700; font-size: 15px; color: #15803d; margin-bottom: 8px;">\n'
            '    🎉 进度提醒：\n'
            '  </div>\n'
            '  <div>目前项目所有 Story 均已顺利推进完成！顺祝商祺！</div>\n'
            '</div>\n'
        )

    lines = []
    lines.append('\n<div style="margin-top: 24px; padding: 20px 24px; background-color: #eff6ff; '
                 'border: 1px solid #bfdbfe; border-radius: 10px; font-size: 14px; color: #1e3a8a; line-height: 1.8;">')
    lines.append('  <div style="font-weight: 700; font-size: 15px; color: #1d4ed8; margin-bottom: 12px;">')
    lines.append('    💬 推进提醒与当前阶段责任人：')
    lines.append('  </div>')
    lines.append('  <div style="color: #1e40af; font-weight: 500; margin-bottom: 12px;">')
    lines.append('    目前项目正在按计划推进中，请以下各未完成 Task 的当前阶段责任人老师加快推进：')
    lines.append('  </div>')
    lines.append('  <ul style="margin: 0; padding-left: 20px; color: #1e293b;">')
    
    for item in uncompleted_reminders:
        lines.append(f"    <li style='margin-bottom: 6px;'><b>{item['story_id']}</b> ({item['system']}) - 当前阶段: <span style='color:#b91c1c; font-weight:600;'>{item['phase']}</span> | 责任人: {item['ats']}</li>")

    lines.append('  </ul>')
    lines.append('  <div style="margin-top: 14px; color: #475569; font-size: 13px;">')
    lines.append('    请确保各环节实际完成时间不晚于排期预计节点，如存在排期延误风险或跨团队依赖，请尽快沟通提示，以便第一时间协调解决。<br><br>')
    lines.append('    顺祝商祺！')
    lines.append('  </div>')
    lines.append('</div>')

    return "\n".join(lines)

def save_schedule_to_coremail_draft(html_file, subject, stakeholders, parsed_data=None):
    draft_script = "/Volumes/Macintosh HD_Data/WorkBuddy/邮件发送/.agents/skills/email-polisher/scripts/save_to_draft.py"
    if not os.path.exists(draft_script):
        print(f"[Email Error] 找不到 Coremail 存草稿脚本: {draft_script}")
        return False
        
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # 动态在邮件正文 HTML 底部追加针对未完成 Task 当前阶段经办人的 @ 提醒 Block
    prompt_block = generate_active_reminder_html(parsed_data) if parsed_data else ""
    
    if "</body>" in html_content:
        email_body = html_content.replace("</body>", f"{prompt_block}</body>")
    else:
        email_body = html_content + prompt_block
        
    temp_email_body_file = html_file.replace(".html", "_email_body.html")
    with open(temp_email_body_file, "w", encoding="utf-8") as f:
        f.write(email_body)
        
    recipients_str = ", ".join(stakeholders)
    print(f"\n[Email] 🚀 正在自动存入 Coremail 草稿箱...")
    print(f"[Email] 📌 主题: {subject}")
    print(f"[Email] 👥 收件人 ({len(stakeholders)}位): {recipients_str}")
    
    cmd = [
        sys.executable,
        draft_script,
        "--subject", subject,
        "--body-file", temp_email_body_file,
        "--recipients", recipients_str,
        "--attachments", html_file
    ]
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if temp_email_body_file and os.path.exists(temp_email_body_file):
            try:
                os.remove(temp_email_body_file)
            except Exception:
                pass
                
        if res.returncode == 0:
            print("[Email] 💾 ✅ 进度跟踪表邮件已成功存入 Coremail 草稿箱！请登录邮箱核对后手动点击发送。")
            return True
        else:
            print(f"[Email Error] ❌ 存入 Coremail 草稿箱失败: {res.stderr or res.stdout}")
            return False
    except Exception as e:
        print(f"[Email Error] ❌ 存入 Coremail 草稿箱异常: {e}")
        return False

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
