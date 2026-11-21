#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ba-to-dev 提速提效工具：平台需求 JSON/MCP → 需求分析 MD 骨架一键生成（v1）。

解决 ba-to-dev Step1 手工解析 13 万+15 万字节平台 JSON 的轮次与 token 开销：
一次调用直接产出：
  1) Front Matter 骨架（对齐落盘规范：req_id/submitter/receiver/co_receiver/ndw/created/tags/domain/system/status）
  2) 一、需求背景 + 二、需求内容（平台 description HTML → 极简 Markdown，100% 平台原文）
  3) 需求属性速览表（状态/期望上线/标签/史诗/公司项目/灰度/监管报送…，供 Step2 快速路由判断）
  4) 评审纪要（slate 双编码自动解码 → 纯文本，供 gtht-accept-review 直接复用；--review 控制）

输入优先本地缓存（.chat/tmp_{reqid}_req.json + _flow.json，秒级），无缓存可 --online 走 kjptai MCP 直连。

用法:
    python3 extract_demand.py R2610270069                                  # 自动找本地缓存并输出骨架
    python3 extract_demand.py R2610270069 --out /tmp/R2610270069-skel.md   # 落盘到指定文件
    python3 extract_demand.py R2610270069 --online                         # 无缓存时 MCP 在线拉取
    python3 extract_demand.py R2610270069 --review --out mm.md             # 额外输出评审纪要解码文本
    python3 extract_demand.py --req x.json --flow y.json R2610270069       # 指定缓存文件

