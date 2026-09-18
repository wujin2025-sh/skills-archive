#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draft review/communication meeting email and call email-polisher save_to_draft.py to save to Coremail draft box"""

import os
import re
import csv
import sys
import argparse
import subprocess
from pathlib import Path

# Script and workspace directory locations
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
WORKSPACE_DIR = Path("/Volumes/Macintosh HD_Data/WorkBuddy/邮件发送")
SCRATCH_DIR = WORKSPACE_DIR / "scratch"
SAVE_DRAFT_SCRIPT = Path("/Users/wujin/.workbuddy/skills/email-polisher/scripts/save_to_draft.py")
PYTHON_EXE = "/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python"
ROSTER_CSV = "/Volumes/Macintosh HD_Data/WorkBuddy/会议纪要/人员部门对应关系表.csv"

def parse_args():
    parser = argparse.ArgumentParser(description="Draft Demand Meeting Invitation Email")
    parser.add_argument("--recipients", required=True, help="List of recipient names separated by spaces, commas, or semicolons")
    parser.add_argument("--demand-title", required=True, help="Demand title, e.g., 【个微两融柜台】支持授信额度实时调整")
    parser.add_argument("--demand-url", required=True, help="Demand details URL")
    
    # Meeting details can be provided individually or parsed from raw text
    parser.add_argument("--meeting-theme", default="", help="Meeting theme")
    parser.add_argument("--meeting-time", default="", help="Meeting time")
    parser.add_argument("--meeting-link", default="", help="Meeting URL link")
    parser.add_argument("--meeting-id", default="", help="Meeting ID")
    parser.add_argument("--meeting-password", default="", help="Meeting password")
    
    parser.add_argument("--raw-meeting", default="", help="Raw copy-paste Tencent Meeting invitation text to parse automatically")
    parser.add_argument("--sender", default="吴进", help="Name of the person inviting (defaults to 吴进)")
    parser.add_argument("--cc", default="", help="List of CC names")
    parser.add_argument("--send", action="store_true", help="Send email immediately instead of saving as draft")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode: print details but do not call Playwright script")
    return parser.parse_args()

def parse_raw_meeting_text(text):
    """Parse meeting details from raw Tencent Meeting invitation text using regex"""
    theme = ""
    time_val = ""
    link = ""
    meeting_id = ""
    password = ""
    
    m_theme = re.search(r'(?:会议主题|主题)\s*[:：]\s*(.*)', text)
    if m_theme:
        theme = m_theme.group(1).strip()
        
    m_time = re.search(r'(?:会议时间|时间)\s*[:：]\s*(.*)', text)
    if m_time:
        time_val = m_time.group(1).strip()
        
    links = re.findall(r'https?://[^\s]+', text)
    if links:
        link = links[0].strip()
        
    m_id = re.search(r'(?:会议\s*ID|会议号|ID)\s*[:：]\s*(\d+)', text, re.IGNORECASE)
    if m_id:
        meeting_id = m_id.group(1).strip()
        
    m_pwd = re.search(r'(?:会议密码|密码)\s*[:：]\s*(\d+)', text)
    if m_pwd:
        password = m_pwd.group(1).strip()
        
    return theme, time_val, link, meeting_id, password

def load_roster_names(csv_path):
    """Load valid names from the personnel roster CSV"""
    names = set()
    if not os.path.exists(csv_path):
        return names
    
    for encoding in ['utf-8', 'gbk', 'gb2312']:
        try:
            with open(csv_path, mode='r', encoding=encoding) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get('人员', '').strip()
                    if name:
                        names.add(name)
            break
        except Exception:
            continue
    return names

