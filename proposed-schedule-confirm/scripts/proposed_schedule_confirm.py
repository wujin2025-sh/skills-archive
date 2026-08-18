#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
proposed_schedule_confirm.py — 拟排期确认工具（极速高性能版）
=============================================================================
根据输入的排期版本号（如 20260821 或 2026-08-21），筛选受理人含“吴进”（或指定受理人）的需求及 Story 明细，
生成用于发送给测试同事核对进度风险的高颜值 HTML 确认表。

特性：
- 优先通过后台 API 实时同步大宽表最新数据，刷新本地缓存 .table_cache.json。
- 包含了 13 大核心字段。
- 支持【发邮件/存草稿】功能：一键自动从确认表中提取开发负责人、SIT负责人、UAT负责人、业务验收人等相关人员。
- 用户触发“发邮件”指令时，**默认存入 Coremail 邮件草稿箱**，以便人工审核后手动点击发送；仅在显式传入 --force-send 时才直接发送。

包含字段 (共 13 列)：
1. 史诗编号 (epicCode / epicConcat - 支持相同单元格合并 rowspan)
2. 需求编号 (demandId - 支持相同单元格合并 rowspan)
3. story编号 (storyCode)
4. 任务名称 (storyTitle)
5. 涉及系统 (storySystemName)
6. 当前状态 (storyStatusName / demandStatus - 不含生产的SIT未完成状态突出标识 🚨，含生产的无风险)
7. 开发负责人 (devManagePerson)
8. SIT负责人 (sitTestManagePerson)
9. UAT负责人 (uatTestManagePerson)
10. 业务验收人 (businessAcceptor / storyBusName)
11. 重点关注 (keyFocus)
12. 影响灰度 (isEffectGrayUpgrade - 需求影响灰度升级)
13. 备注 (beizhuText)

