#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
SVN 需求号粒度代码合并脚本
============================
流程：
  1. 对本地工作目录执行 svn update
  2. 解析 DATA_TEXT 中的表格数据（需求号 / 任务号 / 任务标题 / 经办人）
  3. 按需求号为粒度，从 UAT_NGTP 分支搜索相关 revision 并 merge
  4. 无冲突则 svn commit
  5. 有冲突则 svn revert → svn update → 记录需求号，继续下一个
  6. 全部处理完后，将有冲突的需求号输出为 txt 文件
"""

import subprocess
import sys
import os
import re
import argparse
from collections import defaultdict
from datetime import datetime

def _get_default_commit_prefix():
    filename = "合并版本号.txt"
    # 尝试在当前工作目录下查找
    p1 = os.path.join(os.getcwd(), filename)
    if os.path.isfile(p1):
        try:
            with open(p1, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass

    # 尝试在脚本所在目录下查找
    p2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if os.path.isfile(p2):
        try:
            with open(p2, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass

    return "703"

def _decrypt_password(enc_str, key_path='~/.workbuddy/.meeting_skill_key'):
    if not enc_str.startswith('ENC:'):
        return enc_str
    kp = os.path.expanduser(key_path)
    if not os.path.exists(kp):
        return enc_str
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return enc_str
    try:
        with open(kp, 'rb') as f:
            key = f.read()
        fern = Fernet(key)
        return fern.decrypt(enc_str[4:].encode('utf-8')).decode('utf-8')
    except Exception:
        return enc_str

# Default configuration values
DEFAULT_COMMIT_PREFIX = _get_default_commit_prefix()
if os.name == 'nt':
    DEFAULT_LOCAL_DIR = r"F:\spb\spbsrc"
else:
    DEFAULT_LOCAL_DIR = r"/Volumes/Macintosh HD_Data/Project/jzjy/spbsrc"
DEFAULT_MERGE_SOURCE = "https://jyjs.svn.gtja.net/svn/jjywpt/Src/01Branches/spbsrc_uat_2024"
DEFAULT_SVN_USERNAME = "wujin@gtht.com"
DEFAULT_SVN_PASSWORD = "ENC:gAAAAABqRzK6KSzJbQIJB-5QrF5Fs-v8Oy7gHvsJP4ty7s9931ODbtUQGGUjQFp-mVU6O_LziFCglwx5689PkyP6nOSFCRInrw=="
DEFAULT_LOG_LIMIT = 2000

class Config:
    DATA_TEXT = ""
    COMMIT_PREFIX = DEFAULT_COMMIT_PREFIX
    LOCAL_DIR = DEFAULT_LOCAL_DIR
    MERGE_SOURCE = DEFAULT_MERGE_SOURCE
    SVN_EXECUTABLE = ""
    SVN_USERNAME = DEFAULT_SVN_USERNAME
    SVN_PASSWORD = DEFAULT_SVN_PASSWORD
    LOG_SEARCH_LIMIT = DEFAULT_LOG_LIMIT
    OUTPUT_DIR = ""
    SVN_EXE = None

def _find_svn():
    """
    寻找 svn.exe/svn 的路径。
    优先级：配置项 SVN_EXECUTABLE > PATH 中的 svn > 常见安装位置自动探测。
    """
    # 1) 用户在配置中指定了路径
    if Config.SVN_EXECUTABLE.strip():
        p = Config.SVN_EXECUTABLE.strip()
        if os.path.isfile(p):
            return p

    # 2) PATH 中能否直接找到
    import shutil
    path_svn = shutil.which("svn")
    if path_svn:
        return path_svn

    # 3) 自动探测常见安装位置 (仅在 Windows 下执行)
    if os.name == 'nt':
        candidates = [
            r"C:\Program Files\TortoiseSVN\bin\svn.exe",
            r"C:\Program Files (x86)\TortoiseSVN\bin\svn.exe",
            r"C:\Program Files\SlikSvn\bin\svn.exe",
            r"C:\Program Files\Subversion\bin\svn.exe",
            r"C:\Program Files\VisualSVN\bin\svn.exe",
            r"C:\Program Files\CollabNet\Subversion Client\svn.exe",
        ]
        # 也搜一下 C 盘和 D 盘 (for Windows users)
        for root in ["C:\\", "D:\\"]:
            try:
                for dirpath, _, filenames in os.walk(os.path.join(root, "Program Files"), followlinks=False):
                    if dirpath.count(os.sep) - root.count(os.sep) > 4:  # 最多 4 层深度
                        continue
                    if "svn.exe" in filenames:
                        candidates.append(os.path.join(dirpath, "svn.exe"))
            except OSError:
                continue

        for p in candidates:
            if os.path.isfile(p):
                return p

    return None

def build_svn_cmd(subcommand, *args):
    """拼装 svn 命令，统一附加 --non-interactive 和认证信息，并添加服务器证书信任标志。"""
    cmd = [Config.SVN_EXE, subcommand, "--non-interactive"]
    if Config.SVN_USERNAME:
        cmd += ["--username", Config.SVN_USERNAME]
    if Config.SVN_PASSWORD:
        cmd += ["--password", Config.SVN_PASSWORD]
    cmd += [
        "--trust-server-cert",
        "--trust-server-cert-failures=unknown-ca,cn-mismatch,expired,not-yet-valid"
    ]
    cmd += list(args)
    return cmd

def run_svn(cmd, cwd=None, timeout=300):
    """
    执行 svn 命令，返回 (returncode, stdout, stderr)。
    所有文本强制用 utf-8 / gbk 兜底解码，避免 Windows 下乱码。
    """
    if cwd is None:
        cwd = Config.LOCAL_DIR
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
        )
        stdout = _safe_decode(proc.stdout)
        stderr = _safe_decode(proc.stderr)
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        return -1, "", "SVN 命令超时"
    except FileNotFoundError:
        return -1, "", "未找到 svn 命令，请确认已安装 SVN 命令行客户端并添加到 PATH"

def _safe_decode(data: bytes) -> str:
    """尝试 utf-8 → gbk → latin-1 解码字节。"""
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            continue
    return str(data)

def assert_svn_client():
    """检查 svn 命令可用性。"""
    if not Config.SVN_EXE:
        print("[FATAL] 未找到 svn 可执行文件！")
        print("  请通过以下任一方式解决：")
        print("  1. 使用命令行参数 --svn-executable 指定完整路径")
        print("  2. 将 svn 所在目录添加到系统 PATH 环境变量")
        sys.exit(1)
    code, out, err = run_svn([Config.SVN_EXE, "--version", "--non-interactive"], cwd=os.getcwd())
    if code != 0:
        print(f"[FATAL] svn 命令执行失败: {err}")
        sys.exit(1)
    print(f"SVN client: {out.split(chr(10))[0]}")

def assert_local_dir():
    """确保本地目录存在且是 SVN 工作副本。"""
    if not os.path.isdir(Config.LOCAL_DIR):
        print(f"[FATAL] 目录不存在: {Config.LOCAL_DIR}")
        sys.exit(1)
    dot_svn = os.path.join(Config.LOCAL_DIR, ".svn")
    if not os.path.isdir(dot_svn):
        print(f"[FATAL] {Config.LOCAL_DIR} 不是 SVN 工作副本（缺少 .svn）")
        sys.exit(1)

def svn_update():
    print("=" * 60)
    print("Step 1: svn update")
    print("=" * 60)
    code, out, err = run_svn(
        build_svn_cmd("update", "--accept", "theirs-full")
    )
    print(out)
    if code != 0:
        print(f"[FATAL] svn update 失败:\n{err}")
        sys.exit(1)
    print("update 完成。\n")

def search_revisions(req_num: str):
    """
    在 Config.MERGE_SOURCE 的 svn log 中搜索 commit message 包含需求号的 revision。
    返回按提交顺序排列的 (revision, message) 列表。
    """
    print(f"   搜索 UAT 日志中 message 包含『{req_num}』的 revision ...")
    code, out, err = run_svn(
        build_svn_cmd(
            "log", Config.MERGE_SOURCE,
            "--search", req_num,
            "-l", str(Config.LOG_SEARCH_LIMIT),
        )
    )
    if code != 0:
        print(f"   [WARN] svn log 搜索失败:\n{err}")
        return []

    # 解析 log，提取 revision 号和 message
    entries = []
    current_rev = None
    current_msg_lines = []
    for line in out.splitlines():
        line = line.strip()
        m = re.match(r"^r(\d+)\s+\|", line)
        if m:
            # 新的 revision 条目开始
            if current_rev is not None:
                msg = "\n".join(current_msg_lines).strip()
                if req_num in msg:
                    entries.append((current_rev, msg))
            current_rev = int(m.group(1))
            current_msg_lines = []
        elif line.startswith("---") or line == "":
            continue
        elif current_rev is not None and line and not line.startswith("Changed paths"):
            current_msg_lines.append(line)

    # 最后一个条目
    if current_rev is not None:
        msg = "\n".join(current_msg_lines).strip()
        if req_num in msg:
            entries.append((current_rev, msg))

    # 按 revision 升序（保持提交顺序）
    entries.sort(key=lambda x: x[0])

    if entries:
        rev_list = [e[0] for e in entries]
        print(f"   找到 {len(entries)} 个 revision（message 含『{req_num}』）: {rev_list}")
        for r, m in entries:
            print(f"      r{r}: {m[:80]}")
    else:
        print("   未找到相关 revision，跳过。")
    return entries

def svn_merge_revisions(entries):
    """
    将一批 revision 一次性合并。
    entries: [(rev, msg), ...] 来自 search_revisions 的返回值。
    """
    revs = [e[0] for e in entries]
    print(f"   → 合并 {len(revs)} 个 revision: {revs} ...")

    # 构建 svn merge -c r1 -c r2 -c r3 ... <source>
    cmd = build_svn_cmd("merge")
    for r in revs:
        cmd += ["-c", str(r)]
    cmd += [Config.MERGE_SOURCE, "--accept", "postpone"]

    code, out, err = run_svn(cmd)
    for line in out.splitlines():
        if line.strip():
            print(f"      {line.strip()}")
    if code != 0:
        print(f"   [ERROR] merge 失败:\n{err}")
        return False
    return True

def check_conflicts():
    """检查工作副本中是否存在冲突文件（状态 'C'）。"""
    code, out, _ = run_svn(build_svn_cmd("status"))
    conflicts = []
    for line in out.splitlines():
        if line and line[0] == "C":
            conflicts.append(line)
    return conflicts

def has_changes():
    """检查是否有未提交的变更（排除未受控文件）。"""
    code, out, _ = run_svn(build_svn_cmd("status"))
    for line in out.splitlines():
        stripped = line.strip()
        if stripped and stripped[0] not in ("?",):
            return True
    return False

def build_commit_msg(req_num, tasks):
    """
    生成多行 commit 日志，格式：
      第一行：【前缀】任务号  任务标题  经办人
      后续行：任务号  任务标题  经办人
    tasks: [(task_num, task_title, assignee), ...]
    """
    lines = []
    for i, (task_num, task_title, assignee) in enumerate(tasks):
        row = f"{task_num}  {task_title}  {assignee}"
        if i == 0:
            row = f"【{Config.COMMIT_PREFIX}】{row}"
        lines.append(row)
    return "\n".join(lines)

def render_diff_to_image(diff_text, output_image_path):
    """将 diff 文本转换为格式化的 PNG 图片。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("   [WARN] 缺少 PIL (Pillow) 库，跳过生成冲突截图。")
        return
        
    lines = diff_text.splitlines()
    
    # 限制行数以避免图片过长 (最多保存 300 行)
    max_lines = 300
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append("... [此处省略多余的行数] ...")
        
    padding = 20
    line_height = 20
    char_width = 8
    
    font = None
    font_paths = [
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.ttf"
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 13)
                bbox = font.getbbox("A")
                char_width = bbox[2] - bbox[0]
                line_height = (bbox[3] - bbox[1]) + 6
                break
            except Exception:
                pass
                
    if font is None:
        font = ImageFont.load_default()
        line_height = 15
        char_width = 6

    # 确定尺寸
    max_cols = max(len(line) for line in lines) if lines else 80
    width = max(max_cols * char_width + padding * 2, 800)
    height = len(lines) * line_height + padding * 2

    # 绘制背景 (暗色模式)
    bg_color = (30, 30, 30)
    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    for i, line in enumerate(lines):
        y = padding + i * line_height
        
        text_color = (212, 212, 212)
        line_bg = None
        
        if line.startswith("+") and not line.startswith("+++"):
            text_color = (156, 220, 254)  # 浅蓝
            line_bg = (30, 60, 50)         # 绿背景
        elif line.startswith("-") and not line.startswith("---"):
            text_color = (244, 71, 71)    # 浅红
            line_bg = (70, 30, 30)         # 红背景
        elif line.startswith("<<<<<<<") or line.startswith("=======") or line.startswith(">>>>>>>"):
            text_color = (255, 165, 0)    # 冲突橙
            line_bg = (80, 50, 10)         # 冲突橙背景
            
        if line_bg:
            draw.rectangle([0, y, width, y + line_height], fill=line_bg)
            
        draw.text((padding, y), line, font=font, fill=text_color)

    img.save(output_image_path)


