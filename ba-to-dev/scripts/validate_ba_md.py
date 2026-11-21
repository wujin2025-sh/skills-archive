#!/usr/bin/env python3
"""ba-to-dev 需求分析 MD 落盘前规范校验与自动修复脚本。

用法:
  python3 validate_ba_md.py <file.md> [--fix]
  python3 validate_ba_md.py <dir>   [--fix]   # 目录则递归校验全部 .md
  python3 fix_reqid_filenames.py <dir> [--apply]  # 历史文件名补号（9 位残缺号 → R+10 位），默认 dry-run

规则清单:
  R1 (P0) 文件名规范      : YYYYMMDD-R26xxxxxxxx-标题.md；需求号必须 R + 10 位，标题首字符允许中文/字母/【
  R1b(P0) 编号一致性       : 文件名中的需求号必须与 Front Matter 的 req_id 逐字一致（2026-11-19 新增；
                             历史缺口=文件名写 9 位、req_id 写 10 位互不报错，导致同号截断撞名、检索隐身）
  R2 (P0) Front Matter    : 必须含 req_id/submitter/ndw/created/updated/tags/domain/system/status 九项
  R3 (P0) 评审纪要 9 项    : 需求补充说明/改造范围/各系统改造功能/前端界面/接口交互/业务参数/灰度上线关注/联测涉及系统/业务关注点 逐项齐全；并校验第 2 项【改造范围】与第 8 项【联测涉及系统】绝对互斥（改造范围内系统不得在联测项重复出现，涉及改造必然联测）
  R4 (P0) 纪要末尾红线    : 严禁「涉及系统：」行；「预计上线日期」之后不得再输出其他内容行（附件清单/--- 分隔线/「评审决策日志（可选）」小节除外，附件清单标题支持纯文本或 **加粗**；评审决策日志豁免见 2026-10-12）
  R5 (P2) 分点缩进统一    : 9 项小节分点 (N) 统一 3 空格缩进；「各系统改造功能」的 ① 功能点统一 8 空格缩进（--fix 自动修复）
  R6 (P1) 表格前需空行    : 表格起始行（第一个以 | 开头的行）前一行须为空行或 --- 分隔线，否则 Obsidian/GFM 不识别为表格（2026-10-12 新增）
  R7 (P1) 系统名门禁      : 评审纪要【改造范围】+【各系统改造功能】出现的含「系统」中文名须能在 system_list.csv 第一列精确匹配；不在清单则告警（疑似非本组/厂商系统需核实责任方，见 P0#19）
  R8 (P1) file:// 链接存在: 文档内 file:// 本地链接逐一 test -f（自动解码 %20、剥离 :行号 伪影）；指向不存在的文件则告警死链
  R9 (P1) 双链文件存在    : [[文件名]] 双链（含日期-R号 命名）需在文档所在目录找到对应 .md 文件，否则告警悬空双链
  R10(P0) 六段闭环交付    : 一需求背景/二需求内容/三技术实现/四需求矛盾审计/评审纪要/相关链接 六段必齐（2026-11-20 新增，
                            借鉴 universal-requirement-review「发送前强制检查」）；三技术实现需含（一）~（四）子小节；
                            标题下严禁「需求概要/元信息」引用块。缺任一即判定文档未达"可一次交付"冻结完整版。

-- content-check 说明（2026-11-12 新增强化，防系统性幻觉）:
  * R7 依赖权威系统清单 /Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/system_list.csv（技能 P0#3 挂载，编码为 UTF-8）；
  * R7/R8/R9 为「内容级」辅助校验，弥补 validate 原只查格式不查真伪的认知盲区；均以 P1 提示而非 P0 阻断，避免非本组/厂商系统（合法）产生误导性失败。

--fix 行为（2026-10-08 修订）:
  * R4 违禁「涉及系统：」行 → 实际删除并写盘（修复成功不视为失败）；
  * R5 分点缩进 → 实际统一并写盘（修复成功不视为失败）；
  * 被 --fix 成功修复的项在输出中标记「→ 已修复（--fix）」，不计入失败。

退出码: 0 = 全部通过（含经 --fix 修复后无残留问题）; 1 = 存在未修复 FAIL; 2 = 参数/IO 错误
"""
import re
import sys
import os
import glob
import urllib.parse