def validate_recipients(recipients_str, roster_names):
    """Validate recipient names against the roster and return warnings if unrecognized"""
    if not roster_names:
        return
    
    # Split by common delimiters
    names = [n.strip() for n in re.split(r'[,，;；\s]+', recipients_str) if n.strip()]
    invalid_names = []
    
    for name in names:
        if name not in roster_names:
            invalid_names.append(name)
            
    if invalid_names:
        print("=" * 60, file=sys.stderr)
        print(f"⚠️  [WARNING] The following recipient name(s) are NOT found in the personnel roster ({ROSTER_CSV}):", file=sys.stderr)
        for name in invalid_names:
            print(f"    - {name}", file=sys.stderr)
        print("Please verify the spellings. Autocomplete in Coremail might fail for these names.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

def main():
    args = parse_args()
    
    # Load roster for validation
    roster_names = load_roster_names(ROSTER_CSV)
    validate_recipients(args.recipients, roster_names)
    if args.cc:
        validate_recipients(args.cc, roster_names)
        
    # Extract meeting details
    meeting_theme = args.meeting_theme
    meeting_time = args.meeting_time
    meeting_link = args.meeting_link
    meeting_id = args.meeting_id
    meeting_password = args.meeting_password
    
    if args.raw_meeting:
        print("[INFO] Parsing raw meeting text...")
        raw_theme, raw_time, raw_link, raw_id, raw_pwd = parse_raw_meeting_text(args.raw_meeting)
        if not meeting_theme: meeting_theme = raw_theme
        if not meeting_time: meeting_time = raw_time
        if not meeting_link: meeting_link = raw_link
        if not meeting_id: meeting_id = raw_id
        if not meeting_password: meeting_password = raw_pwd
        
    # Fallbacks and validation
    if not meeting_theme:
        cleaned_title = re.sub(r'^【.+?】', '', args.demand_title).strip()
        if not cleaned_title:
            cleaned_title = args.demand_title
        meeting_theme = f"{cleaned_title}-需求沟通"
        
    if not meeting_time:
        print("[ERROR] Meeting time is required. Please specify --meeting-time or provide raw text in --raw-meeting.", file=sys.stderr)
        sys.exit(1)
        
    meeting_time = meeting_time.strip()
    timezone_pattern = r'GMT|北京|中国标准时间'
    if not re.search(timezone_pattern, meeting_time):
        meeting_time = f"{meeting_time}(GMT+08:00) 中国标准时间 - 北京"
        
    # Generate email subject
    email_subject = f"【会议邀请】{meeting_theme}"
    
    # Generate email body
    email_body = (
        f"{args.demand_title}\n"
        f"{args.demand_url}\n\n\n"
        f"{args.sender} 邀请您参加线上会议\n"
        f"会议主题：{meeting_theme}\n"
        f"会议时间：{meeting_time}\n\n"
        f"点击链接入会，或添加至会议列表：\n"
        f"{meeting_link}\n\n"
        f"会议 ID：{meeting_id}\n"
        f"会议密码：{meeting_password}\n"
        f"*参会人也可通过腾讯会议进入"
    )
    
    # Write body to temporary file
    os.makedirs(SCRATCH_DIR, exist_ok=True)
    temp_body_file = SCRATCH_DIR / "demand_meeting_body.txt"
    with open(temp_body_file, "w", encoding="utf-8") as f:
        f.write(email_body)
        
    print("Email Subject:", email_subject)
    print("Email Body Generated:")
    print("-" * 50)
    print(email_body)
    print("-" * 50)
    
    # Call save_to_draft.py script
    if args.dry_run:
        print("[DRY-RUN] Script running in dry-run mode. Skipping Playwright execution.")
        print(f"Recipients: {args.recipients}")
        if args.cc:
            print(f"CC: {args.cc}")
        print("🎉 Dry run finished successfully!")
        return

    if not SAVE_DRAFT_SCRIPT.exists():
        print(f"[ERROR] save_to_draft.py script not found at {SAVE_DRAFT_SCRIPT}", file=sys.stderr)
        sys.exit(1)
        
    cmd = [
        PYTHON_EXE, str(SAVE_DRAFT_SCRIPT),
        "--subject", email_subject,
        "--body-file", str(temp_body_file),
        "--recipients", args.recipients
    ]
    if args.cc:
        cmd.extend(["--cc", args.cc])
    if args.send:
        cmd.append("--send")
        
    print(f"Running subprocess to save draft...")
    print("Command:", " ".join(cmd))
    
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print("Subprocess stdout:")
        print(result.stdout)
        if result.stderr:
            print("Subprocess stderr:")
            print(result.stderr, file=sys.stderr)
        print("🎉 Meeting invitation email draft created successfully in Coremail!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Subprocess failed with exit code {e.returncode}", file=sys.stderr)
        print("Subprocess stdout:", e.stdout, file=sys.stderr)
        print("Subprocess stderr:", e.stderr, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