def save_conflict_diff_images(conflicts):
    """为冲突文件生成并保存比对截图（diff image）和文本。"""
    os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
    
    for line in conflicts:
        if len(line) < 8:
            continue
        file_path = line[7:].strip()
        full_path = os.path.join(Config.LOCAL_DIR, file_path)
        if not os.path.isfile(full_path):
            continue
            
        code, out, err = run_svn(build_svn_cmd("diff", file_path))
        if code != 0 or not out.strip():
            continue
            
        safe_name = file_path.replace("/", "_").replace("\\", "_")
        
        # 保存文本差异
        text_diff_path = os.path.join(Config.OUTPUT_DIR, f"conflict_diff_{safe_name}.txt")
        try:
            with open(text_diff_path, "w", encoding="utf-8") as f:
                f.write(out)
            print(f"   ✓ 已保存冲突文本差异: {text_diff_path}")
        except Exception as e:
            print(f"   [WARN] 保存冲突文本差异失败: {e}")
            
        # 生成图片差异
        image_diff_path = os.path.join(Config.OUTPUT_DIR, f"conflict_diff_{safe_name}.png")
        try:
            render_diff_to_image(out, image_diff_path)
            print(f"   ✓ 已生成冲突比对截图: {image_diff_path}")
        except Exception as e:
            print(f"   [WARN] 生成冲突比对截图失败: {e}")


