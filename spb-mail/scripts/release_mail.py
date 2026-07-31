# -*- coding: utf-8 -*-
"""
版本发布报告 / 邮件内容生成工具
============================================================
功能：根据中心+日期参数，从 SVN 获取提交记录、读取 Excel Task 信息、
      计算 ZIP 包 MD5，生成美化邮件内容（TXT + HTML）。

用法：
  python release_mail.py <中心> <日期> [类型]
  示例：
    python release_mail.py JZJY 20260529        → Task新增模式
    python release_mail.py JZJY 20260529 upt    → Task更新模式
    python release_mail.py CSZX 20260529        → Task新增模式
    python release_mail.py CSZX 20260529 upt    → Task更新模式

中心：
  JZJY — 集中交易 (SPB 版本)
  CSZX — 参数中心
"""

import subprocess
import datetime
import xml.etree.ElementTree as ET
import os
import hashlib
import re
import sys

import pandas as pd

# ================= 中心配置 =================
CENTER_CONFIG = {
    "JZJY": {
        "name": "集中交易",
        "svn_repo": "https://jyjs.svn.gtja.net/svn/jjywpt/Src/01Branches/Produce",
        "version_fmt": "SPB_V2.2.19_{version}",     # {version} 替换为版本号
        "upgrade_url": "https://yunpan.gtht.com.cn/l/i1LRd3",
        "zip_suffix": "",                            # ZIP 文件名额外后缀
        "data_subdir": "jzjy",                       # Excel 和 ZIP 所在子目录
    },
    "CSZX": {
        "name": "参数中心",
        "svn_repo": "https://jyjs.svn.gtja.net/svn/jjywpt/Src/01Branches/02Trunk_jygl_prod/jygl_prod_s",
        "version_fmt": "CSZX-{version}",
        "upgrade_url": "https://yunpan.gtht.com.cn/l/H1RfMx",
        "zip_suffix": "",
        "data_subdir": "jygl",                       # Excel 和 ZIP 所在子目录
    },
}

SVN_USERNAME = "125360"
SVN_PASSWORD = "wujin@1124"

# 当前工作目录作为数据目录（非脚本所在目录，由调用方 cd 进入）
WORK_DIR = os.getcwd()
# ==============================================


def parse_args():
    """解析命令行参数"""
    if len(sys.argv) < 3:
        print("用法: python release_mail.py <中心> <日期> [类型]")
        print(f"  可用中心: {', '.join(CENTER_CONFIG.keys())}")
        print("  日期: 8位数字，如 20260529")
        print("  类型: 省略=Task新增, upt=Task更新")
        sys.exit(1)

    center = sys.argv[1].upper().strip()
    date_str = sys.argv[2].strip()
    mode = "add"  # 默认：新增
    if len(sys.argv) >= 4 and sys.argv[3].strip().lower() == "upt":
        mode = "upt"

    if center not in CENTER_CONFIG:
        print(f"[ERROR] 未知中心: {center}，可用: {', '.join(CENTER_CONFIG.keys())}")
        sys.exit(1)

    if not (date_str[:8].isdigit() and len(date_str[:8]) == 8):
        print(f"[ERROR] 版本号格式错误: {date_str}，前 8 位应为数字")
        sys.exit(1)

    return center, date_str, mode


