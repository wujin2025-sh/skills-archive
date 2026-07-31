#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
SVN 需求号/任务号差异检查脚本
==============================
功能：
  1. 支持传入一个或多个需求号/任务号。
  2. 针对每个编号，在 UAT 仓库与生产仓库搜索其提交历史。
  3. 支持多线程并发（ThreadPoolExecutor）查询，极大缩减多编号比对耗时。
  4. 通过指定合理的分支版本区间（如最近 20000 个版本）来保证查询高性能。
  5. 分析并找出“UAT 仓库提交记录晚于生产仓库（或生产中未包含，或被回退）”的编号。
  6. 输出控制台摘要表格，并在输出目录中生成详细比对报告。
  7. 不做任何代码修改或合并，仅做差异检查。
"""

import subprocess
import sys
import os
import re
import argparse
import tempfile
import atexit
import xml.etree.ElementTree as ET
import concurrent.futures
from collections import defaultdict
from datetime import datetime

# 默认仓库配置
DEFAULT_UAT_URL = "https://jyjs.svn.gtja.net/svn/jjywpt/Src/01Branches/spbsrc_uat_2024"
DEFAULT_PROD_URL = "https://jyjs.svn.gtja.net/svn/jjywpt/Src/01Branches/Produce"
DEFAULT_SVN_USERNAME = ""
DEFAULT_SVN_PASSWORD = ""
DEFAULT_RANGE_SIZE = 20000  # 默认扫描的版本区间大小
DEFAULT_MAX_WORKERS = 10    # 默认最大并行查询线程数

def _get_default_commit_prefix():
    filename = "合并版本号.txt"
    p1 = os.path.join(os.getcwd(), filename)
    if os.path.isfile(p1):
        try:
            with open(p1, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass
    return "svn_check"

def _decrypt_password(enc_str, key_path='~/.workbuddy/.meeting_skill_key'):
    if not enc_str or not enc_str.startswith('ENC:'):
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

class Config:
    UAT_URL = DEFAULT_UAT_URL
    PROD_URL = DEFAULT_PROD_URL
    SVN_USERNAME = DEFAULT_SVN_USERNAME
    SVN_PASSWORD = DEFAULT_SVN_PASSWORD
    SVN_EXECUTABLE = ""
    RANGE_SIZE = DEFAULT_RANGE_SIZE
    FULL_HISTORY = False
    OUTPUT_DIR = ""
    SVN_EXE = None
    MAX_WORKERS = DEFAULT_MAX_WORKERS

def setup_openssl_compatibility():
    """动态生成 OpenSSL 配置文件以支持 TLSv1.0 (针对 macOS 兼容性)"""
    openssl_conf_content = """openssl_conf = openssl_init

[openssl_init]
providers = provider_sect
ssl_conf = ssl_sect

[provider_sect]
default = default_sect

[default_sect]
activate = 1

[ssl_sect]
system_default = system_default_sect

