#!/usr/bin/env python3
"""
Coremail 邮件草稿保存脚本 (v3.30)

v3.30 变更:
  - fix: 标题提取逻辑改进——优先从 YAML frontmatter 的 topic 字段提取会议主题
  - fix: 跳过章节标题行（如 **一、会议背景**）避免误提取为邮件主题
  - fix: 新增识别"会议议题："行作为主题来源
  - 根因：v3.29 中 frontmatter 后第一个非空行是 **一、会议背景**，导致邮件主题为"关于**一、会议背景**的纪要"

v3.29 变更:
  - fix: YAML frontmatter 剥离逻辑改为正则精确匹配，仅当文件头部为 ---\n + YAML key:value行 + \n---\n 时剥离
  - 旧逐行扫描方法可能误匹配正文中的 --- 水平线；新方法确保只剥离真正的 YAML frontmatter 块
  - 新增调试日志：剥离时输出字节数和确认信息

v3.28 变更:
  - fix: 自动识别并解析正文中的“邮件主题：”行，将其作为邮件主题
  - fix: 邮件正文中自动过滤并去除 YAML frontmatter 标签以及“邮件主题：”整行，避免内容重复
  - fix: 增加删除本地重复 txt 文件后的安全单文件运行兼容性

v3.27 变更 (修复 --local 模式三个 bug):
  - fix: YAML frontmatter (--- ... ---) 不再被误认为会议标题，改为跳过 frontmatter 区域取第一个有效行
  - fix: resolve_csv_path 搜索范围从仅 SKILL_DIR → 扩展到当前工作目录及父级（最多 3 层）
  - fix: --local 模式 save_path/raw_transcript_path glob 同时匹配 .txt 和 .md 文件

v3.26 变更 (重写参会人提取，支持多行+部门格式):
  - 重写 extract_names_from_transcript: 支持三种参会人格式
    格式A（同行）: 参会人：张三、李四
    格式B（多行+部门）: 参会人：\n  技术研发部：张三、李四\n  系统运行部：王五
    格式C（带数量）: 参会人：张三、李四等12人
  - 新增部门前缀识别 (_looks_like_dept): 含部/组/中心/室等关键词
  - 新增人名校验 (_is_valid_person_name): 严格 2-4 汉字
  - 新增停止条件: 会议摘要/一二三章节标题/（注）等自动终止参会人区域
  - 新增跳过条件: "其余人员/以下为" 等非人名行
  - Step 1 成功时不再启用全文搜索兜底（避免"冯通""我"等误匹配）
  - Step 3 兜底仅在没有明确参会人区域时启用，附带警告提示


用法:
  # 本地模式：指定日期，自动从 save_path 搜索纪要文件
  python minutes_draft.py 20260526 --local [--no-headless]

  # 传统模式：指定正文文件和主题
  python minutes_draft.py --subject "主题" --body-file body.txt [--no-headless]
"""

import argparse, json, os, re, shutil, sys, urllib.parse
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    HAS_FERNET = True
except ImportError:
    HAS_FERNET = False

STORAGE_STATE_PATH = os.path.expanduser("~/.workbuddy/.cormail_storage_state.json")
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR  = SCRIPT_DIR.parent

# ────────────────────────────────────────────────
# 1.  config 查找（自动定位，与 SKILL.md 同级）
# ────────────────────────────────────────────────
def find_config(config_arg):
    if config_arg:
        p = Path(config_arg)
        if p.exists():
            if p.is_dir():
                cand = p / "config.json"
                if cand.exists():
                    return str(cand.resolve())
                return str(p.resolve())
            return str(p.resolve())
        print(f"[WARN] 指定路径不存在: {config_arg}，回退到自动查找")
    # 自动：SKILL_DIR/config.json
    cand = SKILL_DIR / "config.json"
    if cand.exists():
        return str(cand.resolve())
    raise FileNotFoundError(
        "config.json 未找到，请通过 --config 指定路径"
    )

