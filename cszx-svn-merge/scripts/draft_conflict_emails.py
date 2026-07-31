#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Conflict Email Drafter for cszx-svn-merge skill
============================================================
Usage:
  python3 draft_conflict_emails.py [-d <output_dir>] [-p <version_prefix>]
"""

import os
import re
import sys
import glob
import argparse
import subprocess
from collections import defaultdict

# Default values
DEFAULT_VERSION_PREFIX = "CSZX"
DEFAULT_CC = ""  # 抄送为空

def get_email_by_name(name):
    """使用 pypinyin 获取中文拼音邮箱，如果失败退回到拼音转换"""
    try:
        from pypinyin import lazy_pinyin
        pinyin_list = lazy_pinyin(name)
        pinyin_name = "".join(pinyin_list).lower()
        return f'"{name}" <{pinyin_name}@gtht.com>'
    except ImportError:
        # Fallback dictionary for common names if pypinyin is not available
        common_map = {
            "蔡静雯": "caijingwen",
            "甘峰浩": "ganfenghao",
            "李骎": "liqin",
            "史立彬": "shilibin",
            "程菲": "chengfei",
            "周静": "zhoujing",
            "厉凌杰": "lilingjie"
        }
        pinyin_name = common_map.get(name, "developer")
        return f'"{name}" <{pinyin_name}@gtht.com>'

def parse_conflict_report(report_path):
    """解析 conflict_reqs_*.txt 报告，提取各个任务的冲突文件及经办人"""
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    blocks = content.split("\n\n")
    parsed_conflicts = []
    
    for block in blocks:
        block = block.strip()
        if not block.startswith("Task编号:"):
            continue
            
        lines = block.splitlines()
        req_num = ""
        assignee = ""
        assignee_name = ""
        conflict_files = []
        task_info = ""
        
        in_files_section = False
        
        for line in lines:
            line = line.strip()
            if line.startswith("Task编号:"):
                req_num = line.replace("Task编号:", "").strip()
            elif line.startswith("关联任务:"):
                continue
            elif line.startswith("冲突文件"):
                in_files_section = True
                continue
            elif in_files_section:
                if line:
                    conflict_files.append(line)
            else:
                if line:
                    task_info = line
                    parts = line.split()
                    if parts:
                        assignee = parts[-1].strip()
                        # Extract name from "Name-ID" (e.g. "蔡静雯-123576" -> "蔡静雯")
                        assignee_name = assignee.split("-")[0]
                        
        if req_num and assignee_name:
            parsed_conflicts.append({
                "req_num": req_num,
                "assignee_name": assignee_name,
                "assignee": assignee,
                "task_info": task_info,
                "conflict_files": conflict_files
            })
            
    return parsed_conflicts

def main():
    parser = argparse.ArgumentParser(description="SVN 冲突明细邮件草稿保存工具")
    parser.add_argument("-d", "--output-dir", help="SVN 合并输出的版本目录路径（包含 conflict_reqs_*.txt 的目录）")
    parser.add_argument("-p", "--version-prefix", default=DEFAULT_VERSION_PREFIX, help=f"版本前缀，默认: {DEFAULT_VERSION_PREFIX}")
    parser.add_argument("--send", action="store_true", help="直接发送邮件，默认仅保存为草稿")
    
    args = parser.parse_args()
    
    # 自动探测 output_dir
    output_dir = args.output_dir
    if not output_dir:
        # 尝试读取当前目录下的 合并版本号.txt
        version_file = os.path.join(os.getcwd(), "合并版本号.txt")
        if os.path.isfile(version_file):
            try:
                with open(version_file, "r", encoding="utf-8") as f:
                    ver = f.read().strip()
                    if ver:
                        output_dir = os.path.join(os.getcwd(), ver)
            except Exception:
                pass
                
        # 兜底为当前目录
        if not output_dir:
            output_dir = os.getcwd()
            
    if not os.path.isdir(output_dir):
        print(f"[FATAL] 目录不存在: {output_dir}")
        sys.exit(1)
        
    # 查找最近的 conflict_reqs_*.txt
    reports = glob.glob(os.path.join(output_dir, "conflict_reqs_*.txt"))
    if not reports:
        print(f"[INFO] 目录 {output_dir} 下未找到任何 conflict_reqs_*.txt，说明没有检测到冲突。")
        sys.exit(0)
        
    # 按修改时间排序，取最新的报告
    reports.sort(key=os.path.getmtime)
    report_path = reports[-1]
    print(f"[INFO] 读取冲突报告: {report_path}")
    
    conflicts = parse_conflict_report(report_path)
    if not conflicts:
        print("[INFO] 冲突报告中未解析到任何有效冲突需求。")
        sys.exit(0)
        
    script_dir = os.path.dirname(os.path.abspath(__file__))
    draft_script = os.path.join(script_dir, "save_to_draft.py")
    
    # 提取版本批次（如从路径 /path/to/20260710 提取 20260710）
    batch_name = os.path.basename(os.path.abspath(output_dir))
    version_id = f"{args.version_prefix}_{batch_name}"
    
    for idx, c in enumerate(conflicts, 1):
        req_num = c["req_num"]
        name = c["assignee_name"]
        recipient = get_email_by_name(name)
        
        # 拼接冲突列表
        files_str = "\n".join([f"     - {f}" for f in c["conflict_files"]])
        
        # 寻找对应的 diff 比对明细文本与图片
        diff_details = ""
        image_html = ""
        for cf in c["conflict_files"]:
            safe_name = cf.replace("/", "_").replace("\\", "_")
            
            # 读取文本比对
            diff_file = os.path.join(output_dir, f"conflict_diff_{safe_name}.txt")
            if os.path.isfile(diff_file):
                try:
                    with open(diff_file, "r", encoding="utf-8") as df:
                        lines = df.readlines()
                        # 截取最多 150 行
                        if len(lines) > 150:
                            truncated = "".join(lines[:150]) + "\n... [已省略多余的比对行数，完整文件请查看附件/发版包] ...\n"
                        else:
                            truncated = "".join(lines)
                        diff_details += f"\n【文件差异明细: {cf}】\n```diff\n{truncated}```\n"
                except Exception as e:
                    print(f"[WARN] 读取比对文件 {diff_file} 失败: {e}")
            
            # 读取并 Base64 编码比对图片以实现邮件内嵌直观显示
            image_file = os.path.join(output_dir, f"conflict_diff_{safe_name}.png")
            if os.path.isfile(image_file):
                try:
                    import base64
                    with open(image_file, "rb") as imf:
                        encoded_img = base64.b64encode(imf.read()).decode("utf-8")
                        image_html += f'\n【比对截图: {cf}】\n<img src="data:image/png;base64,{encoded_img}" alt="Conflict Diff" style="max-width: 100%; border: 1px solid #ccc; margin-top: 5px; margin-bottom: 10px;" />\n'
                        print(f"  ✓ 成功对冲突图片进行 Base64 编码内嵌: {cf}")
                except Exception as e:
                    print(f"[WARN] 读取比对图片 {image_file} 失败: {e}")
                    
        # 构筑邮件内容
        body = f"""【代码合并冲突提示】{version_id} 合并发生冲突 - {name}

