#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read reviewed and modified Obsidian markdown report, parse email components, convert to beautiful HTML, and save draft in Coremail"""

import os
import glob
import re
import sys
import argparse
import subprocess

def text_to_rich_html(body_text):
    # Parse lines
    lines = body_text.split("\n")
    html_lines = []
    
    in_list = False
    
    html_lines.append('<div style="font-family: system-ui, -apple-system, sans-serif; font-size: 14.5px; line-height: 1.6; color: #333;">')
    
    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            if in_list:
                html_lines.append('  </ol>')
                in_list = False
            html_lines.append('  <div><br></div>')
            continue
            
        # Greeting
        if line_strip.startswith("各位老师"):
            html_lines.append(f'  <p style="font-weight: 600; font-size: 16px; margin: 0 0 16px 0;">{line_strip}</p>')
            continue
            
        # Paragraph
        if line_strip.startswith("针对集中交易历史数据BCP文件迁移"):
            html_lines.append(f'  <p style="text-indent: 2em; margin: 0 0 20px 0;">{line_strip}</p>')
            continue
            
        # Section titles
        if "下游系统适配进度" in line_strip or "进度未开始系统" in line_strip:
            if in_list:
                html_lines.append('  </ol>')
            title_text = "一、 下游系统适配进度：" if "下游系统适配进度" in line_strip else "🔴 一、 进度未开始系统："
            color = "#004085" if "下游系统适配进度" in line_strip else "#dc3545"
            html_lines.append(f'  <h4 style="color: {color}; font-size: 15px; font-weight: 600; margin: 20px 0 10px 0;">{title_text}</h4>')
            html_lines.append('  <ol style="margin: 0 0 20px 0; padding-left: 20px; line-height: 1.8;">')
            in_list = True
            continue
            
        if "开发中/测试中系统" in line_strip:
            if in_list:
                html_lines.append('  </ol>')
            html_lines.append('  <h4 style="color: #28a745; font-size: 15px; font-weight: 600; margin: 20px 0 10px 0;">🟡 二、 开发中/测试中系统：</h4>')
            html_lines.append('  <ol style="margin: 0 0 20px 0; padding-left: 20px; line-height: 1.8;">')
            in_list = True
            continue
            
        # List items
        m = re.match(r'^\d+\.\s*(.*?)[：:](.*)', line_strip)
        if m and in_list:
            sys_name = m.group(1).strip()
            details = m.group(2).strip()
            
            # Format the progress segment with colorful status badges
            prog_match = re.search(r'(目前进度\s*[^，；\n]+|目前无迁移计划)', details)
            if prog_match:
                prog_str = prog_match.group(1).strip()
                
                badges = []
                status_parts = [p.strip() for p in re.split(r'[、，,]+', prog_str.replace("目前进度", "").strip()) if p.strip()]
                
                for part in status_parts:
                    if not part:
                        continue
                    color_bg = "#f8d7da"
                    color_txt = "#721c24"
                    if "已上线" in part:
                        color_bg = "#d4edda"
                        color_txt = "#155724"
                    elif "测试完" in part:
                        color_bg = "#cce5ff"
                        color_txt = "#004085"
                    elif "测试中" in part or "开发中" in part:
                        color_bg = "#fff3cd"
                        color_txt = "#856404"
                    elif "未开始" in part:
                        color_bg = "#f8d7da"
                        color_txt = "#721c24"
                        
                    badges.append(f'<span style="background-color: {color_bg}; color: {color_txt}; padding: 2px 6px; border-radius: 4px; font-size: 13px; font-weight: 500; margin-right: 4px; display: inline-block;">{part}</span>')
                
                if badges:
                    badge_html = "目前进度 " + " ".join(badges)
                else:
                    badge_html = prog_str
                    
                details_new = details.replace(prog_str, badge_html)
            else:
                details_new = details
                
            # Style the @ tags nicely
            details_new = re.sub(r'(@\w+)', r'<span style="color: #004085; font-weight: 500; margin-left: 5px;">\1</span>', details_new)
            
            html_lines.append(f'    <li style="margin-bottom: 8px;"><strong>{sys_name}</strong>：{details_new}</li>')
            continue
            
        # Concluding paragraph (third quarter note)
        if "为了保障下游系统能按期适配" in line_strip:
            if in_list:
                html_lines.append('  </ol>')
                in_list = False
            # Make third-quarter note bold
            styled_line = line_strip.replace("该项目须确保于第三季度内完成交付", "<strong>该项目须确保于第三季度内完成交付</strong>")
            html_lines.append(f'  <p style="text-indent: 2em; margin: 24px 0 16px 0;">{styled_line}</p>')
            continue
            
        # WebOffice links
        if "在线文档如下" in line_strip or "详细信息如下" in line_strip:
            if in_list:
                html_lines.append('  </ol>')
                in_list = False
            html_lines.append(f'  <p style="margin: 16px 0 8px 0;">{line_strip}</p>')
            continue
            
        if "weboffice/l/" in line_strip or "https://" in line_strip:
            if in_list:
                html_lines.append('  </ol>')
                in_list = False
            html_lines.append(f'  <p style="margin: 0 0 16px 0;"><a href="{line_strip}" target="_blank" style="color: #007bff; text-decoration: none;">{line_strip}</a></p>')
            continue
            
        # Sign-off
        if "顺祝商祺" in line_strip:
            if in_list:
                html_lines.append('  </ol>')
                in_list = False
            html_lines.append(f'  <p style="margin: 20px 0 0 0;">{line_strip}</p>')
            continue
            
        # Default fallback line
        if in_list:
            html_lines.append('  </ol>')
            in_list = False
        html_lines.append(f'  <div>{line_strip}</div>')
        
    if in_list:
        html_lines.append('  </ol>')
        
    html_lines.append('</div>')
    return "\n".join(html_lines)