# 权威系统清单（技能 P0#3 挂载，2026-11-12 硬化绝对路径）：第一列=系统中文全称
SYSTEM_CSV = "/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/system_list.csv"

REQ_KEYS = ["req_id", "submitter", "ndw", "created", "updated",
            "tags", "domain", "system", "status"]
REVIEW_ITEMS = ["需求补充说明", "改造范围", "各系统改造功能", "前端界面",
                "接口交互", "业务参数", "灰度上线关注", "联测涉及系统", "业务关注点"]
# 2026-11-19 收紧：需求号为 R + 10 位数字（如 R2606030038）。原 R\d{9,11} 会放行 9 位残缺号，
# 导致这类文档对 R\d{10} 检索永久不可见（库内曾累积 20 份，其中 2 对因截断撞成同号、实为 4 个不同需求）。
# 2026-11-19 放宽标题首字符：允许中文 / 英文字母（IPO、GRISK 等缩写标题）/ 全角左括号【，
# 原规则要求纯中文开头，把 6 份合规文档误判为不合规，门禁可信度因此受损。
FN_RE = re.compile(r"^\d{8}-R\d{10}-[\u4e00-\u9fffA-Za-z【].*\.md$")
REQ_ID_RE = re.compile(r"^R\d{10}$")
ITEM_RE = re.compile(r"^\s*(\d+)\.\s*\*\*(.+?)\*\*", re.M)
POINT_RE = re.compile(r"^(\s*)\((\d+)\)\s*(.*)$")
CIRCLE_RE = re.compile(r"^(\s*)([①②③④⑤⑥])\s*(.*)$")
TS_RE = re.compile(r"^预计上线日期：")
SEC_NO_RE = re.compile(r"^\s*\d+\.")
# R4 附件清单标题：支持「附件清单」「**附件清单**」两种写法（2026-10-08 放宽，避免加粗标题误报）
ATTACH_RE = re.compile(r"^(\*\*)?附件清单(\*\*)?$")
# 被 --fix 成功修复的项的标记文案（main 统计时不计入失败）
FIXED_MARK = "→ 已修复（--fix）"


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def parse_frontmatter(text):
    """返回 (keys, frontmatter结束索引); 无 front matter 返回 (None, 0)"""
    if not text.startswith("---"):
        return None, 0
    end = text.find("\n---", 3)
    if end == -1:
        return None, 0
    block = text[3:end]
    keys = set()
    for line in block.splitlines():
        m = re.match(r"^([A-Za-z_][\w]*)\s*:", line.strip())
        if m:
            keys.add(m.group(1))
    return keys, end + 4


def review_region_bounds(text):
    """返回 (start, end) —— 评审纪要章节内容区间 [start, end)，
    start 指向标题行后的首个字符，end 指向「相关链接」行首或文件尾。
    """
    m = re.search(r"^#{2,4}\s*(\*\*)?评审纪要(\*\*)?\s*$", text, re.M)
    if not m:
        return None
    start = text.find("\n", m.end()) + 1
    m2 = re.search(r"^(#{2,4}\s*)?(\*\*)?相关链接(\*\*)?\s*$", text[start:], re.M)
    end = start + m2.start() if m2 else len(text)
    return start, end


def _is_fixed(problem):
    """problem: (rule, level, desc) —— 判断该问题是否已被 --fix 修复"""
    return FIXED_MARK in problem[2]