排序与合并规则：
1. 按【重点关注】优先排序，重点关注在最上方。
2. 排序 key: (is_key_focus DESC, epic_code ASC, demand_id ASC, story_code ASC)。
3. 连续相同【史诗编号】和【需求编号】自动在 HTML 中应用 rowspan 单元格合并。
"""

import sys
import os
import re
import json
import argparse
import subprocess
import requests
from datetime import datetime

# 动态获取系统当前日期
CURRENT_NOW = datetime.now()
CURRENT_DATE_STR = CURRENT_NOW.strftime("%Y-%m-%d")
CURRENT_TIME_STR = CURRENT_NOW.strftime("%Y-%m-%d %H:%M:%S")

# 常用已知邮箱映射表
KNOWN_EMAIL_MAP = {
    "周倩": "zhouqian4@gtht.com", "刘勇明": "liuyongming@gtht.com", "胡玲杰": "hulingjie@gtht.com",
    "乔露露": "qiaolulu@gtht.com", "聂章艳": "niezhangyan@gtht.com", "李萍萍": "lipingping@gtht.com",
    "刘青": "liuqing5@gtht.com", "丁伟": "dingwei2@gtht.com", "罗琼": "luoqiong@gtht.com",
    "高健": "gaojian2@gtht.com", "常丽": "changli@gtht.com", "李正林": "lizhenglin@gtht.com",
    "揭由翔": "jieyouxiang@gtht.com", "黄星": "huangxing@gtht.com", "张志鹏": "zhangzhipeng@gtht.com",
    "单大卫": "shandawei@gtht.com", "程恩惠": "chengenhui@gtht.com", "瞿格": "quge@gtht.com",
    "王冰冰": "wangbingbing@gtht.com", "李庆辉": "liqinghui@gtht.com", "甘峰浩": "ganfenghao@gtht.com",
    "吴亚如": "wuyaru@gtht.com", "柴恒": "chaiheng@gtht.com", "杜军辉": "dujunhui@gtht.com",
    "张兆国": "zhangzhaoguo@gtht.com", "刘辉": "liuhui7@gtht.com", "苏清玲": "suqingling@gtht.com",
    "茆莹莹": "maoyingying@gtht.com", "刘璐": "liulu@gtht.com", "季金燕": "jijinyan@gtht.com",
    "樊静宜": "fanjingyi@gtht.com", "李楷达": "likaida@gtht.com", "张帆": "zhangfan4@gtht.com",
    "唐登龙": "tangdenglong@gtht.com", "谢一凡": "xieyifan@gtht.com", "朱腾龙": "zhutenglong@gtht.com",
    "沈芳": "shenfang@gtht.com", "杨晨旭": "yangchenxu@gtht.com", "俞梦妮": "yumengni@gtht.com",
    "邵从人": "shaocongren@gtht.com", "卢霖铨": "lulinquan@gtht.com", "钱幼文": "qianyouwen@gtht.com",
    "王壮壮": "wangzhuangzhuang@gtht.com", "符振威": "fuzhenwei@gtht.com", "刘牧青": "liumuqing@gtht.com",
    "鄂泓希": "ehongxi@gtht.com", "郑波": "zhengbo2@gtht.com", "倪康夫": "nikangfu@gtht.com",
    "刘栋梁": "liudongliang@gtht.com", "史亮": "shiliang@gtht.com", "陈喆": "chenzhe4@gtht.com",
    "帅翔": "shuaixiang@gtht.com", "刘灿彬": "liucanbin@gtht.com", "徐嫦悦": "xuchangyue@gtht.com",
    "徐适": "xushi@gtht.com", "毕钰东方": "biyudongfang@gtht.com", "张元超": "zhangyuanchao@gtht.com",
    "史安妮": "shianni@gtht.com", "刘琼": "liuqiong3@gtht.com", "张之泽": "zhangzhize@gtht.com",
    "谢越": "xieyue2@gtht.com", "龚燕萍": "gongyanping@gtht.com", "李鹤晨": "lihechen@gtht.com",
    "宋健": "songjian2@gtht.com", "吴进": "wujin@gtht.com", "牛婷婷": "niutingting@gtht.com",
    "张康": "zhangkang2@gtht.com", "陈曦": "chenxi10@gtht.com", "潘首道": "panshoudao@gtht.com",
    "孙丽荣": "sunlirong@gtht.com", "王南图": "wangnantu@gtht.com", "虞聪": "yucong@gtht.com",
    "冯通": "fengtong@gtht.com", "侯英祺": "houyingqi@gtht.com", "陈安童": "chenantong@gtht.com",
    "叶飞": "yefei@gtht.com", "施晔": "shiye@gtht.com", "孙锴": "sunkai4@gtht.com",
    "程菲": "chengfei@gtht.com", "厉凌杰": "lilingjie@gtht.com", "孟子煜": "mengziyu@gtht.com",
    "刘慧雨": "liuhuiyu@gtht.com", "吕正仪": "lvzhengyi@gtht.com", "徐旖旎": "xuyini@gtht.com",
    "金渤文": "jinbowen@gtht.com", "姚永振": "yaoyongzhen@gtht.com", "曾娟": "zengjuan@gtht.com",
    "徐德亮": "xudeliang@gtht.com", "倪梦思": "nimengsi@gtht.com", "宁秀芳": "ningxiufang@gtht.com",
    "郭洋": "guoyang@gtht.com", "杜伟毅": "duweiyi@gtht.com", "孙驰": "sunchi@gtht.com",
    "张智舒": "zhangzhishu@gtht.com", "童国豪": "tongguohao@gtht.com", "孙明红": "sunminghong@gtht.com",
    "王恒": "wangheng@gtht.com", "周静": "zhoujing@gtht.com", "齐伟华": "qiweihua@gtht.com",
    "郭筱玮": "guoxiaowei@gtht.com", "石雪军": "shixuejun@gtht.com", "龚子慧": "gongzihui@gtht.com",
    "李卓远": "lizhuoyuan@gtht.com", "李彦丽": "liyanli@gtht.com", "罗海洪": "luohaihong@gtht.com",
    "解娅宁": "xieyaning@gtht.com", "崔敦良": "cuidunliang@gtht.com", "范秀萍": "fanxiuping@gtht.com",
    "王岗": "wanggang@gtht.com", "陈紫菡": "chenzihan@gtht.com", "肖慧": "xiaohui@gtht.com",
    "薛天明": "xuetianming@gtht.com", "马晓鑫": "maxiaoxin@gtht.com", "周尤珠": "zhouyouzhu@gtht.com"
}

def clean_date_str(d_str):
    """规范化日期字符串格式 YYYY-MM-DD"""
    if not d_str or str(d_str).strip() in ("", "-", "--", "None", "null"):
        return "--"
    d_clean = str(d_str).strip()
    if len(d_clean) == 8 and d_clean.isdigit():
        return f"{d_clean[:4]}-{d_clean[4:6]}-{d_clean[6:]}"
    if len(d_clean) >= 10 and d_clean[4] == "-" and d_clean[7] == "-":
        return d_clean[:10]
    return d_clean

def parse_owner(raw_owner):
    """格式化负责人姓名，如 '吴进-125360' -> '吴进'"""
    if not raw_owner or str(raw_owner).strip() in ("", "-", "--", "None", "null"):
        return "--"
    raw = str(raw_owner).strip()
    if "-" in raw:
        return raw.split("-")[0].strip()
    return raw

def clean_story_name(story_code, story_title):
    """清理 Story 标题冗余前缀"""
    title = str(story_title or "").strip()
    if not title:
        return f"Story ({story_code})"
    return title

def clean_remark(raw_remark):
    """格式化备注信息"""
    if not raw_remark or str(raw_remark).strip() in ("", "-", "--", "None", "null"):
        return "--"
    return str(raw_remark).strip()

def clean_gray_upgrade(raw_val):
    """格式化影响灰度升级值"""
    if not raw_val or str(raw_val).strip() in ("", "-", "--", "None", "null"):
        return "--"
    val = str(raw_val).strip()
    return val

def is_sit_risk_status(status_str):
    """
    判断当前状态是否属于 SIT 进度风险状态。
    规则（用户明确指定）：
    - 含“生产”（如 SIT生产测试待排期、待SIT生产测试）-> 无风险
    - 已完成/已结束/已上线/已终止 -> 无风险
    - 不含“生产”的 SIT 未完成状态（如 SIT测试待排期、待SIT测试、待SIT大远期自测、SIT大远期自测中、SIT大远期打包）-> 存在进度风险 (🚨)
    """
    st = str(status_str or "").strip()
    if not st or st == "--":
        return False
        
    # 含“生产”无风险
    if "生产" in st:
        return False

    # 已完成/已上线/已结束/已终止无风险
    if any(k in st for k in ("完成", "结束", "已上线", "已发布", "已终止", "终止")):
        return False

    # 包含 SIT 且不含生产，未完成者 -> 存在进度风险
    if "SIT" in st or "sit" in st.lower():
        return True

    return False

def get_badge_class(status_str):
    """根据状态生成徽章 CSS 类名"""
    st = str(status_str or "").strip()
    if is_sit_risk_status(st):
        return "badge-sit-risk"
    elif any(k in st for k in ("完成", "结束", "已上线", "已发布")):
        return "badge-done"
    elif any(k in st for k in ("测试中", "自测中", "进行中", "开发中")):
        return "badge-progress"
    elif any(k in st for k in ("待", "未排期", "排期")):
        return "badge-warning"
    elif "终止" in st:
        return "badge-terminated"
    else:
        return "badge-normal"

def find_cache_file(script_dir):
    """寻找大宽表缓存文件 .table_cache.json"""
    candidates = [
        os.path.join(os.getcwd(), ".table_cache.json"),
        os.path.join(script_dir, ".table_cache.json"),
        os.path.join(os.path.dirname(script_dir), ".table_cache.json"),
        "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.table_cache.json"
    ]
    for cp in candidates:
        if os.path.exists(cp):
            return cp
    return candidates[-1]

def load_data_from_cache(cache_path):
    """从缓存读取 JSON 数据"""
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ [Cache Error] 读取缓存失败: {e}")
        return []

def update_and_load_data(script_dir):
    """
    在线实时拉取最新大宽表数据，并更新本地 .table_cache.json 缓存。
    如果拉取失败，退回读取本地缓存。
    """
    cache_path = find_cache_file(script_dir)
    session_file = "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.fintech_session.json"
    
    # 1. 尝试在线 API 获取最新数据
    if os.path.exists(session_file):
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
                
            cookies = {}
            for c in session_data.get("cookies", []):
                if 'gtht.com.cn' in c.get('domain', ''):
                    cookies[c["name"]] = c["value"]
                
            token = None
            for origin_data in session_data.get("origins", []):
                if origin_data.get("origin") == "https://fintech.gtht.com.cn":
                    for item in origin_data.get("localStorage", []):
                        if item.get("name") == "GTJA_TOKEN":
                            token = item.get("value")
                            break
                            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://fintech.gtht.com.cn/kjpt/OnlineGrid?tableId=1597051499572236288",
                "accept": "application/json",
                "content-type": "application/json",
            }
            if token:
                headers["token"] = token
                
            CONTENT_URL = "https://fintech.gtht.com.cn/api/table-service/table/row/getSheetContent?sheetId=1597051509256884224"
            r = requests.get(CONTENT_URL, cookies=cookies, headers=headers, timeout=60)
            if r.status_code == 200:
                resp_json = r.json()
                if resp_json.get("code") == 200:
                    raw_d = resp_json.get("data")
                    if isinstance(raw_d, dict):
                        rows = raw_d.get("data", [])
                    elif isinstance(raw_d, list):
                        rows = raw_d
                    else:
                        rows = []
                    
                    if rows:
                        # 成功拉取最新数据，同步刷新本地缓存
                        if cache_path:
                            try:
                                with open(cache_path, 'w', encoding='utf-8') as cf:
                                    json.dump(rows, cf, ensure_ascii=False, indent=2)
                                print(f"[ProposedSchedule] 🔄 已成功在线同步大宽表最新数据 ({len(rows)} 条)，并已刷新本地缓存！")
                            except Exception as ew:
                                print(f"[ProposedSchedule] ⚠️ 缓存更新异常: {ew}")
                        return rows
        except Exception as e:
            print(f"[ProposedSchedule] 💡 实时 API 拉取完成或跳过，准备读取本地最新缓存: {e}")

    # 2. 读取本地缓存兜底
    if cache_path and os.path.exists(cache_path):
        return load_data_from_cache(cache_path)
    return []

def filter_and_format_stories(raw_records, target_version, receiver="吴进"):
    """
    根据目标版本号和受理人筛选并整理 Story 数据
    """
    clean_ver = target_version.replace("-", "").strip()
    if len(clean_ver) == 8 and clean_ver.isdigit():
        norm_ver_date = f"{clean_ver[:4]}-{clean_ver[4:6]}-{clean_ver[6:]}"
        compact_ver_date = clean_ver
    else:
        norm_ver_date = target_version
        compact_ver_date = clean_ver

    filtered_items = []
    
    for r in raw_records:
        rec = str(r.get("demandReceiver") or "").strip()
        p_date = clean_date_str(r.get("planProdLineDate"))
        
        # 受理人匹配
        receiver_match = (not receiver) or (receiver in rec)
        
        # 排期版本匹配
        date_match = False
        if p_date != "--":
            p_date_compact = p_date.replace("-", "")
            if p_date == norm_ver_date or p_date_compact == compact_ver_date:
                date_match = True
        
        if receiver_match and date_match:
            epic_code = str(r.get("epicCode") or r.get("epicConcat") or "--").strip()
            if not epic_code or epic_code == "None":
                epic_code = "--"
                
            demand_id = str(r.get("demandId") or "--").strip()
            story_code = str(r.get("storyCode") or r.get("storyNo") or "--").strip()
            story_title = clean_story_name(story_code, r.get("storyTitle"))
            system_name = str(r.get("storySystemName") or "--").strip()
            status_name = str(r.get("storyStatusName") or r.get("demandStatus") or "--").strip()
            dev_owner = parse_owner(r.get("devManagePerson"))
            sit_owner = parse_owner(r.get("sitTestManagePerson"))
            uat_owner = parse_owner(r.get("uatTestManagePerson"))
            bus_owner = parse_owner(r.get("businessAcceptor") or r.get("storyBusName"))
            key_focus = str(r.get("keyFocus") or "--").strip()
            effect_gray = clean_gray_upgrade(r.get("isEffectGrayUpgrade"))
            remark = clean_remark(r.get("beizhuText") or r.get("remark"))
            plan_prod_date = p_date

            item = {
                "epic_code": epic_code,
                "demand_id": demand_id,
                "story_code": story_code,
                "story_title": story_title,
                "system_name": system_name,
                "status_name": status_name,
                "dev_owner": dev_owner,
                "sit_owner": sit_owner,
                "uat_owner": uat_owner,
                "bus_owner": bus_owner,
                "key_focus": key_focus,
                "is_key_focus": (key_focus == "是"),
                "effect_gray": effect_gray,
                "is_sit_risk": is_sit_risk_status(status_name),
                "remark": remark,
                "plan_prod_date": plan_prod_date,
                "receiver": rec
            }
            filtered_items.append(item)

    # 重点关注在最上面排序 (keyFocus == '是' 优先)，且 Epic 编号、Demand 编号升序，方便合并单元格
    filtered_items.sort(key=lambda x: (0 if x["is_key_focus"] else 1, x["epic_code"], x["demand_id"], x["story_code"]))
    
    return filtered_items

def extract_table_recipients(items, version_str="", receiver_str="", is_reviewed=False):
    """
    自动提取确认表上所有有效相关人员（开发负责人、SIT负责人、UAT负责人、业务验收人），
    解析并生成 Coremail 格式的标准收件人列表字符串。固定包含：肖慧、刘青、乔露露、常丽、张帆、茆莹莹、张志鹏、薛天明、马晓鑫、李鹤晨、周尤珠。
    若为 -r 模式，会自动读取此前初版确认表的人员名单缓存并自动 Merge，保持收件人完全一致。
    """
    unique_names = {"肖慧", "刘青", "乔露露", "常丽", "张帆", "茆莹莹", "张志鹏", "薛天明", "马晓鑫", "李鹤晨", "周尤珠"}
    invalid_tokens = {"--", "无需业务验收", "None", "null", "", "无"}
    
    for item in items:
        for field in ["dev_owner", "sit_owner", "uat_owner", "bus_owner"]:
            name = item.get(field)
            if name and str(name).strip() not in invalid_tokens:
                unique_names.add(str(name).strip())

    clean_ver = str(version_str).replace("-", "").strip()
    clean_rec = str(receiver_str).strip()
    cache_dir = os.path.dirname(os.path.abspath(__file__))
    recipients_cache_file = os.path.join(cache_dir, f".recipients_{clean_ver}_{clean_rec}.json")

    # 若为 -r 模式，尝试合并初版确认表的人员名单
    if is_reviewed and os.path.exists(recipients_cache_file):
        try:
            with open(recipients_cache_file, "r", encoding="utf-8") as f:
                cached_names = json.load(f)
                if isinstance(cached_names, list):
                    for n in cached_names:
                        if n and str(n).strip() not in invalid_tokens:
                            unique_names.add(str(n).strip())
        except Exception:
            pass
    elif not is_reviewed and clean_ver:
        # 初版确认表模式：将当前收件人持久化缓存起来，供后续 -r 模式继承
        try:
            with open(recipients_cache_file, "w", encoding="utf-8") as f:
                json.dump(sorted(list(unique_names)), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    recipients_list = []
    for name in sorted(list(unique_names)):
        if name in KNOWN_EMAIL_MAP:
            recipients_list.append(f'"{name}" <{KNOWN_EMAIL_MAP[name]}>')
        else:
            try:
                from pypinyin import lazy_pinyin
                pinyin_name = "".join(lazy_pinyin(name)).lower()
                recipients_list.append(f'"{name}" <{pinyin_name}@gtht.com>')
            except ImportError:
                recipients_list.append(f'"{name}" <{name}@gtht.com>')
                
    return recipients_list

def extract_current_status_owners(items):
    """
    只提取未完成/未结束状态对应的负责人。
    规则：
    1. 若状态属于已结束/已完成/已上线/已终止等完成状态 -> 跳过，不需要 @ 负责人
    2. 若状态包含 "SIT" -> 抓取 sit_owner
    3. 若状态包含 "UAT" -> 抓取 uat_owner
    4. 若状态包含 "业务" 或 "验收" -> 抓取 bus_owner
    5. 其它开发相关状态（如 待开发、开发中等） -> 抓取 dev_owner
    """
    status_owners = set()
    invalid_tokens = {"--", "无需业务验收", "None", "null", "", "无"}
    ended_keywords = ("已结束", "已完成", "已上线", "已发布", "已终止", "已关闭", "结束", "完成", "终止", "关闭")
    
    for item in items:
        st = str(item.get("status_name", "")).strip()
        st_upper = st.upper()

        # 对于已结束/已完成等结束状态，不需要 @ 负责人
        if any(k in st for k in ended_keywords):
            continue

        target_owner = ""
        if "SIT" in st_upper:
            target_owner = item.get("sit_owner")
        elif "UAT" in st_upper:
            target_owner = item.get("uat_owner")
        elif "业务" in st or "验收" in st:
            target_owner = item.get("bus_owner")
        else:
            target_owner = item.get("dev_owner")
            
        if target_owner and str(target_owner).strip() not in invalid_tokens:
            status_owners.add(str(target_owner).strip())
            
    return sorted(list(status_owners))

def generate_reminder_html(items, version_str="", is_reviewed=False):
    """
    生成排期提醒 Block HTML（仅用于邮件正文底部）
    包含：📢 当前状态对应负责人 及 💬 下班前确认提醒 / 沟通确认提醒
    """
    status_owners = extract_current_status_owners(items)
    at_mentions_str = " ".join([f"@{name}" for name in status_owners]) if status_owners else "相关状态负责人"
    
    clean_ver = str(version_str).replace("-", "").strip()
    short_ver = clean_ver[-4:] if len(clean_ver) == 8 and clean_ver.isdigit() else version_str

    if is_reviewed:
        prompt_text = f"💬 以上清单为经过与业务、测试老师沟通反馈后的拟计划{short_ver}版本需求明细，请各位老师知悉。对于调出的需求也请测试老师尽快安排测试，以期在下个版本可以上线。如对排期有任何疑问或变动，烦请及时告知，辛苦大家！"
    else:
        prompt_text = "💬 麻烦各位老师在今天下班前帮忙确认一下相关需求是否可以顺利排入当前版本。<br>如评估后存在无法排入或延期风险，烦请及时告知，以便我们提前协调并安排调整至后续版本。辛苦大家！"

    return f"""<div style="margin: 20px 32px 32px 32px; padding: 20px 24px; background-color: #fffbe6; border: 1px solid #ffe58f; border-radius: 10px; font-size: 13px; line-height: 1.8;">
  <div style="font-weight: 700; font-size: 14px; color: #d48806; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
    <span>📢 当前状态对应负责人：</span>
  </div>
  <div style="font-weight: 600; color: #1d4ed8; margin-bottom: 12px; word-break: break-all; line-height: 1.8;">
    {at_mentions_str}
  </div>
  <div style="color: #1f2937; font-size: 14px; font-weight: 600; background-color: #ffffff; padding: 12px 16px; border-radius: 6px; border-left: 4px solid #f59e0b; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
    {prompt_text}
  </div>
