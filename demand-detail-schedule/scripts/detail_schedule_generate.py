#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detail_schedule_generate.py — 需求明细进度监控与环节负责人提醒工具（极速高性能版）
=============================================================================
批量查询多个需求编号或史诗编号，提取开发、SIT测试、UAT自测等各个环节的负责人、
预计结束时间及需求/Story的预计交付验收时间。
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

# 全局内存缓存单例，避免多次读取与解析 JSON
_CACHE_DATA_SINGLETON = None
_CACHE_INDEX_BY_DEMAND = None

# 需求编号子标题硬编码映射
DEMAND_SUBTITLE_MAP = {
    "R2603130062": "富易网络投票切换清算",
    "R2603110056": "历史文件迁移到清算",
    "R2602120019": "银证转账历史文件迁移",
    "R2602120009": "交易历史文件迁移",
    "R2602120017": "担保费率等迁移参数后台",
    "R2604300028": "融资仓单偿还数量优化",
    "R2606170151": "买券还券增加风险警示板权限",
}

# 特殊/已知 Story 实际完成时间精确映射 (对应 #Story 一生 节点完成时间)
STORY_ACTUAL_END_MAP = {
    "S2601070079": {
        "dev": "2026-07-09",
        "sit": "2026-07-03"
    }
}

def check_credentials_prompt(script_dir):
    """检查 config.json 中是否配置了工号与密码，未配置时给予友好、详细的提示"""
    config_paths = [
        os.path.join(script_dir, "config.json"),
        os.path.join(os.path.dirname(script_dir), "config.json"),
        os.path.join(os.getcwd(), "config.json")
    ]
    found_config = None
    cfg = {}
    for cp in config_paths:
        if os.path.exists(cp):
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    found_config = cp
                break
            except Exception:
                pass

    username = str(cfg.get("username", "")).strip()
    password = str(cfg.get("password", "")).strip()

    is_missing = (
        not username or
        not password or
        username in ("你的工号", "YOUR_USERNAME") or
        password in ("你的登录密码", "YOUR_PASSWORD", "密码", "您的密码")
    )

    if is_missing:
        target_path = found_config if found_config else os.path.join(script_dir, "config.json")
        print("\n" + "=" * 75)
        print("⚠️  [配置提醒] 尚未配置金融科技平台账号凭证 (config.json)")
        print("-" * 75)
        print("💡 提示：当前将自动以本地缓存 (.table_cache.json) 模式为您快速生成进度表。")
        print(f"👉 若后续需要自动登录平台同步最新需求/大宽表数据，请修改以下配置文件：")
        print(f"   配置文件路径: {target_path}")
        print("   标准配置格式:")
        print("   {")
        print('     "username": "你的工号",')
        print('     "password": "你的登录密码",')
        print('     "platform_url": "http://fintech.gtht.com.cn"')
        print("   }")
        print("=" * 75 + "\n")
        return False
    return True

def load_external_config(script_dir):
    """动态读取外置 config.json 配置文件（若存在），自动融合需求副标题与节点实际时间映射"""
    global DEMAND_SUBTITLE_MAP, STORY_ACTUAL_END_MAP
    check_credentials_prompt(script_dir)
    config_paths = [
        os.path.join(script_dir, "config.json"),
        os.path.join(os.path.dirname(script_dir), "config.json"),
        os.path.join(os.getcwd(), "config.json")
    ]
    for cp in config_paths:
        if os.path.exists(cp):
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if "demand_subtitles" in cfg and isinstance(cfg["demand_subtitles"], dict):
                    DEMAND_SUBTITLE_MAP.update(cfg["demand_subtitles"])
                if "story_actual_end_map" in cfg and isinstance(cfg["story_actual_end_map"], dict):
                    STORY_ACTUAL_END_MAP.update(cfg["story_actual_end_map"])
                break
            except Exception:
                pass
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

def get_indexed_cache(script_dir):
    """单例高速缓存读取与 O(1) 索引构建"""
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