def load_system_names():
    """读取权威系统清单第一列，返回 {系统中文全称} 集合（UTF-8 编码，第 1 行为表头跳过）。
    文件缺失/读失败时返回 None（主调对该文件类校验降级跳过，不阻塞 validate）。"""
    try:
        with open(SYSTEM_CSV, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return None
    names = set()
    for idx, line in enumerate(lines):
        if idx == 0:
            continue  # 表头
        first = line.split(",", 1)[0].strip()
        if first:
            names.add(first)
    return names if names else None


# 含「系统」二字的中文系统名，用于 R7 门禁（排除「系统」泛称、front matter 短码等噪声）
_SYS_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,50}系统(?:[（(][^）)]+[）)])?")


def _extract_sys_tokens(text):
    """从评审纪要区域提取候选中文系统名 tokens（含「系统」且至少 2 个汉字前缀）。
    排除：评审纪要小节标题（REVIEW_ITEMS）、「无XXX」否定表达、泛称「系统」."""
    out = set()
    for m in _SYS_TOKEN_RE.finditer(text):
        tok = m.group(0).strip()
        if tok in ("系统",) or tok in REVIEW_ITEMS:
            continue
        if tok.startswith("无"):  # 如「无跨系统」「无涉及系统」
            continue
        out.add(tok)
    return out