def render_html_table(rows):
    if not rows:
        return ""
    
    html = []
    html.append('<table style="width: 100%; border-collapse: collapse; margin-bottom: 25px; font-size: 13px; line-height: 1.5; color: #333; border: 1px solid #dee2e6;">')
    
    visible_idx = 0
    for idx, row in enumerate(rows):
        cells = [c.strip() for c in row.split("|")[1:-1]]
        
        # If it is the first row, treat it as the header
        is_header = (idx == 0)
        
        # Filter out rows where 计划迁移 is "否"
        if not is_header:
            if len(cells) > 4 and "否" in cells[4]:
                continue
            visible_idx += 1
            cells[0] = str(visible_idx) # Dynamically re-index
            
        tag = "th" if is_header else "td"
        
        row_style = 'background-color: #f8f9fa; border-bottom: 2px solid #dee2e6; font-weight: 600;' if is_header else 'border-bottom: 1px solid #dee2e6;'
        
        # Zebra striping for visible body rows
        if not is_header and visible_idx % 2 == 0:
            row_style += ' background-color: #fafafa;'
            
        html.append(f'  <tr style="{row_style}">')
        
        for c_idx, cell in enumerate(cells):
            # Alignment: center for 序号, 计划迁移, 进度. Left for others.
            align = "left"
            if c_idx in [0, 4, 5]: # Index, Plan to Migrate, Progress
                align = "center"
                
            # Process markdown elements inside cell
            cell_html = cell
            
            # Format backticks to code tags
            cell_html = re.sub(r'`(.*?)`', r'<code style="background-color: #f1f3f5; padding: 2px 4px; border-radius: 4px; font-family: SFMono-Regular, Consolas, Monaco, monospace; font-size: 12px; color: #e83e8c;">\1</code>', cell_html)
            
            # Format bold text
            cell_html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', cell_html)
            
            # Format progress badges inside cells
            if not is_header and c_idx == 5: # Progress column
                if "已上线" in cell:
                    cell_html = '<span style="background-color: #d4edda; color: #155724; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; display: inline-block;">已上线</span>'
                elif "测试完" in cell:
                    cell_html = '<span style="background-color: #cce5ff; color: #004085; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; display: inline-block;">测试完</span>'
                elif "测试中" in cell or "开发中" in cell:
                    raw_val = cell.replace("**", "").strip()
                    cell_html = f'<span style="background-color: #fff3cd; color: #856404; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; display: inline-block;">{raw_val}</span>'
                elif "未开始" in cell:
                    cell_html = '<span style="background-color: #f8d7da; color: #721c24; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; display: inline-block;">未开始</span>'
                    
            cell_style = f'padding: 8px 10px; border: 1px solid #dee2e6; text-align: {align};'
            if is_header:
                cell_style += ' color: #495057;'
                
            html.append(f'    <{tag} style="{cell_style}">{cell_html}</{tag}>')
            
        html.append('  </tr>')
        
    html.append('</table>')
    return "\n".join(html)