</div>"""

def send_confirmation_email(html_path, version_str, receiver_str, items, is_send=False, is_reviewed=False):
    """
    调用 Coremail 通用发送脚本，将 HTML 确认表存草稿箱（默认 is_send=False）供人工审核，或直接发送 (is_send=True)
    """
    recipients_list = extract_table_recipients(items, version_str=version_str, receiver_str=receiver_str, is_reviewed=is_reviewed)
    if not recipients_list:
        print("⚠️ [Email] 确认表中未识别到有效相关人员，无法起草邮件。")
        return False
        
    recipients_str = "; ".join(recipients_list)
    subject_prefix = "拟排期需求明细清单" if is_reviewed else "拟排期需求确认表"
    subject = f"{subject_prefix} ({version_str} - {receiver_str})"
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_script = os.path.join(script_dir, "save_to_draft.py")
    fallback_script = "/Users/wujin/.workbuddy/skills/svn-merge/scripts/save_to_draft.py"
    script_path = local_script if os.path.exists(local_script) else fallback_script
    if not os.path.exists(script_path):
        print(f"❌ [Email Error] 未找到 Coremail 邮件处理脚本 {script_path}")
        return False

    action_label = "发送邮件" if is_send else "存入 Coremail 草稿箱"
    print(f"[Email] 📧 正在准备为 {len(recipients_list)} 位确认人员{action_label}...")
    print(f"        📌 主题: {subject}")
    print(f"        👥 收件人: {recipients_str[:120]}...")

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    reminder_html = generate_reminder_html(items, version_str=version_str, is_reviewed=is_reviewed)
    email_body_content = html_content + "\n<br>\n" + reminder_html

    email_body_path = os.path.join(os.path.dirname(os.path.abspath(html_path)), f".email_body_{os.path.basename(html_path)}")
    with open(email_body_path, "w", encoding="utf-8") as f:
        f.write(email_body_content)

    cmd = [
        "python3", script_path,
        "--subject", subject,
        "--body-file", email_body_path,
        "--recipients", recipients_str,
        "--attachments", os.path.abspath(html_path)
    ]
    if is_send:
        cmd.append("--send")

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(res.stdout)
        if is_send:
            print("[Email] ✅ 邮件已成功发送！")
        else:
            print("[Email] 💾 确认表邮件已成功存入 Coremail 草稿箱！请登录邮箱人工确认后发送。")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ [Email Error] {action_label}失败: {e.stderr or e.stdout or e}")
        return False
    finally:
        if os.path.exists(email_body_path):
            try:
                os.remove(email_body_path)
            except Exception:
                pass

def calculate_spans(items):
    """
    计算相同 Epic 编号与 Demand 编号的连续跨行数 (rowspan)
    """
    n = len(items)
    epic_spans = [0] * n
    demand_spans = [0] * n
    
    # 1. 计算 Epic Code 跨行数
    i = 0
    while i < n:
        j = i
        while (j < n and 
               items[j]["is_key_focus"] == items[i]["is_key_focus"] and 
               items[j]["epic_code"] == items[i]["epic_code"]):
            j += 1
        epic_spans[i] = j - i
        i = j

    # 2. 计算 Demand ID 跨行数
    i = 0
    while i < n:
        j = i
        while (j < n and 
               items[j]["is_key_focus"] == items[i]["is_key_focus"] and 
               items[j]["epic_code"] == items[i]["epic_code"] and 
               items[j]["demand_id"] == items[i]["demand_id"]):
            j += 1
        demand_spans[i] = j - i
        i = j
        
    return epic_spans, demand_spans

def generate_html(items, output_path, version_str, receiver_str, is_reviewed=False):
    """
    生成高颜值 HTML 确认表 (含 开发负责人 列，带 Epic 与 Demand 单元格合并)
    """
    total_count = len(items)
    key_focus_count = sum(1 for x in items if x["is_key_focus"])
    sit_risk_count = sum(1 for x in items if x["is_sit_risk"])
    systems = sorted(list(set(x["system_name"] for x in items if x["system_name"] != "--")))
    demands_count = len(set(x["demand_id"] for x in items if x["demand_id"] != "--"))
    epic_spans, demand_spans = calculate_spans(items)

    title_text = f"拟排期需求明细清单 ({version_str} - {receiver_str})" if is_reviewed else f"拟排期需求确认表 ({version_str} - {receiver_str})"
    banner_title = "📋 拟排期需求明细清单" if is_reviewed else "📋 拟排期需求确认表"

    rows_html = []
    for idx, item in enumerate(items):
        tr_class = "row-key-focus" if item["is_key_focus"] else ("row-even" if idx % 2 == 0 else "row-odd")
        
        # 重点关注徽章
        if item["is_key_focus"]:
            kf_badge = '<span class="badge badge-key-focus">🔥 是</span>'
        elif item["key_focus"] == "否":
            kf_badge = '<span class="badge badge-gray">否</span>'
        else:
            kf_badge = f'<span class="badge badge-gray">{item["key_focus"]}</span>'
            
        # 影响灰度徽章
        if item["effect_gray"] == "是":
            gray_badge = '<span class="badge badge-purple">⚡ 是</span>'
        elif item["effect_gray"] == "否":
            gray_badge = '<span class="badge badge-gray">否</span>'
        else:
            gray_badge = f'<span class="badge badge-gray">{item["effect_gray"]}</span>'

        # 状态徽章（对不含生产的 SIT 未完成风险状态突出标注 🚨）
        if item["is_sit_risk"]:
            status_badge = f'<span class="badge badge-sit-risk">🚨 {item["status_name"]}</span>'
        else:
            status_badge = f'<span class="badge {get_badge_class(item["status_name"])}">{item["status_name"]}</span>'
        
        # 负责人显示
        dev_disp = f'<strong>{item["dev_owner"]}</strong>' if item["dev_owner"] != "--" else '<span class="text-muted">--</span>'
        sit_disp = f'<strong>{item["sit_owner"]}</strong>' if item["sit_owner"] != "--" else '<span class="text-muted">--</span>'
        uat_disp = f'<strong>{item["uat_owner"]}</strong>' if item["uat_owner"] != "--" else '<span class="text-muted">--</span>'
        bus_disp = f'<strong>{item["bus_owner"]}</strong>' if item["bus_owner"] != "--" else '<span class="text-muted">--</span>'

        # 单元格合并逻辑
        epic_td = ""
        if epic_spans[idx] > 0:
            rowspan_attr = f' rowspan="{epic_spans[idx]}"' if epic_spans[idx] > 1 else ""
            epic_td = f'<td{rowspan_attr} class="text-center font-mono cell-merged">{item["epic_code"]}</td>'

        demand_td = ""
        if demand_spans[idx] > 0:
            rowspan_attr = f' rowspan="{demand_spans[idx]}"' if demand_spans[idx] > 1 else ""
            demand_td = f'<td{rowspan_attr} class="text-center font-bold text-blue cell-merged">{item["demand_id"]}</td>'

        remark_disp = item["remark"] if item["remark"] != "--" else '<span class="text-muted">--</span>'

        row = f"""
      <tr class="{tr_class}">
        {epic_td}
        {demand_td}
        <td class="text-center font-mono font-semibold">{item["story_code"]}</td>
        <td class="story-title-col">{item["story_title"]}</td>
        <td class="text-center"><span class="system-tag">{item["system_name"]}</span></td>
        <td class="text-center">{status_badge}</td>
        <td class="text-center">{dev_disp}</td>
        <td class="text-center">{sit_disp}</td>
        <td class="text-center">{uat_disp}</td>
        <td class="text-center">{bus_disp}</td>
        <td class="text-center">{kf_badge}</td>
        <td class="text-center">{gray_badge}</td>
        <td class="remark-col">{remark_disp}</td>
      </tr>"""
        rows_html.append(row)

    if not rows_html:
        empty_row = f"""
      <tr>
        <td colspan="13" class="empty-cell">
          <div class="empty-state">
            <span class="empty-icon">🔍</span>
            <p>未查找到排期版本为 <strong>{version_str}</strong> 且受理人包含 <strong>{receiver_str}</strong> 的需求/Story数据。</p>
          </div>
        </td>
      </tr>"""
        rows_html.append(empty_row)

    html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title_text}</title>
<style>
  * {{
    box-sizing: border-box;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif;
    background-color: #f8fafc;
    color: #1e293b;
    margin: 0;
    padding: 24px;
  }}
  .container {{
    max-width: 1600px;
    margin: 0 auto;
    background: #ffffff;
    border-radius: 12px;
    box-shadow: 0 10px 25px -5px rgba(0,0,0,0.05), 0 8px 10px -6px rgba(0,0,0,0.01);
    border: 1px solid #e2e8f0;
    overflow: hidden;
  }}
  .header-banner {{
    background: linear-gradient(135deg, #1e3a8a 0%, #1d4ed8 50%, #2563eb 100%);
    color: #ffffff;
    padding: 24px 32px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 16px;
  }}
  .header-banner h2 {{
    margin: 0;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.5px;
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  .header-meta {{
    font-size: 13px;
    color: #93c5fd;
    display: flex;
    gap: 16px;
    align-items: center;
  }}
  .header-meta span {{
    background: rgba(255, 255, 255, 0.15);
    padding: 4px 12px;
    border-radius: 6px;
    backdrop-filter: blur(4px);
    color: #ffffff;
    font-weight: 500;
  }}
  .stat-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    padding: 20px 32px;
    background-color: #f1f5f9;
    border-bottom: 1px solid #e2e8f0;
  }}
  .stat-card {{
    background: #ffffff;
    padding: 16px 20px;
    border-radius: 8px;
    border: 1px solid #cbd5e1;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }}
  .stat-label {{
    font-size: 12px;
    color: #64748b;
    font-weight: 600;
  }}
  .stat-value {{
    font-size: 22px;
    font-weight: 800;
    color: #0f172a;
  }}
  .stat-value.highlight {{
    color: #c2410c;
  }}
  .stat-value.risk-highlight {{
    color: #dc2626;
  }}
  .table-wrapper {{
    overflow-x: auto;
    padding: 0;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    font-size: 13px;
    text-align: left;
  }}
  thead tr {{
    background-color: #1e40af;
    color: #ffffff;
  }}
  thead th {{
    padding: 12px 10px;
    font-weight: 700;
    font-size: 13px;
    border: 1px solid #1d4ed8;
    white-space: nowrap;
    text-align: center;
  }}
  td {{
    padding: 10px 10px;
    border: 1px solid #cbd5e1;
    color: #334155;
    vertical-align: middle;
  }}
  .cell-merged {{
    vertical-align: middle !important;
    background-color: #ffffff;
  }}
  tr.row-key-focus {{
    background-color: #fff7ed;
  }}
  tr.row-key-focus td.cell-merged {{
    background-color: #fff7ed;
  }}
  tr.row-key-focus:hover {{
    background-color: #ffedd5 !important;
  }}
  tr.row-odd {{
    background-color: #ffffff;
  }}
  tr.row-even {{
    background-color: #f8fafc;
  }}
  tr:hover {{
    background-color: #f1f5f9;
  }}
  .font-mono {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  }}
  .font-bold {{
    font-weight: 700;
  }}
  .font-semibold {{
    font-weight: 600;
  }}
  .text-center {{
    text-align: center;
  }}
  .text-blue {{
    color: #1d4ed8;
  }}
  .text-slate {{
    color: #475569;
  }}
  .text-muted {{
    color: #94a3b8;
  }}
  .story-title-col {{
    min-width: 200px;
    max-width: 320px;
    word-break: break-word;
    line-height: 1.4;
  }}
  .remark-col {{
    min-width: 140px;
    max-width: 240px;
    word-break: break-word;
    font-size: 12px;
    color: #475569;
  }}
  .system-tag {{
    display: inline-block;
    background-color: #eff6ff;
    color: #1d4ed8;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
    border: 1px solid #bfdbfe;
  }}
  .badge {{
    display: inline-block;
    padding: 3px 8px;
    border-radius: 9999px;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
  }}
  .badge-sit-risk {{
    background-color: #fee2e2;
    color: #991b1b;
    border: 1px solid #f87171;
    font-weight: 700;
    box-shadow: 0 1px 2px rgba(239, 68, 68, 0.15);
  }}
  .badge-key-focus {{
    background-color: #ffedd5;
    color: #c2410c;
    border: 1px solid #fdba74;
  }}
  .badge-purple {{
    background-color: #f3e8ff;
    color: #7e22ce;
    border: 1px solid #d8b4fe;
    font-weight: 600;
  }}
  .badge-done {{
    background-color: #dcfce7;
    color: #15803d;
    border: 1px solid #86efac;
  }}
  .badge-progress {{
    background-color: #dbeafe;
    color: #1e40af;
    border: 1px solid #93c5fd;
  }}
  .badge-warning {{
    background-color: #fef3c7;
    color: #b45309;
    border: 1px solid #fcd34d;
  }}
  .badge-terminated {{
    background-color: #f1f5f9;
    color: #64748b;
  }}
  .badge-normal {{
    background-color: #f1f5f9;
    color: #334155;
  }}
  .badge-gray {{
    background-color: #f1f5f9;
    color: #64748b;
  }}
  .footer-bar {{
    padding: 16px 32px;
    background-color: #f8fafc;
    border-top: 1px solid #e2e8f0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    font-size: 12px;
    color: #64748b;
  }}
  .legend-box {{
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
  }}
  .empty-cell {{
    padding: 40px !important;
    text-align: center;
  }}
  .empty-state {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    color: #64748b;
  }}
  .empty-icon {{
    font-size: 32px;
  }}
</style>
</head>
<body>

<div class="container">
  <div class="header-banner">
    <h2>{banner_title}</h2>
    <div class="header-meta">
      <span>📌 排期版本：{version_str}</span>
      <span>👤 受理人：{receiver_str}</span>
      <span>🕒 生成时间：{CURRENT_TIME_STR}</span>
    </div>
  </div>

  <div class="stat-grid">
    <div class="stat-card">
      <span class="stat-label">关联需求总数</span>
      <span class="stat-value">{demands_count}</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">关联 Story 总数</span>
      <span class="stat-value">{total_count}</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">🔥 重点关注 Story</span>
      <span class="stat-value highlight">{key_focus_count}</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">🚨 SIT 进度风险 Story</span>
      <span class="stat-value risk-highlight">{sit_risk_count}</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">涉及系统数量</span>
      <span class="stat-value">{len(systems)}</span>
    </div>
  </div>

  <div class="table-wrapper">
    <table>
      <thead>
        <tr>
          <th>史诗编号</th>
          <th>需求编号</th>
          <th>Story编号</th>
          <th>任务名称</th>
          <th>涉及系统</th>
          <th>当前状态</th>
          <th>开发负责人</th>
          <th>SIT负责人</th>
          <th>UAT负责人</th>
          <th>业务验收人</th>
          <th>重点关注</th>
          <th>影响灰度</th>
          <th>备注</th>
        </tr>
      </thead>
      <tbody>{"".join(rows_html)}
      </tbody>
    </table>
  </div>

  <div class="footer-bar">
    <div class="legend-box">
      <strong>图例说明：</strong>
      <span class="badge badge-sit-risk">🚨 SIT进度风险 (不含生产的SIT未完成状态)</span>
      <span class="badge badge-key-focus">🔥 重点关注</span>
      <span class="badge badge-purple">⚡ 影响灰度</span>
      <span class="badge badge-progress">自测中/测试中</span>
      <span class="badge badge-done">已完成</span>
      <span class="badge badge-warning">待测试/待排期</span>
    </div>
    <div>
      💡 提示：本表对 <strong>不含生产的 SIT 未完成状态</strong> 突出高亮标识；含“生产”的状态判定为无风险。
    </div>
  </div>
</div>

</body>
</html>
"""
    abs_output = os.path.abspath(output_path)
    with open(abs_output, "w", encoding="utf-8") as f:
        f.write(html_template)
    return abs_output

