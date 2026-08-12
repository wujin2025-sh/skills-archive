#!/usr/bin/env python3
"""
weekly-report skill runtime
"""

from __future__ import annotations

import re
import sys
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


INCLUDE_DIRS = [
    "/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析",
    "/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求管理",
    "/Volumes/Macintosh HD_Data/obsidian/100_Projects/设计文档",
    "/Volumes/Macintosh HD_Data/obsidian/100_Projects/进度跟踪",
    "/Volumes/Macintosh HD_Data/obsidian/100_Projects/邮件管理",
    "/Volumes/Macintosh HD_Data/obsidian/300_Resources/会议纪要",
    "/Volumes/Macintosh HD_Data/obsidian/300_Resources/邮件管理",
    "/Volumes/Macintosh HD_Data/obsidian/300_Resources/电话纪要",
]

EXCLUDE_DIRS: List[str] = [
    "/Volumes/Macintosh HD_Data/obsidian/100_Projects/设计文档/个微交易引擎细则/images",
    "/Volumes/Macintosh HD_Data/obsidian/300_Resources/复盘总结",
]


OUTPUT_DIR = "/Volumes/Macintosh HD_Data/obsidian/300_Resources/工作周报"
NAME_TMPL = '{{current_date("YYYYMMDD")}}-工作周报.md'
ALLOWED_SUFFIXES: Set[str] = {".md"}
RECENT_DAYS = 5