def markdown_details_to_html(details_text):
    if not details_text:
        return ""
        
    lines = details_text.split("\n")
    html_out = []
    
    in_table = False
    table_rows = []
    
    html_out.append('<div style="font-family: system-ui, -apple-system, sans-serif; margin-top: 40px; border-top: 1px solid #dee2e6; padding-top: 20px;">')
    html_out.append('  <h3 style="color: #004085; border-bottom: 2px solid #004085; padding-bottom: 8px; margin: 0 0 20px 0; font-size: 16px;">📋 二、 下游系统表级明细</h3>')
    
    for line in lines:
        line_strip = line.strip()
        
        # System sub-header
        if line_strip.startswith("### "):
            if in_table:
                html_out.append(render_html_table(table_rows))
                table_rows = []
                in_table = False
            sys_title = line_strip.replace("### ", "").strip()
            html_out.append(f'  <h4 style="color: #004085; font-size: 14.5px; border-left: 4px solid #004085; padding-left: 8px; margin: 25px 0 12px 0;">💻 {sys_title}</h4>')
            continue
            
        # Table rows
        if line_strip.startswith("|"):
            # Skip separator line like |---|---|
            if re.match(r'^\|[\s\-\|]+$', line_strip):
                continue
            in_table = True
            table_rows.append(line_strip)
            continue
            
        # Non-table line
        if not line_strip:
            continue
            
        # If we hit text line outside table
        if in_table:
            html_out.append(render_html_table(table_rows))
            table_rows = []
            in_table = False
            
        # Default text lines (like descriptions or warnings)
        html_out.append(f'  <div style="margin: 10px 0; font-size: 14px; color: #555;">{line_strip}</div>')
        
    if in_table:
        html_out.append(render_html_table(table_rows))
        
    html_out.append('</div>')
    return "\n".join(html_out)

