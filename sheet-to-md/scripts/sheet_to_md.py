#!/usr/bin/env python3
"""
腾讯文档 Sheet → Obsidian MD 反写工具 v7

从腾讯文档在线表格 CSV 数据中提取需求记录，按需求名称匹配本地 MD 文件，
将在线文档中的列数据反写到 MD 对应章节。

v7 更新：
- K列(备注) 智能融合 — 备注融入 三、技术实现 与 评审纪要 的内容中
- G列(关联系统) 位置调整 — 从 技术实现 移到 评审纪要 的 涉及系统 下方
- 临时标记机制 — 用 <!-- REMARK_START -->\n备注：...\n<!-- REMARK_END -->
  将备注插入到对应章节，待 AI 助手语义融合与润色后清理
- 增量比对更新 — 比对所有相关属性，无新变化不重复修改

数据映射：
  F(涉及系统) → 评审纪要 | 涉及系统：xxx（预计完成时间上方）
  G(关联系统) → 评审纪要 | 关联系统：xxx（涉及系统下方）
  H(计划排期) → 评审纪要 | 预计完成时间：计划 xxx
  K(备注)     → 技术实现 + 评审纪要 | 插入临时备注标签后由 AI 融合
  L(参会人员) → 评审纪要(第一句) | YYYY年MM月DD日经与**部门A**人员A和**部门B**人员B沟通评审通过

用法:
  python3 sheet_to_md.py rzrq --apply          # 融资融券
  python3 sheet_to_md.py gpzy --apply          # 股票质押
  python3 sheet_to_md.py qt --apply            # 其他
  python3 sheet_to_md.py gpzy --dry-run        # 预览
  python3 sheet_to_md.py --csv-file data.csv --md-dir /path --dry-run  # 自定义 CSV
"""

import csv
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
import hashlib

# ── 配置 ──────────────────────────────────────────────────────────────
# 引入公共 SDK
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_COMMON_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, '..', '..', 'common'))
if _COMMON_DIR not in sys.path:
    sys.path.append(_COMMON_DIR)

try:
    from sync_utils import (
        call_mcp, load_dept_map, lcs_len, MDIndex, get_md_index, find_md_file,
        get_path, get_biz_file_map, get_match_stop_words
    )
    _HAS_SYNC_UTILS = True
except ImportError:
    _HAS_SYNC_UTILS = False

if not _HAS_SYNC_UTILS:
    DEFAULT_MD_DIR = "/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析/"
    DEFAULT_DEPT_CSV = "/Volumes/Macintosh HD_Data/WorkBuddy/会议纪要/人员部门对应关系表.csv"
    MCP_PORTER_PATH = "/Users/wujin/.npm-global/bin/mcporter"
else:
    DEFAULT_MD_DIR = get_path("md_dir_sheet_to_md", "/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析/")
    DEFAULT_DEPT_CSV = get_path("dept_csv", "/Volumes/Macintosh HD_Data/WorkBuddy/会议纪要/人员部门对应关系表.csv")
    MCP_PORTER_PATH = get_path("mcporter", "/Users/wujin/.npm-global/bin/mcporter")

# ── 临时备注标记 ──────────────────────────────────────────────────────
REMARK_START = "<!-- REMARK_START -->"
REMARK_END   = "<!-- REMARK_END -->"
REMARK_TAG   = re.compile(
    r'<!--\s*REMARK_START\s*-->\s*(?:备注[：:].*?)?\s*<!--\s*REMARK_END\s*-->\s*\n*',
    re.DOTALL
)

# ── 备注哈希幂等机制 ──────────────────────────────────────────────────
REMARK_HASH_KEY = 'remark_applied_hash'

def _remark_hash(remark: str) -> str:
    """生成备注内容 MD5 短哈希（8位），用于幂等判断"""
    return hashlib.md5(remark.strip().encode('utf-8')).hexdigest()[:8]


def _get_frontmatter_hash(content: str) -> str:
    """从 YAML frontmatter 提取已写入的备注哈希"""
    m = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not m:
        return ''
    hm = re.search(rf'^{REMARK_HASH_KEY}:\s*(\S+)', m.group(1), re.MULTILINE)
    return hm.group(1).strip() if hm else ''


def _set_frontmatter_hash(content: str, hash_val: str) -> str:
    """在 YAML frontmatter 中写入/更新备注哈希（支持无 frontmatter 的文档自动补全）"""
    key_line = f'{REMARK_HASH_KEY}: {hash_val}'
    if re.search(rf'^{REMARK_HASH_KEY}:', content, re.MULTILINE):
        return re.sub(rf'^{REMARK_HASH_KEY}:.*$', key_line, content, flags=re.MULTILINE)

    if content.startswith('---'):
        m = re.search(r'^(---\s*\n.*?\n)(---)', content, re.DOTALL)
        if m:
            return content[:len(m.group(1))] + f'{key_line}\n' + content[len(m.group(1)):]

    return f'---\n{key_line}\n---\n\n' + content.lstrip()