{name}，你好：

在进行 {batch_name} 批次代码合并时，你负责的以下任务代码在 UAT 合入主分支时发生合并冲突，已自动回撤。请尽快手工解决冲突并合入主分支。

【冲突任务】
Task编号: {req_num}
关联任务:
    {c["task_info"]}
冲突文件 ({len(c["conflict_files"])} 个):
{files_str}
{image_html}
{diff_details}
冲突比对截图及文本已保存在排期目录下，请核对并及时处理。
"""
        
        temp_body_file = os.path.join(output_dir, f"temp_conflict_email_{req_num}.txt")
        try:
            with open(temp_body_file, "w", encoding="utf-8") as f:
                f.write(body)
        except Exception as e:
            print(f"[ERROR] 写入临时邮件文件失败: {e}")
            continue
            
        subject = f"【代码合并冲突提示】{version_id} 合并发生冲突 - {name}"
        print(f"\n[{idx}/{len(conflicts)}] 正在为 {name} 起草邮件...")
        print(f"  收件人: {recipient}")
        
        cmd = [
            "python3", draft_script,
            "--subject", subject,
            "--body-file", temp_body_file,
            "--recipients", recipient,
            "--cc", DEFAULT_CC
        ]
        if args.send:
            cmd.append("--send")
            
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            print(res.stdout)
            if res.returncode != 0:
                print(f"  ❌ 起草失败: {res.stderr}")
            else:
                print(f"  ✓ 成功起草并保存到草稿箱。")
        except Exception as e:
            print(f"  ❌ 运行起草脚本失败: {e}")
        finally:
            # 清理临时邮件文件
            if os.path.exists(temp_body_file):
                try:
                    os.remove(temp_body_file)
                except:
                    pass

if __name__ == "__main__":
    main()