def generate_markdown(items, output_path, version_str, receiver_str, is_reviewed=False):
    """
    同时输出终端和 Markdown 表格 (包含 开发负责人)
    """
    doc_title = f"拟排期需求清单 ({version_str} - {receiver_str})" if is_reviewed else f"拟排期需求确认表 ({version_str} - {receiver_str})"
    lines = []
    lines.append(f"# 📋 {doc_title}")
    lines.append(f"> **生成时间**：{CURRENT_TIME_STR} | **规则**：按【重点关注】优先排序，高亮 🚨 不含生产的 SIT 未完成进度风险状态")
    lines.append("")
    lines.append("| 史诗编号 | 需求编号 | Story编号 | 任务名称 | 涉及系统 | 当前状态 | 开发负责人 | SIT负责人 | UAT负责人 | 业务验收人 | 重点关注 | 影响灰度 | 备注 |")
    lines.append("| :---: | :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")

    epic_spans, demand_spans = calculate_spans(items)

    for idx, item in enumerate(items):
        kf_str = "**🔥 是**" if item["is_key_focus"] else item["key_focus"]
        gray_str = "**⚡ 是**" if item["effect_gray"] == "是" else item["effect_gray"]
        epic_disp = f"`{item['epic_code']}`" if epic_spans[idx] > 0 else '""'
        demand_disp = f"**{item['demand_id']}**" if demand_spans[idx] > 0 else '""'

        status_disp = f"**🚨 {item['status_name']}**" if item["is_sit_risk"] else item["status_name"]

        lines.append(
            f"| {epic_disp} | {demand_disp} | `{item['story_code']}` | "
            f"{item['story_title']} | {item['system_name']} | {status_disp} | "
            f"{item['dev_owner']} | {item['sit_owner']} | {item['uat_owner']} | {item['bus_owner']} | {kf_str} | {gray_str} | {item['remark']} |"
        )
    if not items:
        lines.append("| - | - | - | 未匹配到符合条件的需求与 Story | - | - | - | - | - | - | - | - | - |")

    status_owners = extract_current_status_owners(items)
    at_mentions_str = " ".join([f"@{name}" for name in status_owners]) if status_owners else "相关状态负责人"

    clean_ver = str(version_str).replace("-", "").strip()
    short_ver = clean_ver[-4:] if len(clean_ver) == 8 and clean_ver.isdigit() else version_str

    prompt_md = (
        f"> 💬 **以上清单为经过与业务、测试老师沟通反馈后的拟计划{short_ver}版本需求明细，请各位老师知悉。对于调出的需求也请测试老师尽快安排测试，以期在下个版本可以上线。如对排期有任何疑问或变动，烦请及时告知，辛苦大家！**"
        if is_reviewed else
        "> 💬 **麻烦各位老师在今天下班前帮忙确认一下相关需求是否可以顺利排入当前版本。如评估后存在无法排入或延期风险，烦请及时告知，以便我们提前协调并安排调整至后续版本。辛苦大家！**"
    )

    lines.append("")
    lines.append("---")
    lines.append(f"### 📢 当前状态对应负责人：\n{at_mentions_str}")
    lines.append("")
    lines.append(prompt_md)

    abs_output = os.path.abspath(output_path)
    with open(abs_output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return abs_output

def main():
    parser = argparse.ArgumentParser(description="生成拟排期需求确认表/拟计划上线清单（用于给测试及业务同事确认排期与进度风险）")
    parser.add_argument("version", help="计划生产排期版本号，如 20260821 或 2026-08-21")
    parser.add_argument("receiver", nargs="?", default="吴进", help="需求受理人，默认为“吴进”")
    parser.add_argument("-r", "--reviewed", action="store_true", help="沟通后拟计划上线清单模式（经过与业务、测试沟通后的拟上线清单）")
    parser.add_argument("--receiver", dest="opt_receiver", default=None, help="显式指定需求受理人")
    parser.add_argument("--output_html", "-o", default=None, help="输出 HTML 文件路径")
    parser.add_argument("--output_md", default=None, help="输出 Markdown 文件路径")
    parser.add_argument("--table-only", "-t", action="store_true", help="只输出 Markdown 表格到控制台")
    parser.add_argument("--send-mail", "--mail", "--send", action="store_true", help="触发发邮件功能（默认存入草稿箱，以便人工确认后发送）")
    parser.add_argument("--draft-mail", "--draft", action="store_true", help="触发存草稿箱功能")
    parser.add_argument("--force-send", action="store_true", help="强行直接发送邮件（跳过草稿箱）")
    
    args = parser.parse_args()

    version_input = args.version.strip()
    receiver_input = args.opt_receiver if args.opt_receiver else args.receiver
    is_reviewed = args.reviewed

    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 优先在线同步大宽表最新数据，刷新缓存后加载
    raw_records = update_and_load_data(script_dir)

    if not raw_records:
        print("❌ [Error] 未能从在线 API 或本地缓存获取到大宽表数据！")
        sys.exit(1)

    items = filter_and_format_stories(raw_records, version_input, receiver=receiver_input)

    clean_ver = version_input.replace("-", "").strip()
    file_prefix = "拟排期需求明细清单" if is_reviewed else "拟排期需求确认表"
    default_html_name = f"{file_prefix}{clean_ver}-{receiver_input}.html"
    default_md_name = f"{file_prefix}{clean_ver}-{receiver_input}.md"

    output_html_path = args.output_html if args.output_html else os.path.join(os.getcwd(), default_html_name)
    saved_html = generate_html(items, output_html_path, version_input, receiver_input, is_reviewed=is_reviewed)

    # 预先提取/记录收件人列表（自动维护初版收件人持久化缓存）
    extract_table_recipients(items, version_str=version_input, receiver_str=receiver_input, is_reviewed=is_reviewed)

    saved_md = None
    if args.output_md or args.table_only:
        output_md_path = args.output_md if args.output_md else os.path.join(os.getcwd(), default_md_name)
        saved_md = generate_markdown(items, output_md_path, version_input, receiver_input, is_reviewed=is_reviewed)

    if args.table_only and saved_md:
        with open(saved_md, "r", encoding="utf-8") as f:
            print(f.read())
    else:
        print(f"[ProposedSchedule] ✅ 成功抽取 {len(items)} 条数据！ (模式: {'拟排期需求明细清单' if is_reviewed else '拟排期需求确认表'})")
        print(f"[ProposedSchedule] 📄 HTML 文件已保存至: {saved_html}")
        if saved_md:
            print(f"[ProposedSchedule] 📝 Markdown 已保存至: {saved_md}")

    # 当触发【发邮件】或【存草稿】时，默认存入 Coremail 草稿箱（is_send=False）；仅在显式传入 --force-send 时才真正发送
    if args.send_mail or args.draft_mail:
        should_send = args.force_send
        send_confirmation_email(saved_html, version_input, receiver_input, items, is_send=should_send, is_reviewed=is_reviewed)

if __name__ == "__main__":
    main()