[system_default_sect]
MinProtocol = TLSv1
CipherString = DEFAULT:@SECLEVEL=0
"""
    try:
        temp_cnf = tempfile.NamedTemporaryFile(mode='w', suffix='.cnf', delete=False)
        temp_cnf.write(openssl_conf_content)
        temp_cnf.close()
        os.environ['OPENSSL_CONF'] = temp_cnf.name
        atexit.register(lambda: _safe_unlink(temp_cnf.name))
    except Exception as e:
        print(f"[WARN] 动态生成 OpenSSL 配置失败: {e}")

def _safe_unlink(path):
    try:
        if os.path.exists(path):
            os.unlink(path)
    except Exception:
        pass

def _find_svn():
    """寻找 svn 可执行文件的路径。"""
    if Config.SVN_EXECUTABLE.strip():
        p = Config.SVN_EXECUTABLE.strip()
        if os.path.isfile(p):
            return p

    import shutil
    path_svn = shutil.which("svn")
    if path_svn:
        return path_svn

    if os.name == 'nt':
        candidates = [
            r"C:\Program Files\TortoiseSVN\bin\svn.exe",
            r"C:\Program Files (x86)\TortoiseSVN\bin\svn.exe",
            r"C:\Program Files\SlikSvn\bin\svn.exe",
            r"C:\Program Files\Subversion\bin\svn.exe",
            r"C:\Program Files\VisualSVN\bin\svn.exe",
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
    return "svn"

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

def run_svn(cmd, timeout=120):
    """执行 svn 命令，返回 (returncode, stdout, stderr)。"""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
        )
        stdout = _safe_decode(proc.stdout)
        stderr = _safe_decode(proc.stderr)
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        return -1, "", "SVN 命令执行超时"
    except FileNotFoundError:
        return -1, "", "未找到 svn 命令，请确认已安装 SVN 命令行客户端并添加到 PATH"

def _safe_decode(data: bytes) -> str:
    """尝试以 utf-8、gbk 或 latin-1 解码。"""
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
        sys.exit(1)
    code, out, err = run_svn([Config.SVN_EXE, "--version", "--non-interactive"])
    if code != 0:
        print(f"[FATAL] svn 命令执行失败: {err}")
        sys.exit(1)

def get_head_revision(url):
    """获取指定仓库的 HEAD 版本号"""
    code, out, err = run_svn(build_svn_cmd("info", url))
    if code == 0:
        for line in out.splitlines():
            line = line.strip()
            m = re.match(r"^(Revision|版本):\s*(\d+)", line)
            if m:
                return int(m.group(2))
    return None

def parse_xml_log(xml_str):
    """解析 svn log --xml 返回的内容，返回包含 revision、author、date、msg 的列表。"""
    if not xml_str.strip():
        return []
    try:
        root = ET.fromstring(xml_str.strip())
        entries = []
        for entry in root.findall('logentry'):
            revision = int(entry.get('revision'))
            author = entry.find('author').text if entry.find('author') is not None else ''
            date_str = entry.find('date').text if entry.find('date') is not None else ''
            msg = entry.find('msg').text if entry.find('msg') is not None else ''
            
            local_time_str = date_str
            if date_str:
                try:
                    utc_dt = datetime.strptime(date_str.split('.')[0], "%Y-%m-%dT%H:%M:%S")
                    from datetime import timedelta
                    local_dt = utc_dt + timedelta(hours=8)
                    local_time_str = local_dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

            entries.append({
                'revision': revision,
                'author': author,
                'date_utc': date_str,
                'date_local': local_time_str,
                'msg': msg.strip()
            })
        entries.sort(key=lambda x: x['revision'])
        return entries
    except Exception as e:
        print(f"   [WARN] 解析 XML 失败: {e}")
        return []

def search_log(url, search_id, head_rev=None):
    """在指定 URL 下搜索包含指定 ID 的日志并返回解析后的列表。"""
    args = ["log", url, "--search", search_id, "--xml"]
    
    if head_rev and not Config.FULL_HISTORY:
        start = head_rev
        end = max(1, head_rev - Config.RANGE_SIZE)
        args += ["-r", f"{start}:{end}"]
        
    cmd = build_svn_cmd(*args)
    code, out, err = run_svn(cmd)
    if code != 0:
        return []
    return parse_xml_log(out)

def parse_input_ids(data_text):
    """解析输入的需求号/任务号列表。"""
    ids = []
    for line in data_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        
        parts = re.split(r'\t|\s{2,}', line)
        first_token = parts[0].strip()
        
        if len(parts) == 1:
            tokens = re.split(r'[,;\s]+', first_token)
            for t in tokens:
                t = t.strip()
                t = re.sub(r'[\[\]"\'\(\)]', '', t)
                if t:
                    ids.append(t)
        else:
            first_token = re.sub(r'[\[\]"\'\(\)]', '', first_token)
            if first_token:
                ids.append(first_token)
                
    seen = set()
    unique_ids = []
    for item in ids:
        if item not in seen:
            seen.add(item)
            unique_ids.append(item)
    return unique_ids

def check_single_id(search_id, head_rev):
    """查询并比对单个 ID 的 UAT 与 生产 分支差异。"""
    uat_logs = search_log(Config.UAT_URL, search_id, head_rev)
    prod_logs = search_log(Config.PROD_URL, search_id, head_rev)

    status = ""
    newer_commits = []
    uat_latest = None
    prod_latest = None
    revert_keywords = ["revert", "rollback", "回退", "撤销", "未验收"]

    if not uat_logs and not prod_logs:
        status = "NOT_FOUND_ANYWHERE"
    elif not uat_logs:
        status = "NOT_FOUND_IN_UAT"
        prod_latest = prod_logs[-1]
    elif not prod_logs:
        status = "NEWER_IN_UAT"
        uat_latest = uat_logs[-1]
        newer_commits = uat_logs
    else:
        uat_latest = uat_logs[-1]
        prod_latest = prod_logs[-1]
        
        # 检测生产最新提交是否包含回退字样
        is_reverted = False
        latest_msg_lower = prod_latest['msg'].lower()
        for kw in revert_keywords:
            if kw in latest_msg_lower:
                is_reverted = True
                break
        
        if is_reverted:
            status = "NEWER_IN_UAT"
            newer_commits = uat_logs
        elif uat_latest['date_utc'] > prod_latest['date_utc']:
            status = "NEWER_IN_UAT"
            prod_latest_time = prod_latest['date_utc']
            newer_commits = [entry for entry in uat_logs if entry['date_utc'] > prod_latest_time]
            if not newer_commits:
                newer_commits = [uat_latest]
        else:
            status = "UP_TO_DATE"

    return {
        "id": search_id,
        "status": status,
        "uat_latest": uat_latest,
        "prod_latest": prod_latest,
        "newer_commits": newer_commits
    }

def main():
    parser = argparse.ArgumentParser(description="SVN 需求号/任务号分支差异检查工具")
    parser.add_argument("-d", "--data-text", help="要检查的编号文本，可以是逗号/空格/换行分隔，或文件路径。也可通过 stdin 传入")
    parser.add_argument("-s", "--uat-url", default=DEFAULT_UAT_URL, help=f"UAT 仓库 URL，默认: {DEFAULT_UAT_URL}")
    parser.add_argument("-t", "--prod-url", default=DEFAULT_PROD_URL, help=f"生产仓库 URL，默认: {DEFAULT_PROD_URL}")
    parser.add_argument("-u", "--svn-username", default=DEFAULT_SVN_USERNAME, help="SVN 用户名 (macOS 默认使用 Keychain, 可传空)")
    parser.add_argument("--svn-password", default=DEFAULT_SVN_PASSWORD, help="SVN 密码 (可传入 ENC: 加密密码)")
    parser.add_argument("--svn-executable", default="", help="手动指定 svn 命令路径")
    parser.add_argument("-r", "--range-size", type=int, default=DEFAULT_RANGE_SIZE, help=f"限制检查的版本数量，默认: {DEFAULT_RANGE_SIZE}")
    parser.add_argument("-f", "--full-history", action="store_true", help="查询完整历史 (可能较慢)")
    parser.add_argument("-o", "--output-dir", help="结果输出目录")
    parser.add_argument("-w", "--workers", type=int, default=DEFAULT_MAX_WORKERS, help=f"并行查询线程数，默认: {DEFAULT_MAX_WORKERS}")

    args = parser.parse_args()

    # 初始化配置
    Config.UAT_URL = args.uat_url
    Config.PROD_URL = args.prod_url
    Config.SVN_USERNAME = args.svn_username
    Config.SVN_PASSWORD = _decrypt_password(args.svn_password)
    Config.SVN_EXECUTABLE = args.svn_executable
    Config.RANGE_SIZE = args.range_size
    Config.FULL_HISTORY = args.full_history
    Config.SVN_EXE = _find_svn()
    Config.MAX_WORKERS = args.workers
    
    prefix = _get_default_commit_prefix()
    if args.output_dir:
        Config.OUTPUT_DIR = args.output_dir
    else:
        Config.OUTPUT_DIR = os.path.join(os.getcwd(), prefix)

    setup_openssl_compatibility()
    assert_svn_client()

    data_text = ""
    if args.data_text:
        if os.path.isfile(args.data_text):
            try:
                with open(args.data_text, "r", encoding="utf-8") as f:
                    data_text = f.read()
            except Exception as e:
                print(f"[FATAL] 读取输入文件失败: {e}")
                sys.exit(1)
        else:
            data_text = args.data_text
    else:
        if not sys.stdin.isatty():
            data_text = sys.stdin.read()

    if not data_text.strip():
        print("[FATAL] 缺少输入数据！请指定 -d/--data-text 或通过管道传入数据。")
        sys.exit(1)

    target_ids = parse_input_ids(data_text)
    if not target_ids:
        print("[FATAL] 未解析到任何有效的编号。")
        sys.exit(1)

    # 预先获取 HEAD 版本号用于限制区间
    head_rev = None
    if not Config.FULL_HISTORY:
        print("正在获取仓库最新版本号...")
        head_rev = get_head_revision(Config.UAT_URL)
        if head_rev:
            print(f"仓库最新版本号: r{head_rev}，比对区间: r{head_rev} 至 r{max(1, head_rev - Config.RANGE_SIZE)}")
        else:
            print("[WARN] 获取 HEAD 版本号失败，将退回全量历史查询")

    print("=" * 75)
    print(f"SVN 差异并发检查启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"UAT  仓库: {Config.UAT_URL}")
    print(f"生产 仓库: {Config.PROD_URL}")
    print(f"待检查编号数: {len(target_ids)} | 并发数: {Config.MAX_WORKERS}")
    print("=" * 75)

    results_map = {}
    stats = {
        "NEWER_IN_UAT": 0,
        "UP_TO_DATE": 0,
        "NOT_FOUND_ANYWHERE": 0,
        "NOT_FOUND_IN_UAT": 0
    }

    status_log_map = {
        "NEWER_IN_UAT": "🔵 UAT较新 (未同步)",
        "UP_TO_DATE": "✓ 已同步到生产",
        "NOT_FOUND_ANYWHERE": "⚠️ 两边无记录",
        "NOT_FOUND_IN_UAT": "⚠️ 仅生产有记录"
    }

    # 并发执行检查
    workers = min(len(target_ids), Config.MAX_WORKERS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_id = {
            executor.submit(check_single_id, search_id, head_rev): search_id
            for search_id in target_ids
        }
        for future in concurrent.futures.as_completed(future_to_id):
            search_id = future_to_id[future]
            try:
                res = future.result()
                results_map[search_id] = res
                
                # 打印单项进度反馈
                stat_desc = status_log_map.get(res['status'], res['status'])
                if res['status'] == "NEWER_IN_UAT":
                    print(f" -> 检查完毕: {search_id:<20} | 状态: {stat_desc:<16} | 待同步数: {len(res['newer_commits'])}")
                else:
                    print(f" -> 检查完毕: {search_id:<20} | 状态: {stat_desc:<16}")
            except Exception as e:
                print(f" -> [ERROR] 检查 {search_id} 失败: {e}")

    # 还原初始输入顺序
    results = [results_map[search_id] for search_id in target_ids if search_id in results_map]
    
    for res in results:
        stats[res['status']] += 1

    os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print("\n" + "=" * 80)
    print("差异检查执行汇总")
    print("=" * 80)
    print(f"{'编号/需求号':<24} | {'UAT最新版本':<12} | {'生产最新版本':<12} | {'对比状态':<18}")
    print("-" * 80)
    
    status_mapping = {
        "NEWER_IN_UAT": "🔵 UAT较新 (未同步)",
        "UP_TO_DATE": "✓ 已同步",
        "NOT_FOUND_ANYWHERE": "⚠️ 两边无记录",
        "NOT_FOUND_IN_UAT": "⚠️ 仅生产有记录"
    }

    for res in results:
        uat_rev_str = f"r{res['uat_latest']['revision']}" if res['uat_latest'] else "-"
        prod_rev_str = f"r{res['prod_latest']['revision']}" if res['prod_latest'] else "-"
        disp_status = status_mapping.get(res['status'], res['status'])
        print(f"{res['id']:<24} | {uat_rev_str:<12} | {prod_rev_str:<12} | {disp_status:<18}")
    print("-" * 80)
    print(f"汇总统计: 待发布(UAT较新): {stats['NEWER_IN_UAT']} | 已同步: {stats['UP_TO_DATE']} | 其他异常: {stats['NOT_FOUND_ANYWHERE'] + stats['NOT_FOUND_IN_UAT']}")
    print("=" * 80)

    report_file = os.path.join(Config.OUTPUT_DIR, f"svn_check_report_{ts}.md")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"# SVN 分支差异检查报告\n\n")
        f.write(f"- **检查时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- **UAT 仓库**: `{Config.UAT_URL}`\n")
        f.write(f"- **生产仓库**: `{Config.PROD_URL}`\n\n")
        
        f.write(f"## 1. 检查结果汇总\n\n")
        f.write(f"| 需求/任务编号 | UAT 最新版本 | UAT 提交时间 (本地) | 生产最新版本 | 生产提交时间 (本地) | 状态 |\n")
        f.write(f"| :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for res in results:
            uat_rev = f"r{res['uat_latest']['revision']}" if res['uat_latest'] else "-"
            uat_time = res['uat_latest']['date_local'] if res['uat_latest'] else "-"
            prod_rev = f"r{res['prod_latest']['revision']}" if res['prod_latest'] else "-"
            prod_time = res['prod_latest']['date_local'] if res['prod_latest'] else "-"
            disp_status = status_mapping.get(res['status'], res['status'])
            f.write(f"| {res['id']} | {uat_rev} | {uat_time} | {prod_rev} | {prod_time} | {disp_status} |\n")
            
        f.write(f"\n## 2. 待发布详情 (UAT 较新记录)\n\n")
        
        newer_count = 0
        revert_keywords = ["revert", "rollback", "回退", "撤销", "未验收"]
        for res in results:
            if res['status'] == "NEWER_IN_UAT":
                newer_count += 1
                f.write(f"### 🔵 [{newer_count}] 编号: {res['id']}\n\n")
                f.write(f"- **生产最新提交**: " + (f"r{res['prod_latest']['revision']} ({res['prod_latest']['date_local']})" if res['prod_latest'] else "无") + "\n")
                if res['prod_latest']:
                    latest_msg_lower = res['prod_latest']['msg'].lower()
                    if any(kw in latest_msg_lower for kw in revert_keywords):
                        f.write(f"- **备注**: ⚠️ 生产最新版本已被回退，具体原因: *{res['prod_latest']['msg'].replace(chr(10), ' ')}*\n")
                f.write(f"- **UAT 待同步提交数**: {len(res['newer_commits'])}\n\n")
                f.write(f"| 版本号 | 提交作者 | 提交时间 (本地) | 提交说明 |\n")
                f.write(f"| :--- | :--- | :--- | :--- |\n")
                for entry in reversed(res['newer_commits']):
                    msg_single_line = entry['msg'].replace('\n', ' ').replace('|', '\\|')
                    f.write(f"| r{entry['revision']} | {entry['author']} | {entry['date_local']} | {msg_single_line} |\n")
                f.write("\n---\n\n")
                
        if newer_count == 0:
            f.write("✓ 没有发现任何待发布的 UAT 差异记录，所有编号均已同步至生产或两边均无记录。\n")

    summary_file = os.path.join(Config.OUTPUT_DIR, f"svn_check_summary_{ts}.txt")
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"SVN CHECK SUMMARY - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 70 + "\n")
        f.write(f"UAT较新(待发布): {stats['NEWER_IN_UAT']}\n")
        f.write(f"已同步最新:      {stats['UP_TO_DATE']}\n")
        f.write(f"两边均无记录:    {stats['NOT_FOUND_ANYWHERE']}\n")
        f.write(f"仅生产有记录:    {stats['NOT_FOUND_IN_UAT']}\n")
        f.write("=" * 70 + "\n\n")
        
        for res in results:
            uat_rev_str = f"r{res['uat_latest']['revision']}" if res['uat_latest'] else "-"
            prod_rev_str = f"r{res['prod_latest']['revision']}" if res['prod_latest'] else "-"
            disp_status = status_mapping.get(res['status'], res['status'])
            f.write(f"{res['id']:<24} UAT: {uat_rev_str:<8} PROD: {prod_rev_str:<8} STATUS: {disp_status}\n")
            if res['status'] == "NEWER_IN_UAT" and res['newer_commits']:
                f.write("  待同步版本列表:\n")
                for entry in res['newer_commits']:
                    f.write(f"    - r{entry['revision']} | {entry['author']} | {entry['date_local']} | {entry['msg'].replace(chr(10), ' ')[:60]}\n")
                f.write("\n")

    print(f"\n✓ 详细报告已写入: {report_file}")
    print(f"✓ 简要汇总已写入: {summary_file}")

if __name__ == "__main__":
    main()