⚠️ system（改造范围）与分析类章节属 BA 判断产物，脚本不臆测，置空并提示补全。
"""
import base64
import html
import json
import os
import re
import sys
import urllib.parse

# 本地缓存默认搜索路径（相对运行目录为 /Volumes/Macintosh HD_Data/obsidian/.chat）
DEFAULT_CACHE = ".chat"

# 需求号权威格式：R + 10 位数字（如 R2606030038）。
# 2026-11-19 收紧：原入参允许 R\d{6,}，9 位残缺号可一路落盘，造成库内 20 份文档对
# R\d{10} 检索永久不可见，故此处对入参做强制校验并显式报错，不再静默接受。
REQ_ID_RE = re.compile(r"^R\d{10}$")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_cache(req_id, cache_dir=DEFAULT_CACHE):
    """自动定位 req/flow 缓存 JSON，返回 (req_path, flow_path) 或 (None, None)。"""
    req_p, flow_p = None, None
    for n in (f"tmp_{req_id}_req.json", f"{req_id}_req.json", f"{req_id}.json"):
        p = os.path.join(cache_dir, n)
        if os.path.exists(p):
            req_p = p
            break
    for n in (f"tmp_{req_id}_flow.json", f"{req_id}_flow.json"):
        p = os.path.join(cache_dir, n)
        if os.path.exists(p):
            flow_p = p
            break
    return req_p, flow_p


# ---------- slate 评审纪要解码 ----------

def decode_slate_fragment(text):
    """解码 data-slate-angular-fragment：base64 → utf-8 → URL unquote → json → 递归提取 text。"""
    try:
        raw = base64.b64decode(text)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        raw = urllib.parse.unquote(raw)
        tree = json.loads(raw)
    except Exception:
        return ""
    parts = []

    def walk(node):
        if isinstance(node, dict):
            t = node.get("text")
            if isinstance(t, str) and t:
                parts.append(t)
            for ch in node.get("children") or []:
                walk(ch)
        elif isinstance(node, list):
            for ch in node:
                walk(ch)

    walk(tree)
    return "".join(parts).strip()


# ---------- HTML → 极简 Markdown ----------

def html_to_md(html_text):
    """平台 description HTML → 极简 Markdown（不引第三方库）。

    <h4><strong>一、需求背景</strong></h4> → #### **一、需求背景**
    加粗/斜体保留，样式 span/p/br/li 归一，合并多余空行。
    """
    t = html_text or ""
    # 保留加粗/斜体标记（先于标签剥离）
    t = re.sub(r"<strong[^>]*>(.*?)</strong>", lambda m: "**" + m.group(1) + "**", t, flags=re.S)
    t = re.sub(r"<em[^>]*>(.*?)</em>", lambda m: "*" + m.group(1) + "*", t, flags=re.S)
    # 标题分级（h4 内容若已含 ** 加粗则不重复包裹，避免 `#### ****x****`）
    t = re.sub(r"<h4[^>]*>(.*?)</h4>", lambda m: "\n\n#### " + _heading(m.group(1)) + "\n\n", t, flags=re.S)
    t = re.sub(r"<h3[^>]*>(.*?)</h3>", lambda m: "\n\n### " + re.sub(r"<[^>]+>", "", m.group(1)).strip() + "\n\n", t, flags=re.S)
    # 块级换行
    t = re.sub(r"</p>", "\n", t, flags=re.I)
    t = re.sub(r"<p[^>]*>", "\n", t, flags=re.I)
    t = re.sub(r"</div>", "\n", t, flags=re.I)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"<li[^>]*>", "\n- ", t, flags=re.I)
    t = re.sub(r"</li>", "", t, flags=re.I)
    t = re.sub(r"<ul[^>]*>|<ol[^>]*>|</ul>|</ol>", "\n", t, flags=re.I)
    # 剥离残留标签与实体
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t).replace("\u200b", "").replace("\xa0", " ")
    # 归一空行
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _heading(s):
    """h4 内容规范化：剥残留标签；已含 ** 加粗则不重复包裹。"""
    s = re.sub(r"<[^>]+>", "", s or "").strip()
    if not s:
        return ""
    if s.startswith("**") and s.endswith("**"):
        return s
    return f"**{s}**"


# ---------- 字段映射 ----------

def split_display(s):
    """submitterDisplay '金渤文-112936' → 姓名 '金渤文'；'吴进、许允执' → '吴进, 许允执'。"""
    if not s:
        return ""
    return s.split("-")[0].replace("、", ", ").strip()


def build_front_matter(detail, ndw, domain, system, req_id):
    from datetime import date
    # submitter: 姓名 (部门) / receiver·co_receiver: 保留「姓名-工号」原样，顿号→逗号
    submitter = detail.get("submitterDisplay", "") or ""
    submitter = submitter.split("-")[0].strip()
    dept = detail.get("department", "")
    if submitter and dept:
        submitter = f"{submitter} ({dept})"
    receiver = (detail.get("receiverDisplay", "") or "").replace("、", ", ").strip()
    co_receiver = (detail.get("commonReceiverDisplay", "") or "").replace("、", ", ").strip()
    demand_tag = detail.get("demandTag", "") or ""
    tags = ["需求"]
    if domain:
        tags.append(domain)
    if demand_tag and demand_tag not in tags:
        tags.append(demand_tag)
    created = (detail.get("createTime") or "")[:10]
    lines = [
        "---",
        f"req_id: {req_id}",
        f"submitter: {submitter}",
        f"receiver: {receiver}",
        f"co_receiver: {co_receiver}",
        f"ndw: {ndw}",
        f"created: {created}",
        f"updated: {date.today().isoformat()}",
        f"tags: [{', '.join(tags)}]",
        f"domain: {domain}",
        f"system: {system or '[]'}  # TODO 待 Step2 三域检索后补全改造范围系统",
        "status: 需求分析",
        "---",
        "",
    ]
    return "\n".join(lines)


# ---------- 主流程 ----------

def extract_description(req_data, flow_data):
    """优先 req.markdown '### 描述' 段；缺则 flow.demand.description。返回原始 HTML。"""
    if req_data:
        md = req_data.get("markdown") or ""
        i = md.find("### 描述")
        if i >= 0:
            seg = md[i + len("### 描述"):]
            # 截到下一个二级/三级标题（若无则到结尾）
            m = re.search(r"\n#{2,3} ", seg)
            if m:
                seg = seg[: m.start()]
            return seg
    if flow_data:
        dem = (flow_data.get("data") or {}).get("data") or {}
        desc = dem.get("demand", {}).get("description")
        if desc:
            return desc
    return ""


def review_minutes_text(req_data):
    """解码 reviewMinutes[0].mettingSummary → (reviewTypeName, title, 纯文本, 原始HTML)。"""
    rms = (req_data or {}).get("reviewMinutes") or []
    if not rms:
        return None
    rm = rms[0]
    summ = rm.get("mettingSummary") or ""
    m = re.search(r'data-slate-angular-fragment="([^"]+)"', summ)
    if m:
        plain = decode_slate_fragment(m.group(1))
    else:
        plain = html_to_md(summ)
    return {
        "type": rm.get("reviewTypeName", ""),
        "title": rm.get("title", ""),
        "text": plain,
        "html": summ,
    }


def attr_table(detail):
    """需求属性速览表（供 Step2 快速路由判断：轻量/纯配置/是否影响灰度等）。"""
    rows = [
        ("需求编号", detail.get("demandId", "")),
        ("标题", detail.get("summary", "")),
        ("需求类型/子类型", f"{detail.get('demandTypeName','')} / {detail.get('subdivisionTypeName','')}"),
        ("状态", detail.get("status", "")),
        ("优先级", detail.get("priority", "")),
        ("一级领域", detail.get("groupName", "")),
        ("提出部门", detail.get("department", "")),
        ("提交人", detail.get("submitterDisplay", "")),
        ("业务主管", detail.get("businessDirectorDisplay", "")),
        ("受理人", detail.get("receiverDisplay", "")),
        ("共同受理人", detail.get("commonReceiverDisplay", "")),
        ("史诗", f"{detail.get('epicCode','-')} {detail.get('epicName','')}".strip()),
        ("需求标签", detail.get("demandTag", "-")),
        ("期望上线时间", detail.get("wishDate", "-")),
        ("评审预计交付", detail.get("reviewDeliveryTime", "-")),
        ("创建时间", detail.get("createTime", "")),
        ("公司项目", detail.get("companyProjectDisplay", "-")),
        ("需求价值量", detail.get("storyValue", "-")),
        ("是否暂停", detail.get("suspendedDisplay", "-")),
        ("是否监管报送", detail.get("regulatoryReportingDisplay", "-")),
        ("是否影响灰度", detail.get("grayUpgradeDisplay", "-")),
        ("当前 OA 节点", detail.get("oaNodeDisplay", "-")),
    ]
    out = ["| 字段 | 内容 |", "| --- | --- |"]
    for k, v in rows:
        out.append(f"| {k} | {str(v).replace('|', '\\|')} |")
    return "\n".join(out) + "\n"


def main():
    args = sys.argv[1:]
    # 2026-11-19 收紧：先把任意形态入参（裸号 / 20260414-R2603270060 / 平台链接）归一，
    # 再强制要求 R + 10 位。原实现接受 R\d{6,}，9 位残缺号可一路落盘 → 文档对 R\d{10} 检索隐身。
    raw = next((a for a in args if re.search(r"R\d+", a)), None)
    if not args or not raw:
        print(__doc__)
        return 1
    cand = re.findall(r"R\d+", raw)
    ok = [c for c in cand if REQ_ID_RE.match(c)]
    if not ok:
        print(f"✗ 需求号非法: {raw} → 解析到 {cand or '无'}。"
              f"需求号必须是 R + 10 位数字（如 R2606030038），请回需求原文或平台链接核对。",
              file=sys.stderr)
        return 2
    if len(set(ok)) > 1:
        print(f"✗ 入参含多个合法需求号 {sorted(set(ok))}，请只保留一个。", file=sys.stderr)
        return 2
    req_id = ok[0]
    # 参数解析
    def flag(name, default=None):
        if name in args:
            i = args.index(name)
            return args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith("--") else default
        return default
    out = flag("--out")
    ndw = flag("--ndw", "0.5")
    domain = flag("--domain", "")
    system = flag("--system", "")
    online = "--online" in args
    want_review = "--review" in args
    req_path = flag("--req", None) or flag("-r", None)
    flow_path = flag("--flow", None) or flag("-f", None)

    if not req_path and not flow_path and not online:
        cache_dir = flag("--cache", DEFAULT_CACHE)
        req_path, flow_path = find_cache(req_id, cache_dir)
        if not req_path:
            # 尝试全局 .chat 下任意需求缓存
            req_path, flow_path = find_cache(req_id, ".")

    req_data = flow_data = None
    if req_path and os.path.exists(req_path):
        try:
            req_data = load_json(req_path).get("data") or {}
            if not isinstance(req_data, dict):
                req_data = json.load(open(req_path, encoding="utf-8"))
        except Exception as e:
            print(f"⚠ req 缓存解析失败({req_path}): {e}", file=sys.stderr)
            req_data = None
    if flow_path and os.path.exists(flow_path):
        try:
            flow_data = load_json(flow_path)
        except Exception as e:
            print(f"⚠ flow 缓存解析失败({flow_path}): {e}", file=sys.stderr)
            flow_data = None

    if (req_data is None and flow_data is None):
        if online:
            # MCP 在线拉取：import epic-to-sheet 的 kjptai_mcp
            ep = os.path.expanduser("~/.chat/skills/epic-to-sheet/scripts")
            if ep not in sys.path:
                sys.path.insert(0, ep)
            import kjptai_mcp
            client = kjptai_mcp.KjptaiClient()
            r = kjptai_mcp.query_requirement_detail(client, req_id)
            req_data = r.get("data") or {}
            try:
                flow_res = client.call("query_requirement_flow", {"demandId": req_id})
                flow_data = kjptai_mcp.extract_text(flow_res)
            except Exception as e:
                print(f"⚠ flow 拉取失败: {e}", file=sys.stderr)
            print(f"⏱ MCP 在线拉取完成（{req_id}）", file=sys.stderr)
        else:
            print(f"✗ 未找到 {req_id} 的本地缓存（{req_path or DEFAULT_CACHE}），请先缓存 req/flow JSON，或加 --online 在线拉取", file=sys.stderr)
            return 2

    detail = {}
    if req_data and isinstance(req_data.get("detail"), dict):
        detail = req_data["detail"]
    elif flow_data:
        dem = (flow_data.get("data") or {}).get("data") or {}
        d0 = dem.get("demand") or {}
        for k, v in d0.items():
            detail.setdefault(k, v)

    # 领域推断：--domain 未给时按一级领域映射
    if not domain:
        g = detail.get("groupName", "")
        domain = {"信用": "信用两融", "参数": "交易参数", "清算": "清算与对账"}.get(g, g or "信用两融")

    doc_title = detail.get("summary") or req_id

    body = []
    body.append(build_front_matter(detail, ndw, domain, system, req_id))
    body.append(f"# {doc_title}")
    body.append("")

    desc_html = extract_description(req_data, flow_data)
    if desc_html:
        md = html_to_md(desc_html)
        # 若无显式“一、需求背景”分节，则套用标准骨架
        if "需求背景" not in md:
            body.append("#### **一、需求背景**\n")
            body.append(md)
            body.append("")
            body.append("#### **二、需求内容**\n")
            body.append("")
            body.append("> ⚠ 平台描述未显式区分背景/内容两节，以上原文来自平台 description，请按需拆分。")
        else:
            body.append(md)
    else:
        body.append("#### **一、需求背景**\n")
        body.append("> ⚠ 未获取到平台描述正文（缓存缺失 description），请用平台详情页补录。")
        body.append("")
        body.append("#### **二、需求内容**\n")
    body.append("")
    body.append("---")
    body.append("")

    # 属性速览（附于骨架尾，供 Step2 快速路由；落盘前应删除或以注释形式保留）
    body.append("---")
    body.append("")
    body.append("<!-- 附：平台属性速览（Step2 快速路由参考，落盘前删除） -->")
    body.append("")
    body.append(attr_table(detail))

    if want_review:
        rm = review_minutes_text(req_data)
        if rm and rm["text"]:
            body.append("## 二、评审纪要（解码原文，供评审纪要规范化小节参考）")
            body.append("")
            body.append(f"> reviewType: {rm['type']}")
            body.append("")
            body.append(rm["text"])
            body.append("")

    content = "\n".join(body)
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✓ 骨架已生成: {out}（{len(content)} 字符）")
    else:
        print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