def process_requirement(req_num, tasks):
    """
    处理一个Task编号：
      - 搜索 revision（message 包含Task编号）
      - 一次性合并所有相关 revision
      - 检测冲突 → revert + 记录冲突
      - 无冲突 → commit
    """
    task_num_str = ", ".join(t[0] for t in tasks)
    print(f"\n{'─' * 60}")
    print(f"Task编号: {req_num}")
    print(f"任务号: {task_num_str}")
    print(f"{'─' * 60}")

    entries = search_revisions(req_num)
    if not entries:
        return "skipped"

    # 一次性合并所有 revision
    merge_ok = svn_merge_revisions(entries)

    # ── 检测冲突 ──
    conflicts = check_conflicts()
    if conflicts:
        print(f"\n⚠️  检测到 {len(conflicts)} 个冲突文件:")
        for line in conflicts:
            print(f"    {line}")
        # 保存比对截图及文本差异
        try:
            save_conflict_diff_images(conflicts)
        except Exception as e:
            print(f"   [WARN] 自动保存冲突比对信息失败: {e}")
            
        print("   → svn revert 回退 ...")
        run_svn(build_svn_cmd("revert", "-R", "."))
        return ("conflict", conflicts)

    # 非冲突原因导致的 merge 失败
    if not merge_ok:
        print("   merge 执行异常（非冲突原因），正在 revert ...")
        run_svn(build_svn_cmd("revert", "-R", "."))
        return "error"

    # ── 检测是否有实际变更 ──
    if not has_changes():
        print("   没有实际变更，跳过 commit。")
        return "no_changes"

    # ── Commit ──
    commit_msg = build_commit_msg(req_num, tasks)
    print(f"\n   提交日志:\n{commit_msg}")
    code, out, err = run_svn(
        build_svn_cmd("commit", "-m", commit_msg)
    )
    print(out)
    if code != 0:
        print(f"[ERROR] commit 失败:\n{err}")
        return "commit_failed"

    print(f"   ✓ {req_num} 提交成功")
    return "success"