def main():
    parser = argparse.ArgumentParser(description="Save email draft from Obsidian markdown report")
    parser.add_argument("--send", action="store_true", help="Send the email immediately instead of saving as draft")
    parser.add_argument("--html-only", action="store_true", help="Only generate the local HTML file, do not save draft")
    args = parser.parse_args()

    obsidian_dir = "/Volumes/Macintosh HD_Data/obsidian/100_Projects/进度跟踪"
    pattern = os.path.join(obsidian_dir, "*-进度-集中交易历史数据BCP文件迁移项目下游系统适配进度跟踪.md")
    
    files = glob.glob(pattern)
    if not files:
        print(f"[ERROR] No BCP progress report found in: {obsidian_dir}")
        sys.exit(1)
        
    # Sort files by modification time to get the latest one edited by the user
    latest_file = max(files, key=os.path.getmtime)
    print(f"📖 Reading latest reviewed report: {latest_file}")
    
    with open(latest_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Regex extraction of email components
    subject_match = re.search(r'Subject\s*\(邮件主题\)：\s*\n\s*(.*?)\s*(?:\n\s*To\s*\(收件人\)：|\Z)', content, re.DOTALL | re.IGNORECASE)
    to_match = re.search(r'To\s*\(收件人\)：\s*\n\s*(.*?)\s*(?:\n\s*CC\s*\(抄送\)：|\Z)', content, re.DOTALL | re.IGNORECASE)
    cc_match = re.search(r'CC\s*\(抄送\)：\s*\n\s*(.*?)\s*(?:\n\s*Body\s*\(正文\)：|\Z)', content, re.DOTALL | re.IGNORECASE)
    body_match = re.search(r'Body\s*\(正文\)：\s*\n\s*(.*?)\s*(?:\n\s*(?:---|## (?:2|二)[.、]\s*下游系统表级明细Format)|\Z)', content, re.DOTALL | re.IGNORECASE)
 
    # Fallback body match if header format is slightly different
    if not body_match:
        body_match = re.search(r'Body\s*\(正文\)：\s*\n\s*(.*?)\s*(?:\n\s*(?:---)|\Z)', content, re.DOTALL | re.IGNORECASE)
 
    if not (subject_match and to_match and cc_match and body_match):
        print("[ERROR] Failed to parse email sections from the markdown file.")
        print(f"Subject found: {bool(subject_match)}")
        print(f"To found: {bool(to_match)}")
        print(f"CC found: {bool(cc_match)}")
        print(f"Body found: {bool(body_match)}")
        sys.exit(1)
 
    subject = subject_match.group(1).strip()
    
    to_text = to_match.group(1).strip()
    to_list = [r.strip() for r in re.split(r'[,，\s]+', to_text) if r.strip()]
    recipients_str = " ".join(to_list)
 
    cc_text = cc_match.group(1).strip()
    cc_list = [r.strip() for r in re.split(r'[,，\s]+', cc_text) if r.strip()]
    cc_str = " ".join(cc_list)
 
    body = body_match.group(1).strip()
    # Strip any trailing "顺祝商祺！" from body (just in case)
    body = re.sub(r'\n*顺祝商祺！\s*$', '', body).strip()
 
    # Transform plain text body to beautiful visualized HTML!
    rich_html_body = text_to_rich_html(body)
 
    # Parse Section 2 details if present
    details_html = ""
    details_match = re.search(r'## (?:2|二)[.、]\s*下游系统表级明细\s*\n\s*(.*)$', content, re.DOTALL | re.IGNORECASE)
    if details_match:
        details_text = details_match.group(1).strip()
        details_text = re.sub(r'\n*顺祝商祺！\s*$', '', details_text).strip()
        details_html = markdown_details_to_html(details_text)

    # Combine body and details
    combined_html_body = rich_html_body
    if details_html:
        combined_html_body += "\n" + details_html
    
    # Append sign-off at the very end of combined HTML
    combined_html_body += '\n<p style="margin: 25px 0 0 0; font-family: system-ui, -apple-system, sans-serif; font-size: 14.5px; color: #333;">顺祝商祺！</p>'

    print(f"🎯 Subject: {subject}")
    print(f"👥 To: {recipients_str}")
    print(f"📢 CC: {cc_str}")
    
    # Save HTML body to a temp file for CLI passage
    cache_dir = "/Users/wujin/.gemini/antigravity/state/bcp_tracker"
    os.makedirs(cache_dir, exist_ok=True)
    temp_body_path = os.path.join(cache_dir, "mail_body_reviewed_html.txt")
    with open(temp_body_path, "w", encoding="utf-8") as f:
        f.write(combined_html_body)

    # Save standalone HTML file in the working directory
    output_html_name = os.path.basename(latest_file).replace(".md", ".html")
    output_html_path = os.path.join("/Volumes/Macintosh HD_Data/WorkBuddy/邮件发送", output_html_name)
    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{subject}</title>
</head>
<body style="margin: 0; padding: 20px; background-color: #ffffff;">
{combined_html_body}
</body>
</html>"""
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"📄 Saved synced HTML mail template to working directory: {output_html_path}")

    # 4. Trigger save_to_draft.py
    draft_saver_script = "/Volumes/Macintosh HD_Data/WorkBuddy/邮件发送/.agents/skills/email-polisher/scripts/save_to_draft.py"
    
    cmd = [
        "python3", draft_saver_script,
        "--subject", subject,
        "--body-file", temp_body_path,
        "--recipients", recipients_str,
        "--cc", cc_str
    ]
    if args.send:
        cmd.append("--send")

    print("🚀 Triggering mail draft saver agent in Coremail using reviewed report...")
    try:
        res = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(res.stdout)
        if res.stderr:
            print("Stderr output:")
            print(res.stderr)
        print("🎉 Mail successfully draft saved/sent from reviewed report!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error executing mail draft saver: {e}")
        print("Stdout:")
        print(e.stdout)
        print("Stderr:")
        print(e.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