def determine_story_phase_level(status_name):
    """
    根据 Story 当前状态判定流程层级:
    Level 4: 全流程/验收/生产测试完成 (结束 / 已结束 / 完成 / 已发布 / 已上线 / 业务验收/设计走查 / SIT生产测试 / UAT生产自测 / xx完成) -> 开发、SIT、UAT 均已完成!
    Level 3: 已进入/待 UAT 自测阶段 (UAT小远期打包 / UAT小远期自测中 / 待UAT测试 ...) -> 开发与SIT均已完成!
    Level 2: 已进入/待 SIT 自测阶段 / 开发完成 (SIT测试中 / 开发完成 / 待SIT测试 ...) -> 开发已完成!
    Level 1: 仍处于开发/分析阶段 (开发中 / 待排期 / 待开发 / 待处理 ...)
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
        if phase_level > 1:
            return "✅ 已完成"
        else:
            return "⚠️ 未排期" if res == "--" else res

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

def compute_overdue_days(planned_end, actual_end):
    """计算实际结束相比预计结束超出的天数"""
    if not planned_end or not actual_end or planned_end == "--" or actual_end == "--":
        return 0
    try:
        dt_plan = datetime.strptime(planned_end, "%Y-%m-%d")
        dt_act = datetime.strptime(actual_end, "%Y-%m-%d")
        delta = (dt_act.date() - dt_plan.date()).days
        return delta if delta > 0 else 0
    except Exception:
        return 0

def format_phase_status_html(status_str, planned_end, actual_end):
    badge = f'<span class="badge {get_badge_class(status_str)}">{status_str}</span>'
    days = compute_overdue_days(planned_end, actual_end)
    if days > 0:
        badge += f'<br><span style="font-size: 11px; color: #b91c1c; font-weight: 500; display: block; margin-top: 2px;">逾期{days}天</span>'
    return badge

def format_phase_status_md(status_str, planned_end, actual_end):
    days = compute_overdue_days(planned_end, actual_end)
    if days > 0:
        return f"{status_str}<br><span style='color:#b91c1c;'>逾期{days}天</span>"
    return status_str

def is_risk_story(story):
    """
    判定 Story 是否属于需在风险提醒表中展示的风险项。
    规则：
    1. 若 开发相关、SIT测试、UAT自测 三个环节的状态均为 '✅ 已完成'，一律彻底过滤掉，不在风险列表中显示。
    2. 若存在任何活跃环节为 '已逾期'、'临近到期'、'今天到期' 或 '未排期'，判定为风险 Story 予以展示。
    """
    dev_st = story.get("dev_status", "")
    sit_st = story.get("sit_status", "")
    uat_st = story.get("uat_status", "")

    # 若开发、SIT、UAT三大环节均已完成，彻底过滤
    if dev_st == "✅ 已完成" and sit_st == "✅ 已完成" and uat_st == "✅ 已完成":
        return False

    phases = [dev_st, sit_st, uat_st, story.get("overall_status", "")]
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

            small_deliver = clean_date_str(r.get("smallDeliverDate"))
            large_deliver = clean_date_str(r.get("largeDeliverDate"))
            uat_inner = clean_date_str(r.get("uatSmallForwardInner"))
            demand_finish = clean_date_str(r.get("demandFinishTime"))

            # 实际结束时间计算逻辑：
            # 若环节未完成 (!= '✅ 已完成')，必定为 '--'
            # 若环节已完成 (== '✅ 已完成')：
            # 1. 优先从 STORY_ACTUAL_END_MAP 精确节点映射查找
            # 2. 其次取 smallDeliverDate / largeDeliverDate / demandFinishTime 等实际完成字段
            # 3. 兜底取对应阶段估算/排期时间，确保必定填写具体 YYYY-MM-DD 日期（绝不显示 '已完成' 字样）
            def resolve_actual_date(phase_name, phase_status, assess_end_date):
                if phase_status != "✅ 已完成":
                    return "--"
                if s_id in STORY_ACTUAL_END_MAP and phase_name in STORY_ACTUAL_END_MAP[s_id]:
                    return STORY_ACTUAL_END_MAP[s_id][phase_name]
                if phase_name == 'dev':
                    if small_deliver != "--": return small_deliver
                    if large_deliver != "--": return large_deliver
                    if demand_finish != "--": return demand_finish
                    if assess_end_date != "--": return assess_end_date
                    plan_line = clean_date_str(r.get("storyPlanLineDate"))
                    return plan_line if plan_line != "--" else "--"
                elif phase_name == 'sit':
                    if small_deliver != "--": return small_deliver
                    if large_deliver != "--": return large_deliver
                    if demand_finish != "--": return demand_finish
                    if assess_end_date != "--": return assess_end_date
                    plan_line = clean_date_str(r.get("storyPlanLineDate"))
                    return plan_line if plan_line != "--" else "--"
                elif phase_name == 'uat':
                    if uat_inner != "--": return uat_inner
                    if small_deliver != "--": return small_deliver
                    if large_deliver != "--": return large_deliver
                    if demand_finish != "--": return demand_finish
                    if assess_end_date != "--": return assess_end_date
                    due_date = clean_date_str(r.get("demandEsDuedate"))
                    return due_date if due_date != "--" else "--"
                return "--"

            dev_act = resolve_actual_date('dev', dev_status, dev_end)
            sit_act = resolve_actual_date('sit', sit_status, sit_end)
            uat_act = resolve_actual_date('uat', uat_status, uat_end)

            delivery_date = clean_date_str(r.get("demandEsDuedate"))
            story_it_duedate = clean_date_str(r.get("storyItDuedate"))
            plan_prod_date = clean_date_str(r.get("planProdLineDate"))
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
                "plan_prod_date": plan_prod_date,
                "dev_owner": dev_owner,
                "dev_end": dev_end,
                "dev_act": dev_act,
                "dev_status": dev_status,
                "sit_owner": sit_owner,
                "sit_end": sit_end,
                "sit_act": sit_act,
                "sit_status": sit_status,
                "uat_owner": uat_owner,
                "uat_end": uat_end,
                "uat_act": uat_act,
                "uat_status": uat_status,
                "story_it_duedate": story_it_duedate,
                "delivery_date": delivery_date,
                "overall_status": overall_status
            })

        first_plan_date = stories[0]["plan_prod_date"] if stories else "--"
        demands_dict[d_id] = {
            "demand_id": d_id,
            "title": title,
            "subtitle": subtitle,
            "plan_prod_date": first_plan_date,
            "stories": stories
        }

    return demands_dict

def generate_html(data_list, output_path, project_name, only_risk=True, show_plan_date_col=True):
    rows_html = []
    
    total_risk_stories = 0
    rendered_demands_count = 0
    for idx, item in enumerate(data_list):
        demand_id = item["demand_id"]
        subtitle = item["subtitle"]
        stories = item["stories"]

        if only_risk:
            stories = [s for s in stories if is_risk_story(s)]
            if len(stories) == 0:
                continue

        story_count = len(stories)
        total_risk_stories += story_count
        rendered_demands_count += 1
        row_style = ' style="border-top: 2px solid #cbd5e1;"' if rendered_demands_count > 1 else ''
        
        plan_td = f"""
        <td rowspan="{story_count}" class="req-col" style="background-color: #f8fafc; color: #1e3a8a;">
          <strong>{item.get("plan_prod_date", stories[0]["plan_prod_date"] if stories else "--")}</strong>
        </td>""" if show_plan_date_col else ""

        empty_plan_td = f"""
        <td class="req-col" style="background-color: #f1f5f9; color: #1e3a8a;">
          <strong>{item.get("plan_prod_date", "--")}</strong>
        </td>""" if show_plan_date_col else ""

        empty_colspan = "19" if show_plan_date_col else "18"

        if story_count == 0:
            rows_html.append(f"""
      <tr{row_style}>
        {empty_plan_td}
        <td class="req-col">
          <strong>{demand_id}</strong>
          <span class="req-sub">{subtitle}</span>
        </td>
        <td colspan="{empty_colspan}" style="text-align: center; color: #64748b;">（无关联 Story）</td>
      </tr>""")
        else:
            for s_idx, story in enumerate(stories):
                dev_badge = format_phase_status_html(story["dev_status"], story["dev_end"], story["dev_act"])
                sit_badge = format_phase_status_html(story["sit_status"], story["sit_end"], story["sit_act"])
                uat_badge = format_phase_status_html(story["uat_status"], story["uat_end"], story["uat_act"])
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
        {plan_td}
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
        <td>{story["dev_act"]}</td>
        <td>{dev_badge}</td>
        <td>{story["sit_owner"]}</td>
        <td>{story["sit_end"]}</td>
        <td>{story["sit_act"]}</td>
        <td>{sit_badge}</td>
        <td>{story["uat_owner"]}</td>
        <td>{story["uat_end"]}</td>
        <td>{story["uat_act"]}</td>
        <td>{uat_badge}</td>
        <td>{story["story_it_duedate"]}</td>
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
        <td>{story["dev_act"]}</td>
        <td>{dev_badge}</td>
        <td>{story["sit_owner"]}</td>
        <td>{story["sit_end"]}</td>
        <td>{story["sit_act"]}</td>
        <td>{sit_badge}</td>
        <td>{story["uat_owner"]}</td>
        <td>{story["uat_end"]}</td>
        <td>{story["uat_act"]}</td>
        <td>{uat_badge}</td>
        <td>{story["story_it_duedate"]}</td>
        <td><strong>{story["delivery_date"]}</strong></td>
        <td>{overall_badge}</td>
      </tr>""")

    total_cols = "21" if show_plan_date_col else "20"
    group_colspan = "6" if show_plan_date_col else "5"
    plan_th = "<th>计划生产排期</th>\n        " if show_plan_date_col else ""

    if len(rows_html) == 0:
        rows_html.append(f"""
      <tr>
        <td colspan="{total_cols}" style="text-align: center; padding: 20px; color: #166534; font-weight: 600;">
          🎉 太棒了！当前查询的所有需求均无逾期、预警或未排期 Story。
        </td>
      </tr>""")

    filter_desc = "🚨 仅显示存在逾期/预警/未排期的需求与 Story" if only_risk else "全量 Story 跟踪"

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>需求明细风险提醒表</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background-color: #f8fafc;
    color: #1e293b;
    padding: 24px 16px;
    margin: 0;
  }}
  .container {{
    max-width: 2000px;
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
    <h2>📋 需求明细风险提醒表</h2>
    <span class="sub-date">跟踪日期：{CURRENT_DATE_STR}（评估标准：结合阶段推进，仅评估活跃阶段与交付排期；包含未排期预警）</span>
  </div>

  <table>
    <thead>
      <tr class="group-header">
        <th colspan="{group_colspan}">📌 Story 基础与当前状态</th>
        <th colspan="4">💻 开发相关</th>
        <th colspan="4">🧪 SIT 测试</th>
        <th colspan="4">🔍 UAT 自测</th>
        <th colspan="3">🚀 交付验收与综合预警</th>
      </tr>
      <tr class="sub-header">
        {plan_th}<th>需求编号</th>
        <th>Story编号</th>
        <th>任务名称</th>
        <th>涉及系统</th>
        <th>当前状态</th>
        <th>开发负责人</th>
        <th>预计结束</th>
        <th>实际结束</th>
        <th>开发状态</th>
        <th>SIT负责人</th>
        <th>预计结束</th>
        <th>实际结束</th>
        <th>SIT状态</th>
        <th>UAT负责人</th>
        <th>预计结束</th>
        <th>实际结束</th>
        <th>UAT状态</th>
        <th>需求评审预计交付时间</th>
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

    abs_output_path = os.path.abspath(os.path.join(os.getcwd(), output_path))
    with open(abs_output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[DetailedSchedule] 已成功生成 HTML 表格: {abs_output_path} (关联风险需求 {rendered_demands_count} 个，共 {total_risk_stories} 条风险 Story)")

def generate_markdown(data_list, output_path, project_name, only_risk=True, show_plan_date_col=True):
    lines = []
    filter_desc = "仅显示逾期/临近到期预警/未排期 Story" if only_risk else "全量 Story 跟踪"
    lines.append(f"# 📋 {project_name} - 需求明细风险提醒表 ({CURRENT_DATE_STR})")
    lines.append("")
    lines.append(f"> **筛选模式**：`{filter_desc}` | 规则：结合 Story 状态推进，已通过阶段自动标记 `✅ 已完成`；仅评估活跃阶段与交付排期，已过预计结束时间为 `🚨 已逾期`；距预计结束时间 ≤3 天或活跃阶段缺失时间为 `⚠️ 临近到期 / ⚠️ 未排期`。")
    lines.append("")
    
    if show_plan_date_col:
        lines.append("| 计划生产排期 | 需求编号 | Story编号 | 任务名称 | 涉及系统 | 当前状态 | 开发负责人 | 开发预计结束 | 开发实际结束 | 开发状态 | SIT负责人 | SIT预计结束 | SIT实际结束 | SIT状态 | UAT负责人 | UAT预计结束 | UAT实际结束 | UAT状态 | 需求评审预计交付时间 | 预计交付验收时间 | 综合预警 |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    else:
        lines.append("| 需求编号 | Story编号 | 任务名称 | 涉及系统 | 当前状态 | 开发负责人 | 开发预计结束 | 开发实际结束 | 开发状态 | SIT负责人 | SIT预计结束 | SIT实际结束 | SIT状态 | UAT负责人 | UAT预计结束 | UAT实际结束 | UAT状态 | 需求评审预计交付时间 | 预计交付验收时间 | 综合预警 |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    all_filtered_stories = []
    rendered_count = 0
    for item in data_list:
        demand_id = item["demand_id"]
        subtitle = item["subtitle"]
        stories = item["stories"]

        if only_risk:
            stories = [s for s in stories if is_risk_story(s)]
            if len(stories) == 0:
                continue

        demand_col = f"**{demand_id}**<br>({subtitle})"
        
        if len(stories) == 0:
            if show_plan_date_col:
                lines.append(f"| **{item.get('plan_prod_date', '--')}** | {demand_col} | - | (无关联 Story) | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |")
            else:
                lines.append(f"| {demand_col} | - | (无关联 Story) | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |")
        else:
            rendered_count += 1
            for s_idx, story in enumerate(stories):
                s_copy = story.copy()
                s_copy["demand_id"] = demand_id
                s_copy["demand_subtitle"] = subtitle
                all_filtered_stories.append(s_copy)

                d_col = demand_col if s_idx == 0 else ""
                dev_st_md = format_phase_status_md(story['dev_status'], story['dev_end'], story['dev_act'])
                sit_st_md = format_phase_status_md(story['sit_status'], story['sit_end'], story['sit_act'])
                uat_st_md = format_phase_status_md(story['uat_status'], story['uat_end'], story['uat_act'])

                if show_plan_date_col:
                    p_col = f"**{story['plan_prod_date']}**" if s_idx == 0 else ""
                    lines.append(
                        f"| {p_col} | {d_col} | **{story['id']}** | {story['name']} | {story['system']} | {story['status']} | "
                        f"{story['dev_owner']} | {story['dev_end']} | {story['dev_act']} | {dev_st_md} | "
                        f"{story['sit_owner']} | {story['sit_end']} | {story['sit_act']} | {sit_st_md} | "
                        f"{story['uat_owner']} | {story['uat_end']} | {story['uat_act']} | {uat_st_md} | "
                        f"{story['story_it_duedate']} | **{story['delivery_date']}** | {story['overall_status']} |"
                    )
                else:
                    lines.append(
                        f"| {d_col} | **{story['id']}** | {story['name']} | {story['system']} | {story['status']} | "
                        f"{story['dev_owner']} | {story['dev_end']} | {story['dev_act']} | {dev_st_md} | "
                        f"{story['sit_owner']} | {story['sit_end']} | {story['sit_act']} | {sit_st_md} | "
                        f"{story['uat_owner']} | {story['uat_end']} | {story['uat_act']} | {uat_st_md} | "
                        f"{story['story_it_duedate']} | **{story['delivery_date']}** | {story['overall_status']} |"
                    )

    if rendered_count == 0 and only_risk:
        if show_plan_date_col:
            lines.append("| **全部正常** | - | - | 🎉 太棒了！当前查询的所有需求均无逾期、预警或未排期 Story。 | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |")
        else:
            lines.append("| **全部正常** | - | 🎉 太棒了！当前查询的所有需求均无逾期、预警或未排期 Story。 | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |")

    lines.append("")
    lines.append("## 🚨 重点逾期与预警汇总（按负责人提醒）")

def generate_markdown(data_list, output_path, project_name, only_risk=True):
    lines = []
    filter_desc = "仅显示逾期/临近到期预警/未排期 Story" if only_risk else "全量 Story 跟踪"
    lines.append(f"# 📋 {project_name} - 需求明细风险提醒表 ({CURRENT_DATE_STR})")
    lines.append("")
    lines.append(f"> **筛选模式**：`{filter_desc}` | 规则：结合 Story 状态推进，已通过阶段自动标记 `✅ 已完成`；仅评估活跃阶段与交付排期，已过预计结束时间为 `🚨 已逾期`；距预计结束时间 ≤3 天或活跃阶段缺失时间为 `⚠️ 临近到期 / ⚠️ 未排期`。")
    lines.append("")
    lines.append("| 计划生产排期 | 需求编号 | Story编号 | 任务名称 | 涉及系统 | 当前状态 | 开发负责人 | 开发预计结束 | 开发实际结束 | 开发状态 | SIT负责人 | SIT预计结束 | SIT实际结束 | SIT状态 | UAT负责人 | UAT预计结束 | UAT实际结束 | UAT状态 | 需求评审预计交付时间 | 预计交付验收时间 | 综合预警 |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    all_filtered_stories = []
    rendered_count = 0
    for item in data_list:
        demand_id = item["demand_id"]
        subtitle = item["subtitle"]
        stories = item["stories"]

        if only_risk:
            stories = [s for s in stories if is_risk_story(s)]
            if len(stories) == 0:
                continue

        demand_col = f"**{demand_id}**<br>({subtitle})"
        
        if len(stories) == 0:
            lines.append(f"| **{item.get('plan_prod_date', '--')}** | {demand_col} | - | (无关联 Story) | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |")
        else:
            rendered_count += 1
            for s_idx, story in enumerate(stories):
                s_copy = story.copy()
                s_copy["demand_id"] = demand_id
                s_copy["demand_subtitle"] = subtitle
                all_filtered_stories.append(s_copy)

                p_col = f"**{story['plan_prod_date']}**" if s_idx == 0 else ""
                d_col = demand_col if s_idx == 0 else ""
                dev_st_md = format_phase_status_md(story['dev_status'], story['dev_end'], story['dev_act'])
                sit_st_md = format_phase_status_md(story['sit_status'], story['sit_end'], story['sit_act'])
                uat_st_md = format_phase_status_md(story['uat_status'], story['uat_end'], story['uat_act'])
                lines.append(
                    f"| {p_col} | {d_col} | **{story['id']}** | {story['name']} | {story['system']} | {story['status']} | "
                    f"{story['dev_owner']} | {story['dev_end']} | {story['dev_act']} | {dev_st_md} | "
                    f"{story['sit_owner']} | {story['sit_end']} | {story['sit_act']} | {sit_st_md} | "
                    f"{story['uat_owner']} | {story['uat_end']} | {story['uat_act']} | {uat_st_md} | "
                    f"{story['story_it_duedate']} | **{story['delivery_date']}** | {story['overall_status']} |"
                )

    if rendered_count == 0 and only_risk:
        lines.append("| **全部正常** | - | - | 🎉 太棒了！当前查询的所有需求均无逾期、预警或未排期 Story。 | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |")

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

    abs_output_path = os.path.abspath(os.path.join(os.getcwd(), output_path))
    with open(abs_output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")
    print(f"[DetailedSchedule] 已成功生成 Markdown 表格: {abs_output_path}")

def find_demands_by_plan_date(plan_date_str, script_dir, receiver=None):
    clean = plan_date_str.replace("-", "").strip()
    if len(clean) == 8 and clean.isdigit():
        norm_date = f"{clean[:4]}-{clean[4:6]}-{clean[6:]}"
        compact_date = clean
    else:
        norm_date = plan_date_str
        compact_date = clean

    cache_data, by_demand = get_indexed_cache(script_dir)
    if not cache_data:
        return []

    matched_demands = []
    seen = set()
    for r in cache_data:
        p_date = clean_date_str(r.get("planProdLineDate"))
        r_rec = (r.get("demandReceiver") or "").strip()

        # 严格按计划生产排期 (planProdLineDate) 权威匹配
        date_match = (p_date != "--" and (p_date == norm_date or p_date.replace("-", "") == compact_date))
        rec_match = (receiver is None or receiver in r_rec)

        if date_match and rec_match:
            d_id = r.get("demandId")
            if d_id and d_id not in seen:
                seen.add(d_id)
                matched_demands.append(d_id)

    return matched_demands

def main():
    parser = argparse.ArgumentParser(description="生成需求明细风险提醒表（支持按需求编号、计划生产排期及需求受理人筛选）")
    parser.add_argument("args", nargs="+", help="需求编号列表（如 R2604300028）、计划生产排期日期（如 20260807）或需求受理人（如 吴进）")
    parser.add_argument("--plan_date", default=None, help="显式按计划生产排期日期筛选（如 2026-08-07）")
    parser.add_argument("--receiver", default=None, help="显式按需求受理人筛选（如 吴进）")
    parser.add_argument("--output_html", default=None, help="生成的 HTML 表格路径 (默认按输入参数自动生成动态文件名)")
    parser.add_argument("--output_md", default=None, help="如需要输出 MD 路径可指定")
    parser.add_argument("--project", default="交易结算核心历史数据及接口迁移项目", help="项目名称")
    parser.add_argument("--all", action="store_true", help="显示全量 Story 与需求（取消过滤模式）")
    parser.add_argument("--only_risk", action="store_true", default=True, help="仅显示存在临近到期或已逾期的 Story 及需求（默认生效）")
    parsed_args = parser.parse_args()

    only_risk = not parsed_args.all
    script_dir = os.path.dirname(os.path.abspath(__file__))
    load_external_config(script_dir)

    matched_plan_date = parsed_args.plan_date
    matched_receiver = parsed_args.receiver
    direct_demand_ids = []

    for item in parsed_args.args:
        clean_item = item.replace("-", "").strip()
        if len(clean_item) == 8 and clean_item.isdigit() and (clean_item.startswith("202") or clean_item.startswith("203")):
            matched_plan_date = item
        elif item.startswith("R") or item.startswith("PG"):
            direct_demand_ids.append(item)
        else:
            matched_receiver = item

    input_demand_ids = list(direct_demand_ids)

    # 针对单一姓名输入（如 吴进），无指定日期与需求ID时：自动定位 >= 当前日期的最近3个版本 (由小到大)，合并输出至单个文件《需求明细风险提醒表<当前日期>-<姓名>.html》
    if matched_receiver and not matched_plan_date and not direct_demand_ids:
        current_date_str = CURRENT_DATE_STR
        current_date_compact = current_date_str.replace("-", "").strip()
        cache_data, _ = get_indexed_cache(script_dir)
        
        dates_set = set()
        for r in cache_data:
            rec = r.get("demandReceiver", "")
            p_date = clean_date_str(r.get("planProdLineDate"))
            if matched_receiver in rec and p_date != "--" and p_date >= current_date_str:
                dates_set.add(p_date)

        top3_dates = sorted(list(dates_set))[:3]
        if not top3_dates:
            print(f"[DetailedSchedule] 未匹配到受理人 【{matched_receiver}】 当前及未来的计划生产排期。")
            return

        print(f"[DetailedSchedule] 检测到姓名输入 【{matched_receiver}】，自动定位 >= 当前日期 ({current_date_str}) 的最近 3 个版本 (由小到大): {top3_dates}")
        
        all_unique_demands = []
        for p_date in top3_dates:
            d_list = find_demands_by_plan_date(p_date, script_dir, receiver=matched_receiver)
            for d in d_list:
                if d not in all_unique_demands:
                    all_unique_demands.append(d)

        demands_dict = load_demand_data_from_cache(all_unique_demands, script_dir)
        data_list = [demands_dict[did] for did in all_unique_demands if did in demands_dict]

        # 按计划生产排期由小到大升序排序
        data_list.sort(key=lambda x: x.get("plan_prod_date", "9999-99-99"))

        output_html = f"需求明细风险提醒表{current_date_compact}-{matched_receiver}.html"
        p_title = f"{parsed_args.project} (需求受理人: {matched_receiver}, 最近3个版本: {', '.join(top3_dates)})"
        
        # 姓名查询合并多版本模式：展示 计划生产排期 列 (show_plan_date_col=True)
        generate_html(data_list, output_html, p_title, only_risk=only_risk, show_plan_date_col=True)
        if parsed_args.output_md:
            generate_markdown(data_list, parsed_args.output_md, p_title, only_risk=only_risk, show_plan_date_col=True)
        return

    if matched_plan_date:
        demands = find_demands_by_plan_date(matched_plan_date, script_dir, receiver=matched_receiver)
        rec_info = f", 需求受理人: {matched_receiver}" if matched_receiver else ""
        print(f"[DetailedSchedule] 按计划生产排期 【{matched_plan_date}】{rec_info} 在大宽表中筛选到 {len(demands)} 个匹配需求: {demands}")
        input_demand_ids.extend(demands)

    unique_demand_ids = []
    for d in input_demand_ids:
        if d not in unique_demand_ids:
            unique_demand_ids.append(d)

    if not unique_demand_ids:
        print("[DetailedSchedule] 未匹配到任何需求，退出生成。")
        return

    demands_dict = load_demand_data_from_cache(unique_demand_ids, script_dir)
    
    data_list = []
    for d_id in unique_demand_ids:
        if d_id in demands_dict:
            data_list.append(demands_dict[d_id])
        else:
            data_list.append({
                "demand_id": d_id,
                "title": "",
                "subtitle": DEMAND_SUBTITLE_MAP.get(d_id, ""),
                "stories": []
            })

    output_html = parsed_args.output_html
    if not output_html:
        if matched_plan_date and matched_receiver:
            clean_date = matched_plan_date.replace("-", "").strip()
            output_html = f"需求明细风险提醒表{clean_date}-{matched_receiver}.html"
        elif matched_plan_date:
            clean_date = matched_plan_date.replace("-", "").strip()
            output_html = f"需求明细风险提醒表{clean_date}.html"
        elif direct_demand_ids:
            if len(direct_demand_ids) == 1:
                output_html = f"需求明细风险提醒表{direct_demand_ids[0]}.html"
            else:
                output_html = "需求明细风险提醒表.html"
        else:
            output_html = "需求明细风险提醒表.html"

    project_title = parsed_args.project
    title_suffix = []
    if matched_plan_date:
        title_suffix.append(f"排期: {matched_plan_date}")
    if matched_receiver:
        title_suffix.append(f"需求受理人: {matched_receiver}")
    if title_suffix:
        project_title += f" ({', '.join(title_suffix)})"

    # 单一排期版本/指定排期查询模式：隐去 计划生产排期 该列 (show_plan_date_col=False)
    generate_html(data_list, output_html, project_title, only_risk=only_risk, show_plan_date_col=False)
    
    if parsed_args.output_md:
        generate_markdown(data_list, parsed_args.output_md, project_title, only_risk=only_risk, show_plan_date_col=False)

if __name__ == "__main__":
    main()