# ── MCP 调用工具 ──────────────────────────────────────────────────────
def call_mcp(tool_name: str, args: dict) -> dict:
    """通过 mcporter 调用 tencent-docs 的 MCP 工具"""
    cmd = [
        MCP_PORTER_PATH,
        "call",
        "tencent-docs",
        tool_name,
        "--args",
        json.dumps(args)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise Exception(f"MCP 调用失败 (工具: {tool_name}):\nError: {res.stderr}\nOutput: {res.stdout}")

    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        raise Exception(f"MCP 返回的数据无法解析为 JSON:\n{res.stdout}")


# ── CSV 列索引 (0-based) ──────────────────────────────────────────────
IDX_DATE      = 0   # A: 提出日期
IDX_PRIORITY  = 1   # B: 优先级
IDX_LINK      = 2   # C: 需求链接
IDX_NAME      = 3   # D: 需求名称
IDX_DESC      = 4   # E: 需求描述
IDX_SYSTEMS   = 5   # F: 涉及系统
IDX_RELATED   = 6   # G: 关联系统
IDX_SCHEDULE  = 7   # H: 计划排期
IDX_STORY     = 8   # I: story拆分
IDX_STATUS    = 9   # J: 评审状态
IDX_REMARK    = 10  # K: 备注
IDX_ATTENDEES = 11  # L: 参会人员


# ── 部门映射 ────────────────────────────────────────────────────────────

def load_dept_map(csv_path: str) -> dict[str, str]:
    """加载「人员部门对应关系表.csv」，返回 {人名: 部门} 映射。"""
    dept_map = {}
    if not csv_path or not Path(csv_path).is_file():
        return dept_map

    text = Path(csv_path).read_text(encoding='utf-8')
    reader = csv.reader(io.StringIO(text))
    try:
        next(reader)
    except StopIteration:
        return dept_map

    for line in reader:
        if len(line) < 2:
            continue
        name = line[0].strip()
        dept = line[1].strip()
        if name and dept:
            dept_map[name] = dept
    return dept_map


import concurrent.futures
from functools import lru_cache

# ── MD 匹配 ────────────────────────────────────────────────────────────

def lcs_len(s1: str, s2: str) -> int:
    m = [[0] * (len(s2) + 1) for _ in range(len(s1) + 1)]
    longest = 0
    for i in range(len(s1)):
        for j in range(len(s2)):
            if s1[i] == s2[j]:
                m[i+1][j+1] = m[i][j] + 1
                if m[i+1][j+1] > longest:
                    longest = m[i+1][j+1]
    return longest


class MDIndex:
    """MD 文件全量索引与预计算缓存类，彻底避免重复全盘 IO 与正则反复计算"""
    def __init__(self, md_dir: str):
        self.base = Path(md_dir)
        if not self.base.is_dir():
            self.entries = []
            return

        files = sorted(list(self.base.glob("**/*.md")), key=lambda x: x.name, reverse=True)
        self.entries = []
        for f in files:
            c_all = self._clean_all(f.name)
            c_match = self._clean_for_match(f.name)
            self.entries.append((f, f.name, c_all, c_match, set(c_match)))

    @staticmethod
    def _clean_all(s: str) -> str:
        return re.sub(r'[【】\[\]\(\)\{\}\s\-—_、，。,.:：]', '', s).lower()

    @staticmethod
    def _clean_for_match(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r'^\d{8}', '', s)
        s = re.sub(r'【.+?】', '', s)
        s = re.sub(r'\[.+?\]', '', s)
        prefixes_to_strip = [
            '两融清算', '低延时两融', '个微两融柜台', '个微两融', '低延时系统', 
            '集中交易系统', '集中清算系统', '集中交易', '集中清算', '低延时', 
            '三方存管', '相关', '关于', '的', '优化', '需求', '说明', 
            '方案', '系统', '业务', '改造', '控制', '支持', '新规', '柜台'
        ]
        for p in prefixes_to_strip:
            s = s.replace(p, '')
        s = re.sub(r'[\s\-—_、，。,.:：【】\[\]\(\)\{\}]', '', s)
        return s

    def find(self, req_name: str) -> Path | None:
        name = req_name.strip()
        if not name or not self.entries:
            return None

        # 1. 尝试完全包含匹配
        for f, fname, _, _, _ in self.entries:
            if name in fname:
                return f

        # 2. 移除所有括号/空格/标点后完全包含匹配
        clean_name_val = self._clean_all(name)
        for f, _, c_all, _, _ in self.entries:
            if clean_name_val in c_all or c_all in clean_name_val:
                return f

        # 3. 核心名称 LCS 与 字符重合度评分匹配
        q_stripped = self._clean_for_match(name)
        if not q_stripped:
            return None

        q_set = set(q_stripped)
        best_file = None
        best_lcs = 0
        best_overlap = 0

        for f, _, _, f_stripped, f_set in self.entries:
            lcs = lcs_len(q_stripped, f_stripped)
            overlap = len(q_set & f_set)

            if lcs > best_lcs:
                best_lcs = lcs
                best_overlap = overlap
                best_file = f
            elif lcs == best_lcs and lcs > 0:
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_file = f

        if best_file and (best_lcs >= 3 or best_overlap >= 4):
            return best_file

        return None


_INDEX_CACHE: dict[str, MDIndex] = {}

def get_md_index(md_dir: str) -> MDIndex:
    resolved = str(Path(md_dir).resolve())
    if resolved not in _INDEX_CACHE:
        _INDEX_CACHE[resolved] = MDIndex(md_dir)
    return _INDEX_CACHE[resolved]


def find_md_file(req_name: str, md_dir: str, index: MDIndex | None = None) -> Path | None:
    if index is None:
        index = get_md_index(md_dir)
    return index.find(req_name)


# ── MD 解析 ────────────────────────────────────────────────────────────

SECTION_TECH    = "#### **三、技术实现**"
SECTION_REVIEW  = "#### **评审纪要**"
SECTION_LINKS   = "**相关链接**"

# 新版自然融入行（用于检测已有值）
RE_SYSTEMS_LINE  = re.compile(r'^[ \t]*涉及系统[：:][ \t]*(.+)$', re.MULTILINE)
RE_RELATED_LINE  = re.compile(r'^[ \t]*关联系统[：:][ \t]*(.+)$', re.MULTILINE)
RE_TIME_LINE     = re.compile(r'^[ \t]*预计完成时间[：:][ \t]*(.+)$', re.MULTILINE)

# 评审纪要编号条目: N. **标题**：内容
RE_NUM_ITEM = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*[：:](.+?)$', re.MULTILINE)

# 备注→标题动词提取
_REMARK_VERBS = [
    '核对', '确认', '验证', '检查', '梳理', '补充',
    '优化', '完善', '调整', '新增', '解决', '处理', '评估',
]

# 评审纪要第一句：日期 + 沟通评审
RE_REVIEW_FIRST = re.compile(
    r'^[ \t]*(.+?)经与(.+?)(?:沟通)?评审通过[：:\t ]*$',
    re.MULTILINE
)


class MdSections:
    """MD 文件分段结构"""

    def __init__(self, content: str):
        self.raw = content
        self.preamble = ""
        self.tech = ""
        self.review = ""
        self.tail = ""
        self.has_tech = False
        self.has_review = False
        self._parse()

    def _parse(self):
        t = self.raw
        
        tech_match = re.search(r'####\s*\*\*\s*(?:[一二三四五六七八九十百、\.\s]+)?三、技术实现\s*\*\*', t)
        review_match = re.search(r'####\s*\*\*\s*(?:[一二三四五六七八九十百、\.\s]+)?评审纪要\s*\*\*', t)
        links_match = re.search(r'\*\*\s*(?:[一二三四五六七八九十百、\.\s]+)?相关链接\s*\*\*', t)

        tech_i = tech_match.start() if tech_match else -1
        review_i = review_match.start() if review_match else -1
        links_i = links_match.start() if links_match else -1

        if tech_i >= 0:
            self.has_tech = True
            self.preamble = t[:tech_i].rstrip()
            if review_i > tech_i:
                self.tech = t[tech_i:review_i].rstrip()
            else:
                self.tech = t[tech_i:].rstrip()
                return
        else:
            self.preamble = t.rstrip()
            return

        if review_i >= 0:
            self.has_review = True
            if links_i > review_i:
                self.review = t[review_i:links_i].rstrip()
                self.tail = t[links_i:]
            else:
                self.review = t[review_i:].rstrip()

    def rebuild(self) -> str:
        parts = [self.preamble]
        if self.has_tech:
            parts.append(self.tech)
        if self.has_review:
            parts.append(self.review)
        parts.append(self.tail)
        return '\n\n'.join(p for p in parts if p)


# ── 文本工具 ────────────────────────────────────────────────────────────

def _clean_multiline(s: str) -> str:
    """清理换行 → 用 、 连接"""
    return '、'.join(line.strip() for line in s.split('\n') if line.strip())


def _has_remark_in_text(text: str, remark: str) -> bool:
    """检查备注内容（不含标记）是否已存在于文本中"""
    if not remark or not text:
        return False
    clean = remark.strip()
    return clean in text


def _text_differs(text: str, key: str, value: str, pattern: re.Pattern) -> bool:
    """判断目标行中的值是否与传入值不同"""
    m = pattern.search(text)
    if m:
        existing = m.group(1).strip()
        return existing != value
    return True  # 行不存在也算差异


# ── 技术实现 更新 ──────────────────────────────────────────────────────

def update_tech_section(tech: str, remark: str) -> tuple[str, bool]:
    """在 技术实现 中插入备注临时标记。

    v7：G列(关联系统) 和 F列(涉及系统) 不再出现在此章节。
    仅插入 K列备注 的临时标记，AI 助手后续进行语义融合。

    返回 (更新后文本, 是否有变更)
    """
    changed = False

    # 1. 清理残留在技术实现中的涉及系统行和关联系统行（已迁移到评审纪要）
    if RE_SYSTEMS_LINE.search(tech):
        tech = RE_SYSTEMS_LINE.sub('', tech)
        changed = True
    if RE_RELATED_LINE.search(tech):
        tech = RE_RELATED_LINE.sub('', tech)
        changed = True

    # 2. 清理旧的临时备注标记（避免重复）
    old_tech = tech
    tech = REMARK_TAG.sub('', tech)
    if tech != old_tech:
        changed = True

    # 3. 如果存在备注，插入临时标记
    if remark and remark.strip():
        remark_clean = remark.strip()
        if not _has_remark_in_text(tech, remark_clean):
            header_pattern = re.compile(r'^(#### \*\*三、技术实现\*\*)\s*\n', re.MULTILINE)
            m = header_pattern.search(tech)
            if m:
                insert_pos = m.end()
                insert_text = (
                    f"{REMARK_START}\n备注：{remark_clean}\n{REMARK_END}\n\n"
                )
                tech = tech[:insert_pos] + insert_text + tech[insert_pos:].lstrip('\n')
                changed = True

    # 避免连续3个以上空行
    tech = re.sub(r'\n{3,}', '\n\n', tech)

    return tech, changed


# ── 评审纪要 更新 ──────────────────────────────────────────────────────

def _extract_names(raw: str) -> list[str]:
    """从 L列文本中提取独立人名。"""
    if not raw or not raw.strip():
        return []
    parts = re.split(r'[\n、，,]+', raw.strip())
    return [p.strip() for p in parts if p.strip()]


def _parse_attendees(attendees_raw: str, dept_map: dict[str, str]) -> list[tuple[str, list[str]]]:
    """解析参会人员列，返回按部门分组的结构。

    返回 [(部门, [人员列表]), ...] 保持原始顺序
    """
    if not attendees_raw or not attendees_raw.strip():
        return []

    raw = attendees_raw.strip()
    has_dept = re.search(r'[\u4e00-\u9fff]{2,6}[部室组处科中心]-', raw)

    if has_dept:
        parts = re.split(r'[、，,\n]+', raw)
        groups: dict[str, list[str]] = {}
        group_order: list[str] = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            m = re.match(r'^(.+?)-(.+)$', p)
            if m:
                dept = m.group(1).strip()
                person = m.group(2).strip()
                if dept not in groups:
                    groups[dept] = []
                    group_order.append(dept)
                if person not in groups[dept]:
                    groups[dept].append(person)
        return [(d, groups[d]) for d in group_order]

    # 无部门前缀 → 通过 dept_map 查询
    names = _extract_names(raw)
    if not names:
        return []

    if not dept_map:
        return [("[部门名称A]", names)]

    dept_groups: dict[str, list[str]] = {}
    dept_order: list[str] = []
    unknown: list[str] = []

    for name in names:
        clean_name = re.sub(r'\s+', '', name)
        dept = dept_map.get(clean_name, '')
        if dept:
            if dept not in dept_groups:
                dept_groups[dept] = []
                dept_order.append(dept)
            dept_groups[dept].append(clean_name)
        else:
            unknown.append(name)

    result = [(d, dept_groups[d]) for d in dept_order]
    if unknown:
        result.append(("[部门名称A]", unknown))

    return result


def _generate_remark_title(remark: str) -> str:
    """从备注文本智能生成编号项加粗标题"""
    remark = remark.strip().rstrip('。，；,;.')
    if not remark:
        return '补充说明'

    for verb in _REMARK_VERBS:
        if verb in remark:
            idx = remark.index(verb)
            after = remark[idx + len(verb):].strip()
            if after:
                key = re.sub(r'[跟与和及以及的之了是]', '', after)[:6]
                if key:
                    return f'{key}{verb}'
            return f'相关{verb}'

    return remark[:8]


def _merge_remark_into_items(review: str, remark: str) -> tuple[str, bool]:
    """将备注内容（去除临时标记）融入评审纪要的编号列表中。

    v7 行为：
    1. 清理 <!-- REMARK_START/END --> 标记
    2. 检查备注内容是否已存在于某条目中 → 跳过
    3. 尝试按关键词重叠合并到语义最接近的条目
    4. 无法合并则新增一条编号条目（N+1）

    返回 (更新后文本, 是否有变更)
    """
    if not remark or not remark.strip():
        return review, False

    changed = False

    # 1. 清理临时备注标记
    old_review = review
    review = REMARK_TAG.sub('', review)
    if review != old_review:
        changed = True

    remark_text = remark.strip().rstrip('。，；,;.')
    if not remark_text:
        return review, changed

    # 将备注里的多行换行替换为分号，使列表项在单行内展示
    remark_text = re.sub(r'\n+', '；', remark_text)

    # 2. 解析现有编号条目 (使用通用匹配以包含无加粗标题的普通条目，以及标准带加粗标题的条目)
    RE_GENERIC_NUM_ITEM = re.compile(r'^\s*(\d+)\.\s+(.+)$', re.MULTILINE)
    generic_items = list(RE_GENERIC_NUM_ITEM.finditer(review))
    items = list(RE_NUM_ITEM.finditer(review))

    # 3. 检查是否已存在 (支持增量追加备注时的就地更新)
    for m in generic_items:
        existing = m.group(2).strip().rstrip('。，；')
        if remark_text == existing:
            return review, changed
        if existing in remark_text and len(existing) > 5:
            old_item = m.group(0)
            # 如果现有条目属于加粗标题风格，生成新加粗项，否则生成普通文本项
            is_bold = any(item.group(0) == old_item for item in items)
            if is_bold:
                # 寻找 m.group(2) 中真正的文本部分（m.group(2) 是 "**标题**：内容")
                match_bold = RE_NUM_ITEM.match(old_item)
                if match_bold:
                    new_item = old_item.replace(match_bold.group(3), remark_text)
                else:
                    new_item = old_item.replace(m.group(2), remark_text)
            else:
                new_item = old_item.replace(m.group(2), remark_text)
            review = review.replace(old_item, new_item)
            return review, True

    # 4. 关键词重叠 → 尝试合并到最匹配条目 (仅对标准条目做合并)
    remark_words = set(
        remark_text.replace('跟', ' ').replace('和', ' ').replace('与', ' ').replace('及', ' ').split()
    )

    best_match = None
    best_score = 0
    for m in items:
        item_content = m.group(3).strip().rstrip('。，；')
        item_words = set(
            item_content.replace('跟', ' ').replace('和', ' ').replace('与', ' ').replace('及', ' ').split()
        )
        overlap = len(remark_words & item_words)
        if overlap > best_score:
            best_score = overlap
            best_match = m

    if best_match and best_score >= 2:
        old_item = best_match.group(0)
        existing_content = best_match.group(3).strip().rstrip('。')
        new_content = f'{existing_content}；{remark_text}。'
        new_item = old_item.replace(best_match.group(3), new_content)
        review = review.replace(old_item, new_item)
        return review, True

    # 5. 新增编号条目
    max_num = max([int(m.group(1)) for m in generic_items], default=0)
    new_num = max_num + 1
    
    # 风格一致性控制：如果现有条目全是普通文本风格（无加粗标题），则新增条目也保持无加粗标题风格
    # 风格一致性控制及缩进对齐：
    item_leading_ws = ''
    if generic_items:
        last_item = generic_items[-1]
        full_line = last_item.group(0)
        leading_ws_match = re.match(r'^[ \t]*', full_line)
        if leading_ws_match:
            item_leading_ws = leading_ws_match.group(0)
    else:
        first_line_match = RE_REVIEW_FIRST.search(review)
        if first_line_match:
            full_first = first_line_match.group(0)
            leading_ws_match = re.match(r'^[ \t]*', full_first)
            if leading_ws_match:
                item_leading_ws = leading_ws_match.group(0)

    if generic_items and not items:
        new_item = f'{item_leading_ws}{new_num}. {remark_text}。'
    else:
        title = _generate_remark_title(remark_text)
        new_item = f'{item_leading_ws}{new_num}. **{title}**：{remark_text}。'

    if generic_items:
        last_item = generic_items[-1]
        end_pos = last_item.end()
        review = review[:end_pos] + '\n' + new_item + review[end_pos:]
    else:
        first_line_match = RE_REVIEW_FIRST.search(review)
        if first_line_match:
            insert_pos = first_line_match.end()
            review = review[:insert_pos] + '\n\n' + new_item + review[insert_pos:]
        else:
            first_line_end = review.find('\n')
            if first_line_end > 0:
                review = review[:first_line_end + 1] + '\n' + new_item + review[first_line_end + 1:]
            else:
                review += '\n\n' + new_item

    review = re.sub(r'\n{3,}', '\n\n', review)
    return review, True


def update_review_section(
    review: str,
    schedule: str,
    remark: str,
    attendees: str,
    systems: str,
    related: str,
    date_str: str,
    dept_map: dict[str, str],
) -> tuple[str, bool]:
    """更新 评审纪要 部分。

    v7 关键顺序：
    1. 参会人员第一句
    2. 编号评审要点（备注语义融入后清理标记）
    3. 涉及系统
    4. 关联系统（涉及系统下方）
    5. 预计完成时间
    """
    changed = False

    # 捕获评审纪要首行的空白缩进（实现各行排版严格对齐）
    leading_ws = ''
    old_first = RE_REVIEW_FIRST.search(review)
    if old_first:
        leading_ws = old_first.group(0)[:len(old_first.group(0)) - len(old_first.group(0).lstrip())]

    # ── 1. 第一句话：参会人员 ──
    if attendees and attendees.strip():
        dept_groups = _parse_attendees(attendees, dept_map)

        if dept_groups:
            group_strs = []
            for dept, people in dept_groups:
                people_str = '、'.join(people)
                group_strs.append(f"**{dept}**{people_str}")

            if len(group_strs) == 1:
                attendee_part = group_strs[0]
            elif len(group_strs) == 2:
                attendee_part = '和'.join(group_strs)
            else:
                attendee_part = '、'.join(group_strs[:-1]) + '和' + group_strs[-1]
        else:
            attendee_part = r"**[部门名称A]**：[人员X]、[人员Y]"

        first_line = f"{date_str}经与{attendee_part}沟通评审通过"

        if old_first:
            new_full = f"{leading_ws}{first_line}"
            if new_full != old_first.group(0):
                review = review[:old_first.start()] + new_full + review[old_first.end():]
                changed = True

    # ── 2. 备注 → 融入编号列表（清理临时标记） ──
    if remark and remark.strip():
        remark_clean = remark.strip()
        review, merged_changed = _merge_remark_into_items(review, remark_clean)
        if merged_changed:
            changed = True

    # ── 3. 涉及系统 与 关联系统（仅在值或缩进有变化时才修改，保持幂等与排版对齐） ──
    systems_clean = _clean_multiline(systems) if systems else ''
    related_clean = _clean_multiline(related) if related else ''

    sys_match = RE_SYSTEMS_LINE.search(review)
    rel_match = RE_RELATED_LINE.search(review)
    expected_sys = f"{leading_ws}涉及系统：{systems_clean}" if systems_clean else ''
    expected_rel = f"{leading_ws}关联系统：{related_clean}" if related_clean else ''

    sys_needs = systems_clean and (not sys_match or sys_match.group(0) != expected_sys)
    rel_needs = related_clean and (not rel_match or rel_match.group(0) != expected_rel)
    sys_remove = sys_match and not systems_clean
    rel_remove = rel_match and not related_clean

    if sys_needs or rel_needs or sys_remove or rel_remove:
        review = RE_SYSTEMS_LINE.sub('', review)
        review = RE_RELATED_LINE.sub('', review)
        lines_to_insert = []
        if systems_clean:
            lines_to_insert.append(expected_sys)
        if related_clean:
            lines_to_insert.append(expected_rel)
        if lines_to_insert:
            sys_related_block = "\n".join(lines_to_insert) + "\n"
            time_pos = review.find('预计完成时间')
            if time_pos > 0:
                prefix = review[:time_pos].rstrip() + "\n\n"
                review = prefix + sys_related_block + review[time_pos:]
            else:
                review = review.rstrip() + f'\n\n{sys_related_block}'
        changed = True

    # ── 4. 预计完成时间 ──
    if schedule and schedule.strip():
        s_val = schedule.strip()
        if not s_val.startswith("计划"):
            s_val = f"计划 {s_val}"
        time_str = f"{leading_ws}预计完成时间：{s_val}"
        old_time = RE_TIME_LINE.search(review)
        if old_time:
            if old_time.group(0) != time_str:
                review = review.replace(old_time.group(0), time_str)
                changed = True
        else:
            review = review.rstrip() + f'\n\n{time_str}\n'
            changed = True

    # 整理空行
    review = re.sub(r'\n{3,}', '\n\n', review)

    return review, changed


# ── J列 评审状态 过滤 ──────────────────────────────────────────────

APPROVED_STATUSES = {'通过', '评审通过'}

def is_approved(status: str) -> bool:
    s = status.strip()
    return s in APPROVED_STATUSES


# ── 增量比对 ──────────────────────────────────────────────────────────

def _build_compare_key(sections: MdSections, row: dict) -> str:
    """构建用于增量比对的键值字符串。

    比对所有相关属性，如果在线数据与 MD 当前内容一致，则返回空字符串表示无变化。
    """
    parts = []

    # 技术实现中的关键行
    for line in sections.tech.split('\n'):
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            parts.append(stripped)

    # 评审纪要中的关键行
    for line in sections.review.split('\n'):
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            parts.append(stripped)

    # 在线表格数据
    for key in ('systems', 'related', 'schedule', 'remark', 'attendees'):
        val = row.get(key, '').strip()
        if val:
            parts.append(val)

    return '\n'.join(parts)


# ── 主流程 ─────────────────────────────────────────────────────────────

def process_row(row: dict, md_dir: str, dry_run: bool,
                dept_map: dict[str, str], index: MDIndex | None = None) -> dict:
    """处理单行数据"""
    name = row.get('name', '').strip()
    if not name:
        return {"status": "skip", "name": "", "message": "需求名称为空"}

    # J列过滤：仅「通过」才处理
    status = row.get('status', '')
    if not is_approved(status):
        return {
            "name": name,
            "status": "skipped_not_approved",
            "message": f"评审状态为「{status}」非「通过」，跳过"
        }

    md_file = find_md_file(name, md_dir, index=index)
    if not md_file:
        return {
            "name": name,
            "status": "no_match",
            "message": f"未找到匹配的 MD 文件（搜索: {md_dir}）"
        }

    try:
        content = md_file.read_text(encoding='utf-8')
    except Exception as e:
        return {"name": name, "status": "error", "message": str(e)}

    # ── 备注幂等判断：哈希一致说明已被 AI 融合，跳过重新插入 ──
    remark_val = row.get('remark', '').strip()
    apply_remark = remark_val
    if remark_val and _get_frontmatter_hash(content) == _remark_hash(remark_val):
        apply_remark = ''  # 已融合，本次跳过
    row = dict(row, remark=apply_remark)

    sections = MdSections(content)
    changes = []

    # 优先使用在线表格中的日期，若为空则降级为本地文件在磁盘上的最后修改时间 (mtime)
    date_raw = row.get('date', '').strip()
    if date_raw:
        date_str = _extract_date(date_raw)
    else:
        import datetime
        try:
            mtime = os.path.getmtime(md_file)
            dt = datetime.datetime.fromtimestamp(mtime)
            date_str = dt.strftime("%Y年%m月%d日")
        except Exception:
            date_str = datetime.datetime.now().strftime("%Y年%m月%d日")

    # 更新 技术实现 (K: 备注)
    if sections.has_tech:
        new_tech, tech_changed = update_tech_section(
            sections.tech,
            row.get('remark', '')
        )
        if tech_changed:
            sections.tech = new_tech
            changes.append('技术实现')

    # 更新 评审纪要 (F:涉及系统, G:关联系统, H:排期, K:备注, L:参会人员)
    if sections.has_review:
        new_review, review_changed = update_review_section(
            sections.review,
            row.get('schedule', ''),
            row.get('remark', ''),
            row.get('attendees', ''),
            row.get('systems', ''),
            row.get('related', ''),
            date_str,
            dept_map,
        )
        if review_changed:
            sections.review = new_review
            changes.append('评审纪要')

    if not changes:
        return {
            "name": name,
            "file": str(md_file),
            "status": "unchanged",
            "message": "内容已是最新，无需更新"
        }

    new_content = sections.rebuild()

    # 首次插入备注时，将哈希写入 frontmatter，AI 融合后下次跳过
    if remark_val and apply_remark:
        new_content = _set_frontmatter_hash(new_content, _remark_hash(remark_val))

    return {
        "name": name,
        "file": str(md_file),
        "status": "updated",
        "changes": changes,
        "new_content": new_content,
        "dry_run": dry_run,
    }


def _extract_date(date_raw: str) -> str:
    """从日期列提取格式化日期字符串，如 '2026/6/1' → '2026年06月01日'"""
    if not date_raw:
        return "2026年06月01日"
    for fmt in [r'(\d{4})/(\d{1,2})/(\d{1,2})', r'(\d{4})-(\d{1,2})-(\d{1,2})']:
        m = re.search(fmt, date_raw)
        if m:
            return f"{m.group(1)}年{int(m.group(2)):02d}月{int(m.group(3)):02d}日"
    return date_raw


def parse_csv(csv_text: str) -> list[dict]:
    """解析 mcporter sheet.get_cell_data 返回的 CSV"""
    reader = csv.reader(io.StringIO(csv_text))
    rows = []
    try:
        next(reader)
    except StopIteration:
        return rows

    for line in reader:
        while len(line) < 13:
            line.append('')

        name = line[IDX_NAME].strip() if len(line) > IDX_NAME else ''
        if not name or len(name) < 3 or not any('\u4e00' <= c <= '\u9fff' for c in name):
            continue

        rows.append({
            'date':      line[IDX_DATE].strip()      if len(line) > IDX_DATE      else '',
            'name':      name,
            'systems':   line[IDX_SYSTEMS].strip()   if len(line) > IDX_SYSTEMS   else '',
            'related':   line[IDX_RELATED].strip()   if len(line) > IDX_RELATED   else '',
            'schedule':  line[IDX_SCHEDULE].strip()  if len(line) > IDX_SCHEDULE  else '',
            'remark':    line[IDX_REMARK].strip()    if len(line) > IDX_REMARK    else '',
            'status':    line[IDX_STATUS].strip()    if len(line) > IDX_STATUS    else '',
            'attendees': line[IDX_ATTENDEES].strip() if len(line) > IDX_ATTENDEES else '',
        })
    return rows


def main():
    import argparse
    ap = argparse.ArgumentParser(description='腾讯文档 Sheet → Obsidian MD 反写 v7')
    ap.add_argument(
        'biz', nargs='?', choices=['rzrq', 'gpzy', 'qt'],
        help='业务类型: rzrq (融资融券), gpzy (股票质押) 或 qt (其他)',
    )
    ap.add_argument('--csv-file',   help='CSV 数据文件路径 (若不指定则自动通过 MCP 获取)')
    ap.add_argument('--md-dir',     default=DEFAULT_MD_DIR, help='本地 MD 文件目录')
    ap.add_argument('--dept-csv',   default=DEFAULT_DEPT_CSV, help='人员部门对应关系表 CSV 路径')
    ap.add_argument('--dry-run',    action='store_true', help='预览模式，不修改文件')
    ap.add_argument('--json',       action='store_true', help='JSON 格式输出')
    ap.add_argument('--output-dir', help='输出目录：将更新后的内容写入此目录下的临时文件')
    ap.add_argument('--apply',      action='store_true', help='直接写入 MD 文件')
    args = ap.parse_args()

    dept_map = load_dept_map(args.dept_csv) if args.dept_csv else {}
    if args.dept_csv:
        print(f"📋 已加载 {len(dept_map)} 条人员部门映射")
    else:
        print("⚠️  未提供 --dept-csv，L列人员将按无部门前缀处理")

    if not args.csv_file:
        biz_file_map = get_biz_file_map() if _HAS_SYNC_UTILS else {
            "rzrq": "DVGtPSXpzWU1zYXNi",
            "gpzy": "DVEtyb05taEFDc0xL",
            "qt":   "DVE9Gb0daTmtzUE9H",
        }
        biz = args.biz if args.biz else "rzrq"
        file_id = biz_file_map[biz]
        print(f"📡 自动通过 MCP 获取 {biz} 的在线表格结构 ({file_id})...")
        try:
            sheet_info = call_mcp("sheet.get_sheet_info", {"file_id": file_id})
        except Exception as e:
            print(f"❌ 获取在线表格结构失败: {e}", file=sys.stderr)
            sys.exit(1)

        sheets = sheet_info.get("sheets", [])
        if not sheets:
            print("❌ 未在目标表格中找到子表", file=sys.stderr)
            sys.exit(1)

        target_sheet = sheets[0]
        sheet_id     = target_sheet["sheet_id"]
        row_count    = target_sheet["row_count"]
        sheet_name   = target_sheet["sheet_name"]
        print(f"📡 正在读取子表 '{sheet_name}' (ID: {sheet_id}, 行数: {row_count}) 的数据...")

        try:
            cell_data = call_mcp("sheet.get_cell_data", {
                "file_id": file_id,
                "sheet_id": sheet_id,
                "start_row": 0,
                "end_row": row_count,
                "start_col": 0,
                "end_col": 12,
                "return_csv": True,
            })
        except Exception as e:
            print(f"❌ 读取表格数据失败: {e}", file=sys.stderr)
            sys.exit(1)

        csv_text = cell_data.get("csv_data", "")
    else:
        csv_text = Path(args.csv_file).read_text(encoding='utf-8')

    rows = parse_csv(csv_text)
    if not rows:
        print("⚠️ CSV 中无有效数据行", file=sys.stderr)
        sys.exit(1)

    md_index = get_md_index(args.md_dir)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = list(executor.map(
            lambda r: process_row(r, args.md_dir, args.dry_run, dept_map, index=md_index),
            rows
        ))

    # 输出到独立文件（供 agent 用 Write 工具写入）
    if args.output_dir:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for r in results:
            if r['status'] == 'updated' and r.get('new_content'):
                out_file = out_dir / Path(r['file']).name
                out_file.write_text(r['new_content'], encoding='utf-8')
                r['output_file'] = str(out_file)

    # 直接写入（有权限时）
    if args.apply:
        for r in results:
            if r['status'] == 'updated' and r.get('new_content'):
                try:
                    Path(r['file']).write_text(r['new_content'], encoding='utf-8')
                    r['written'] = True
                except PermissionError:
                    r['written'] = False
                    r['write_error'] = '权限不足'
                except Exception as e:
                    r['written'] = False
                    r['write_error'] = str(e)

    # ── 输出 ──
    if args.json:
        clean = [{k: v for k, v in r.items() if k != 'new_content'} for r in results]
        print(json.dumps(clean, ensure_ascii=False, indent=2))
    else:
        updated = 0
        skipped = 0
        for r in results:
            rname = r.get('name', '?')
            if r['status'] == 'updated':
                action = "预览" if r.get('dry_run') else "更新"
                written = ""
                if r.get('output_file'):
                    written = f" → {r['output_file']}"
                elif r.get('written'):
                    written = " (已写入)"
                elif r.get('write_error'):
                    written = f" (写入失败: {r['write_error']})"
                print(f"✅ [{rname}]: {action}了 {', '.join(r['changes'])}{written}")
                updated += 1
            elif r['status'] == 'unchanged':
                print(f"⏭️  [{rname}]: 内容已是最新")
            elif r['status'] == 'skipped_not_approved':
                print(f"⏭️  [{rname}]: {r['message']}")
                skipped += 1
            elif r['status'] == 'no_match':
                print(f"⚠️  [{rname}]: {r['message']}")
            elif r['status'] == 'error':
                print(f"❌ [{rname}]: {r['message']}")
        print(f"\n📊 共 {len(results)} 条记录: {updated} 条更新, "
              f"{len(results) - updated - skipped} 条跳过, {skipped} 条非通过状态过滤")

    has_error = any(r['status'] == 'error' for r in results)
    sys.exit(1 if has_error else 0)


if __name__ == '__main__':
    main()