def check_file(path, fix=False):
    name = os.path.basename(path)
    problems = []  # (rule, level, desc)
    text = load(path)

    # ---- R1 文件名 ----
    if not FN_RE.match(name):
        title = name.split("-", 2)[2] if name.count("-") >= 2 else ""
        if title.startswith("】"):
            problems.append(("R1", "P0",
                             f"文件名标题缺前半括号: {name}（标题以「】」开头，应为「【…】」）"))
        else:
            problems.append(("R1", "P0",
                             f"文件名不合规: {name}，应为 YYYYMMDD-R26xxxxxxxx-纯中文标题.md（需求号 = R + 10 位）"))

    # ---- R1b 文件名需求号 vs Front Matter req_id 一致性（P0，2026-11-19 新增）----
    # 历史缺口：文件名写 9 位、Front Matter 写 10 位，两处互相矛盾却无人报错，
    # 结果同一需求号被截断成同一文件名，两份不同需求的文档互相有覆盖风险。
    m_fm = re.search(r'^req_id:\s*"?([^"\n]+)"?\s*$', text, re.M)
    fm_req = m_fm.group(1).strip() if m_fm else None
    ids_fn = re.findall(r"R\d+", name)
    if fm_req and ids_fn:
        fn_id = max(ids_fn, key=len)  # 取最长，兼容文件名里夹带其他 R 号
        if not REQ_ID_RE.match(fm_req):
            problems.append(("R1b", "P0",
                             f"Front Matter req_id 格式非法: {fm_req}（应为 R + 10 位）"))
        elif fn_id != fm_req:
            problems.append(("R1b", "P0",
                             f"文件名需求号 {fn_id} 与 Front Matter req_id {fm_req} 不一致"))

    # ---- R2 Front Matter ----
    fm_keys, _ = parse_frontmatter(text)
    if fm_keys is None:
        problems.append(("R2", "P0", "缺少 YAML Front Matter"))
    else:
        missing = [k for k in REQ_KEYS if k not in fm_keys]
        if missing:
            problems.append(("R2", "P0", f"Front Matter 缺失属性: {', '.join(missing)}"))

    # ---- R3 评审纪要 9 项 ----
    bounds = review_region_bounds(text)
    if bounds is None:
        problems.append(("R3", "P0", "未找到「## 评审纪要」章节"))
    else:
        start, end = bounds
        region = text[start:end]
        found = [m.group(2) for m in ITEM_RE.finditer(region)]
        for item in REVIEW_ITEMS:
            if not any(f.startswith(item) for f in found):
                problems.append(("R3", "P0", f"评审纪要缺少小节: {item}"))
        # 互斥铁律 (P0, 2026-10-08): 第 8 项【联测涉及系统】与第 2 项【改造范围】绝对互斥
        # 解析两项内容区间，按「，、, 空格」拆分系统名后求交集，交集非空即报 P0
        item_pos = [(m.start(), m.end(), int(m.group(1)), m.group(2))
                    for m in ITEM_RE.finditer(region)]
        item_content = {}
        for k, (_, e, num, _title) in enumerate(item_pos):
            nxt = item_pos[k + 1][0] if k + 1 < len(item_pos) else len(region)
            item_content[num] = region[e:nxt]
        if 2 in item_content and 8 in item_content:
            def _sys_names(content):
                names = set()
                # 标题行残留「：」冒号需纳入分隔符，避免冒号被误识别为系统名（2026-10-08 假阳性修复）
                for tok in re.split(r"[,，、：:\s]+", content):
                    tok = tok.strip()
                    if tok and tok != "无":
                        names.add(tok)
                return names
            dup = sorted(_sys_names(item_content[2]) & _sys_names(item_content[8]))
            for sys_name in dup:
                problems.append(("R3", "P0",
                                 f"第8项【联测涉及系统】出现改造范围内系统「{sys_name}」，"
                                 f"与第2项【改造范围】绝对互斥（涉及改造必然联测，严禁重复突出）"))
        # 换行铁律: 小节标题冒号后内容必须换行书写
        for line in region.splitlines():
            m = re.match(r"^\s*(\d+\.\s*\*\*[^*]+\*\*)：\s*\S.*$", line)
            if m:
                problems.append(("R3", "P0",
                                 f"评审纪要小节标题与内容同行未换行: {m.group(1)}"))
                break

    # ---- R4 末尾红线 & R5 分点缩进（联动 --fix 写回，2026-10-08 重构）----
    if bounds is not None:
        start, end = bounds
        seg_lines = text[start:end].splitlines()
        new_lines = list(seg_lines)
        r4_changed = False
        r5_changed = False

        # --- R4a: 违禁「涉及系统：」行（--fix 时实际删除并写回）---
        for i, line in enumerate(seg_lines):
            if line.strip().startswith("涉及系统"):
                if fix:
                    new_lines[i] = ""
                    r4_changed = True
                    problems.append(("R4", "P0",
                                     f"评审纪要出现违禁行「{line.strip()}」→ 已删除 {FIXED_MARK}"))
                else:
                    problems.append(("R4", "P0",
                                     f"评审纪要出现违禁行「{line.strip()}」（严禁输出涉及系统行）"))

        # --- R4b: 预计上线日期行 + 之后内容红线 ---
        ts_idx = None
        for i, line in enumerate(seg_lines):
            if TS_RE.match(line.strip()):
                ts_idx = i
                break
        if ts_idx is None:
            problems.append(("R4", "P0", "评审纪要缺少「预计上线日期：YYYY年MM月上线」行"))
        else:
            skip_attach = False
            extra = []
            for l in seg_lines[ts_idx + 1:]:
                s = l.strip()
                if not s or s.startswith("---"):
                    continue
                if ATTACH_RE.match(s):
                    skip_attach = True
                    continue
                if skip_attach:
                    continue
                # 豁免「评审决策日志（可选）」小节（2026-10-12 用户要求：决策日志在预计上线日期之后）
                # 2026-11-01 补：待确认事项（> - **待确认 N**）同为决策日志合法内容，一并豁免
                if s.startswith("##### **评审决策日志") or s.startswith("> - **决策") or s.startswith("> - **待确认"):
                    continue
                extra.append(s)
            for e in extra:
                problems.append(("R4", "P0",
                                 f"预计上线日期之后存在多余内容行: {e}（严禁输出涉及系统等行）"))

        # --- R5: 分点缩进（(N) 3 空格、① 8 空格）---
        seg_a = seg_b = None
        for i, line in enumerate(seg_lines):
            if re.match(r"^\s*3\.", line) and "各系统改造功能" in line:
                seg_a = i
            elif seg_a is not None and SEC_NO_RE.match(line):
                seg_b = i
                break
        if seg_a is not None and seg_b is None:
            seg_b = len(seg_lines)

        for i, line in enumerate(seg_lines):
            m = POINT_RE.match(line)
            if m and m.group(1).count(" ") != 3:
                new_lines[i] = f"   ({m.group(2)}) {m.group(3)}"
                r5_changed = True
            elif seg_a is not None and seg_a < i < (seg_b or len(seg_lines)):
                c = CIRCLE_RE.match(line)
                if c and c.group(1).count(" ") != 8:
                    new_lines[i] = f"        {c.group(2)} {c.group(3)}"
                    r5_changed = True

        if r5_changed:
            if fix:
                problems.append(("R5", "P2",
                                 "分点缩进已自动统一（(N) 分点 3 空格 / ① 功能点 8 空格）" + FIXED_MARK))
            else:
                problems.append(("R5", "P2",
                                 "分点缩进不规范（(N) 分点应为 3 空格、① 功能点应为 8 空格），可用 --fix 自动修复"))

        # --- 联动写回（R4 删行与 R5 缩进统一原子生效，2026-10-08 修复原只改内存不写盘 bug）---
        if fix and (r4_changed or r5_changed):
            text2 = text[:start] + "\n".join(new_lines) + text[end:]
            with open(path, "w", encoding="utf-8") as f:
                f.write(text2)

    # --- R6: 表格前需空行（Obsidian/GFM 渲染要求，2026-10-12）---
    # 表格起始行（第一个以 | 开头的行）的前一行须为空行或 --- 分隔线，否则 Obsidian 不识别为表格
    full_lines = text.splitlines()
    in_code = False
    prev = ""
    for line in full_lines:
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            prev = line
            continue
        if in_code:
            prev = line
            continue
        if not line.lstrip().startswith("|"):
            prev = line
            continue
        if prev.lstrip().startswith("|"):
            prev = line
            continue  # 非表格起始行（前一行也是表格行）
        if prev.strip() == "" or prev.strip() == "---":
            prev = line
            continue  # 前一行为空行或分隔线，OK
        problems.append(("R6", "P1",
                         f"表格前需空行（表格起始行前一行应为空行或 ---，当前为: {prev.strip()[:30]}）"))
        prev = line

    # ---- R7 系统名门禁（P1，2026-11-12 内容级校验，依赖 system_list.csv）----
    if bounds is not None and "评审纪要" in text:
        start, end = bounds
        region = text[start:end]
        sys_names = load_system_names()
        if sys_names is not None:
            for tok in sorted(_extract_sys_tokens(region)):
                if tok not in sys_names:
                    # 低延时交易系统统称豁免：BA 阶段清单无独立域中不能精确带域，拆 Story 才区分域
                    # （见 SKILL P0#3 补充说明）；清单内存在其域变体（如低延时交易系统(大集中-信创域)）
                    if tok == "低延时交易系统" and any(
                        s.startswith("低延时交易系统(") for s in sys_names
                    ):
                        continue
                    problems.append(("R7", "P1",
                                     f"系统名「{tok}」不在 system_list.csv 清单中，"
                                     f"疑似非本组/厂商系统或全称不精确，需核实责任与域全称（P0#3/#19）"))

    # ---- R8 file:// 链接存在性（P1，2026-11-12 内容级校验）----
    for m in re.finditer(r"file://([^\s\)\]\|]+)", text):
        loc = urllib.parse.unquote(m.group(1))
        # 剥离末尾「:行号」伪影（保留可能的 : 路径段）
        loc2 = re.sub(r":\d+(\s|$)", "", loc)
        if not os.path.isfile(loc2):
            problems.append(("R8", "P1",
                             f"file:// 链接指向不存在文件: {m.group(1)}（死链，需核对绝对路径）"))

    # ---- R9 双链文件存在性（P1，2026-11-12 内容级校验）----
    if bounds is not None:
        start, end = bounds
    else:
        start, end = 0, len(text)
    region = text[start:end]
    base = os.path.dirname(os.path.abspath(path))
    for m in re.finditer(r"\[\[([^\]\|]+)", region):
        name = m.group(1).strip()
        if not name or not re.search(r"\d{8}-R\d", name):
            continue  # 仅校验含日期-R号 命名的双链（多为需求文档双链）
        # 具体文件名可能是 name.md 或 name（前缀），在文档所在目录找 name*.md
        hits = glob.glob(os.path.join(base, name + "*.md"))
        if not hits:
            problems.append(("R9", "P1",
                             f"双链 [[{name}]] 在 {os.path.basename(base)}/ 下找不到对应 .md 文件（悬空双链）"))

    # ---- R10 六段闭环交付完整性（P0，2026-11-20 新增，借鉴 universal-requirement-review「发送前强制检查」）----
    # 校验文档是否达到"可一次交付"的六段完整闭环：一需求背景/二需求内容/三技术实现/四需求矛盾审计/
    # 评审纪要/相关链接。任一缺段即非冻结完整版，不得作为最终交付。
    R10_SECTIONS = [
        ("一、需求背景", r"^#{1,4}\s*(\*\*)?一、需求背景(\*\*)?\s*$"),
        ("二、需求内容", r"^#{1,4}\s*(\*\*)?二、需求内容(\*\*)?\s*$"),
        ("三、技术实现", r"^#{1,4}\s*(\*\*)?三、技术实现(\*\*)?\s*$"),
        ("四、需求矛盾", r"^#{1,4}\s*(\*\*)?四、.*(?:矛盾|审计|漏洞|风险)(\*\*)?\s*$"),
        ("评审纪要", r"^#{1,4}\s*(\*\*)?评审纪要(\*\*)?\s*$"),
        ("相关链接", r"^#{1,4}\s*(\*\*)?相关链接(\*\*)?\s*$"),
    ]
    for secname, ptn in R10_SECTIONS:
        if not re.search(ptn, text, re.M):
            # 「四章」允许名为 矛盾/审计/漏洞/风险 任一，已由正则宽匹配；缺失即报
            problems.append(("R10", "P0", f"交付完整性缺失章节: {secname}（六段闭环未齐，不得作为最终交付）"))
    # 三技术实现需含（四）伪代码 或（一）业务逻辑 等小节，避免空壳
    if re.search(r"^#{1,4}\s*(\*\*)?三、技术实现(\*\*)?\s*$", text, re.M):
        has_sub = re.search(r"^#{5,6}\s*[（(][一二三四五六][）)].*($|\n)", text, re.M)
        if not has_sub:
            problems.append(("R10", "P0", "交付完整性：三、技术实现 无（一）~（四）子小节（章节空洞）"))
    # 标题下严禁「需求概要/元信息」引用块（三道硬约束 2）
    # 定位正文标题 = 第一个以 # 开头的标题行（front matter 块之后的 `# 标题`，而非首行的 front matter `---`）
    title_line = ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# "):
            title_line = line
            break
    if title_line.startswith("# "):
        after_title = text[text.find(title_line) + len(title_line):]
        if re.search(r"^\s*>\s*\*\*需求(?:编号|来源)\*\*", after_title, re.M):
            problems.append(("R10", "P0", "标题下存在「需求概要/元信息」引用块（三道硬约束 2，应删除）"))

    return problems


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fix = "--fix" in sys.argv
    if len(args) < 1:
        print(__doc__)
        sys.exit(2)
    target = args[0]
    files = []
    if os.path.isdir(target):
        for root, _, fs in os.walk(target):
            for f in fs:
                if f.endswith(".md"):
                    files.append(os.path.join(root, f))
    else:
        files = [target]

    all_pass = True
    for path in sorted(files):
        try:
            probs = check_file(path, fix=fix)
        except FileNotFoundError:
            print(f"[IO] 文件不存在: {path}")
            all_pass = False
            continue
        display = path if not os.path.isabs(path) else os.path.relpath(path, "/")
        if probs:
            # 统计失败：已修复项（--fix）不计为失败
            if any(not _is_fixed(p) for p in probs):
                all_pass = False
            print(f"== {display} ==")
            for rule, level, desc in probs:
                print(f"  [{rule} {level}] {desc}")
        else:
            print(f"== {display} == 全部通过 ✓")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
