#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
platform_api.py — 科技平台写操作 API 封装（需求受理提速核心）

基于「拦截-中止」实测捕获的端点与 payload（20260813 确认），将表单类落地操作
从 Playwright（6-15s）改为 requests 直调（sub-second）：

  - save_review        POST /demand-service/conclusion/saveDemandReviewInfo   （以本人身份新增评审纪要）
  - update_review      POST /demand-service/conclusion/updateDemandReviewInfo （仅 update 本人同主题记录）
  - add_non_dev_work   POST /task-service/nonDevTask/addNonDevTask            （非开发工作量登记）
  - list_reviews       POST /demand-service/conclusion/getDemandInfoList      （读全部评审记录，含他人占位）
  - list_templates     POST /story-service/fastCreateTemplate/getFastCreateTemplate（Story 模板）
  - save_story         POST /story-service/stcpstory/storydetail/create      （新建 Story，payload 推断待 E2E 验证）

凭据：复用 session.py 的 JWT token（api_post 已封装 401 自动重登，4s 内）。

实测要点（20260813 拦截确认）：
  - 评审落地 payload（新增会议纪要）：
      {demandId, userId, userName, title, reviewType, summaryType:"2", mettingSummary}
      title = f"{需求标题}评审会_{YYYYMMDD}"；reviewType = 评审结果字典 ID
  - 评审结果字典（pdmDictionary/foldDict dictId=f9271713515442f39c）：
      评审通过=f54fbe2e327e4ee68d / 评审未通过=a694c153ca014ed792 / 待继续沟通=529ed382ac6a4ac995
  - NDW 登记 payload（plan 捕获 + 弹窗默认值）：
      {taskTitle, taskType:1(需求分析), systemId, demandId, assignUserNo,
       reapplicationTaskValue, evaluatorNo, status:1(未完成), startTime, endTime,
       relateType:1, relateId:""}
      经办人默认=刘辉(020822/114305)，评估人默认=周尤珠(033055/106881)，时间=今天/今天+5天
