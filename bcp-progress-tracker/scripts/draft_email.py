#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draft or send BCP progress email with automated recipient and CC listing"""

import os
import json
import re
import sys
import argparse
import subprocess

def clean_names(raw_contacts_dict):
    names = set()
    for sys_name, contact_str in raw_contacts_dict.items():
        if not contact_str or contact_str == "未登记":
            continue
        # Clean and split names (by commas, spaces, etc.)
        cleaned = contact_str.replace("、", " ").replace(",", " ").replace(";", " ")
        for part in cleaned.split():
            part = part.strip()
            if part and len(part) >= 2:
                names.add(part)
    return sorted(list(names))

def main():
    parser = argparse.ArgumentParser(description="Automate BCP progress reminder email drafting/sending")
    parser.add_argument("--send", action="store_true", help="Send the email immediately instead of saving as draft")
    args = parser.parse_args()

    cache_dir = "/Users/wujin/.gemini/antigravity/state/bcp_tracker"
    json_path = os.path.join(cache_dir, "systems_status.json")
    subj_file = os.path.join(cache_dir, "mail_subject.txt")
    body_file = os.path.join(cache_dir, "mail_body.txt")

    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found. Run parse_workbook.py first.")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Resolve recipients
    # (a) Content-related system contacts
    system_contacts = data.get("contacts", {})
    involved_people = clean_names(system_contacts)
    print(f"👥 Content-involved recipients: {involved_people}")

    # (b) Static list of additional recipients
    static_recipients = [
        "黄志昌", "王图南", "杨蓉渊", "柴恒", "李骎", "周静", "胡玲杰", 
        "揭由翔", "丁伟", "高健", "李萍萍", "曾娟", "茆莹莹", "刘青"
    ]
    
    # Combine (remove duplicates, preserve order/set)
    all_recipients = set(involved_people + static_recipients)
    recipients_str = " ".join(sorted(list(all_recipients)))
    print(f"🎯 Total Recipients (To): {recipients_str}")

    # 2. Resolve CC list
    cc_list = ["姜婷婷", "钱维佳", "吴保杰", "彭伟", "纪飞", "赵永杰", "周哲博", "周尤珠"]
    cc_str = " ".join(cc_list)
    print(f"📢 Total CC (抄送): {cc_str}")

    # 3. Read subject
    with open(subj_file, "r", encoding="utf-8") as f:
        subject = f.read().strip()

    # 4. Trigger save_to_draft.py
    draft_saver_script = "/Volumes/Macintosh HD_Data/WorkBuddy/邮件发送/.agents/skills/email-polisher/scripts/save_to_draft.py"
    
    cmd = [
        "python3", draft_saver_script,
        "--subject", subject,
        "--body-file", body_file,
        "--recipients", recipients_str,
        "--cc", cc_str
    ]
    if args.send:
        cmd.append("--send")

    print("🚀 Triggering mail draft saver agent in Coremail...")
    try:
        res = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(res.stdout)
        if res.stderr:
            print("Stderr output:")
            print(res.stderr)
        print("🎉 Mail successfully processed!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error executing mail draft saver: {e}")
        print("Stdout:")
        print(e.stdout)
        print("Stderr:")
        print(e.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
