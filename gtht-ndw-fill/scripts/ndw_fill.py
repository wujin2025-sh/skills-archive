#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ndw_fill.py — 国泰海通科技平台 需求分析非开发工作量 (NDW / 价值量) 登记

核心功能与规则：
  1. 【完全独立】：所有依赖（session / config / API）集中管理在 gtht-ndw-fill skill 目录下，开箱即用；
  2. 【默认已完成】：状态字段默认为「已完成」(status=2)；
  3. 【前置校验】：若需求尚未拆分 Story（Story 数量为 0），强制拦截不予登记，防止交付倒挂；
  4. 【半月周期】：按填写日的半月工作日自动推断：
     - 上半月填写 (1日~15日)：开始时间=当月首个工作日 (如 2026-08-03)，完成时间=填写日+5天 (如 2026-08-19)；
     - 下半月填写 (16日~月末)：开始时间=下半月首个工作日 (如 2026-08-17)，完成时间=当月末工作日 (如 2026-08-31)；
  5. 【经办主管】：经办人采用 userNo (050599)，自动通过 /getEvaluatorInfo API 关联获取经办人主管/评估人 (周尤珠 033055 / 106881)；
  6. 【智能归属】：优先取需求所属 Story 的实际系统或 storySystem，确保系统 ID 精准对齐；
  7. 【幂等安全】：严格幂等防重与自动纠偏。

用法:
  python3 ndw_fill.py <req_id> [--value 0.3] [--system "低延时交易系统"] [--status 2] [--force] [--dry-run]
  python3 ndw_fill.py --batch "R2608030112:0.3,R2608040048:0.3"