"""
import re
import html
from datetime import datetime, timedelta

import session as SESSION
import config

# ---------------------------------------------------------------------------
# 常量（实测确认）
# ---------------------------------------------------------------------------
# 评审结果 → reviewType（平台字典 f9271713515442f39c）
REVIEW_TYPE_MAP = {
    "通过": "f54fbe2e327e4ee68d",        # 评审通过
    "驳回": "a694c153ca014ed792",        # 评审未通过
    "有条件通过": "529ed382ac6a4ac995",   # 待继续沟通（平台无「有条件通过」项，最接近）
}
REVIEW_TYPE_NAME = {v: k for k, v in REVIEW_TYPE_MAP.items()}
DEFAULT_SUMMARY_TYPE = "2"               # 评审纪要类型（常量）
DEFAULT_SUBDIVISION = "15610859709344UP19"  # 一级需求类型=普通业务功能（完成评审表单默认）

# 非开发工作量默认值（弹窗实测 20260813；值可被 config defaults 覆盖）
NDW_TASK_TYPE_ANALYSIS = 1               # 非开发工作类别：需求分析
NDW_STATUS_UNFINISHED = 1                # 状态：未完成
NDW_RELATE_TYPE = 1
DEFAULT_ASSIGN_USER_NO = config.get_default("default_assign_user_no", "020822")   # 经办人 刘辉
DEFAULT_EVALUATOR_NO = config.get_default("default_evaluator_no", "033055")       # 评估人 周尤珠
NDW_END_OFFSET_DAYS = 5                  # 完成时间 = 今天 + 5 天（弹窗默认）

# 当前用户（session 的 user_info 可能为空，回退到 config defaults）
CUR_USER_NO = config.get_default("cur_user_no", "020822")
CUR_USER_NAME = config.get_default("cur_user_name", "刘辉")


# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------
def _api_write(path: str, payload: dict) -> dict:
    """写操作 API 封装：成功时返回 {ok:True, data}；data 可能为 None（部分端点成功无返回体）。"""
    data = SESSION.api_post(path, payload)
    return {"ok": True, "data": data}


def _current_user():
    """返回 (workno, personname)，优先取 session.user_info"""
    sess = SESSION.get_session()
    ui = sess.get("user_info") or {}
    return ui.get("workno") or CUR_USER_NO, ui.get("personname") or CUR_USER_NAME


def get_demand_info(demand_id: str) -> dict:
    """需求要素（summary/storySystem/userName/deptName 等）"""
    uid, uname = _current_user()
    return SESSION.api_post("/demand-service/demandsub/queryDemandsubInfo",
                            {"demandId": demand_id, "userId": uid, "userName": uname})


def get_stories(demand_id: str) -> list:
    """需求已有 Story 列表（系统/状态/评估状态）"""
    d = SESSION.api_get("/demand-service/demandsub/queryStoryDemand",
                        {"current": 1, "demandId": demand_id, "pageSize": 9999})
    return (d or {}).get("voList", []) or []


def md_to_html(text: str) -> str:
    """会议纪要 Markdown → 富文本 HTML：**加粗** → <strong>，段落间保持紧凑自然行距"""
    out = []
    for line in (text or "").split("\n"):
        if not line.strip():
            continue
        leading = len(line) - len(line.lstrip(" "))
        indent = "&nbsp;" * leading
        rest = html.escape(line.lstrip(" "), quote=False)
        rest = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rest)
        out.append(f"<p>{indent}{rest}</p>")
    return "".join(out)


def compute_review_delivery(version: str) -> str:
    """需求评审预计交付时间 = 版本排期迁移两周（YYYY-MM-DD）"""
    d = datetime.strptime(version, "%Y%m%d").date()
    return (d - timedelta(days=14)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 评审落地
# ---------------------------------------------------------------------------
def list_reviews(demand_id: str) -> list:
    """评审记录列表（含 createUserWorkno/mettingSummary/title；用 getDemandInfoList 返回全部，
    含他人空占位记录，供 save_review 按当前用户过滤、绝不触碰他人记录）。"""
    d = SESSION.api_post("/demand-service/conclusion/getDemandInfoList",
                         {"demandId": demand_id})
    return d if isinstance(d, list) else []


def save_review(demand_id: str, result: str, minutes: str,
                type_: str = "普通业务功能", version: str = None,
                epic: str = None, operational: str = None,
                dry_run: bool = False) -> dict:
    """评审落地（≤1s）——**以当前登录人身份新增评审记录**。

    - result: 通过 / 有条件通过 / 驳回
    - minutes: RVW 正文（Markdown，不含标题）
    - version: 版本排期 YYYYMMDD（用于预计交付时间；新增纪要场景不落该字段）
    - type_/epic/operational: 保留入参（完成评审表单字段），本次场景不提交

    **身份与所有权约束（20260813 修复）**：
    - 一律以当前用户（session user_info，如 刘辉 020822）身份 **save 新增**评审记录；
    - **绝不 update/篡改他人创建的评审记录**（UI 上他人记录无编辑入口，API 不得绕过）；
    - 幂等仅作用于**当前用户自己的记录**：同主题（日期标题）且同纪要 → 跳过；同主题不同纪要 → update 自己的记录；
      其他用户同主题记录一律不动，直接新增。
    """
    uid, uname = _current_user()
    info = get_demand_info(demand_id)
    title = (info.get("summary") or "").strip()
    today = datetime.now().strftime("%Y%m%d")
    meeting_title = f"{title}评审会_{today}"
    rt = REVIEW_TYPE_MAP.get(result)
    if not rt:
        raise ValueError(f"未知评审结果: {result}（支持 {list(REVIEW_TYPE_MAP)}）")
    body = md_to_html(minutes)
    base = {
        "demandId": demand_id,
        "userId": uid,
        "userName": uname,
        "title": meeting_title,
        "reviewType": rt,
        "summaryType": DEFAULT_SUMMARY_TYPE,
        "mettingSummary": body,
    }
    reviews = list_reviews(demand_id)
    # 只看当前用户自己创建的记录（createUserWorkno == 当前工号）
    my_reviews = [r for r in reviews if str(r.get("createUserWorkno") or "") == str(uid)]
    # 1) 自己已有同主题记录：同纪要 → 幂等跳过；不同纪要 → update 自己的记录（改错/修正场景）
    for rec in my_reviews:
        if rec.get("title") == meeting_title:
            existing_body = (rec.get("mettingSummary") or "").strip()
            if existing_body == body:
                return {"skipped": True, "reason": "本人已有相同主题且相同纪要", "id": rec.get("id")}
            upd = dict(base, id=rec["id"], subdivisionType=[DEFAULT_SUBDIVISION],
                       isService="0", moduleId=[], reviewDeliveryTime=None,
                       isRegulatoryReporting="0")
            if dry_run:
                return {"dry_run": True, "mode": "update", "payload": upd}
            return _api_write("/demand-service/conclusion/updateDemandReviewInfo", upd)
    # 2) 其余一律新增自己的评审记录（绝不触碰他人记录，包括空占位记录）
    if dry_run:
        return {"dry_run": True, "mode": "save", "payload": base}
    return _api_write("/demand-service/conclusion/saveDemandReviewInfo", base)


# ---------------------------------------------------------------------------
# 非开发工作量登记
# ---------------------------------------------------------------------------
def add_non_dev_work(demand_id: str, value: float, task_type: int = NDW_TASK_TYPE_ANALYSIS,
                     assign_user_no: str = DEFAULT_ASSIGN_USER_NO,
                     evaluator_no: str = DEFAULT_EVALUATOR_NO,
                     start: str = None, end: str = None,
                     system_id: str = None, system_name: str = None,
                     dry_run: bool = False) -> dict:
    """登记非开发工作量（需求分析类，≤0.5s）。

    规则（SKILL 步骤 9）：
      - 跨系统需求（Story>1）名称加「【跨系统】」前缀；
      - 所属系统选择优先级：显式 system_id/system_name > 需求的 storySystem 主系统（在已有 Story 中匹配）
        > 第一个 Story；避免选到批次预置的杂项系统（如 股权激励管理前台系统）；
      - 经办人/评估人默认刘辉/周尤珠；状态未完成；时间 今天/今天+5；
      - 幂等：同需求同类别同名称已登记 → 跳过（不产生重复记录）。
    """
    info = get_demand_info(demand_id)
    title = (info.get("summary") or "").strip()
    stories = get_stories(demand_id)
    # 系统选择
    if not system_id and system_name:
        for s in stories:
            if (s.get("systemName") or "").strip() == system_name:
                system_id = s.get("systemId")
                break
    if not system_id:
        story_system = (info.get("storySystem") or "").strip()
        if story_system:
            # 优先：storySystem 主系统在已有 Story 中 → 用其 systemId
            for s in stories:
                if (s.get("systemName") or "").strip() == story_system:
                    system_id = s.get("systemId")
                    break
        if not system_id:
            first_sys = stories[0] if stories else {}
            system_id = first_sys.get("systemId") or story_system
    is_cross = len(stories) > 1
    task_title = f"【跨系统】{title}" if is_cross else title
    today = datetime.now().strftime("%Y-%m-%d")
    end = end or (datetime.now() + timedelta(days=NDW_END_OFFSET_DAYS)).strftime("%Y-%m-%d")

    # 幂等检查：同需求 + 同类别 + 同名称 → 跳过
    try:
        lst = SESSION.api_post("/task-service/nonDevTask/getNonDevTaskList",
                               {"current": 1, "pageSize": 50, "demandId": demand_id})
        for r in (lst or {}).get("records", []) or []:
            if r.get("taskTitle") == task_title and r.get("taskType") == task_type:
                return {"skipped": True, "taskTitle": task_title,
                        "existingId": r.get("id"), "existingValue": r.get("reapplicationTaskValue")}
    except Exception:
        pass

    payload = {
        "taskTitle": task_title,
        "taskType": task_type,
        "systemId": system_id,
        "demandId": demand_id,
        "assignUserNo": assign_user_no,
        "reapplicationTaskValue": float(value),
        "evaluatorNo": evaluator_no,
        "status": NDW_STATUS_UNFINISHED,
        "startTime": start or today,
        "endTime": end,
        "relateType": NDW_RELATE_TYPE,
        "relateId": "",
    }
    if dry_run:
        return {"dry_run": True, "payload": payload}
    return _api_write("/task-service/nonDevTask/addNonDevTask", payload)


# ---------------------------------------------------------------------------
# Story 模板 & 新建 Story
# ---------------------------------------------------------------------------
def list_templates() -> list:
    """Story 拆分模板列表（使用模板下拉数据源）。

    实测端点：/story-service/fastCreateTemplate/getFastCreateTemplate（非 queryDemandTemplates）
    每项含 content(JSON 字符串)：systemId/devHeader/testHeader/systemModule/projectId 等。
    """
    d = SESSION.api_post("/story-service/fastCreateTemplate/getFastCreateTemplate", {"type": 1})
    return d if isinstance(d, list) else []


def get_template_by_system(templates: list, system_name: str) -> dict:
    """按系统名匹配模板（双向子串匹配：模板「道合大宗」↔ 系统「道合大宗信息服务系统」）。

    content 解析后返回 {title, id, content}；找不到返回 None。
    """
    system_name = (system_name or "").strip()
    for t in templates or []:
        title = t.get("title") or ""
        if title == system_name or (system_name and (system_name in title or title in system_name)):
            try:
                content = json_loads(t.get("content"))
            except Exception:
                content = {}
            return {"title": title, "id": t.get("id"), "content": content}
    return None


def json_loads(s):
    import json
    return json.loads(s) if s else {}


def save_story(demand_id: str, system_name: str, story_type: str = "改造",
               template: dict = None, impact_grayscale: str = "否",
               need_biz_accept: str = None, biz_acceptor: str = None,
               parent_desc: str = None, story_name: str = None,
               dry_run: bool = False) -> dict:
    """新建 Story 并自动绑定至需求。
    
    1. POST /story-service/stcpstory/storydetail/create 创建 Story 并获取 storyCode
    2. POST /story-service/stcpstory/storydetail/demandBindStory 将 Story 绑定至 Demand
    """
    info = get_demand_info(demand_id)
    demand_title = (info.get("summary") or "").strip()
    if template is None:
        template = get_template_by_system(list_templates(), system_name)
    if not template or not template.get("content"):
        raise ValueError(f"未找到系统「{system_name}」的拆分模板")
    c = template["content"]
    # 二级需求类型默认「敏捷模板」；systemModule "业务模块&&12000355" → name&&id
    module_name, module_id = "", ""
    if "&&" in (c.get("systemModule") or ""):
        module_name, module_id = (c.get("systemModule") or "&&").split("&&", 1)
    
    # 需要业务验收：非技术研发部→是
    if need_biz_accept is None:
        dept = (info.get("deptName") or "").strip()
        need_biz_accept = "否" if dept == "技术研发部" else "是"
    biz_no = ""
    if need_biz_accept == "是":
        biz_acceptor = biz_acceptor or c.get("businessAccept") or info.get("userName") or ""
        biz_no = biz_acceptor.split("-")[-1].strip() if "-" in biz_acceptor else biz_acceptor.strip()

    # Story 名称
    if not story_name:
        story_name = demand_title
        if story_type == "配合测试":
            story_name = f"【配合测试】{demand_title}"

    # 父需求描述
    if not parent_desc:
        parent_desc = info.get("description") or ""

    payload = {
        "demandId": demand_id,
        "templateId": str(info.get("templateId") or "8888"),
        "summary": story_name,
        "systemId": c.get("systemId"),
        "systemName": c.get("systemName"),
        "projectId": c.get("projectId"),
        "projectName": c.get("projectName"),
        "bchildTypeCode": c.get("bchildTypeCode"),
        "systemLabelId": c.get("systemLabelId"),
        "systemModuleId": module_id,
        "systemModuleName": module_name,
        "isHaveDev": c.get("isHaveDev", 1),
        "devHeaderId": (c.get("devHeader") or {}).get("value"),
        "isHaveTest": c.get("isHaveTest", 1),
        "testHeaderId": (c.get("testHeader") or {}).get("value"),
        "isHaveUat": c.get("isHaveUat", 1),
        "isHaveUatBusinessAccept": "1" if need_biz_accept == "是" else "0",
        "businessAcceptor": biz_no,
        "isGrayUpgrade": "1" if impact_grayscale == "是" else "0",
        "isDesignWalkthrough": c.get("isDesignWalkthrough", 0),
        "description": parent_desc,
        "tId": c.get("tId"),
        "involveInfDev": 0,
        "isReverseBind": 0,
        "priority": "P4",
        "source": 1
    }
    if dry_run:
        return {"dry_run": True, "template": template["title"], "payload": payload}
    
    story_code = SESSION.api_post("/story-service/stcpstory/storydetail/create", payload)
    
    # 绑定至需求
    bind_res = SESSION.api_post("/story-service/stcpstory/storydetail/demandBindStory", {
        "demandId": demand_id,
        "storyNos": str(story_code)
    })
    
    return {
        "code": 200,
        "storyCode": story_code,
        "bindResult": bind_res,
        "systemName": c.get("systemName"),
        "summary": story_name
    }


def initiate_assessment(demand_id: str, dry_run: bool = False) -> dict:
    """发起技术评估（纯 API 直连，将状态推进至技术评估 boardId=15）"""
    sess = SESSION.get_session()
    ui = sess.get("user_info") or {}
    uid = ui.get("workno") or "050599"
    uname = ui.get("personname") or "吴进"
    
    if dry_run:
        return {"dry_run": True, "demandId": demand_id, "boardId": "15"}
        
    res = SESSION.api_post("/demand-service/discussNeed/updateDemandsubStatus", {
        "boardId": "15",
        "demandId": demand_id,
        "userId": uid,
        "userName": uname
    })
    return {"code": 200, "result": res, "boardId": "15"}



if __name__ == "__main__":
    import sys
    import json
    if len(sys.argv) < 2:
        print("用法: python3 platform_api.py <RID> [--ndw 0.3] [--review 通过 \"纪要\"] [--templates]")
        sys.exit(1)
    rid = sys.argv[1]
    args = sys.argv[2:]
    if "--templates" in args:
        tpls = list_templates()
        print(f"共 {len(tpls)} 个模板:")
        for t in tpls:
            print(f"  {t.get('title')} (id={t.get('id')})")
        sys.exit(0)
    if "--ndw" in args:
        v = args[args.index("--ndw") + 1]
        print(json.dumps(add_non_dev_work(rid, float(v), dry_run=True), ensure_ascii=False, indent=2))
    if "--review" in args:
        i = args.index("--review")
        result, minutes = args[i + 1], args[i + 2]
        print(json.dumps(save_review(rid, result, minutes, dry_run=True), ensure_ascii=False, indent=2))
    if "--story" in args:
        i = args.index("--story")
        sys_name = args[i + 1]
        print(json.dumps(save_story(rid, sys_name, dry_run=True), ensure_ascii=False, indent=2))