def parse_data(text: str):
    """解析 tab/空格 分隔 of 文本数据，返回按需求号分组的结果。"""
    grouped = defaultdict(list)

    for line_num, line in enumerate(text.strip().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue

        # 尝试使用 Tab 或连续多个空格分割
        parts = re.split(r'\t|\s{2,}', line)
        parts = [p.strip() for p in parts if p.strip()]

        if len(parts) >= 4:
            # 标准的 4 列格式：需求号, 任务号, 任务标题, 经办人
            req_num = parts[0]
            task_num = parts[1]
            task_title = parts[2]
            assignee = parts[3]
        elif len(parts) == 3:
            # 3 列格式：需求号/任务号, 任务标题, 经办人
            req_num = parts[0]
            task_num = parts[0]
            task_title = parts[1]
            assignee = parts[2]
        else:
            # 尝试通过正则匹配：[Key] [Title] [Assignee]
            # 例如：JZJYPT-T202504823 债券质押式协议回购...  蔡静雯-123576
            match = re.match(r"^([A-Za-z0-9_-]+)\s+(.+?)\s+([^\s]+)$", line)
            if match:
                req_num = match.group(1).strip()
                task_num = req_num
                task_title = match.group(2).strip()
                assignee = match.group(3).strip()
            else:
                subparts = line.split()
                if len(subparts) >= 4:
                    req_num = subparts[0]
                    task_num = subparts[1]
                    task_title = " ".join(subparts[2:-1])
                    assignee = subparts[-1]
                elif len(subparts) == 3:
                    req_num = subparts[0]
                    task_num = subparts[0]
                    task_title = subparts[1]
                    assignee = subparts[2]
                else:
                    print(f"   [WARN] 第 {line_num} 行格式无法解析，跳过: {line[:60]}")
                    continue

        if not req_num:
            print(f"   [WARN] 第 {line_num} 行Task编号为空，跳过")
            continue
        if not task_num:
            print(f"   [WARN] 第 {line_num} 行任务号为空，跳过")
            continue

        grouped[req_num].append((task_num, task_title, assignee))

    return grouped

def main():
    parser = argparse.ArgumentParser(description="SVN Task编号粒度代码合并工具")
    parser.add_argument("-d", "--data-text", help="输入数据文本或包含数据的文本文件路径")
    parser.add_argument("-p", "--commit-prefix", default=DEFAULT_COMMIT_PREFIX, help=f"Commit 日志前缀/版本标识，默认: {DEFAULT_COMMIT_PREFIX}")
    parser.add_argument("-l", "--local-dir", default=DEFAULT_LOCAL_DIR, help=f"本地 SVN 工作副本路径，默认: {DEFAULT_LOCAL_DIR}")
    parser.add_argument("-s", "--merge-source", default=DEFAULT_MERGE_SOURCE, help=f"合并来源 SVN 分支 URL，默认: {DEFAULT_MERGE_SOURCE}")
    parser.add_argument("-u", "--svn-username", default=DEFAULT_SVN_USERNAME, help="SVN 用户名")
    parser.add_argument("--svn-password", default=DEFAULT_SVN_PASSWORD, help="SVN 密码")
    parser.add_argument("--svn-executable", default="", help="svn 可执行文件路径")
    parser.add_argument("--log-limit", type=int, default=DEFAULT_LOG_LIMIT, help=f"svn log 搜索的最大条数，默认: {DEFAULT_LOG_LIMIT}")
    parser.add_argument("-o", "--output-dir", help="输出汇总和冲突文件的目录，默认当前目录下的 commit-prefix 文件夹")

    args = parser.parse_args()

    # Determine data_text
    data_text = ""
    if args.data_text:
        if os.path.isfile(args.data_text):
            try:
                with open(args.data_text, "r", encoding="utf-8") as f:
                    data_text = f.read()
            except Exception as e:
                print(f"[FATAL] 读取数据文件失败: {e}")
                sys.exit(1)
        else:
            data_text = args.data_text
    else:
        # Fallback to stdin if not TTY
        if not sys.stdin.isatty():
            data_text = sys.stdin.read()

    # If still empty, print message and exit
    if not data_text.strip():
        print("[FATAL] 数据内容为空！请提供数据。")
        print("  可以通过以下方式提供：")
        print("  1. 命令行参数: --data-text \"需求号\\t任务号\\t任务标题\\t经办人\"")
        print("  2. 文件路径: --data-text data.txt")
        print("  3. 标准输入 (stdin)")
        sys.exit(1)

    Config.DATA_TEXT = data_text
    Config.COMMIT_PREFIX = args.commit_prefix
    Config.LOCAL_DIR = args.local_dir
    Config.MERGE_SOURCE = args.merge_source
    Config.SVN_USERNAME = args.svn_username
    Config.SVN_PASSWORD = _decrypt_password(args.svn_password)
    Config.SVN_EXECUTABLE = args.svn_executable
    Config.LOG_SEARCH_LIMIT = args.log_limit
    
    if args.output_dir:
        Config.OUTPUT_DIR = args.output_dir
    else:
        Config.OUTPUT_DIR = os.path.join(os.getcwd(), Config.COMMIT_PREFIX)

    Config.SVN_EXE = _find_svn()

    # ── 前置检查 ──
    assert_svn_client()
    assert_local_dir()

    # ── Step 1: svn update ──
    svn_update()

    # ── 解析数据并按Task编号分组 ──
    print("=" * 60)
    print("解析输入数据 ...")
    print("=" * 60)
    grouped = parse_data(Config.DATA_TEXT)
    print(f"共读取 {sum(len(v) for v in grouped.values())} 条记录，"
          f"按Task编号归为 {len(grouped)} 组。\n")

    if not grouped:
        print("没有可处理的数据，退出。")
        sys.exit(0)

    # ── 逐个Task编号处理 ──
    stats = {"success": 0, "conflict": 0, "skipped": 0,
             "error": 0, "no_changes": 0, "commit_failed": 0}
    result_records = {k: [] for k in stats}
    conflict_details = {}   # req_num -> [冲突文件行]

    for req_num, tasks in grouped.items():
        status = process_requirement(req_num, tasks)

        # 冲突返回 tuple: ("conflict", [文件列表])
        conflict_files = []
        if isinstance(status, tuple):
            status, conflict_files = status
            conflict_details[req_num] = conflict_files

        stats[status] = stats.get(status, 0) + 1
        result_records[status].append((req_num, tasks))

        if status in ("success", "conflict", "error", "commit_failed"):
            # ── 恢复到干净且单一版本的状态 ──
            print(f"\n   正在 svn update 以恢复干净且单一版本的状态 ...")
            code, out, err = run_svn(
                build_svn_cmd("update", "--accept", "theirs-full")
            )
            if code != 0:
                print(f"[WARN] svn update 失败: {err}")
            else:
                print("   update 完成，继续处理下一个需求。")

    # ── 汇总打印 ──
    print(f"\n{'=' * 60}")
    print("执行汇总")
    print(f"{'=' * 60}")
    print(f"  成功提交:         {stats['success']}")
    print(f"  有冲突(已revert): {stats['conflict']}")
    print(f"  无 revision:      {stats['skipped']}")
    print(f"  无实际变更:       {stats['no_changes']}")
    print(f"  执行异常:         {stats['error']}")
    print(f"  commit 失败:      {stats['commit_failed']}")

    # ── 创建输出目录 ──
    os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── 输出冲突文件 ──
    if result_records["conflict"]:
        conflict_file = os.path.join(Config.OUTPUT_DIR, f"conflict_reqs_{ts}.txt")
        with open(conflict_file, "w", encoding="utf-8") as f:
            f.write("以下Task编号在合并时发生冲突，已 revert：\n")
            f.write("=" * 60 + "\n\n")
            for req_num, tasks in result_records["conflict"]:
                f.write(f"Task编号: {req_num}\n")
                f.write("关联任务:\n")
                for task_num, task_title, assignee in tasks:
                    f.write(f"    {task_num}  {task_title}  {assignee}\n")
                files = conflict_details.get(req_num, [])
                f.write(f"冲突文件 ({len(files)} 个):\n")
                for cf in files:
                    f.write(f"    {cf[7:].strip()}\n")
                f.write("\n")
        print(f"\n冲突记录已写入: {conflict_file}")
    else:
        print("\n所有任务均无冲突 ✓")

    # ── 输出汇总 txt ──
    summary_file = os.path.join(Config.OUTPUT_DIR, f"summary_{ts}.txt")
    label_map = {
        "success":      "成功提交",
        "conflict":     "有冲突(已revert)",
        "skipped":      "无 revision",
        "no_changes":   "无实际变更",
        "error":        "执行异常",
        "commit_failed":"commit 失败",
    }
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"执行汇总  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        for key, label in label_map.items():
            records = result_records.get(key, [])
            f.write(f"{label}: {len(records)}\n")
            for req_num, tasks in records:
                for task_num, task_title, assignee in tasks:
                    f.write(f"    {task_num}  {task_title}  {assignee}\n")
            f.write("\n")
    print(f"执行汇总已写入: {summary_file}")

if __name__ == "__main__":
    main()