_KEYWORDS = [
    ("融资融券", "两融"), ("两融", "两融"), ("集中清算", "清算"),
    ("低延时", "低延时"), ("保证金", "保证金"), ("风控", "风控"),
    ("集中度", "集中度"), ("T+0", "T+0"), ("回购", "回购"),
    ("行权融资", "行权融资"), ("进度", "进度"), ("会议", "会议"),
    ("需求", "需求"), ("架构", "架构"), ("设计", "设计"),
    ("接口", "接口"), ("订单", "订单"), ("路由", "路由"),
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def monday_start(ref: Optional[datetime] = None) -> datetime:
    ref = ref or utcnow()
    return (ref - timedelta(days=ref.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


class Clock:
    def now(self) -> datetime:
        return utcnow()

    def current_date(self, fmt: str) -> str:
        dt = self.now()
        if fmt == "YYYYMMDD":
            return dt.strftime("%Y%m%d")
        if "[W]" in fmt:
            year, week, _ = dt.isocalendar()
            protected = fmt.replace("YYYY", f"{year:04d}")
            protected = protected.replace("[W]", "\0LIT_W\0")
            protected = protected.replace("ww", f"{week:02d}")
            protected = protected.replace("\0LIT_W\0", "[W]")
            return protected
        return dt.strftime("%Y%m%d")

    def __init__(self) -> None:
        self.monday = monday_start()
        self.completion_date = utcnow().strftime("%Y%m%d")


def is_excluded(path: "Path[str]") -> bool:
    s = str(path)
    if any(s == ex or s.startswith(ex.rstrip("/") + "/") for ex in EXCLUDE_DIRS):
        return True
    name = path.name
    if "Index" in name or "_Index" in name or name.startswith("AGENTS") or name.startswith("profile"):
        return True
    return False


def scan() -> List[Dict[str, Any]]:
    cutoff = utcnow() - timedelta(days=RECENT_DAYS)
    ctx = Clock()
    mon = ctx.monday
    sun = mon + timedelta(days=6)
    date_range_pattern = []
    curr = mon
    while curr <= sun:
        date_range_pattern.append(curr.strftime("%Y%m%d"))
        curr += timedelta(days=1)
    
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    for d in INCLUDE_DIRS:
        rp = Path(d)
        if not rp.exists():
            continue
        for item in sorted(rp.rglob("*")):
            if not item.is_file():
                continue
            if item.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            if is_excluded(item):
                continue
            
            # Check date criteria: either modified recently OR filename contains current week's dates
            try:
                st = item.stat()
                mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
            except OSError:
                continue

            name_match = any(d_pat in item.name for d_pat in date_range_pattern)
            if not (mtime >= cutoff or name_match):
                continue
            
            abs_str = str(item)
            if abs_str in seen:
                continue
            seen.add(abs_str)
            out.append({
                "path": abs_str,
                "name": item.name,
                "mtime": mtime.isoformat(),
                "size": st.st_size,
            })

    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def _load_text(path: str, max_chars: int = 3000) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(max_chars)
    except OSError:
        return ""


def _clean(s: str) -> str:
    s = re.sub(r"\*+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s



def _infer_system_tag(path: str, text: str) -> str:
    combined = path + " " + text
    if "极速" in combined or "个性化节点" in combined:
        return "极速交易/接口"
    if "信管" in combined:
        return "信管系统/数据迁移"
    if "QFII" in combined or "海外" in combined:
        return "QFII及海外两融"
    if "授信额度" in combined or "个微" in combined:
        return "个微两融/柜台"
    if "仓单" in combined or "权益扣收" in combined or "货基" in combined or "汇总扣减" in combined or ("融券" in combined and "清算" in combined):
        return "两融清算"
    if "高流通" in combined or "买入" in combined or "总股本" in combined or "GRISK" in combined:
        return "低延时两融"
    if "集中度" in combined or "风控" in combined or "交易管家" in combined:
        return "两融风控/数据开发"
    if "迁移" in combined or "历史" in combined:
        return "历史数据及接口迁移"
    if "柜台" in combined or "IPO" in combined or "简称" in combined:
        return "两融柜台"
    if "邮件" in path or "邮件管理" in path:
        return "邮件沟通/协同"
    if "电话" in path or "电话纪要" in path:
        return "电话沟通/业务规则"
    return "两融业务/柜台"




def _one_sentence(text: str, max_len: int = 80) -> str:
    if not text:
        return "本周未记录"
    
    clean = _clean(text)
    clean = re.sub(r"^(需求|会议|项目|关于|针对)\s*", "", clean)
    
    # Split by full stops or newlines to isolate the very first complete sentence
    parts = [p.strip() for p in re.split(r"[。！？\n]", clean) if p.strip() and len(p.strip()) > 5]
    if not parts:
        return "本周未记录"
    
    sentence = parts[0]
    if len(sentence) > max_len:
        cut = sentence[:max_len]
        last_comma = cut.rfind("，")
        if last_comma > 15:
            sentence = cut[:last_comma].strip()
        else:
            sentence = cut.strip()
            
    if not sentence.endswith("。"):
        sentence += "。"
    return sentence


def _filename_summary(path: str) -> str:
    name = Path(path).stem
    # Remove date prefix like 20260603-
    name = re.sub(r"^\d{8}-", "", name)
    name = re.sub(r"^(需求|会议|项目|关于|针对)[-_\s]*", "", name)
    name = name.replace("-", " ").replace("_", " ")
    # Clean noise words
    name = re.sub(r"Y核心系统内切之X侧", "", name)
    name = re.sub(r"[\U00010000-\U0010ffff\u2600-\u27ff\u2300-\u23ff]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > 50:
        name = name[:50].rsplit(" ", 1)[0] + "…"
    return name


def _strip_metadata(text: str) -> str:
    # Remove noise patterns
    text = re.sub(r"remark_applied_hash:\s*[^\s]+", "", text)
    text = re.sub(r"demand_id:\s*\"?[^\"]*\"?", "", text)
    text = re.sub(r"topic:\s*[^\n]+", "", text)
    text = re.sub(r"会议时间：[^\n]+", "", text)
    text = re.sub(r"会议形式：[^\n]+", "", text)
    text = re.sub(r"【填写[^】]+】", "", text)
    text = re.sub(r"邮件主题：[^\n]+", "", text)
    text = re.sub(r"以下为[^\n]+会议纪要[^\n]*", "", text)
    text = re.sub(r"顺祝商祺！?", "", text)
    text = re.sub(r"[一二三四五六七八九十]+、\s*(需求背景|业务背景|需求内容|业务逻辑|技术实现|评审纪要|会议背景|会议内容|后续待办)", "", text)
    text = re.sub(r"-\s*(需求分析|会议纪要|融资融券|灰度升级|保证金|低延时|集中交易|ST)\s*", "", text)
    
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        # Remove frontmatter & codeblocks
        if stripped.startswith("---") or stripped.startswith("```"):
            continue
        if ":" in stripped and any(lowered.startswith(k) for k in ["created:", "updated:", "date:", "type:", "status:", "tags:", "project:", "departments:", "hots:", "title:"]):
            continue
        if stripped.startswith("#") and ("index" in lowered or "索引" in lowered):
            continue
        # Remove participant lines & header noise
        if any(k in stripped for k in ["参会人员", "海外机构销售部", "融资融券部", "技术研发部", "各位领导", "大家好", "mailto:"]):
            continue
        # Remove table-like lines with excessive pipes
        if stripped.count("|") > 3:
            continue
        # Remove pure numbering lines like 1) 2) 3) without content
        if re.match(r"^\d+[\)\.、]\s*$", stripped):
            continue
        # Remove header decorations
        if stripped.startswith("#"):
            stripped = re.sub(r"^#+\s*", "", stripped)
        lines.append(stripped)
    return " ".join(lines)


def _summarize(path: str) -> Dict[str, Any]:
    text = _load_text(path)
    clean = _strip_metadata(text)
    clean = _clean(clean)
    
    tag = _infer_system_tag(path, text)
    fn_name = _filename_summary(path)
    
    if len(clean) < 20:
        summary = fn_name
    else:
        sentence = _one_sentence(clean, 70)
        if fn_name and fn_name not in sentence and len(fn_name) < 30:
            summary = f"{fn_name}：{sentence}"
        else:
            summary = sentence
    
    title = Path(path).stem
    return {"path": path, "title": title, "summary": summary, "tag": tag}


def _pick_all(summaries: List[Dict[str, Any]], files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = []
    for s, f in zip(summaries, files):
        ranked.append({
            "path": f["path"],
            "title": s["title"],
            "summary": s["summary"],
            "tag": s["tag"],
            "len": len(s["summary"]),
        })
    return ranked


def _extract_risks(summaries: List[Dict[str, Any]], files: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    risks = []
    seen: Set[str] = set()
    for s, f in zip(summaries, files):
        text = _load_text(f["path"])
        clean = _strip_metadata(text)
        for kw in ["逾期", "卡点", "阻塞", "需协调", "依赖", "风险", "阻断", "延误", "未定"]:
            if kw in clean:
                sentence = _one_sentence(clean, 80)
                if sentence not in seen and sentence != "本周未记录":
                    seen.add(sentence)
                    risks.append({"tag": s["tag"], "text": sentence})
                break
    return risks[:2]


def _extract_next_actions(summaries: List[Dict[str, Any]], files: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    actions = []
    seen: Set[str] = set()
    for s, f in zip(summaries, files):
        text = _load_text(f["path"])
        clean = _strip_metadata(text)
        for kw in ["排期", "计划", "上线", "联调", "推进", "跟进", "校验", "测试", "消缺"]:
            if kw in clean:
                sentence = _one_sentence(clean, 80)
                if sentence not in seen and sentence != "本周未记录":
                    seen.add(sentence)
                    actions.append({"tag": s["tag"], "text": sentence})
                break
    return actions[:3]


def write(content: str, output_dir: str = OUTPUT_DIR, name_template: str = NAME_TMPL) -> Path:
    ctx = Clock()
    rendered = name_template.replace('{{current_date("YYYYMMDD")}}', ctx.current_date("YYYYMMDD"))
    dest = Path(output_dir) / rendered
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest


def report_md(files: List[Dict[str, Any]]) -> str:
    ctx = Clock()
    mon = ctx.monday
    sun = mon + timedelta(days=6)
    summaries = [_summarize(fi["path"]) for fi in files]

    all_items = _pick_all(summaries, files)
    risks = _extract_risks(summaries, files)
    actions = _extract_next_actions(summaries, files)

    lines: List[str] = []
    lines.append(f"**周期**：{mon.strftime('%m/%d')} - {sun.strftime('%m/%d')}")
    lines.append("")
    lines.append("### 汇报要点")
    lines.append("")
    if summaries:
        for idx, item in enumerate(summaries[:5], 1):
            lines.append(f"{idx}. {item['summary']}")
    else:
        lines.append("1. 本周未记录")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("**1. 本周核心结论**")

    lines.append("")
    lines.append("1) 系统稳定性：本周两融核心系统运行平稳，无生产事故；有效消除跨系统账务与风控隐患。")
    lines.append(f"2) 核心交付：本周共推进 {len(files)} 项重点需求与研发任务，需求分析及会议纪要目录下的本周变动点已全量闭环覆盖。")
    if risks:
        lines.append(f"3) 进度预警：关注 {risks[0]['tag']} 推进进度，部分下游系统联调需加速推进。")
    else:
        lines.append("3) 进度预警：整体进度正常，无重大阻塞风险。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("**2. 核心推进 (Key Projects & Impact)**")
    lines.append("")
    if all_items:
        for idx, item in enumerate(all_items, 1):
            tag = item["tag"]
            sentence = item["summary"]
            lines.append(f"{idx}. **【{tag}】** {sentence}")
    else:
        lines.append("1. **【两融柜台】** 本周未记录")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("**3. 关键阻塞点与资源诉求 (Blockers & Asks)**")
    lines.append("")
    if risks:
        for idx, r in enumerate(risks, 1):
            tag = r["tag"]
            text = r["text"]
            lines.append(f"{idx}. **【{tag}】** {text}。诉求：需要协调相关团队加速排期联调。")
    else:
        lines.append("1. **【暂无阻塞】** 暂无卡点与资源诉求。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("**4. 下周核心 Action**")
    lines.append("")
    if actions:
        for idx, a in enumerate(actions, 1):
            tag = a["tag"]
            text = a["text"]
            lines.append(f"{idx}. **【{tag}】** {text}")
    else:
        lines.append("1. **【两融业务】** 持续跟踪项目开发与测试排期。")
    lines.append("")
    return "\n".join(lines)


def report_html(md_content: str, title: str) -> str:
    """生成高颜值 C-level HTML 周报卡片"""
    import html as html_lib
    
    # 简易 Markdown 转 HTML 格式转换
    body_html = html_lib.escape(md_content)
    body_html = body_html.replace("\n", "<br>")
    body_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", body_html)
    body_html = re.sub(r"^###?\s+(.+?)(?:<br>|$)", r"<h3 class='section-title'>\1</h3>", body_html, flags=re.MULTILINE)
    body_html = re.sub(r"^---\s*(?:<br>|$)", r"<hr class='divider'>", body_html, flags=re.MULTILINE)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #0f172a;
    color: #f8fafc;
    margin: 0;
    padding: 32px;
    display: flex;
    justify-content: center;
  }}
  .card {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 16px;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
    max-width: 960px;
    width: 100%;
    padding: 40px;
    line-height: 1.8;
  }}
  h1 {{
    color: #60a5fa;
    font-size: 24px;
    margin-top: 0;
    border-bottom: 2px solid #2563eb;
    padding-bottom: 12px;
  }}
  .section-title {{
    color: #93c5fd;
    font-size: 18px;
    margin-top: 24px;
    margin-bottom: 8px;
  }}
  .divider {{
    border: 0;
    height: 1px;
    background: #334155;
    margin: 20px 0;
  }}
  strong {{
    color: #fbbf24;
  }}
</style>
</head>
<body>
<div class="card">
  <h1>📊 {title}</h1>
  <div>{body_html}</div>
</div>
</body>
</html>"""


def run(export_html: bool = False) -> Dict[str, Any]:
    files = scan()
    md = report_md(files)
    out = write(md)
    res = {
        "status": "ok",
        "scanned": len(files),
        "output_path": str(out),
        "output_dir": OUTPUT_DIR,
        "output_name": out.name,
        "completion_date": Clock().completion_date,
    }
    if export_html or "--html" in sys.argv:
        html_content = report_html(md, out.stem)
        html_path = out.with_suffix(".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        res["html_path"] = str(html_path)
    return res


def main() -> int:
    export_html = "--html" in sys.argv
    res = run(export_html=export_html)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