def get_config(center, date_str):
    """根据中心+日期构建完整配置"""
    cfg = CENTER_CONFIG[center]
    version = cfg["version_fmt"].replace("{version}", date_str)

    # Dynamically read upgrade_url from 版本地址.txt if available
    upgrade_url = cfg["upgrade_url"]
    addr_file = os.path.join(WORK_DIR, "版本地址.txt")
    if os.path.exists(addr_file):
        try:
            with open(addr_file, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
            
            target_name = cfg["name"]  # "集中交易" or "参数中心"
            for i, line in enumerate(lines):
                if target_name in line and i + 1 < len(lines):
                    potential_url = lines[i+1]
                    if potential_url.startswith("http"):
                        upgrade_url = potential_url
                        print(f"[INFO] 从 版本地址.txt 动态获取 {target_name} 升级包位置: {upgrade_url}")
                        break
        except Exception as e:
            print(f"[WARN] 读取 版本地址.txt 失败: {e}")

    return {
        "center": center,
        "center_name": cfg["name"],
        "svn_repo": cfg["svn_repo"],
        "version": version,
        "zip_filename": f"{version}{cfg['zip_suffix']}.zip",
        "zip_subdir": cfg.get("data_subdir", ""),
        "upgrade_url": upgrade_url,
        "excel_file": f"{version}.xlsx",
        "excel_upt_file": f"{version}_upt.xlsx",
    }


# ================= SVN 部分 =================
# SVN 命令行因 OpenSSL 3.x 不支持服务器老旧 TLS 1.0，改用 curl 请求

def _get_proxy():
    # 优先使用环境变量中的代理配置
    p = os.environ.get("HTTPS_PROXY", os.environ.get("https_proxy", ""))
    if p:
        return p
    # 检测本地默认代理是否存活，存活才使用
    default_proxy = "http://127.0.0.1:63562"
    from urllib.parse import urlparse
    import socket
    try:
        parsed = urlparse(default_proxy)
        host = parsed.hostname
        port = parsed.port
        if host and port:
            with socket.create_connection((host, port), timeout=1):
                return default_proxy
    except Exception:
        pass
    return None

SVN_PROXY = _get_proxy()


def _get_repo_info(repo_url):
    """从完整 repo URL 中提取 repo 根路径和内部路径"""
    # repo_url 如: https://jyjs.svn.gtja.net/svn/jjywpt/Src/01Branches/Produce
    # repo_root: https://jyjs.svn.gtja.net/svn/jjywpt
    # path_in_repo: /Src/01Branches/Produce
    from urllib.parse import urlparse
    parsed = urlparse(repo_url)
    parts = parsed.path.strip("/").split("/")
    # 第一段是 "svn"，第二段是 repo 名，取前两段作为 repo 根
    if len(parts) >= 2 and parts[0] == "svn":
        repo_root_path = "/".join(parts[:2])
        path_in_repo = "/" + "/".join(parts[2:])
    else:
        return repo_url, ""
    repo_root = f"{parsed.scheme}://{parsed.netloc}/{repo_root_path}"
    return repo_root, path_in_repo


def _find_head_revision(repo_root):
    """通过 curl PROPFIND 快速获取 HEAD 版本号"""
    curl_cmd = ["curl", "-k"]
    if SVN_PROXY:
        curl_cmd += ["--proxy", SVN_PROXY]
    curl_cmd += [
        "-u", f"{SVN_USERNAME}:{SVN_PASSWORD}",
        "-H", "Depth: 0",
        "-X", "PROPFIND",
        "-s", "--max-time", "15",
        f"{repo_root}/!svn/vcc/default",
    ]
    try:
        result = subprocess.run(curl_cmd, capture_output=True, check=False, timeout=20)
        xml_text = result.stdout.decode('utf-8', errors='ignore')
        if not xml_text.strip():
            return 0
        # 解析 <D:checked-in><D:href>.../!svn/bln/<rev></D:href></D:checked-in>
        import re
        m = re.search(r'!svn/bln/(\d+)', xml_text)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 0


def get_svn_logs_today(repo_path):
    """通过 curl SVN REPORT 获取今日提交记录，仅返回指定分支的提交"""
    try:
        now = datetime.datetime.now()
        repo_root, path_in_repo = _get_repo_info(repo_path)

        # 先获取 HEAD 版本号
        head_rev = _find_head_revision(repo_root)
        if head_rev <= 0:
            print("[WARN] 无法获取 SVN HEAD 版本号")
            return []
        print(f"[INFO] SVN HEAD 版本: r{head_rev}")
        print(f"[INFO] 分支路径过滤: {path_in_repo}")

        # 使用 HEAD 作为起始，获取最近 200 条
        body = f"""<?xml version="1.0" encoding="utf-8"?>
<S:log-report xmlns:S="svn:" xmlns:D="DAV:">
<S:start-revision>{head_rev}</S:start-revision>
<S:end-revision>0</S:end-revision>
<S:limit>200</S:limit>
<S:discover-changed-paths/>
</S:log-report>"""

        curl_cmd = ["curl", "-k"]
        if SVN_PROXY:
            curl_cmd += ["--proxy", SVN_PROXY]
        curl_cmd += [
            "-u", f"{SVN_USERNAME}:{SVN_PASSWORD}",
            "-H", "Content-Type: application/xml",
            "-H", "Depth: 0",
            "-X", "REPORT",
            "-d", body,
            "-s", "--max-time", "60",
            f"{repo_root}/!svn/me",
        ]

        result = subprocess.run(curl_cmd, capture_output=True, check=False, timeout=65)
        xml_text = result.stdout.decode('utf-8', errors='ignore')
        if not xml_text.strip():
            xml_text = result.stdout.decode('gbk', errors='ignore')

        if not xml_text.strip():
            return []
        return parse_svn_report_xml(xml_text, now, branch_path=path_in_repo)
    except Exception as e:
        print(f"[ERROR] SVN 查询错误: {e}")
        return []


def parse_svn_report_xml(xml_text, today, branch_path=""):
    """解析 SVN REPORT 返回的 XML，按日期 + 分支路径过滤"""
    logs = []
    if not xml_text.strip():
        return logs
    try:
        if xml_text.startswith('\ufeff'):
            xml_text = xml_text[1:]
        root = ET.fromstring(xml_text)

        today_str = today.strftime("%Y-%m-%d")
        ns = {"S": "svn:", "D": "DAV:"}

        for item in root.findall('S:log-item', ns):
            rev = item.findtext('D:version-name', '', ns)
            date = item.findtext('S:date', '', ns)
            author = item.findtext('D:creator-displayname', '', ns)
            msg = item.findtext('D:comment', '', ns) or ""

            if not date.startswith(today_str):
                continue

            # 收集所有变更路径
            all_paths = []
            for mp in item.findall('S:modified-path', ns):
                mp_text = mp.text or ""
                node_kind = mp.get('node-kind', '')
                if node_kind == 'dir' and mp.get('prop-mods') == 'true' and mp.get('text-mods') == 'false':
                    continue
                text_mods = mp.get('text-mods', 'false')
                action = "M" if text_mods == "true" else "A"
                all_paths.append((action, mp_text))

            # 分支过滤：只保留属于当前中心的路径
            if branch_path:
                branch_paths = [(a, p) for a, p in all_paths if p.startswith(branch_path)]
                if not branch_paths:
                    continue  # 该提交未涉及本分支，跳过
                paths = [f"[{a}] {p}" for a, p in branch_paths]
            else:
                paths = [f"[{a}] {p}" for a, p in all_paths]

            logs.append({
                "revision": rev,
                "author": author,
                "date": date,
                "message": msg.strip() if msg else "",
                "changed_paths": paths,
            })
    except ET.ParseError as e:
        print(f"[ERROR] XML 解析错误: {e}")
    return logs


# ================= MD5 部分 =================
def calculate_file_md5(filepath):
    """计算文件 MD5"""
    if not os.path.exists(filepath):
        return None
    md5_hash = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


# ================= Excel 部分 =================
def read_tasks_from_excel(excel_path):
    """从 Excel 读取 Task 编号和标题"""
    if not os.path.exists(excel_path):
        print(f"[WARN] Excel 文件不存在: {excel_path}")
        return []

    try:
        df = pd.read_excel(excel_path)
        if 'Task编号' not in df.columns or 'Task标题' not in df.columns:
            print("[ERROR] Excel 缺少必要列 'Task编号' 或 'Task标题'")
            return []

        tasks = []
        for _, row in df.iterrows():
            tid = str(row['Task编号']).strip()
            title = str(row['Task标题']).strip()
            if tid == 'nan' or title == 'nan':
                continue
            tasks.append((tid, title))
        return tasks
    except Exception as e:
        print(f"[ERROR] 读取 Excel 失败: {e}")
        return []


def read_tasks_from_txt(txt_path):
    """从 txt 报告中读取 Task 编号和标题作为备用"""
    tasks = []
    if not os.path.exists(txt_path):
        return tasks
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        in_detail = False
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("# Task编号详细"):
                in_detail = True
                continue
            if in_detail:
                if line.startswith("#"):
                    break
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    tid, title = parts
                    tasks.append((tid.strip(), title.strip()))
    except Exception as e:
        print(f"[WARN] 读取 txt 报告失败: {e}")
    return tasks


def format_tasks_for_email(tasks):
    """格式化 Task 列表"""
    if not tasks:
        return "无 Task 或无法自动提取，请人工补充"

    lines = []
    for tid, title in tasks:
        lines.append(f"{tid}  {title}")
    return "\n".join(lines)


# ================= 报告生成 =================
def format_svn_log_detailed(logs):
    """详细 SVN 日志格式（spb 风格）"""
    lines = []
    for i, log in enumerate(logs, 1):
        date_str = log['date']
        if 'T' in date_str:
            try:
                dt = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                date_str = date_str[:19].replace('T', ' ')

        lines.append("")
        lines.append(f"**提交 #{i}** - r{log['revision']}")
        lines.append("- 作者：" + log['author'])
        lines.append("- 时间：" + date_str)

        if log['message']:
            msg_lines = log['message'].strip().split('\n')
            first_msg = ""
            for ml in msg_lines:
                ml = ml.strip()
                if ml and not ml.startswith('........'):
                    first_msg = ml
                    break
            if first_msg:
                lines.append("- 消息：" + first_msg)

        if log['changed_paths']:
            max_show = 10
            files = log['changed_paths'][:max_show]
            lines.append(f"- 变更文件（{len(log['changed_paths'])} 个）：")
            for p in files:
                lines.append("  - " + p)
            if len(log['changed_paths']) > max_show:
                lines.append(f"  - ... 还有 {len(log['changed_paths']) - max_show} 个文件")

    return "\n".join(lines)


def generate_text_report(config, tasks, md5_value, logs, mode):
    """生成文本邮件内容"""
    version = config['version']
    upgrade_url = config['upgrade_url']
    zip_filename = config['zip_filename']

    subj_prefix = "【版本更新】" if mode == "upt" else "【版本发布】"
    subject = f"{subj_prefix}{version}"

    lines = []
    lines.append(f"主题：{subject}")
    lines.append("各位好：")
    lines.append("")
    lines.append(version)
    lines.append("")

    task_label = "Task更新" if mode == "upt" else "Task新增"
    task_content = format_tasks_for_email(tasks)
    lines.append(f"【{task_label}】")
    for line in task_content.split('\n'):
        lines.append("- " + line)
    lines.append("")

    lines.append("【包变更】详见排期表")
    lines.append("")
    lines.append(f"【升级包位置】{upgrade_url}")
    lines.append("")
    lines.append(f"【MD5】{md5_value if md5_value else f'未找到文件 {zip_filename}'}")
    lines.append("")
    lines.append("【变更内容】")

    if not logs:
        lines.append("今日暂无 SVN 提交记录。")
    else:
        lines.append(format_svn_log_detailed(logs))

    return "\n".join(lines)


def build_html_report(config, tasks, md5_value, logs, mode):
    """生成 HTML 邮件内容"""
    version = config['version']
    upgrade_url = config['upgrade_url']
    zip_filename = config['zip_filename']
    task_label = "Task更新" if mode == "upt" else "Task新增"

    # Task HTML
    if tasks:
        task_items = "\n".join(
            f'<li>{tid}&nbsp;&nbsp;{title}</li>'
            for tid, title in tasks
        )
        task_html = f"<ul>\n{task_items}\n</ul>"
    else:
        task_html = "<p>无 Task 或无法自动提取，请人工补充</p>"

    # 变更内容 HTML
    if not logs:
        log_html = "<p>今日暂无 SVN 提交记录。</p>"
    else:
        log_items = []
        for i, log in enumerate(logs, 1):
            date_str = log['date']
            if 'T' in date_str:
                try:
                    dt = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    date_str = date_str[:19].replace('T', ' ')

            first_msg = ""
            if log['message']:
                for ml in log['message'].strip().split('\n'):
                    ml = ml.strip()
                    if ml and not ml.startswith('........'):
                        first_msg = ml
                        break

            file_count = len(log['changed_paths'])
            sample_path = ""
            if log['changed_paths']:
                last_path = log['changed_paths'][-1]
                path_str = re.sub(r'^\[.\]\s*', '', last_path).strip()
                parts = [p for p in path_str.split('/') if p]
                if len(parts) >= 2:
                    sample_path = parts[-2] + "/" + parts[-1]
                elif parts:
                    sample_path = parts[-1]

            bullets = [f'<li>提交 #{i} &mdash; r{log["revision"]}，作者 {log["author"]}，时间 {date_str}</li>']
            if first_msg:
                bullets.append(f'<li>消息：{first_msg}</li>')
            file_part = f"变更文件 {file_count} 个（{sample_path} 等）" if sample_path else f"变更文件 {file_count} 个"
            bullets.append(f'<li>{file_part}</li>')
            log_items.append("\n".join(bullets))

        log_html = "<ul>\n" + "\n".join(log_items) + "\n</ul>"

    md5_display = md5_value if md5_value else f"未找到文件 {zip_filename}"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{
    font-family: "Microsoft YaHei", "SimSun", Arial, sans-serif;
    font-size: 14px;
    line-height: 2;
    padding: 24px 32px;
    max-width: 820px;
    color: #222;
  }}
  p {{ margin: 6px 0; }}
  b {{ font-weight: 600; }}
  ul {{
    margin: 4px 0 10px 0;
    padding-left: 1.5em;
  }}
  li {{ margin: 2px 0; }}
  a {{ color: #1a6bbf; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .section {{ margin-bottom: 10px; }}
  .mono {{ font-family: Consolas, "Courier New", monospace; font-size: 13px; color: #444; }}
</style>
</head><body>

<p>各位好：</p>

<div class="section">
  <p><b>版本：</b>&nbsp;&nbsp;{version}</p>
</div>

<div class="section">
  <p><b>{task_label}：</b></p>
  {task_html}
</div>

<div class="section">
  <p><b>包变更：</b>&nbsp;&nbsp;详见排期表</p>
</div>

<div class="section">
  <p><b>升级包位置：</b>&nbsp;&nbsp;<a href="{upgrade_url}">{upgrade_url}</a></p>
</div>

<div class="section">
  <p><b>MD5：</b>&nbsp;&nbsp;<span class="mono">{md5_display}</span></p>
</div>

<div class="section">
  <p><b>变更内容：</b></p>
  {log_html}
</div>

</body></html>"""
    return html


# ================= 主流程 =================
def main():
    center, date_str, mode = parse_args()
    config = get_config(center, date_str)

    print("=" * 60)
    print(f"  版本邮件生成工具 — {config['center_name']}({center})")
    print(f"  版本: {config['version']}  |  模式: {'Task更新' if mode == 'upt' else 'Task新增'}")
    print("=" * 60)

    # 1. 读取 Excel Task
    excel_file = config['excel_upt_file'] if mode == 'upt' else config['excel_file']
    excel_path = os.path.join(WORK_DIR, config['zip_subdir'], excel_file)
    
    if not os.path.exists(excel_path):
        lower_path = os.path.join(WORK_DIR, config['zip_subdir'], excel_file.lower())
        if os.path.exists(lower_path):
            excel_path = lower_path
            excel_file = excel_file.lower()

    print(f"\n[INFO] 读取 Excel: {excel_file}")
    tasks = read_tasks_from_excel(excel_path)
    if not tasks:
        txt_file = "upt_excel_output.txt" if mode == 'upt' else "excel_output.txt"
        txt_path = os.path.join(WORK_DIR, config['zip_subdir'], txt_file)
        if os.path.exists(txt_path):
            print(f"[INFO] Excel 无数据，尝试读取本地导出文本: {txt_file}")
            tasks = read_tasks_from_txt(txt_path)
            
    print(f"[INFO] 提取到 {len(tasks)} 个 Task")

    # 2. 获取 SVN 日志
    print(f"\n[INFO] 获取 SVN 提交记录...")
    logs = get_svn_logs_today(config['svn_repo'])
    print(f"[INFO] 获取到 {len(logs)} 条记录")

    # 3. 计算 MD5
    zip_path = os.path.join(WORK_DIR, config['zip_subdir'], config['zip_filename'])
    print(f"\n[INFO] 计算 MD5: {config['zip_filename']}")
    md5_val = calculate_file_md5(zip_path)
    if md5_val:
        print(f"[INFO] MD5: {md5_val}")
    else:
        print(f"[WARN] 未找到文件: {config['zip_filename']}")

    # 4. 生成文本报告
    text_content = generate_text_report(config, tasks, md5_val, logs, mode)
    txt_path = os.path.join(WORK_DIR, "release_report.txt")
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(text_content)
    print(f"\n[OK] 文本报告 → release_report.txt")

    # 5. 生成 HTML 报告
    html_content = build_html_report(config, tasks, md5_val, logs, mode)
    html_path = os.path.join(WORK_DIR, "release_report.html")
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"[OK] HTML 报告 → release_report.html")

    # 6. 打印预览（文本版）
    print("\n")
    print("=" * 60)
    print("                    邮  件  内  容  预  览")
    print("=" * 60)
    print()
    print(text_content)
    print()
    # 7. 打印 HTML 内容（同步输出到对话窗口）
    print("=" * 60)
    print("                  HTML  内  容  预  览")
    print("=" * 60)
    print()
    print(html_content)
    print()
    print("=" * 60)
    print(f"完成！输出目录: {WORK_DIR}")
    print(f"  - {txt_path}")
    print(f"  - {html_path}")


if __name__ == "__main__":
    main()