"""
import sys
import os
import re
import json
import time
import tempfile
import argparse
import calendar
from datetime import datetime, timedelta, date
from pathlib import Path

# 确保优先加载当前技能目录下的 session 与 config，保持独立性
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import session as SESSION
import config

# 系统与 ID 常见映射表
SYSTEM_ID_MAP = {
    "低延时交易系统": "164325248684900500",
    "低延时交易系统(大集中-信创域)": "164325248684900500",
    "低延时交易系统(两融创新域)": "158674333006900117",
    "集中交易系统": "142891263425277DZ1",
    "集中清算系统": "1539073197362VTA7L",
    "交易参数管理后台系统": "1585110383611MMQ3P",
    "参数中心后台": "1585110383611MMQ3P",
    "参数管理中心后台": "1585110383611MMQ3P",
    "证金监管数据报送子系统": "162398553837200127",
    "三方存管系统": "1539073238612ZNY4D",
}

# 经办人与主管工号体系
DEFAULT_ASSIGN_USER_NO = "050599"    # 吴进 系统内用户编号 (可关联到团队)
DEFAULT_ASSIGN_STAFF_ID = "125360"   # 吴进 员工工号
DEFAULT_STATUS_DONE = 2              # 默认状态：已完成 (2: 已完成, 1: 未完成)


def get_stories(demand_id: str) -> list:
    """查询需求下已有的 Story 列表"""
    try:
        res = SESSION.api_get("/demand-service/demandsub/queryStoryDemand", {
            "demandId": demand_id,
            "current": 1,
            "pageSize": 50
        })
        return (res or {}).get("voList", []) or []
    except Exception:
        return []


def _first_workday_from(dt: datetime.date) -> datetime.date:
    """从 dt 起向后找第一个工作日（跳过周六周日）"""
    while dt.weekday() >= 5:  # 5=周六, 6=周日
        dt += timedelta(days=1)
    return dt


def _last_workday_of_month(y: int, m: int) -> datetime.date:
    """当月最后一个工作日"""
    last_day = calendar.monthrange(y, m)[1]
    dt = datetime(y, m, last_day).date()
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
    return dt


def _parse_date(date_str) -> datetime.date:
    """解析 YYYYMMDD / YYYY-MM-DD / YYYY/MM/DD 为 date"""
    if isinstance(date_str, date):
        return date_str
    return datetime.strptime(str(date_str).replace("-", "").replace("/", ""), "%Y%m%d").date()


def compute_ndw_period(fill_date=None) -> tuple:
    """计算非开发工作量的开始时间与完成时间（默认模式：按填写日半月推断）
    
    规则：
      - 上半月填写 (1~15日)：开始时间=当月第一个工作日，完成时间=填写日+5天（如 2026-08-14填写 -> 2026-08-03 ~ 2026-08-19）
      - 下半月填写 (16~月末)：开始时间=下半月第一个工作日 (16日及之后首个工作日)，完成时间=当月末工作日（如 2026-08-18填写 -> 2026-08-17 ~ 2026-08-31）
    """
    if fill_date is None:
        fill_date = datetime.now().date()
    else:
        fill_date = _parse_date(fill_date)

    year, month, day = fill_date.year, fill_date.month, fill_date.day

    if day <= 15:
        start_date = _first_workday_from(datetime(year, month, 1).date())
        end_date = fill_date + timedelta(days=5)
    else:
        start_date = _first_workday_from(datetime(year, month, 16).date())
        end_date = _last_workday_of_month(year, month)

    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


def compute_schedule_period(schedule_date) -> tuple:
    """按「计划生产排期」推算工作量周期（排期工作量登记模式）
    
    规则：
      - 开始时间 = 排期日期所在月的第一个工作日（工作量覆盖当月首工作日 ~ 排期日）
      - 结束时间 = 排期日期（若为周六/周日，取之前最近的工作日）
    示例：20261009 -> 2026-10-09 为周五，周期 = 2026-10-01(周四,首个工作日) ~ 2026-10-09
    """
    sd = _parse_date(schedule_date)
    start_date = _first_workday_from(datetime(sd.year, sd.month, 1).date())
    end_date = sd
    while end_date.weekday() >= 5:
        end_date -= timedelta(days=1)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


# 需求详情中可视为「排期」的候选字段（按优先级取第一个非空）
SCHEDULE_FIELD_CANDIDATES = ("wishDate", "launchTime", "esDuedate")


def auto_schedule_from_demand(info: dict) -> str:
    """从需求详情自动提取排期日期（wishDate 期望上线 > launchTime 上线 > esDuedate 研发交付截止），
    返回 YYYY-MM-DD 字符串；全部为空返回空串。"""
    for f in SCHEDULE_FIELD_CANDIDATES:
        v = (info.get(f) or "").strip()
        if v:
            try:
                return _parse_date(v).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return ""


# ---------------------------------------------------------------------------
# 版本排期工作量登记（项目管理类，taskType=2，无需求关联）
# 输入示例：'20261009版本预排期' → 【版本排期】20261009版本预排期 / 项目管理 / 集中交易系统 / 0.3
#           '20261009版本排期'  → 【版本排期】20261009版本排期  / 项目管理 / 集中交易系统 / 0.2
# 参考历史记录：TR2606090003 / TR2607230027（均为 taskType=2、relateType=2、无 demandId）
# ---------------------------------------------------------------------------
VERSION_SCHEDULE_RE = re.compile(r"(\d{4}[-/]?\d{2}[-/]?\d{2})\s*版本(预排期|排期)")
VERSION_SCHEDULE_DEFAULT_VALUE = {"预排期": 0.3, "排期": 0.2}
VERSION_SCHEDULE_SYSTEM = "集中交易系统"


def parse_version_schedule(text: str):
    """解析版本排期输入文本 → (版本日期YYYYMMDD, 类型[预排期|排期], 默认价值量)
    例：'20261009版本预排期' → ('20261009', '预排期', 0.3)
        '20261009版本排期'  → ('20261009', '排期', 0.2)
    无法解析返回 None。
    """
    m = VERSION_SCHEDULE_RE.search(str(text))
    if not m:
        return None
    ver_date = m.group(1).replace("-", "").replace("/", "")
    kind = m.group(2)
    return ver_date, kind, VERSION_SCHEDULE_DEFAULT_VALUE[kind]


def get_existing_ndw_by_title(task_title: str) -> list:
    """按任务标题精确匹配已登记的非开发工作量（接口标题过滤不可靠时回退全量本地匹配）"""
    try:
        res = SESSION.api_post("/task-service/nonDevTask/getNonDevTaskList", {
            "current": 1, "pageSize": 50, "taskTitle": task_title
        })
        records = (res or {}).get("records", []) or []
        if records:
            return [r for r in records if (r.get("taskTitle") or "").strip() == task_title]
    except Exception:
        pass
    # 回退：全量拉取本地精确匹配
    try:
        all_records = []
        for page in range(1, 51):
            res = SESSION.api_post("/task-service/nonDevTask/getNonDevTaskList", {
                "current": page, "pageSize": 100
            })
            page_records = (res or {}).get("records", []) or []
            all_records.extend(page_records)
            total = (res or {}).get("total") or len(all_records)
            if len(all_records) >= total or not page_records:
                break
        return [r for r in all_records if (r.get("taskTitle") or "").strip() == task_title]
    except Exception:
        return []


def fill_version_schedule(text: str, value: float = None,
                          status: int = DEFAULT_STATUS_DONE,
                          assign_user_no: str = DEFAULT_ASSIGN_USER_NO,
                          evaluator_no: str = None,
                          start_date: str = None, end_date: str = None,
                          schedule_date: str = None,
                          force_recreate: bool = False,
                          dry_run: bool = False,
                          yes_mode: bool = False) -> dict:
    """版本排期工作量登记（项目管理类，taskType=2，无需求关联）

    输入：'20261009版本预排期' / '20261009版本排期'
    登记要素：
      - taskTitle = 【版本排期】{输入文本}
      - taskType  = 2（项目管理）
      - systemId  = 集中交易系统
      - 价值量    = 预排期默认 0.3 / 排期默认 0.2（可 --value 显式覆盖）
      - relateType= 2（版本类，无需求），demandId 为空
      - 周期      = 默认半月推断；可 --schedule 按排期日期推算
      - 经办/主管评估/状态 与需求分析登记一致（其他不变）
    """
    parsed = parse_version_schedule(text)
    if not parsed:
        return {
            "ok": False, "skipped": True,
            "reason": f"无法解析版本排期输入：{text!r}（期望格式如 20261009版本预排期 / 20261009版本排期）"
        }
    ver_date, kind, default_value = parsed
    actual_value = float(value) if value is not None else default_value

    task_title = f"【版本排期】{str(text).strip()}"
    system_id = SYSTEM_ID_MAP.get(VERSION_SCHEDULE_SYSTEM, "142891263425277DZ1")
    sys_name = VERSION_SCHEDULE_SYSTEM

    eval_info = get_evaluator_from_platform(assign_user_no)
    evaluator_no = evaluator_no or eval_info["evaluatorNo"]

    # 周期：显式 --schedule 按排期推算，否则默认半月推断（其他不变）
    if schedule_date:
        calc_start, calc_end = compute_schedule_period(schedule_date)
    else:
        calc_start, calc_end = compute_ndw_period()
    start = start_date or calc_start
    end = end_date or calc_end

    # 幂等检查与缺陷纠偏（按标题精确匹配）
    existing = get_existing_ndw_by_title(task_title)
    for r in existing:
        if str(r.get("taskType")) == "2":
            has_eval_name = bool(r.get("evaluatorName"))
            is_correct_eval = str(r.get("evaluatorNo")) in [str(evaluator_no), "033055"]
            is_same_period = (r.get("startTime") == start and r.get("endTime") == end)
            is_same_status = (r.get("status") == status)
            is_same_value = abs(float(r.get("reapplicationTaskValue") or 0) - actual_value) < 1e-9
            if has_eval_name and is_correct_eval and is_same_period and is_same_status and is_same_value and not force_recreate:
                return {
                    "ok": True, "skipped": True, "taskTitle": task_title,
                    "reason": "已存在符合规范（含主管评估人、正确周期/价值量/已完成状态）的版本排期记录",
                    "record": {
                        "id": r.get("id"),
                        "taskNo": r.get("taskNo"),
                        "taskTitle": r.get("taskTitle"),
                        "value": r.get("reapplicationTaskValue"),
                        "status": r.get("status"),
                        "statusName": "已完成" if r.get("status") == 2 else "未完成",
                        "startTime": r.get("startTime"),
                        "endTime": r.get("endTime"),
                        "evaluator": f"{r.get('evaluatorName')}-{r.get('evaluatorStaffId')}",
                        "assign": f"{r.get('assignUserName')}-{r.get('assignUserStaffId')}",
                        "systemName": r.get("systemName")
                    }
                }
            else:
                # 记录不完整或需更新，自动删除重建（仅真落库时）
                if not dry_run:
                    delete_ndw_record(r.get("id"))

    payload = {
        "taskTitle": task_title,
        "taskType": 2,  # 2: 项目管理（版本排期/版本发布类）
        "systemId": system_id,
        "demandId": "",
        "assignUserNo": assign_user_no,
        "reapplicationTaskValue": float(actual_value),
        "evaluatorNo": evaluator_no,
        "status": status,  # 默认 2: 已完成
        "startTime": start,
        "endTime": end,
        "relateType": 2,
        "relateId": ""
    }

    if dry_run and not yes_mode:
        return {"ok": True, "dry_run": True, "taskTitle": task_title, "payload": payload,
                "evaluatorInfo": eval_info, "parsed": {"verDate": ver_date, "kind": kind}}

    resp = SESSION.api_post("/task-service/nonDevTask/addNonDevTask", payload)

    # 去重 re-query：优先从提交响应取 taskNo，取不到再查一次（兼容后端返回结构）
    rec = {}
    if isinstance(resp, dict):
        cand = resp.get("data") if isinstance(resp.get("data"), dict) else resp
        if cand.get("taskNo"):
            rec = cand
    if not rec.get("taskNo"):
        latest = get_existing_ndw_by_title(task_title)
        rec = latest[0] if latest else {}

    return {
        "ok": True,
        "skipped": False,
        "taskNo": rec.get("taskNo", ""),
        "taskTitle": task_title,
        "value": float(actual_value),
        "status": status,
        "statusName": "已完成" if status == 2 else "未完成",
        "period": f"{start} ~ {end}",
        "assign": f"{rec.get('assignUserName', '吴进')}-{rec.get('assignUserStaffId', DEFAULT_ASSIGN_STAFF_ID)}",
        "evaluator": f"{rec.get('evaluatorName', eval_info['evaluatorName'])}-{rec.get('evaluatorStaffId', eval_info['evaluatorStaffId'])}",
        "systemName": rec.get("systemName") or sys_name,
        "data": resp
    }


def get_evaluator_from_platform(assign_user_no: str = DEFAULT_ASSIGN_USER_NO):
    """从平台实时查询经办人的团队主管评估人"""
    try:
        res = SESSION.api_get("/task-service/nonDevTask/getEvaluatorInfo", {"assignUserNo": assign_user_no})
        if isinstance(res, list) and len(res) > 0:
            leader = res[0]
            return {
                "evaluatorNo": leader.get("userNo", "033055"),
                "evaluatorStaffId": leader.get("userStaffId", "106881"),
                "evaluatorName": leader.get("userName", "周尤珠"),
                "teamName": leader.get("teamName", "")
            }
    except Exception:
        pass
    # 兜底默认值
    return {
        "evaluatorNo": "033055",
        "evaluatorStaffId": "106881",
        "evaluatorName": "周尤珠",
        "teamName": "交易结算业务创新组"
    }


def get_demand_detail(demand_id: str) -> dict:
    """获取需求详细要素"""
    res = SESSION.api_post("/demand-service/demandsub/queryDemandsubInfo", {
        "demandId": demand_id,
        "userId": DEFAULT_ASSIGN_USER_NO,
        "userName": "吴进"
    })
    return res or {}


def get_existing_ndw(demand_id: str) -> list:
    """查询该需求下已登记的非开发工作量列表"""
    try:
        res = SESSION.api_post("/task-service/nonDevTask/getNonDevTaskList", {
            "current": 1,
            "pageSize": 50,
            "demandId": demand_id
        })
        return (res or {}).get("records", []) or []
    except Exception:
        return []


def delete_ndw_record(record_id: int):
    """删除非开发工作量记录"""
    try:
        return SESSION.api_post("/task-service/nonDevTask/deleteNonDevTask", {"id": record_id})
    except Exception:
        return None


# ---------------------------------------------------------------------------
# dry-run 计划缓存（两段式落库复用，省去重复 API）
# ---------------------------------------------------------------------------
def _plan_path(demand_id: str) -> Path:
    return Path(tempfile.gettempdir()) / f"ndw_{demand_id}_plan.json"


def _write_plan(demand_id: str, plan: dict):
    try:
        _plan_path(demand_id).write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    except Exception:
        pass


def _read_plan(demand_id: str, max_age_sec: int = 1800) -> dict:
    """读取 dry-run 缓存；过期或缺失返回空（落库前重新查询）。"""
    p = _plan_path(demand_id)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        if time.time() - data.get("cached_at", 0) > max_age_sec:
            return {}
        return data
    except Exception:
        return {}


def determine_system_id(info: dict, stories: list = None, specified_system: str = None) -> tuple:
    """推断所属系统 ID 与系统名称
    
    优先级：
      1. 显式指定的系统名称
      2. 需求下已有 Story 的所属系统 (stories[0].systemId)
      3. 需求要素中的 storySystem
      4. 需求标题中的关键字推断
    """
    if specified_system:
        specified_system = specified_system.strip()
        for k, v in SYSTEM_ID_MAP.items():
            if specified_system in k or k in specified_system:
                return v, k
        return SYSTEM_ID_MAP.get(specified_system, "164325248684900500"), specified_system

    # 优先从已有 Story 提取系统
    if stories and len(stories) > 0:
        first_s = stories[0]
        s_sys_id = first_s.get("systemId")
        s_sys_name = first_s.get("systemName")
        if s_sys_id and s_sys_name:
            return str(s_sys_id), str(s_sys_name)

    # 其次从需求元数据的 storySystem 提取
    story_sys = (info.get("storySystem") or "").strip()
    if story_sys:
        for k, v in SYSTEM_ID_MAP.items():
            if story_sys in k or k in story_sys:
                return v, k

    summary = (info.get("summary") or "").strip()
    if "证金" in summary:
        return SYSTEM_ID_MAP["证金监管数据报送子系统"], "证金监管数据报送子系统"
    if "参数" in summary:
        return SYSTEM_ID_MAP["交易参数管理后台系统"], "交易参数管理后台系统"
    if "清算" in summary:
        return SYSTEM_ID_MAP["集中清算系统"], "集中清算系统"
    if "低延时" in summary or "两融" in summary:
        # 低延时系统域归属判定（2026-09-10 新增，对齐 ba-to-dev 规则8 / story-split 规则4）：
        # 涉及「个微」「98/98创新域」「创新域」→ 两融创新域；其余两融/信用业务默认 95 信创域
        if any(kw in summary for kw in ["个微", "98", "创新域"]):
            return SYSTEM_ID_MAP["低延时交易系统(两融创新域)"], "低延时交易系统(两融创新域)"
        return SYSTEM_ID_MAP["低延时交易系统(大集中-信创域)"], "低延时交易系统(大集中-信创域)"
    if "集中交易" in summary:
        return SYSTEM_ID_MAP["集中交易系统"], "集中交易系统"

    return SYSTEM_ID_MAP["低延时交易系统(大集中-信创域)"], "低延时交易系统(大集中-信创域)"


def find_local_demand_md(demand_id: str) -> dict:
    """在本地需求分析目录中检索需求 MD 文档并提取 frontmatter 和改造范围"""
    base_dir = Path("/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析")
    if not base_dir.exists():
        return {}

    for p in base_dir.glob("*.md"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read(4096)

            if demand_id not in content:
                continue

            res = {"path": str(p), "systems": [], "ndw": None}
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    fm_text = parts[1]
                    for line in fm_text.splitlines():
                        if line.startswith("ndw:"):
                            val_str = line.split(":", 1)[1].strip()
                            try:
                                res["ndw"] = float(val_str)
                            except ValueError:
                                pass
                        elif line.startswith("system:"):
                            sys_part = line.split(":", 1)[1].strip()
                            if sys_part.startswith("[") and sys_part.endswith("]"):
                                sys_items = [x.strip() for x in sys_part[1:-1].split(",") if x.strip()]
                                res["systems"].extend(sys_items)
            return res
        except Exception:
            pass
    return {}


def infer_ndw_value(demand_id: str, info: dict, stories: list = None, passed_value: float = None) -> float:
    """智能推断价值量：
    - 若用户显式传入了指定值，以显式传入为准；
    - 若从本地 MD 解析到 ndw，以 MD 设定为准；
    - 否则根据改造系统数量智能推断：
      * 涉及多个系统改造 (>= 2 个系统，如 dys + jzjy / 多 Story 跨系统)：默认 0.5 人月
      * 单系统改造：默认 0.3 人月
    """
    if passed_value is not None:
        return float(passed_value)

    local_info = find_local_demand_md(demand_id)
    if local_info.get("ndw") is not None:
        return float(local_info["ndw"])

    # 1. 检查本地 MD 系统数 >= 2
    if len(local_info.get("systems", [])) > 1:
        return 0.5

    # 2. 检查线上 Story 数量 >= 2 或涉及不同系统
    if stories and len(stories) > 1:
        return 0.5
    if stories:
        distinct_sys = {s.get("systemName") for s in stories if s.get("systemName")}
        if len(distinct_sys) > 1:
            return 0.5

    # 3. 需求标题与内容关键字
    summary = (info.get("summary") or "")
    if any(kw in summary for kw in ["跨系统", "低延时两融", "集中交易与低延时", "低延时与集中交易", "集中交易与集中清算", "清算与交易"]):
        return 0.5

    return 0.3


def fill_ndw(demand_id: str, value: float = None, system_name: str = None,
             status: int = DEFAULT_STATUS_DONE,
             assign_user_no: str = DEFAULT_ASSIGN_USER_NO,
             evaluator_no: str = None,
             start_date: str = None, end_date: str = None,
             schedule_date: str = None, by_schedule: bool = False,
             force_recreate: bool = False,
             ignore_story_check: bool = False,
             dry_run: bool = False,
             yes_mode: bool = False) -> dict:
    """登记非开发工作量"""
    # 1. 前置强约束：Story 未拆分则不填写（强制重查，防 Story 被删倒挂）
    stories = get_stories(demand_id)
    if not stories and not ignore_story_check:
        return {
            "ok": False,
            "skipped": True,
            "demandId": demand_id,
            "reason": "【前置拦截】该需求尚未拆分 Story，按规范暂不填写非开发工作量。请先完成 Story 拆分后再登记。"
        }

    # 2. 复用 dry-run 计划缓存（两段式落库时跳过重复 API；--yes 不读缓存，单进程完整查）
    plan = _read_plan(demand_id) if not yes_mode else {}
    reuse = bool(plan) and plan.get("stories_count") == len(stories)

    if reuse:
        eval_info = plan.get("evaluator", {})
        evaluator_no = evaluator_no or eval_info.get("evaluatorNo")
        info = plan.get("demand_info", {})
    else:
        eval_info = get_evaluator_from_platform(assign_user_no)
        evaluator_no = evaluator_no or eval_info["evaluatorNo"]
        info = get_demand_detail(demand_id)

    title = (info.get("summary") or "").strip()
    if not title:
        raise ValueError(f"未找到需求 {demand_id} 的详情信息")

    # 智能推断价值量（多系统改造默认 0.5，单系统默认 0.3）
    actual_value = infer_ndw_value(demand_id, info, stories, value)

    system_id, matched_sys_name = determine_system_id(info, stories, system_name)

    # 跨系统判定（2026-09-16 修复：去掉 actual_value>=0.5 启发式判据，单系统高复杂度需求误判如 R2609160070）
    # 正确判据 = 多 Story / 多不同系统 / 标题显式标注跨系统
    distinct_sys = {s.get("systemName") for s in stories if s.get("systemName")}
    is_cross = len(stories) > 1 or len(distinct_sys) > 1 or "跨系统" in title
    # 单系统需求标题前新增【单系统】；跨系统需求标题前新增【跨系统】；已带前缀则不重复叠加
    if is_cross:
        task_title = f"【跨系统】{title}" if not title.startswith("【跨系统】") else title
    else:
        task_title = f"【单系统】{title}" if not title.startswith("【单系统】") and not title.startswith("【跨系统】") else title


    # 计算周期（优先级：显式 --start/--end > --schedule 排期登记 > --by-schedule 自动读排期 > 默认半月推断）
    if schedule_date:
        calc_start, calc_end = compute_schedule_period(schedule_date)
    elif by_schedule:
        auto_sd = auto_schedule_from_demand(info)
        if auto_sd:
            calc_start, calc_end = compute_schedule_period(auto_sd)
        else:
            calc_start, calc_end = compute_ndw_period()
    else:
        calc_start, calc_end = compute_ndw_period()
    start = start_date or calc_start
    end = end_date or calc_end

    # 幂等检查与缺陷纠偏
    existing = get_existing_ndw(demand_id)
    for r in existing:
        if r.get("taskType") == 1:  # 需求分析
            has_eval_name = bool(r.get("evaluatorName"))
            is_correct_eval = str(r.get("evaluatorNo")) in [str(evaluator_no), "033055"]
            is_same_period = (r.get("startTime") == start and r.get("endTime") == end)
            is_same_status = (r.get("status") == status)
            is_same_system = (str(r.get("systemId")) == str(system_id))
            
            if has_eval_name and is_correct_eval and is_same_period and is_same_status and is_same_system and not force_recreate:
                return {
                    "ok": True,
                    "skipped": True,
                    "demandId": demand_id,
                    "reason": "已存在符合规范（含主管评估人、正确半月周期及已完成状态）的价值量记录",
                    "record": {
                        "id": r.get("id"),
                        "taskNo": r.get("taskNo"),
                        "taskTitle": r.get("taskTitle"),
                        "value": r.get("reapplicationTaskValue"),
                        "status": r.get("status"),
                        "statusName": "已完成" if r.get("status") == 2 else "未完成",
                        "startTime": r.get("startTime"),
                        "endTime": r.get("endTime"),
                        "evaluator": f"{r.get('evaluatorName')}-{r.get('evaluatorStaffId')}",
                        "assign": f"{r.get('assignUserName')}-{r.get('assignUserStaffId')}",
                        "systemName": r.get("systemName")
                    }
                }
            else:
                # 记录不完整或需要更新系统/状态/周期，自动删除重建（仅真落库时）
                if not dry_run:
                    delete_ndw_record(r.get("id"))

    payload = {
        "taskTitle": task_title,
        "taskType": 1,  # 1: 需求分析
        "systemId": system_id,
        "demandId": demand_id,
        "assignUserNo": assign_user_no,
        "reapplicationTaskValue": float(actual_value),
        "evaluatorNo": evaluator_no,
        "status": status,  # 默认 2: 已完成
        "startTime": start,
        "endTime": end,
        "relateType": 1,
        "relateId": ""
    }

    # 写计划缓存（两段式落库复用 / --yes 追溯）
    _write_plan(demand_id, {
        "cached_at": int(time.time()),
        "stories_count": len(stories),
        "evaluator": eval_info,
        "demand_info": info,
        "payload": payload,
    })

    if dry_run and not yes_mode:
        return {"ok": True, "dry_run": True, "demandId": demand_id, "payload": payload, "evaluatorInfo": eval_info}

    resp = SESSION.api_post("/task-service/nonDevTask/addNonDevTask", payload)

    # 去重 re-query：优先从提交响应取 taskNo，取不到再查一次（兼容后端返回结构）
    rec = {}
    if isinstance(resp, dict):
        cand = resp.get("data") if isinstance(resp.get("data"), dict) else resp
        if cand.get("taskNo"):
            rec = cand
    if not rec.get("taskNo"):
        latest = get_existing_ndw(demand_id)
        rec = latest[0] if latest else {}

    return {
        "ok": True,
        "skipped": False,
        "demandId": demand_id,
        "taskNo": rec.get("taskNo", ""),
        "taskTitle": task_title,
        "value": float(actual_value),
        "status": status,
        "statusName": "已完成" if status == 2 else "未完成",
        "period": f"{start} ~ {end}",
        "assign": f"{rec.get('assignUserName', '吴进')}-{rec.get('assignUserStaffId', DEFAULT_ASSIGN_STAFF_ID)}",
        "evaluator": f"{rec.get('evaluatorName', eval_info['evaluatorName'])}-{rec.get('evaluatorStaffId', eval_info['evaluatorStaffId'])}",
        "systemName": rec.get("systemName") or matched_sys_name,
        "data": resp
    }


def main():
    parser = argparse.ArgumentParser(description="国泰海通需求分析非开发工作量登记")
    parser.add_argument("demand_id", nargs="?", help="需求编号，如 R2608030112")
    parser.add_argument("--value", "-v", "--ndw", type=float, default=None, help="申请价值量 (人月)，未指定时自动智能推断：多系统改造默认 0.5，单系统默认 0.3")
    parser.add_argument("--status", type=int, default=DEFAULT_STATUS_DONE, help="状态 (默认 2:已完成，1:未完成)")
    parser.add_argument("--system", "-s", help="所属系统名称")
    parser.add_argument("--schedule", help="排期日期 YYYYMMDD（排期工作量登记）：工作量周期=排期所在月首个工作日 ~ 排期日")
    parser.add_argument("--by-schedule", action="store_true",
                        help="自动从需求详情读取排期（wishDate>launchTime>esDuedate）推算工作量周期；读不到回退半月推断")
    parser.add_argument("--batch", "-b", help="批量格式: 'R2608030112:0.3,R2608120012:0.5,R2608110032:0.3'")
    parser.add_argument("--version-schedule", "--vs",
                        help="版本排期工作量登记（项目管理类，无需求）：输入如 '20261009版本预排期'(默认0.3) 或 '20261009版本排期'(默认0.2)，系统=集中交易系统")
    parser.add_argument("--ignore-story", action="store_true", help="忽略 Story 拆分状态强行登记")
    parser.add_argument("--force", action="store_true", help="强制删除旧记录并重新创建")
    parser.add_argument("--dry-run", action="store_true", help="只预览 payload，不实际提交（默认两段式先 dry-run 展示再确认落库）")
    parser.add_argument("--yes", "-y", "--auto", action="store_true",
                        help="预授权直接落库：单进程完成 查→校验→提交，跳过 dry-run 展示与确认轮（仅命令显式 opt-in 启用）")

    args = parser.parse_args()

    if args.batch:
        items = [x.strip() for x in args.batch.split(",") if x.strip()]
        results = []
        for it in items:
            if ":" in it:
                rid, val = it.split(":", 1)
                val = float(val)
            else:
                rid, val = it, args.value
            res = fill_ndw(rid.strip(), value=val, system_name=args.system,
                           status=args.status,
                           schedule_date=args.schedule, by_schedule=args.by_schedule,
                           force_recreate=args.force,
                           ignore_story_check=args.ignore_story,
                           dry_run=args.dry_run and not args.yes,
                           yes_mode=args.yes)
            results.append(res)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    if args.version_schedule:
        res = fill_version_schedule(args.version_schedule, value=args.value, status=args.status,
                                    schedule_date=args.schedule,
                                    force_recreate=args.force,
                                    dry_run=args.dry_run and not args.yes,
                                    yes_mode=args.yes)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if not args.demand_id:
        parser.print_help()
        sys.exit(1)

    res = fill_ndw(args.demand_id, value=args.value, system_name=args.system,
                   status=args.status,
                   schedule_date=args.schedule, by_schedule=args.by_schedule,
                   force_recreate=args.force,
                   ignore_story_check=args.ignore_story,
                   dry_run=args.dry_run and not args.yes,
                   yes_mode=args.yes)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