def load_config(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def decrypt_password(enc):
    if not enc:
        return ""
    if isinstance(enc, list):
        enc = "".join(enc)
    m = re.match(r"^ENC:(.*)", enc)
    if not m:
        return enc
    if not HAS_FERNET:
        print("[ERROR] 密码已加密，请先 pip install cryptography")
        sys.exit(1)
    key = (os.environ.get("CORMAIL_ENC_KEY") or "").encode()
    if len(key) != 44:
        print("[ERROR] 环境变量 CORMAIL_ENC_KEY 未设置或长度不对（需要 44 字符）")
        sys.exit(1)
    try:
        return Fernet(key).decrypt(m.group(1).encode()).decode()
    except Exception as e:
        print(f"[ERROR] 密码解密失败: {e}")
        sys.exit(1)

# ────────────────────────────────────────────────
# 2.  纪要文件检测（--local 模式）
# ────────────────────────────────────────────────
def detect_local_transcript(config, date_str):
    raw_dir = config.get("raw_transcript_path", "")
    if not raw_dir:
        print("[ERROR] config 中 raw_transcript_path 未设置")
        sys.exit(1)
    p = Path(raw_dir)
    if not p.exists():
        print(f"[ERROR] raw_transcript_path 不存在: {p}")
        sys.exit(1)
    # 搜索匹配日期的文件
    pattern = f"*{date_str}*" if date_str else "*"
    files = sorted(p.glob(f"{pattern}.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        print(f"[ERROR] 未找到匹配 '{date_str}' 的转写文件")
        sys.exit(1)
    if len(files) == 1:
        return files[0], ""
    # 多个：列出供选择
    print(f"\n  找到 {len(files)} 个转写文件，请选择：")
    for i, f in enumerate(files, 1):
        print(f"    {i}. {f.name}")
    print(f"    输入编号（逗号分隔）或 a 全选，回车确认：", end="")
    choice = input().strip().lower()
    if choice == "a":
        chosen = files[0]   # 默认用第一个的主题 hint
        return chosen.resolve(), ""
    idxs = [int(x.strip()) - 1 for x in choice.split(",") if x.strip().isdigit()]
    chosen = files[idxs[0]] if idxs else files[0]
    return chosen.resolve(), ""

def resolve_csv_path(config):
    raw = config.get("csv_path", "")
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute():
        return str(p) if p.exists() else None
    # 搜索优先级：SKILL 目录 → 当前工作目录及其父级（最多往上 3 层）
    search_roots = [SKILL_DIR, Path.cwd()]
    for _ in range(3):
        pdir = Path.cwd().parent
        if pdir != Path.cwd():
            search_roots.append(pdir)
    for root in search_roots:
        cand = root / raw
        if cand.exists():
            return str(cand.resolve())
        for d in config.get("csv_search_dirs", []):
            if d:
                cand = root / d / raw
                if cand.exists():
                    return str(cand.resolve())
    return None


def get_sender_name(username, csv_path):
    """
    根据发件人邮箱用户名拼音去 CSV 中匹配其真实中文姓名。
    """
    if not username:
        return None
    email_prefix = username.split("@")[0].lower()
    email_prefix = re.sub(r"\d+$", "", email_prefix)
    if not email_prefix:
        return None

    # 兜底：如果是 wujin 打头，发件人姓名直接设定为 "吴进"
    if email_prefix.startswith("wujin"):
        return "吴进"

    sender_name = None
    try:
        import pypinyin
        import csv
        roster_names = []
        if csv_path and os.path.exists(csv_path):
            for encoding in ['utf-8', 'gbk', 'gb2312']:
                try:
                    with open(csv_path, mode='r', encoding=encoding) as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            name = row.get('人员', '')
                            if not name:
                                name = list(row.values())[0] if row.values() else ''
                            name = name.strip()
                            if name:
                                roster_names.append(name)
                    break
                except:
                    continue
        for rname in roster_names:
            name_pinyin = "".join(pypinyin.lazy_pinyin(rname)).lower()
            if name_pinyin == email_prefix:
                sender_name = rname
                break
    except Exception as e:
        print(f"[*] 解析发件人拼音出错: {e}")
    return sender_name

# ── 部门前缀关键词（用于判断"技术研发部：张三"中的前缀是否为部门名）──
_DEPT_KEYWORDS = ["部", "组", "中心", "室", "处", "科", "办"]

# ── 参会人区域停止标记（遇到这些行表示参会人列表结束）──
_ATTENDEE_STOP_PATTERNS = [
    re.compile(r"^(会议摘要|会议纪要|会议内容|会议议程)"),
    re.compile(r"^[一二三四五六七八九十]+[、.．]"),
    re.compile(r"^(一|二|三|四|五|六|七|八|九|十)[、.]"),
    re.compile(r"^#"),
    re.compile(r"^（注"),
    re.compile(r"^\(注"),
    re.compile(r"^>"),
]

def _is_stop_line(line):
    """判断是否到达参会人区域边界。"""
    for pat in _ATTENDEE_STOP_PATTERNS:
        if pat.match(line):
            return True
    return False

def _is_skip_line(line):
    """判断是否为应跳过的非人名行。"""
    skip_keywords = ["其余人员", "剩余人员", "其他人员", "以下为", "（注", "(注"]
    return any(kw in line for kw in skip_keywords)

def _looks_like_dept(text):
    """判断文本是否像部门名（含部/组/中心等关键词，长度 >= 3）。"""
    return len(text) >= 3 and any(kw in text for kw in _DEPT_KEYWORDS)

def _is_valid_person_name(text):
    """判断是否为有效中文人名（2-4个汉字，不含标点/数字/英文）。"""
    cleaned = text.strip()
    if not (2 <= len(cleaned) <= 4):
        return False
    return bool(re.fullmatch(r"[\u4e00-\u9fff]{2,4}", cleaned))

def extract_names_from_transcript(transcript_text, csv_path):
    """
    从纪要文本中提取参会人名，对照 CSV 匹配部门。

    支持三种参会人格式：
      格式A（同行）:   参会人：张三、李四、王五
      格式B（多行+部门）:
                      参会人（共25人，以下为转写中确认出席人员）：
                        技术研发部：张三、李四
                        系统运行部：王五
      格式C（带数量）: 参会人：张三、李四等12人

    Step 1 优先：解析参会人区域，精确提取 → 对照 CSV 分类 matched/unmatched
    Step 2 兜底：Step 1 零产出时，全文搜索 CSV 人名（last resort）

    返回: (matched_list, unmatched_list)
      matched_list:   [(姓名, 部门), ...]   — CSV 中找到了
      unmatched_list: [姓名, ...]           — CSV 中没有
    """
    matched = []
    unmatched = []
    known_names = set()
    name_to_dept = {}

    # ── 加载 CSV ──
    try:
        with open(csv_path, encoding="utf-8") as f:
            next(f, None)  # 跳过表头
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) >= 2:
                    name = parts[0].strip()
                    dept = parts[1].strip()
                    if name:
                        known_names.add(name)
                        name_to_dept[name] = dept
    except Exception as e:
        print(f"  [!] 读取 CSV 失败: {e}")
        return [], []

    if not known_names:
        return [], []

    # ═══════════════════════════════════════════════════════════════
    #  Step 1: 解析参会人区域（支持同行/多行/带括号三种格式）
    # ═══════════════════════════════════════════════════════════════
    all_attendees = []
    lines = transcript_text.split("\n")
    in_section = False
    same_line_names = None  # 同行格式的人名字符串

    for i, line in enumerate(lines):
        stripped = line.strip()

        # ── 检测参会人行首 ──
        m_start = re.match(
            r"参会人[（(].*?[）)]\s*[：:]?\s*$|"   # 参会人（共N人...）：
            r"参会人[：:]\s*$|"                     # 参会人：
            r"参会人[：:]\s*(.+?)(?:等\d+人)?$",    # 参会人：张三、李四等N人
            stripped
        )
        if m_start and not in_section:
            in_section = True
            # 同行格式：冒号后紧跟人名
            if m_start.lastindex and m_start.group(1):
                same_line_names = m_start.group(1).strip()
            continue

        if not in_section:
            continue

        # ── 空行处理：如果已收集到人名，空行=边界 ──
        if not stripped:
            if all_attendees:
                break   # 非空人名行后的空行 → 终止
            continue     # 还没收集到人名 → 跳过

        # ── 停止条件 ──
        if _is_stop_line(stripped):
            break

        # ── 跳过非人名行 ──
        if _is_skip_line(stripped):
            continue

        # ── 解析人名行 ──
        # 类型1: "技术研发部：张三、李四"  → 部门前缀 + 人名
        # 类型2: "张三、李四、王五"        → 纯人名
        # 类型3: "技术研发部 张三、李四"   → 空格分隔（备用）
        colon_m = re.match(r"^(.+?)[：:]\s*(.+)$", stripped)
        if colon_m:
            prefix = colon_m.group(1).strip()
            names_str = colon_m.group(2).strip()
            # 判断前缀是否为部门名
            if _looks_like_dept(prefix):
                # 部门名在前，后面是人名列表
                for name in re.split(r"[、,，\s]+", names_str):
                    name = name.strip()
                    if _is_valid_person_name(name):
                        all_attendees.append(name)
            else:
                # 前缀可能是人名（如"周倩：..."），先加前缀再拆分
                if _is_valid_person_name(prefix):
                    all_attendees.append(prefix)
                for name in re.split(r"[、,，\s]+", names_str):
                    name = name.strip()
                    if _is_valid_person_name(name):
                        all_attendees.append(name)
        else:
            # 无冒号：纯人名列表
            for name in re.split(r"[、,，\s]+", stripped):
                name = name.strip()
                if _is_valid_person_name(name):
                    all_attendees.append(name)

    # ── 处理同行格式的人名 ──
    if same_line_names and not all_attendees:
        for name in re.split(r"[、,，]", same_line_names):
            name = name.strip()
            if _is_valid_person_name(name):
                all_attendees.append(name)

    # ═══════════════════════════════════════════════════════════════
    #  Step 2: 对照 CSV 分类（matched / unmatched）
    # ═══════════════════════════════════════════════════════════════
    if all_attendees:
        print(f"  [-] Step 1 解析到 {len(all_attendees)} 位参会人: {'、'.join(all_attendees)}")
        seen = set()
        for name in all_attendees:
            if name in seen:
                continue
            seen.add(name)
            if name in known_names:
                matched.append((name, name_to_dept.get(name, "")))
            else:
                unmatched.append(name)
        if unmatched:
            print(f"  [*] CSV 未覆盖 ({len(unmatched)}人): {'、'.join(unmatched)}")
        return matched, unmatched

    # ═══════════════════════════════════════════════════════════════
    #  Step 3 (兜底): 全文搜索 CSV 人名
    #  仅在 Step 1 零产出时才启用（说明纪要没有明确的"参会人"区域）
    # ═══════════════════════════════════════════════════════════════
    print("  [*] 未找到「参会人」区域，启用全文搜索兜底（可能不准）")

    sorted_names = sorted(known_names, key=lambda n: len(n), reverse=True)
    found_positions = []

    for name in sorted_names:
        pattern = re.compile(re.escape(name))
        for m in pattern.finditer(transcript_text):
            overlap = any(
                existing[0] <= m.start() < existing[1]
                or existing[0] < m.end() <= existing[1]
                for existing in found_positions
            )
            if not overlap:
                found_positions.append((m.start(), m.end(), name))

    found_positions.sort(key=lambda x: x[0])
    seen = set()
    for _, _, name in found_positions:
        if name not in seen:
            seen.add(name)
            matched.append((name, name_to_dept.get(name, "")))

    return matched, unmatched

# ────────────────────────────────────────────────
# 3.  Session 管理
# ────────────────────────────────────────────────
def try_restore_session(page, url):
    """
    尝试用 session 恢复登录。
    返回: (success: bool, page) 
      - success=True, page 可能是原 page 或新 tab 的 page
      - success=False, page 不变
    """
    if not Path(STORAGE_STATE_PATH).exists():
        return False, page
    try:
        # Plan C: commit 不等 HTML 解析，直接让服务器响应就返回
        page.goto(url, wait_until="commit", timeout=10_000)
        # 快速轮询：先 2s，没找到再 3s
        for wait_s in [2_000, 3_000]:
            el, _ = wait_for_compose_btn(page, timeout=wait_s)
            if el:
                print(f"  [+] Session 恢复成功 (当前 tab, {wait_s//1000}s)")
                return True, page
    except Exception:
        pass

    # 检查是否有新 tab（session 恢复后可能在新 tab 打开）
    all_pages = page.context.pages
    if len(all_pages) > 1:
        for p in all_pages:
            el, _ = wait_for_compose_btn(p, timeout=3_000)
            if el:
                p.bring_to_front()
                print(f"  [+] Session 恢复成功 (新 tab): {p.url}")
                return True, p

    return False, page

def save_session(context):
    try:
        context.storage_state(path=STORAGE_STATE_PATH)
        print(f"  [+] Session 已保存: {STORAGE_STATE_PATH}")
    except Exception as e:
        print(f"  [!] Session 保存失败: {e}")

def login_coremail(page, url, username, password):
    """填写登录表单并提交。"""
    print("[1/5] Logging in...")
    # Plan C: commit 不等 HTML 解析，然后 2s 轮询登录表单
    page.goto(url, wait_until="commit", timeout=10_000)

    SEL_UID   = ", ".join([
        'input[name="uid"]', 'input[id*="uid"]',
        'input[placeholder*="账号"]', 'input[placeholder*="邮箱"]',
        'input[type="text"]',
    ])
    SEL_PWD   = ", ".join([
        'input[name="password"]', 'input[name="pwd"]',
        'input[type="password"]',
    ])
    SEL_LOGIN_BTN = ", ".join([
        'input[type="submit"]', 'button:has-text("登录")',
        'button:has-text("登入")', 'input[value*="登录"]',
        'a:has-text("登录")',
    ])

    # 快速轮询登录表单：2s → 3s → 5s 递进
    uid_el = None
    for wait_s in [2_000, 3_000, 5_000]:
        try:
            uid_el = page.wait_for_selector(SEL_UID, timeout=wait_s)
            if uid_el:
                break
        except Exception:
            print(f"  [*] 登录表单尚未出现 ({wait_s//1000}s)，继续等待...")
    if not uid_el:
        raise Exception("登录表单未出现，请检查 Coremail 页面是否正常")

    uid_el.click()
    uid_el.fill(username)
    print(f"  [-] UID: {username}")

    try:
        pwd_el = page.wait_for_selector(SEL_PWD, timeout=5_000)
        pwd_el.fill(password)
        print("  [-] Password: ****")
    except Exception as e:
        print(f"  [!] PWD selector: {e}")
        raise

    # 填完密码立刻回车
    page.keyboard.press("Enter")
    print("  [-] Login submitted (Enter)")

    # 等登录跳转完成，轮询等待新 tab 出现（最多 1.5 秒）
    for _ in range(15):
        if len(page.context.pages) > 1:
            break
        page.wait_for_timeout(100)

    # 检查是否有新 tab 打开
    all_pages = page.context.pages
    if len(all_pages) > 1:
        print(f"  [*] 检测到 {len(all_pages)} 个 tab，查找邮箱主页...")
        for p in all_pages:
            el, _ = wait_for_compose_btn(p, timeout=5_000)
            if el:
                page = p
                page.bring_to_front()
                print(f"  [+] 切换到新 tab: {page.url}")
                break

    print("[2/5] Verifying login...")
    el, _ = wait_for_compose_btn(page, timeout=15_000)
    if el:
        print("  [+] Logged in!")
    else:
        try:
            shot = Path(__file__).resolve().parent / "debug_login_fail.png"
            page.screenshot(path=str(shot))
            print(f"  [!] 登录失败截图: {shot}")
        except Exception:
            pass
        raise Exception(
            "登录失败：未找到'写信'按钮。"
            "请检查：(1) 账号密码是否正确 (2) 是否有验证码 (3) 是否在 --no-headless 模式下手动处理"
        )

    return page


# ────────────────────────────────────────────────
# 4.  填写收件人（下拉框）
# ────────────────────────────────────────────────
SEL_TO  = ", ".join([
    'input#toInput', 'input#to', 'input[id*="toInput"]', 'input[id*="toAddrInput"]', '#toAddrInput',
    'input[placeholder*="收件人"]', 'input[placeholder*="收件"]',
    'input[title*="收件人"]', 'input[title*="收件"]',
    'input[name="to"]', 'textarea[name="to"]', 'textarea[id*="to"]',
    'input[class*="addr"]', 'textarea[class*="addr"]',
])
SEL_CC  = ", ".join([
    'input[name="cc"]', 'input[id*="cc"]', 'input[id*="Cc"]',
    'textarea[name="cc"]', 'textarea[id*="cc"]',
    'input[placeholder*="抄送"]', 'input[title*="抄送"]',
])

def fill_recipients_with_dropdown(page, target, names, debug=False):
    """
    逐个输入收件人，并敲击回车确认，确保 Coremail 稳定解析所有收件人为 Tag。
    """
    if not names:
        return

    # ── 确认焦点在收件人字段 ──
    try:
        to_el = target.wait_for_selector(SEL_TO, timeout=5_000)
        if to_el:
            to_el.focus()
            to_el.evaluate("el => el.click()")
            print("  [+] Focused and JS-clicked To input field")
    except Exception as e:
        print(f"  [!] Failed to focus To input field: {e}")
    page.wait_for_timeout(200)

    try:
        for name in names:
            page.keyboard.type(name, delay=10)
            page.wait_for_timeout(800)  # 等待下拉建议显现
            page.keyboard.press("Enter")
            page.wait_for_timeout(200)  # 等待 Tag 稳定渲染
            print(f"  [+] Entered recipient: {name}")
    except Exception as e:
        print(f"  [!] Failed to type recipients: {e}")


# ────────────────────────────────────────────────
# 5.  写信 & 存草稿
# ────────────────────────────────────────────────
SEL_COMPOSE = ", ".join([
    'a:has-text("写信")', 'button:has-text("写信")',
    'span:has-text("写信")', 'div:has-text("写信")', 'li:has-text("写信")',
    '[title*="写信"]', '[aria-label*="写信"]',
    '#composeBtn', '.compose-btn', '.btn-compose',
])


def wait_for_compose_btn(page, timeout=15_000):
    """用多种方式等待"写信"按钮出现。在主 page 和所有子 frame 中查找，返回 (el, frame) 或 (None, None)"""
    import time
    end_time = time.time() + (timeout / 1000.0)
    
    while True:
        # 1. 尝试主 page
        try:
            el = page.query_selector(SEL_COMPOSE)
            if el and el.is_visible():
                return el, page
        except Exception:
            pass
            
        # 2. 尝试所有 iframe
        for fr in page.frames:
            if fr == page:
                continue
            try:
                el = fr.query_selector(SEL_COMPOSE)
                if el and el.is_visible():
                    return el, fr
            except Exception:
                continue
                
        if time.time() >= end_time:
            break
        page.wait_for_timeout(200)
        
    return None, None
SEL_SUBJ = ", ".join([
    'input[name="subject"]', 'input[id*="subject"]', 'input[id*="Subject"]',
    'input[placeholder*="主题"]', 'input[title*="主题"]',
    'textarea[name="subject"]', 'textarea[placeholder*="主题"]',
])

def convert_md_table_to_html(rows):
    if len(rows) < 2:
        return "\n".join(rows)
    headers = [cell.strip() for cell in rows[0].split("|")[1:-1]]
    sep_cells = [cell.strip() for cell in rows[1].split("|")[1:-1]]
    if not all(re.match(r"^:?-+:?$", cell) for cell in sep_cells):
        return "\n".join(rows)
    
    html = []
    html.append('<table style="border-collapse: collapse; width: 100%; border: 1px solid #ddd; font-size: 14px; font-family: sans-serif; margin: 15px 0;">')
    html.append('<thead>')
    html.append('<tr style="background-color: #f2f2f2; text-align: left;">')
    for cell in headers:
        cell_formatted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", cell)
        html.append(f'<th style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">{cell_formatted}</th>')
    html.append('</tr>')
    html.append('</thead>')
    html.append('<tbody>')
    for row in rows[2:]:
        cells = [cell.strip() for cell in row.split("|")[1:-1]]
        html.append('<tr>')
        for cell in cells:
            cell_formatted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", cell)
            html.append(f'<td style="padding: 10px; border: 1px solid #ddd;">{cell_formatted}</td>')
        html.append('</tr>')
    html.append('</tbody>')
    html.append('</table>')
    return "".join(html)

def md_to_html(md: str) -> str:
    # 1. First parse tables
    lines = md.split("\n")
    new_lines = []
    in_table = False
    table_rows = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            in_table = True
            table_rows.append(line)
        else:
            if in_table:
                html_table = convert_md_table_to_html(table_rows)
                new_lines.append(html_table)
                in_table = False
                table_rows = []
            new_lines.append(line)
            
    if in_table:
        html_table = convert_md_table_to_html(table_rows)
        new_lines.append(html_table)
        
    html = "\n".join(new_lines)
    
    # 2. General markdown formatting
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = html.replace("　", "&nbsp;&nbsp;")
    html = html.replace("\n\n", "<div><br></div>")
    html = html.replace("\n", "<br>")
    return html

def insert_body(page, body_text):
    """将正文插入 Coremail 编辑器。
    KindEditor 可能用 designMode='on' 或 contentEditable='true'，轮询等待异步加载。"""
    html = md_to_html(body_text)
    js_html = json.dumps(html)

    inserted = False

    # ── 检测条件：designMode='on'（KindEditor 标准）或 contentEditable='true' ──
    def _is_editor_body(fr):
        try:
            return fr.evaluate("""() => {
                const d = document;
                return (d.designMode === 'on') ||
                       (d.body && d.body.contentEditable === 'true') ||
                       (d.querySelector('[contenteditable="true"]') !== null);
            }""")
        except Exception:
            return False

    def _write_body(fr):
        try:
            fr.evaluate(f"""
                (() => {{
                    const d = document;
                    if (d.designMode === 'on') {{
                        d.open();
                        d.write({js_html});
                        d.close();
                    }} else if (d.body && d.body.contentEditable === 'true') {{
                        d.body.innerHTML = {js_html};
                        d.body.dispatchEvent(new Event("input", {{bubbles:true}}));
                    }} else {{
                        const ed = d.querySelector('[contenteditable="true"]');
                        if (ed) {{
                            ed.innerHTML = {js_html};
                            ed.dispatchEvent(new Event("input", {{bubbles:true}}));
                        }}
                    }}
                }})()
            """)
            return True
        except Exception:
            return False

    # ── 先立即检查（body editor 通常已加载）──
    print(f"  [D] Total frames: {len(page.frames)}")
    for idx, fr in enumerate(page.frames):
        if fr == page:
            continue
        if _is_editor_body(fr):
            if _write_body(fr):
                print(f"  [+] Body in frame #{idx} (immediate)")
                return True

    # ── 未找到则轮询等待异步加载（最多 10 秒）──
    for attempt in range(20):
        for idx, fr in enumerate(page.frames):
            if fr == page:
                continue
            if _is_editor_body(fr):
                if _write_body(fr):
                    print(f"  [+] Body in frame #{idx} (attempt {attempt+1})")
                    inserted = True
                    break
        if inserted:
            break
        page.wait_for_timeout(500)

    if not inserted:
        # 降级：点击 body 区域激活编辑器再搜
        print("  [*] Trying click-activate for body editor...")
        try:
            body_area = page.locator(
                "iframe[id*='_ke'], iframe[title*='编辑'], iframe[src*='ke'], "
                "iframe[src*='editor'], body[contenteditable]"
            ).first
            body_area.click(force=True)
            page.wait_for_timeout(1_500)
            for attempt in range(20):
                for idx, fr in enumerate(page.frames):
                    if fr == page:
                        continue
                    if _is_editor_body(fr):
                        if _write_body(fr):
                            print(f"  [+] Body after click-activate in frame #{idx}")
                            inserted = True
                            break
                if inserted:
                    break
                page.wait_for_timeout(500)
        except Exception:
            pass

    if not inserted:
        print("  [!] Body insert failed (no editor iframe found)")

    return inserted

def compose_and_save(page, subject, body_text, recipient, cc, recipient_names=None, debug=False):
    print("[3/5] Opening compose...")

    # 先确保回到邮箱主页，找到"写信"按钮
    # Coremail 的"写信"可能在主 page，也可能在 iframe 里
    def find_in_all_frames(page, selector, timeout=8_000):
        """在所有 frame（含主 page）里找元素，返回第一个可见的"""
        # 先试主 page
        try:
            el = page.wait_for_selector(selector, timeout=timeout)
            if el and el.is_visible():
                return el, None  # None 表示在主 page
        except Exception:
            pass
        # 再试所有 iframe
        for fr in page.frames:
            if fr == page:
                continue
            try:
                el = fr.wait_for_selector(selector, timeout=2_000)
                if el and el.is_visible():
                    return el, fr
            except Exception:
                continue
        return None, None

    btn, btn_frame = find_in_all_frames(page, SEL_COMPOSE, timeout=3_000)
    if btn:
        btn.click()
        print("  [+] Compose clicked")
    else:
        print("  [!] Compose button not found, trying direct URL...")
        base = "/".join(page.url.split("/")[:3])
        for path in [
            "/coremail/XTS/jsp/compose.jsp",
            "/coremail/compose.jsp",
        ]:
            try:
                page.goto(base + path, wait_until="domcontentloaded", timeout=8_000)
                break
            except Exception:
                continue

    # ── 点击"写信"或直接打开 URL 后，立即检查是否有新 tab 打开 ──
    all_pages = page.context.pages
    if len(all_pages) > 1:
        print(f"  [*] compose 后检测到 {len(all_pages)} 个 tab，查找写邮件页面...")
        for p in all_pages:
            try:
                p.wait_for_selector(
                    "input[name='to'], textarea[name='to'], "
                    "input[name='subject'], input[id*='subject'], "
                    "input[placeholder*='主题']",
                    timeout=3_000
                )
                page = p
                page.bring_to_front()
                print(f"  [+] 切换到写邮件 tab: {page.url}")
                break
            except Exception:
                continue

    # 等写信表单加载，同时定位 compose_frame（B: 统一检测+赋值）
    print("  [-] Waiting for compose form...")
    compose_frame = None
    for _ in range(8):  # 最多等 4 秒
        page.wait_for_timeout(500)
        for fr in ([page] + [f for f in page.frames if f != page]):
            try:
                el = fr.query_selector(SEL_SUBJ + ", " + SEL_TO)
                if el and el.is_visible():
                    compose_frame = fr
                    break
            except Exception:
                continue
        if compose_frame:
            break

    if not compose_frame:
        print("  [!] Compose form not loaded, taking screenshot...")
        try:
            shot = Path(__file__).resolve().parent / "debug_compose_form.png"
            page.screenshot(path=str(shot))
            print(f"      Screenshot: {shot}")
        except Exception:
            pass
        compose_frame = page  # 回退，后续操作仍尝试

    target = compose_frame
    print(f"  [+] Form found in {'page' if target == page else 'iframe'}")

    # ── 收件人：优先用 recipient_names（列表，逐个触发下拉选第一条）──
    if recipient_names:
        fill_recipients_with_dropdown(page, target, recipient_names, debug=debug)
    elif recipient:
        try:
            to_el = target.wait_for_selector(SEL_TO, timeout=3_000)
            to_el.fill(recipient)
            print(f"  [-] To: {recipient}")
        except Exception:
            print("  [*] To-field skipped")

    if cc:
        try:
            cc_el = target.wait_for_selector(SEL_CC, timeout=3_000)
            cc_el.fill(cc)
            print(f"  [-] Cc: {cc}")
        except Exception:
            print("  [*] Cc-field skipped")

    # ── 主题 ──
    try:
        subj_el = target.wait_for_selector(SEL_SUBJ, timeout=5_000)
        subj_el.fill(subject)
        print(f"  [-] Subject: {subject[:40]}...")
    except Exception as e:
        print(f"  [!] Subject field: {e}")

    # ── 正文 ──
    insert_body(page, body_text)

    # ── 存草稿（三重触发策略，Coremail 自定义组件单一方法不可靠）──
    print("[4/5] Saving draft...")
    # 收窄选择器：只精确匹配含"存草稿"文字的 a/button/span
    # 去掉 [class*="draft"]/.draft-btn 等宽泛选择器——可能匹配侧边栏"草稿箱"
    SEL_SAVE_DRAFT = ", ".join([
        'a:has-text("存草稿")', 'button:has-text("存草稿")',
        'span:has-text("存草稿")', 'a[title*="存草稿"]',
        'a:has-text("保存")', 'button:has-text("保存")',
    ])

    # 先搜 target(iframe)，再回退 page；按钮和写邮件表单通常在同一个 frame
    save_btn = None
    for scope_label, scope in [("target", target), ("page", page)]:
        if scope_label == "page" and scope == target:
            continue  # target == page 时避免重复
        try:
            save_btn = scope.wait_for_selector(SEL_SAVE_DRAFT, timeout=3_000)
            if save_btn:
                # 打印匹配元素信息，确认到底匹配到了什么
                info = save_btn.evaluate("""el => {
                    const tag = el.tagName.toLowerCase();
                    const text = (el.textContent || '').trim().substring(0, 30);
                    const cls = (el.className || '').toString().substring(0, 50);
                    const href = el.getAttribute('href') || '';
                    return {tag, text, cls, href};
                }""")
                print(f"  [-] Save button found in {scope_label}: <{info['tag']}> text='{info['text']}' class='{info['cls']}' href='{info['href']}'")
                break
        except Exception:
            continue

    if save_btn:
        save_btn.scroll_into_view_if_needed()
        # 点击前截图（调试用）
        try:
            shot = Path(__file__).resolve().parent / "debug_before_save.png"
            page.screenshot(path=str(shot))
            print(f"  [D] Pre-save screenshot: {shot}")
        except Exception:
            pass

        # ── 触发存草稿 ──
        # v3.22 实测: MouseEvent dispatch 对 Coremail 的 span.j-tbl-draft 有效
        save_btn.evaluate("""el => {
            const opts = {bubbles: true, cancelable: true, view: window};
            el.dispatchEvent(new MouseEvent('mousedown', opts));
            el.dispatchEvent(new MouseEvent('mouseup', opts));
            el.dispatchEvent(new MouseEvent('click', opts));
            el.focus();
        }""")
        print("  [-] Save dispatched (MouseEvent)")

        # ── 验证保存结果 ──
        # Coremail 实际提示为「保存草稿成功」（绿色提示条）
        try:
            page.locator('text=/保存草稿成功|草稿已保存|已保存|保存成功/').wait_for(timeout=3000)
            for confirm_text in ["保存草稿成功", "草稿已保存", "已保存", "保存成功"]:
                if page.locator(f"text={confirm_text}").is_visible():
                    print(f"  [+] ✅ 确认: {confirm_text}")
                    saved = True
                    break
        except Exception:
            pass

        if not saved:
            print("  [*] 未检测到保存确认，草稿大概率已保存")

        # ── 关闭写邮件内部标签（而非关闭整个浏览器 tab）──
        # Coremail 内部标签栏结构: [欢迎页] [20260526 ×]
        # 点击 × 关闭当前写邮件标签，自动回到收件箱/欢迎页
        SEL_TAB_CLOSE = ", ".join([
            'div.tab-title:has-text("写信") span.tab-close',
            'div.tab-item:has-text("写信") a.close',
            'span.tab-close',
            'a.close-tab',
            'li.active a.close',
        ])
        closed = False
        try:
            close_btn = page.query_selector(SEL_TAB_CLOSE)
            if close_btn:
                close_btn.click(force=True)
                page.wait_for_timeout(200)
                closed = True
        except Exception as e:
            print(f"  [*] Internal tab close failed: {e}")

        if not closed:
            try:
                # 尝试按 Escape 关闭写邮件标签
                page.keyboard.press("Escape")
                page.wait_for_timeout(100)
                print("  [-] Tried Escape to close compose tab")
                closed = True
            except Exception:
                pass

        return saved, page


def main():
    ap = argparse.ArgumentParser(
        description="""Coremail Draft Saver Utility

示例:
  python minutes_draft.py 20260526 --local --no-headless
  python minutes_draft.py 20260526 --local --subject "【会议纪要】612上线规划"
  python minutes_draft.py --subject "主题" --body-file body.txt --no-headless
        """,
    )
    ap.add_argument("date", nargs="?", default="",
                    help="日期 (YYYYMMDD)，--local 模式下用于搜索匹配的纪要文件")
    ap.add_argument("--config", default="",
                    help="config.json 路径（文件或目录，默认自动查找 SKILL.md 同级）")
    ap.add_argument("--local", action="store_true",
                    help="本地模式：从 config.save_path 搜索匹配日期的纪要文件")
    ap.add_argument("--subject", default="",
                    help="邮件主题（--local 模式可选，自动从纪要文件提取）")
    ap.add_argument("--body-file", default="",
                    help="邮件正文文件（--local 模式可选，纪要文件直接作为正文）")
    ap.add_argument("--recipient", default="", help="收件人（覆盖 config）")
    ap.add_argument("--cc", default="", help="抄送（覆盖 config）")
    ap.add_argument("--no-headless", action="store_true",
                    help="显示浏览器窗口（强烈推荐，避免验证码问题）")
    args = ap.parse_args()

    # ── 定位 config ──
    cfg_path = find_config(args.config)
    print(f"[*] Config: {cfg_path}")
    cfg = load_config(cfg_path)

    mail_cfg = cfg.get("mail", {})
    url      = mail_cfg.get("url", "https://mail.gtht.com/")
    username = mail_cfg.get("username", "")
    password = decrypt_password(mail_cfg.get("password", ""))

    if not username or not password:
        print("[ERROR] mail.username / mail.password 未设置于 config.json")
        sys.exit(1)

    # ════════════════════════════════════════════
    #  --local 模式：收集所有要处理的纪要文件
    # ════════════════════════════════════════════
    minutes_files = []   # 存所有选中的纪要文件路径（Path 对象）
    if args.local:
        save_dir = cfg.get("save_path", "")
        if save_dir and args.date:
            save_p = Path(save_dir)
            if save_p.exists():
                candidates = sorted(
                    [f for f in save_p.glob(f"{args.date}*") if f.is_file() and f.suffix in (".txt", ".md")],
                    key=lambda f: f.stat().st_mtime, reverse=True
                )
                if candidates:
                    minutes_files = list(candidates)
                    print(f"  [+] 当日 {len(candidates)} 份纪要，全部处理:")
                    for i, f in enumerate(candidates, 1):
                        print(f"      {i}. {f.name}")

        # 如果 save_path 没有，回退到 raw_transcript_path（取全部文件）
        if not minutes_files:
            raw_dir = cfg.get("raw_transcript_path", "")
            if raw_dir:
                raw_p = Path(raw_dir)
                if raw_p.exists():
                    raw_files = sorted(
                        [f for f in raw_p.glob(f"{args.date}*") if f.is_file() and f.suffix in (".txt", ".md")],
                        key=lambda f: f.stat().st_mtime, reverse=True
                    )
                    if raw_files:
                        minutes_files = raw_files
                        print(f"  [*] save_path 无纪要，回退到 raw 目录，找到 {len(raw_files)} 个转写文件:")
                        for i, f in enumerate(raw_files, 1):
                            print(f"      {i}. {f.name}")

        if not minutes_files:
            print("[ERROR] 未能找到任何纪要/转写文件")
            sys.exit(1)

        # 为每份纪要预先提取：主题 hint、收件人名单
        tasks = []  # [(minutes_path, subject, body_content, recipient_names)]
        csv_path = resolve_csv_path(cfg)

        for mf in minutes_files:
            content = mf.read_text(encoding="utf-8")
            # 提取会议标题/主题：优先从 YAML frontmatter 的 topic 字段提取
            # 回退：跳过 frontmatter，取第一个有效非空行（排除章节标题如 **一、会议背景**）
            meeting_title = ""
            email_subject = ""
            # 尝试从 YAML frontmatter 提取 topic
            yaml_topic_match = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
            if yaml_topic_match:
                yaml_body = yaml_topic_match.group(1)
                for yline in yaml_body.split("\n"):
                    ystripped = yline.strip()
                    if ystripped.startswith("topic:") or ystripped.startswith("topic :"):
                        meeting_title = re.sub(r"^topic\s*:\s*", "", ystripped).strip()
                        break
            # 如 frontmatter 未提供 topic，回退到正文提取
            if not meeting_title:
                in_frontmatter = False
                for line in content.split("\n"):
                    stripped = line.strip()
                    if stripped == "---":
                        in_frontmatter = not in_frontmatter
                        continue
                    if in_frontmatter:
                        continue
                    if stripped:
                        # 跳过章节标题（**一、...**、**二、...**、**三、...**）
                        if re.match(r'^\*\*[一二三四五六七八九十]、', stripped):
                            continue
                        # 跳过纯加粗行但不含序号的（如 **会议背景**）
                        if re.match(r'^\*\*[^*]+\*\*\s*$', stripped) and not re.match(r'^\*\*\d+\.', stripped):
                            continue
                        if stripped.startswith("邮件主题：") or stripped.startswith("邮件主题:"):
                            email_subject = re.sub(r"^邮件主题[：:]\s*", "", stripped)
                        else:
                            # 优先匹配 "会议议题：" 行
                            topic_match = re.match(r'^会议议题[：:]\s*(.+)', stripped)
                            if topic_match:
                                meeting_title = topic_match.group(1).strip()
                            else:
                                meeting_title = stripped
                        break

            # 构造邮件主题
            subject = args.subject or email_subject or ""
            if not subject:
                date_str = args.date if len(args.date) == 8 else ""
                if date_str and meeting_title:
                    subject = f"{date_str} 关于{meeting_title}的纪要"
                elif meeting_title:
                    subject = f"关于{meeting_title}的纪要"
                elif date_str:
                    subject = f"{date_str} 会议纪要"
                else:
                    subject = "会议纪要"

            # 提取收件人
            recipient_names = None
            if csv_path:
                matched, unmatched = extract_names_from_transcript(content, csv_path)
                if matched or unmatched:
                    sender_name = get_sender_name(username, csv_path)
                    matched_filtered = [(n, d) for n, d in matched if n != sender_name]
                    unmatched_filtered = [n for n in unmatched if n != sender_name]

                    # ── 按部门分组显示 ──
                    dept_groups = {}  # {部门: [姓名, ...]}
                    for name, dept in matched_filtered:
                        dept_groups.setdefault(dept, []).append(name)
                    if unmatched_filtered:
                        dept_groups.setdefault("其他", []).extend(unmatched_filtered)

                    total_before = len(matched) + len(unmatched)
                    total_after = len(matched_filtered) + len(unmatched_filtered)
                    print(f"  [*] {mf.name} → 提取到 {total_before} 位参会人 (已排除发件人 {sender_name}，剩 {total_after} 人):")
                    for dept in dept_groups:
                        names_str = "、".join(dept_groups[dept])
                        # 标记未匹配的
                        if dept == "其他":
                            names_str += "  ← CSV未覆盖"
                        print(f"      [{dept}] {names_str}")

                    recipient_names = [name for name, _ in matched_filtered] + unmatched_filtered
                else:
                    print(f"  [*] {mf.name} → 未提取到参会人")
            else:
                print(f"  [*] {mf.name} → CSV 路径未配置，跳过收件人提取")

            # Strip YAML frontmatter for email body
            # 使用正则从文件头部精确匹配 --- ... --- 块（仅在开头且包含 YAML key: value 行时剥离）
            body_content = content
            fm_match = re.match(
                r"^---\s*\n(?:[a-zA-Z_][\w.-]*\s*:.+\n)+---\s*\n",
                content
            )
            if fm_match:
                body_content = content[fm_match.end():].strip()
                print(f"  [D] 已剥离 YAML frontmatter ({fm_match.end()} 字节)")

            # Strip "邮件主题：" line from body if present
            body_lines = body_content.split("\n")
            if body_lines:
                first_line = body_lines[0].strip()
                if first_line.startswith("邮件主题：") or first_line.startswith("邮件主题:"):
                    body_content = "\n".join(body_lines[1:]).strip()
                    print(f"  [D] 已剥离邮件主题行")

            tasks.append({
                "path": mf,
                "subject": subject,
                "body": body_content,
                "recipient_names": recipient_names,
            })

        # 如果同时提供了 --body-file，追加到最后一份纪要
        if args.body_file:
            extra_path = Path(args.body_file)
            if not extra_path.exists():
                print(f"[ERROR] 正文文件不存在: {extra_path}")
                sys.exit(1)
            extra = extra_path.read_text(encoding="utf-8")
            tasks[-1]["body"] += "\n\n" + extra
            print(f"  [*] 已追加 --body-file 内容 ({len(extra)} 字符) 到最后一份纪要")

    else:
        # ── 传统模式：--body-file 和 --subject 必填 ──
        if not args.body_file:
            print("[ERROR] 非 --local 模式下 --body-file 是必填参数")
            ap.print_usage()
            sys.exit(1)
        if not args.subject:
            print("[ERROR] 非 --local 模式下 --subject 是必填参数")
            ap.print_usage()
            sys.exit(1)
        body_path = Path(args.body_file)
        if not body_path.exists():
            print(f"[ERROR] 正文文件不存在: {body_path}")
            sys.exit(1)
        tasks = [{
            "path": None,
            "subject": args.subject,
            "body": body_path.read_text(encoding="utf-8"),
            "recipient_names": None,
        }]

    recipient = args.recipient or mail_cfg.get("default_recipient", "")
    cc        = args.cc or mail_cfg.get("default_cc", "")

    # ════════════════════════════════════════════
    #  启动 Playwright（只一次）
    # ════════════════════════════════════════════
    debug_mode = args.no_headless   # --no-headless 时开启下拉调试截图
    from playwright.sync_api import sync_playwright

    headless = not args.no_headless
    
    chrome_locs = [
        shutil.which("google-chrome"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        Path(os.path.expanduser("~/AppData/Local/Google/Chrome/Application/chrome.exe")).as_posix(),
    ]
    chrome_exe = next(
        (loc for loc in chrome_locs if loc and Path(loc).exists()),
        None,
    )

    with sync_playwright() as pw:
        browser = None
        try:
            browser = pw.chromium.launch(headless=headless, executable_path=chrome_exe)
            print(f"[*] 浏览器: {chrome_exe or 'Playwright Bundled'}")
        except Exception as err:
            print(f"[!] Chrome 启动失败 ({err})，使用内置 Chromium")
            browser = pw.chromium.launch(headless=headless)

        ctx_kwargs = {
            "viewport": {"width": 1280, "height": 900},
            "locale": "zh-CN",
        }
        if Path(STORAGE_STATE_PATH).exists():
            ctx_kwargs["storage_state"] = STORAGE_STATE_PATH
            print(f"[*] 复用登录态: {STORAGE_STATE_PATH}")

        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()

        try:
            # 登录（只一次）
            restored, page = try_restore_session(page, url)
            if not restored:
                page = login_coremail(page, url, username, password)
                save_session(ctx)

            # 记录收件箱地址（登录后的实际页面 URL，非登录页）
            mailbox_url = page.url
            print(f"  [*] 收件箱: {mailbox_url}")

            # 循环处理每份纪要
            for i, task in enumerate(tasks, 1):
                print(f"\n{'='*55}")
                print(f"  处理第 {i}/{len(tasks)} 份: {task['subject'][:40]}...")
                # 打印本封邮件的收件人名单（确认按纪要独立）
                rn = task.get("recipient_names") or []
                if rn:
                    print(f"  收件人({len(rn)}人): {'、'.join(rn)}")
                print(f"{'='*55}")

                _, page = compose_and_save(
                    page,
                    task["subject"],
                    task["body"],
                    recipient,
                    cc,
                    recipient_names=task["recipient_names"],
                    debug=debug_mode,
                )
                print(f"  [DONE] 第 {i} 份草稿已保存!")

                # ── compose_and_save 已关闭 Coremail 内部写邮件标签 ──
                # page 仍然有效（浏览器 tab 没关），直接点"写信"开下一封
                if i < len(tasks):
                    print("  [*] 点击「写信」开下一封...")
                    try:
                        el, target = wait_for_compose_btn(page, timeout=10_000)
                        if el:
                            el.click(force=True)
                            print("  [+] 写信按钮 clicked")
                        else:
                            print("  [!] 未找到写信按钮，尝试导航到收件箱")
                            page.goto(mailbox_url, wait_until="commit", timeout=10_000)
                            page.wait_for_timeout(2_000)
                            el, _ = wait_for_compose_btn(page, timeout=5_000)
                            if el:
                                el.click(force=True)
                    except Exception as e:
                        print(f"  [!] 下一封准备失败: {e}")

            print(f"\n[DONE] 共处理 {len(tasks)} 份纪要，草稿已全部保存!")

        except Exception as exc:
            print(f"\n[ERROR] {exc}")
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
