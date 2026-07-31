#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import argparse

# Colors/emojis for output
PASS_SYM = "🟢"
WARN_SYM = "🟡"
FAIL_SYM = "🔴"
BOLD = '\033[1m'
RESET = '\033[0m'

def colorize_bold(text, use_color=True):
    if use_color:
        return f"{BOLD}{text}{RESET}"
    return text

def read_file_content(filepath):
    """Reads file content with encoding fallbacks."""
    for encoding in ['utf-8', 'gbk', 'gb18030', 'latin1']:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    # Ultimate fallback with error ignore
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception:
        return ""

def parse_excel_output(file_path):
    """
    Parses excel_output.txt and categorizes lines by section.
    """
    if not os.path.exists(file_path):
        return None

    sections = {}
    current_section = None

    content = read_file_content(file_path)
    lines = content.splitlines()

    # Match section headers like # === cli (共 2 项) ===
    header_pat = re.compile(r'^#\s*===\s*([a-zA-Z_0-9\s\u4e00-\u9fa5]+?)\s*(?:\([^)]+\))?\s*===')
    # Match append calls like: table_run_list.append(['user_task', [['snonightorderid','TDictionary.sql']]])
    append_pat = re.compile(r"\[\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\]")

    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            continue

        m_header = header_pat.match(line_strip)
        if m_header:
            raw_sec_name = m_header.group(1).strip()
            # Normalize names: ProcUpd/ProcAdd -> proc, cli -> cli, dll -> dll, table/table_develop -> table, init -> init
            sec_lower = raw_sec_name.lower()
            if 'cli' in sec_lower:
                current_section = 'cli'
            elif 'dll' in sec_lower:
                current_section = 'dll'
            elif 'table' in sec_lower:
                current_section = 'table'
            elif 'proc' in sec_lower:
                current_section = 'proc'
            elif 'init' in sec_lower:
                current_section = 'init'
            elif '升级备注' in sec_lower or 'upgraderemark' in sec_lower:
                current_section = 'upgraderemark'
            else:
                current_section = sec_lower

            if current_section not in sections:
                sections[current_section] = []
            continue

        if current_section:
            # Skip comment lines
            if line_strip.startswith('#'):
                continue
            # Skip python assignment lines that are not lists or appends we care about
            if '=' in line_strip and not line_strip.startswith('table_run_list.append') and not line_strip.startswith('proc_list.append'):
                continue

            # Parse Table / Proc append statements
            if current_section in ['table', 'proc']:
                matches = append_pat.findall(line_strip)
                if matches:
                    for item_name, sql_file in matches:
                        sections[current_section].append({
                            'type': 'content',
                            'name': item_name,
                            'file': sql_file,
                            'raw': line_strip
                        })
                    continue

            # File names (e.g. init files or sql files in CSZX)
            if '.' in line_strip:
                sections[current_section].append({
                    'type': 'file',
                    'name': line_strip,
                    'raw': line_strip
                })
            else:
                # Plain items (like CmCli_Of or lbm_acct)
                sections[current_section].append({
                    'type': 'plain',
                    'name': line_strip,
                    'raw': line_strip
                })

    return sections

def find_file_in_dir(directory, filename, recursive=True):
    """
    Finds a file case-insensitively under directory.
    Returns relative path if found, otherwise None.
    """
    target = filename.lower()
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.lower() == target:
                return os.path.relpath(os.path.join(root, f), directory)
        if not recursive:
            break
    return None

def search_string_in_files(directory, search_str):
    """
    Searches for search_str case-insensitively in all file contents under directory.
    Returns list of relative file paths where the string was found.
    """
    found_files = []
    target = search_str.lower()
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.startswith('.'):
                continue
            filepath = os.path.join(root, f)
            # Skip obviously non-text files to speed up
            if f.lower().endswith(('.xlsx', '.xls', '.zip', '.pdf', '.doc', '.docx', '.png', '.jpg', '.gif')):
                continue
            content = read_file_content(filepath)
            if target in content.lower():
                found_files.append(os.path.relpath(filepath, directory))
    return found_files

def get_expected_dll_name(name):
    if name.lower().endswith('.dll'):
        return name
    return name + '.dll'

def find_similar_file_by_task_id(directory, filename):
    """
    Attempts to find a file in directory containing the task ID extracted from filename,
    prioritizing files with matching extension and the highest name similarity.
    """
    # Extract task ID (e.g. JZJYPT-T202606586, T202606586, or CSZXCXJS-T202601392)
    match = re.search(r'(T\d{5,})', filename)
    if not match:
        # Fallback to search for any number sequence of 5+ digits
        match = re.search(r'(\d{5,})', filename)
        
    if not match:
        return None
        
    task_id = match.group(1).lower()
    ext = os.path.splitext(filename)[1].lower()
    
    target_words = set(re.split(r'[_.\-\s]+', filename.lower()))
    
    best_match = None
    best_score = -1
    best_ext_match = False
    
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.startswith('.'):
                continue
            if task_id in f.lower():
                # Score similarity
                cand_words = set(re.split(r'[_.\-\s]+', f.lower()))
                score = len(target_words & cand_words)
                has_matching_ext = f.lower().endswith(ext)
                
                # Check if this candidate is better
                is_better = False
                if not best_match:
                    is_better = True
                else:
                    if has_matching_ext and not best_ext_match:
                        is_better = True
                    elif has_matching_ext == best_ext_match:
                        if score > best_score:
                            is_better = True
                            
                if is_better:
                    best_match = os.path.relpath(os.path.join(root, f), directory)
                    best_score = score
                    best_ext_match = has_matching_ext
                    
    return best_match

def check_package(package_dir, sections, system_type):
    """
    Checks the package directory against parsed sections.
    """
    report = []
    summary = {
        'passed': 0,
        'warnings': 0,
        'errors': 0
    }

    # Helper to log results
    def log_result(status, message, section_name, item_name=None):
        report.append({
            'status': status,
            'message': message,
            'section': section_name,
            'item_name': item_name
        })
        if status == 'PASS':
            summary['passed'] += 1
        elif status == 'WARN':
            summary['warnings'] += 1
        elif status == 'FAIL':
            summary['errors'] += 1

    # Check CLI
    cli_items = sections.get('cli', [])
    if cli_items:
        client_dir = os.path.join(package_dir, 'client')
        if not os.path.exists(client_dir):
            log_result('FAIL', f"client/ 文件夹缺失，但 CLI 选项已被声明。", 'cli', 'client')
        else:
            for item in cli_items:
                dll_name = get_expected_dll_name(item['name'])
                rel_path = find_file_in_dir(client_dir, dll_name, recursive=False)
                if rel_path:
                    log_result('PASS', f"{dll_name} 已在 client/ 文件夹中存在。", 'cli', item['name'])
                else:
                    any_path = find_file_in_dir(package_dir, dll_name, recursive=True)
                    if any_path:
                        log_result('WARN', f"未在 client/ 文件夹中，但已在 {any_path} 文件夹中找到。", 'cli', item['name'])
                    else:
                        log_result('FAIL', f"文件缺失。", 'cli', item['name'])

    # Check DLL (lbm)
    dll_items = sections.get('dll', [])
    if dll_items:
        lbm_dir = os.path.join(package_dir, 'lbm')
        if not os.path.exists(lbm_dir):
            log_result('FAIL', f"lbm/ 文件夹缺失，但 DLL 选项已被声明。", 'dll', 'lbm')
        else:
            for item in dll_items:
                dll_name = get_expected_dll_name(item['name'])
                rel_path = find_file_in_dir(lbm_dir, dll_name, recursive=False)
                if rel_path:
                    log_result('PASS', f"{dll_name} 存在。", 'dll', item['name'])
                else:
                    any_path = find_file_in_dir(package_dir, dll_name, recursive=True)
                    if any_path:
                        log_result('WARN', f"未在 lbm/ 文件夹中，但已在 {any_path} 文件夹中找到。", 'dll', item['name'])
                    else:
                        log_result('FAIL', f"文件缺失。", 'dll', item['name'])

    # Check Table
    table_items = sections.get('table', [])
    if table_items:
        table_dir = os.path.join(package_dir, 'table')
        if not os.path.exists(table_dir):
            log_result('FAIL', f"table/ 文件夹缺失，但 table 选项已被声明。", 'table', 'table')
        else:
            for item in table_items:
                if item['type'] == 'content':
                    # Search table name in table contents
                    found_files = search_string_in_files(table_dir, item['name'])
                    if found_files:
                        log_result('PASS', f"成功在 {', '.join(found_files)} 文件内容中找到。", 'table', f"表名 {item['name']}")
                    else:
                        log_result('FAIL', f"未在任何 table/ 文件的内容中找到。", 'table', f"表名 {item['name']}")
                elif item['type'] == 'file':
                    # Check file existence in table/
                    rel_path = find_file_in_dir(table_dir, item['name'], recursive=True)
                    if rel_path:
                        log_result('PASS', f"已在 table/{rel_path} 找到。", 'table', item['name'])
                    else:
                        any_path = find_file_in_dir(package_dir, item['name'], recursive=True)
                        if any_path:
                            log_result('WARN', f"未在 table/ 文件夹中，但已在 {any_path} 文件夹中找到。", 'table', item['name'])
                        else:
                            # Search for similar file by task ID
                            similar_path = find_similar_file_by_task_id(table_dir, item['name'])
                            if similar_path:
                                log_result('WARN', f"未在 table/ 文件夹中找到该文件，但在 table/{similar_path} 找到相似文件，请核对。", 'table', item['name'])
                            else:
                                log_result('FAIL', f"文件缺失。", 'table', item['name'])
                else:
                    # Plain text
                    found_files = search_string_in_files(table_dir, item['name'])
                    if found_files:
                        log_result('PASS', f"成功在 {', '.join(found_files)} 文件内容中找到。", 'table', item['name'])
                    else:
                        rel_path = find_file_in_dir(table_dir, item['name'], recursive=True)
                        if rel_path:
                            log_result('PASS', f"已在 table/{rel_path} 找到。", 'table', item['name'])
                        else:
                            log_result('FAIL', f"未找到（文件不存在且内容中未出现）。", 'table', item['name'])

    # Check Proc (ProcUpd & ProcAdd)
    proc_items = sections.get('proc', [])
    if proc_items:
        proc_dir = os.path.join(package_dir, 'proc')
        if not os.path.exists(proc_dir):
            log_result('FAIL', f"proc/ 文件夹缺失，但 proc 选项已被声明。", 'proc', 'proc')
        else:
            for item in proc_items:
                if item['type'] == 'content':
                    found_files = search_string_in_files(proc_dir, item['name'])
                    if found_files:
                        log_result('PASS', f"成功在 {', '.join(found_files)} 文件内容中找到。", 'proc', f"存储过程 {item['name']}")
                    else:
                        log_result('FAIL', f"未在任何 proc/ 文件的内容中找到。", 'proc', f"存储过程 {item['name']}")
                elif item['type'] == 'file':
                    rel_path = find_file_in_dir(proc_dir, item['name'], recursive=True)
                    if rel_path:
                        log_result('PASS', f"已在 proc/{rel_path} 找到。", 'proc', item['name'])
                    else:
                        any_path = find_file_in_dir(package_dir, item['name'], recursive=True)
                        if any_path:
                            log_result('WARN', f"未在 proc/ 文件夹中，但已在 {any_path} 文件夹中找到。", 'proc', item['name'])
                        else:
                            # Search for similar file by task ID
                            similar_path = find_similar_file_by_task_id(proc_dir, item['name'])
                            if similar_path:
                                log_result('WARN', f"未在 proc/ 文件夹中找到该文件，但在 proc/{similar_path} 找到相似文件，请核对。", 'proc', item['name'])
                            else:
                                log_result('FAIL', f"文件缺失。", 'proc', item['name'])
                else:
                    found_files = search_string_in_files(proc_dir, item['name'])
                    if found_files:
                        log_result('PASS', f"成功在 {', '.join(found_files)} 文件内容中找到。", 'proc', item['name'])
                    else:
                        rel_path = find_file_in_dir(proc_dir, item['name'], recursive=True)
                        if rel_path:
                            log_result('PASS', f"已在 proc/{rel_path} 找到。", 'proc', item['name'])
                        else:
                            log_result('FAIL', f"未找到（文件不存在且内容中未出现）。", 'proc', item['name'])

    # Check Init
    init_items = sections.get('init', [])
    if init_items:
        init_dir = os.path.join(package_dir, 'init')
        if not os.path.exists(init_dir):
            log_result('FAIL', f"init/ 文件夹缺失，但 init 选项已被声明。", 'init', 'init')
        else:
            for item in init_items:
                filename = item['name']
                rel_path = find_file_in_dir(init_dir, filename, recursive=False)
                if rel_path:
                    log_result('PASS', f"已在 init/ 文件夹中存在。", 'init', filename)
                else:
                    any_path = find_file_in_dir(package_dir, filename, recursive=True)
                    if any_path:
                        log_result('WARN', f"未在 init/ 文件夹中，但已在 {any_path} 文件夹中找到。", 'init', filename)
                    else:
                        # Search for similar file by task ID
                        similar_path = find_similar_file_by_task_id(init_dir, filename)
                        if similar_path:
                            log_result('WARN', f"未在 init/ 文件夹中找到该文件，但在 init/{similar_path} 找到相似文件，请核对。", 'init', filename)
                        else:
                            log_result('FAIL', f"文件缺失。", 'init', filename)

    # Check UpgradeRemark
    remark_items = sections.get('upgraderemark', [])
    if remark_items:
        init_dir = os.path.join(package_dir, 'init')
        for item in remark_items:
            if item['type'] == 'file':
                filename = item['name']
                if not os.path.exists(init_dir):
                    log_result('FAIL', f"init/ 文件夹缺失，但升级备注文件已被声明。", 'upgraderemark', filename)
                else:
                    rel_path = find_file_in_dir(init_dir, filename, recursive=False)
                    if rel_path:
                        log_result('PASS', f"已在 init/ 文件夹中存在。", 'upgraderemark', filename)
                    else:
                        any_path = find_file_in_dir(package_dir, filename, recursive=True)
                        if any_path:
                            log_result('WARN', f"未在 init/ 文件夹中，但已在 {any_path} 文件夹中找到。", 'upgraderemark', filename)
                        else:
                            # Search for similar file by task ID
                            similar_path = find_similar_file_by_task_id(init_dir, filename)
                            if similar_path:
                                log_result('WARN', f"未在 init/ 文件夹中找到该文件，但在 init/{similar_path} 找到相似文件，请核对。", 'upgraderemark', filename)
                            else:
                                log_result('FAIL', f"文件缺失。", 'upgraderemark', filename)

    return report, summary

def get_all_files_in_dir(directory):
    """Recursively lists all non-hidden files in directory."""
    all_files = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.startswith('.'):
                continue
            all_files.append(os.path.join(root, f))
    return all_files

def run_reverse_audit(package_dir, sections, report_results):
    """
    Finds files in the package directory that are not referenced in sections.
    """
    extra_files = {}

    # Build maps of expected files (lowercased)
    expected_cli = {get_expected_dll_name(item['name']).lower() for item in sections.get('cli', [])}
    expected_dll = {get_expected_dll_name(item['name']).lower() for item in sections.get('dll', [])}
    expected_init = {item['name'].lower() for item in sections.get('init', [])}
    expected_init.update({item['name'].lower() for item in sections.get('upgraderemark', []) if item['type'] == 'file'})
    
    # For table and proc files, we extract actual filenames checkable
    expected_table_files = {item['name'].lower() for item in sections.get('table', []) if item['type'] == 'file'}
    expected_proc_files = {item['name'].lower() for item in sections.get('proc', []) if item['type'] == 'file'}

    # Helper: check if file is verified in content checks
    verified_files = set()
    for res in report_results:
        if res['status'] in ['PASS', 'WARN']:
            # Search for referenced paths in message
            for word in re.split(r'[\s,\'\"]+', res['message']):
                if '/' in word or word.lower().endswith(('.sql', '.xml', '.zip', '.dll')):
                    # clean path
                    clean_word = word.strip('.').lower()
                    # extract filename
                    verified_files.add(os.path.basename(clean_word))

    # Audit folders
    folders = ['client', 'lbm', 'init', 'table', 'proc']
    for folder in folders:
        folder_dir = os.path.join(package_dir, folder)
        if not os.path.exists(folder_dir):
            continue

        extra_files[folder] = []
        files = get_all_files_in_dir(folder_dir)
        for filepath in files:
            rel_path = os.path.relpath(filepath, folder_dir)
            filename = os.path.basename(filepath)
            filename_lower = filename.lower()

            # Ignore common files
            if filename_lower in ['.ds_store', 'thumbs.db']:
                continue

            # Check if this file is expected
            is_expected = False
            if folder == 'client':
                is_expected = filename_lower in expected_cli
            elif folder == 'lbm':
                is_expected = filename_lower in expected_dll
            elif folder == 'init':
                is_expected = filename_lower in expected_init
            elif folder == 'table':
                is_expected = filename_lower in expected_table_files or filename_lower in verified_files
            elif folder == 'proc':
                is_expected = filename_lower in expected_proc_files or filename_lower in verified_files

            if not is_expected and filename_lower not in verified_files:
                extra_files[folder].append(os.path.join(folder, rel_path))

    return extra_files

def resolve_extracted_dir(directory):
    """Checks if there is exactly one subdirectory inside and no files, returning it if so."""
    try:
        items = os.listdir(directory)
        # Filter out hidden files
        items = [i for i in items if not i.startswith('.')]
        if len(items) == 1:
            subpath = os.path.join(directory, items[0])
            if os.path.isdir(subpath):
                return subpath
    except Exception:
        pass
    return directory

def main():
    parser = argparse.ArgumentParser(description="SPB Package Verification Tool")
    parser.add_argument('-d', '--dir', help="Path to package directory (e.g. SPB_V2.2.19_20260710)")
    parser.add_argument('-f', '--file', default="excel_output.txt", help="Verification file (default: excel_output.txt)")
    parser.add_argument('-s', '--system', choices=['jzjy', 'cszx'], help="System type (jzjy or cszx)")
    parser.add_argument('-o', '--output', default="./spb_check_report.md", help="Output Markdown report path")
    args = parser.parse_args()

    # 1. Determine CWD
    cwd = os.getcwd()

    # 2. Locate Package Directory first (since reference file depends on it if run from parent)
    package_dir = args.dir
    system_type = args.system
    
    if not package_dir:
        matches = []
        # Check CWD first
        for name in os.listdir(cwd):
            full_path = os.path.join(cwd, name)
            if os.path.isdir(full_path):
                if (name.lower().startswith('spb_v') or 'spb' in name.lower()):
                    matches.append((full_path, 'jzjy'))
                elif (name.lower().startswith('cszx') or 'cszx' in name.lower()):
                    matches.append((full_path, 'cszx'))
            elif os.path.isfile(full_path) and name.lower().endswith('.zip'):
                basename = os.path.splitext(name)[0]
                if (basename.lower().startswith('spb_v') or 'spb' in basename.lower()):
                    matches.append((full_path, 'jzjy_zip'))
                elif (basename.lower().startswith('cszx') or 'cszx' in basename.lower()):
                    matches.append((full_path, 'cszx_zip'))
                    
        # Check subdirectories 'jzjy' and 'jygl'
        if not matches:
            for sub in ['jzjy', 'jygl']:
                sub_path = os.path.join(cwd, sub)
                if os.path.exists(sub_path) and os.path.isdir(sub_path):
                    sub_sys = 'jzjy' if sub == 'jzjy' else 'cszx'
                    for name in os.listdir(sub_path):
                        full_path = os.path.join(sub_path, name)
                        if os.path.isdir(full_path):
                            if sub_sys == 'jzjy' and (name.lower().startswith('spb_v') or 'spb' in name.lower()):
                                matches.append((full_path, 'jzjy'))
                            elif sub_sys == 'cszx' and (name.lower().startswith('cszx') or 'cszx' in name.lower()):
                                matches.append((full_path, 'cszx'))
                        elif os.path.isfile(full_path) and name.lower().endswith('.zip'):
                            basename = os.path.splitext(name)[0]
                            if sub_sys == 'jzjy' and (basename.lower().startswith('spb_v') or 'spb' in basename.lower()):
                                matches.append((full_path, 'jzjy_zip'))
                            elif sub_sys == 'cszx' and (basename.lower().startswith('cszx') or 'cszx' in basename.lower()):
                                matches.append((full_path, 'cszx_zip'))
                                
        # Filter matches by explicit system_type if provided
        if system_type:
            matches = [m for m in matches if m[1].replace('_zip', '') == system_type]
            
        if matches:
            # Sort matches by modification time to get the latest folder
            matches.sort(key=lambda x: os.path.getmtime(x[0]))
            package_dir, auto_system = matches[-1]
            
            # If the best match is a zip file, unzip it
            if auto_system.endswith('_zip'):
                zip_path = package_dir
                extracted_parent = os.path.dirname(zip_path)
                zip_basename = os.path.basename(zip_path)
                folder_name = os.path.splitext(zip_basename)[0]
                package_dir = os.path.join(extracted_parent, folder_name)
                system_type = auto_system.replace('_zip', '')
                
                if not os.path.exists(package_dir):
                    import zipfile
                    print(f"📦 Auto-detecting package ZIP file: {colorize_bold(zip_basename)}")
                    print(f"📦 Unzipping to {colorize_bold(package_dir)}...")
                    try:
                        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                            zip_ref.extractall(package_dir)
                        print(f"✅ Unzipped successfully.")
                    except Exception as e:
                        print(f"🔴 [ERROR] Failed to unzip {zip_basename}: {e}")
                        sys.exit(1)
                
                # Resolve nested folder if exists
                package_dir = resolve_extracted_dir(package_dir)
            else:
                system_type = auto_system
        else:
            print(f"{FAIL_SYM} [ERROR] No matching package directory or ZIP found in current directory or subdirectories.")
            sys.exit(1)
    else:
        package_dir = os.path.abspath(package_dir)
        if not system_type:
            # Detect from path
            if 'jzjy' in package_dir.lower():
                system_type = 'jzjy'
            elif 'jygl' in package_dir.lower() or 'cszx' in package_dir.lower():
                system_type = 'cszx'
            else:
                system_type = 'jzjy'

    if not os.path.exists(package_dir) or not os.path.isdir(package_dir):
        print(f"{FAIL_SYM} [ERROR] Package directory '{package_dir}' does not exist.")
        sys.exit(1)

    print(f"System Type: {colorize_bold(system_type.upper())}")
    print(f"Package Dir: {colorize_bold(package_dir)}")

    # 3. Locate Verification File
    verify_file = args.file
    if not os.path.exists(verify_file):
        # Try next to package parent directory
        pkg_parent = os.path.dirname(package_dir)
        alt_path = os.path.join(pkg_parent, verify_file)
        if os.path.exists(alt_path):
            verify_file = alt_path
        else:
            print(f"{FAIL_SYM} [ERROR] Verification file '{args.file}' not found.")
            sys.exit(1)

    print(f"Reference File: {colorize_bold(verify_file)}")

    # 4. Parse Verification File
    sections = parse_excel_output(verify_file)
    if not sections:
        print(f"{FAIL_SYM} [ERROR] Failed to parse verification file.")
        sys.exit(1)

    # 5. Run Verification Checks
    report, summary = check_package(package_dir, sections, system_type)

    # 6. Run Reverse Audit
    extra_files = run_reverse_audit(package_dir, sections, report)

    # 7. Print Console Output
    # Group report by section
    by_section = {}
    for item in report:
        sec = item['section']
        if sec not in by_section:
            by_section[sec] = []
        by_section[sec].append(item)

    section_titles = {
        'cli': '1. 客户端 CLI 核对',
        'dll': '2. 核心 DLL 核对',
        'table': '3. SQL 表结构核对',
        'proc': '4. 存储过程 (Proc) 核对',
        'init': '5. 初始化脚本 (Init) 核对',
        'upgraderemark': '6. 升级备注核对'
    }

    ordered_sections = ['cli', 'dll', 'table', 'proc', 'init', 'upgraderemark']
    for sec in ordered_sections:
        if sec not in by_section:
            continue
        items = by_section[sec]
        
        has_errors = any(i['status'] == 'FAIL' for i in items)
        has_warnings = any(i['status'] == 'WARN' for i in items)
        
        if has_errors:
            sec_status = f"{FAIL_SYM} {sum(1 for i in items if i['status'] == 'FAIL')} 项缺失"
        elif has_warnings:
            sec_status = f"{WARN_SYM} 存在警告"
        else:
            sec_status = f"{PASS_SYM} 全部通过"
            
        title = section_titles.get(sec, f"{sec.upper()} 核对")
        print(f"\n{title} (共 {len(items)} 项, {sec_status})")
        
        if sec == 'dll':
            print("以下 LBM 模块的 DLL 文件均已正确存放在 lbm/ 文件夹中：\n")
            
        for item in items:
            item_name = item.get('item_name') or ''
            sym = PASS_SYM if item['status'] == 'PASS' else WARN_SYM if item['status'] == 'WARN' else FAIL_SYM
            if item_name:
                print(f"  • {sym} {item_name} ➔ {item['message']}")
            else:
                print(f"  • {sym} {item['message']}")

    # Print Reverse Audit (Extra Files)
    has_extras = False
    for folder, files in extra_files.items():
        if files:
            has_extras = True
            
    if has_extras:
        print(f"\n{WARN_SYM} 发现未在 excel_output.txt 中声明的额外文件：")
        for folder, files in extra_files.items():
            if files:
                print(f"  {folder}/:")
                for f in files:
                    print(f"    - {f}")

    # Summary
    print("\n" + "=" * 50)
    summary_text = f"Summary: {summary['passed']} checks passed, {summary['warnings']} warnings, {summary['errors']} errors."
    if summary['errors'] > 0:
        print(summary_text)
    elif summary['warnings'] > 0:
        print(summary_text)
    else:
        print(summary_text)
    print("=" * 50 + "\n")

    # 8. Write Markdown & HTML Reports
    write_markdown_report(args.output, package_dir, verify_file, system_type, report, summary, extra_files)
    html_output_path = f"{package_dir}_check_report.html"
    write_html_report(html_output_path, package_dir, verify_file, system_type, report, summary, extra_files)

    # Return non-zero code if error
    if summary['errors'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)

def write_markdown_report(output_path, package_dir, verify_file, system_type, report, summary, extra_files):
    pkg_basename = os.path.basename(package_dir)
    file_basename = os.path.basename(verify_file)
    
    status_text = "🟢 All Checked OK"
    if summary['errors'] > 0:
        status_text = "🔴 Errors Found"
    elif summary['warnings'] > 0:
        status_text = "🟡 Warnings Found"

    lines = [
        f"# SPB Package Verification Report",
        f"",
        f"- **Package Directory**: `{pkg_basename}`",
        f"- **Reference File**: `{file_basename}`",
        f"- **System Type**: `{system_type.upper()}`",
        f"- **Status**: {status_text}",
        f"",
        f"## Summary",
        f"",
        f"| Category | Count | Status |",
        f"| :--- | :---: | :--- |",
        f"| Passed Checks | {summary['passed']} | 🟢 |",
        f"| Warnings | {summary['warnings']} | 🟡 |",
        f"| Errors | {summary['errors']} | 🔴 |",
        f"",
        f"## Verification Details",
        f""
    ]

    by_section = {}
    for item in report:
        sec = item['section']
        if sec not in by_section:
            by_section[sec] = []
        by_section[sec].append(item)

    section_titles = {
        'cli': '1. 客户端 CLI 核对',
        'dll': '2. 核心 DLL 核对',
        'table': '3. SQL 表结构核对',
        'proc': '4. 存储过程 (Proc) 核对',
        'init': '5. 初始化脚本 (Init) 核对',
        'upgraderemark': '6. 升级备注核对'
    }

    ordered_sections = ['cli', 'dll', 'table', 'proc', 'init', 'upgraderemark']
    for sec in ordered_sections:
        if sec not in by_section:
            continue
        items = by_section[sec]
        
        has_errors = any(i['status'] == 'FAIL' for i in items)
        has_warnings = any(i['status'] == 'WARN' for i in items)
        
        if has_errors:
            sec_status = f"🔴 {sum(1 for i in items if i['status'] == 'FAIL')} 项缺失"
        elif has_warnings:
            sec_status = "🟡 存在警告"
        else:
            sec_status = "🟢 全部通过"
            
        title = section_titles.get(sec, f"{sec.upper()} 核对")
        lines.append(f"### {title} (共 {len(items)} 项, {sec_status})")
        lines.append("")
        if sec == 'dll':
            lines.append("以下 LBM 模块的 DLL 文件均已正确存放在 lbm/ 文件夹中：")
            lines.append("")
            
        for item in items:
            symbol = PASS_SYM if item['status'] == 'PASS' else WARN_SYM if item['status'] == 'WARN' else FAIL_SYM
            item_name = item.get('item_name') or ''
            if item_name:
                lines.append(f"- {symbol} {item_name} ➔ {item['message']}")
            else:
                lines.append(f"- {symbol} {item['message']}")
        lines.append("")

    lines.append("## Reverse Audit (Unlisted Files in Package)")
    lines.append("")
    has_extras = False
    for folder, files in extra_files.items():
        if files:
            has_extras = True
            lines.append(f"### Extra files in `{folder}/`")
            for f in files:
                lines.append(f"- `{f}`")
            lines.append("")
            
    if not has_extras:
        lines.append("🟢 No extra/unlisted files found in package.")
        lines.append("")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

def write_html_report(output_path, package_dir, verify_file, system_type, report, summary, extra_files):
    pkg_basename = os.path.basename(package_dir)
    file_basename = os.path.basename(verify_file)
    
    status_text = "🟢 All Checked OK"
    status_class = "pass"
    if summary['errors'] > 0:
        status_text = "🔴 Errors Found"
        status_class = "fail"
    elif summary['warnings'] > 0:
        status_text = "🟡 Warnings Found"
        status_class = "warn"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>SPB Package Verification Report - {pkg_basename}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
      color: #334155;
      background-color: #f8fafc;
      margin: 0;
      padding: 40px 20px;
      line-height: 1.6;
    }}
    .report-container {{
      max-width: 800px;
      margin: 0 auto;
      background: #ffffff;
      border-radius: 16px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.05);
      padding: 36px;
      border: 1px solid #f1f5f9;
    }}
    h1 {{
      font-size: 26px;
      margin-top: 0;
      margin-bottom: 24px;
      color: #0f172a;
      border-bottom: 2px solid #e2e8f0;
      padding-bottom: 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .meta-info {{
      background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
      border-radius: 12px;
      padding: 18px 24px;
      margin-bottom: 28px;
      border-left: 5px solid #3b82f6;
    }}
    .meta-info p {{
      margin: 6px 0;
      font-size: 14px;
      color: #475569;
    }}
    .meta-info strong {{
      color: #0f172a;
    }}
    .status-badge {{
      display: inline-block;
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 600;
    }}
    .status-badge.pass {{
      background-color: #dcfce7;
      color: #15803d;
    }}
    .status-badge.warn {{
      background-color: #fef9c3;
      color: #a16207;
    }}
    .status-badge.fail {{
      background-color: #fee2e2;
      color: #b91c1c;
    }}
    .summary-table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 36px;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid #e2e8f0;
    }}
    .summary-table th, .summary-table td {{
      padding: 14px 18px;
      text-align: left;
      font-size: 14px;
    }}
    .summary-table th {{
      background-color: #f1f5f9;
      color: #475569;
      font-weight: 600;
    }}
    .summary-table td {{
      border-bottom: 1px solid #f1f5f9;
      color: #0f172a;
    }}
    .summary-table tr:last-child td {{
      border-bottom: none;
    }}
    .section-card {{
      margin-bottom: 28px;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
    }}
    .section-header {{
      background-color: #f8fafc;
      padding: 16px 24px;
      border-bottom: 1px solid #e2e8f0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-weight: bold;
      font-size: 16px;
      color: #0f172a;
    }}
    .section-body {{
      padding: 20px 24px;
      background-color: #fff;
    }}
    .desc-text {{
      font-size: 13.5px;
      color: #64748b;
      margin-bottom: 14px;
      background-color: #f8fafc;
      padding: 10px 16px;
      border-radius: 6px;
      border: 1px solid #f1f5f9;
    }}
    .item-list {{
      list-style: none;
      padding: 0;
      margin: 0;
    }}
    .item-list li {{
      padding: 10px 0;
      font-size: 14px;
      display: flex;
      align-items: flex-start;
      border-bottom: 1px solid #f1f5f9;
    }}
    .item-list li:last-child {{
      border-bottom: none;
    }}
    .item-icon {{
      margin-right: 12px;
      font-size: 16px;
      line-height: 1.2;
    }}
    .item-name {{
      font-weight: 600;
      color: #0f172a;
      margin-right: 8px;
    }}
    .item-arrow {{
      color: #94a3b8;
      margin-right: 8px;
    }}
    .item-msg {{
      color: #334155;
    }}
    .reverse-card {{
      border: 1px solid #fee2e2;
      border-radius: 12px;
      margin-top: 40px;
      overflow: hidden;
      box-shadow: 0 4px 6px -1px rgba(220, 38, 38, 0.02);
    }}
    .reverse-header {{
      background-color: #fef2f2;
      color: #991b1b;
      padding: 16px 24px;
      border-bottom: 1px solid #fca5a5;
      font-weight: bold;
      font-size: 16px;
    }}
    .reverse-body {{
      padding: 20px 24px;
      background-color: #fff;
    }}
    .reverse-folder {{
      margin-bottom: 20px;
    }}
    .reverse-folder:last-child {{
      margin-bottom: 0;
    }}
    .reverse-folder-title {{
      font-weight: 600;
      color: #1f2937;
      font-size: 14.5px;
      margin-bottom: 8px;
      border-bottom: 1px solid #f9fafb;
      padding-bottom: 4px;
    }}
    .reverse-folder-files {{
      list-style: none;
      padding-left: 20px;
      margin: 0;
    }}
    .reverse-folder-files li {{
      font-size: 13.5px;
      color: #4b5563;
      padding: 4px 0;
      position: relative;
    }}
    .reverse-folder-files li::before {{
      content: "•";
      color: #ef4444;
      font-weight: bold;
      display: inline-block;
      width: 1em;
      margin-left: -1em;
    }}
  </style>
</head>
<body>
  <div class="report-container">
    <h1>
      <span>SPB Package Verification Report</span>
      <span class="status-badge {status_class}">{status_text}</span>
    </h1>

    <div class="meta-info">
      <p><strong>Package Directory:</strong> <code>{pkg_basename}</code></p>
      <p><strong>Reference File:</strong> <code>{file_basename}</code></p>
      <p><strong>System Type:</strong> <code>{system_type.upper()}</code></p>
    </div>

    <h2>Summary</h2>
    <table class="summary-table">
      <thead>
        <tr>
          <th>Category</th>
          <th>Count</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Passed Checks</td>
          <td>{summary['passed']}</td>
          <td>🟢</td>
        </tr>
        <tr>
          <td>Warnings</td>
          <td>{summary['warnings']}</td>
          <td>🟡</td>
        </tr>
        <tr>
          <td>Errors</td>
          <td>{summary['errors']}</td>
          <td>🔴</td>
        </tr>
      </tbody>
    </table>

    <h2>Verification Details</h2>
"""

    by_section = {}
    for item in report:
        sec = item['section']
        if sec not in by_section:
            by_section[sec] = []
        by_section[sec].append(item)

    section_titles = {
        'cli': '1. 客户端 CLI 核对',
        'dll': '2. 核心 DLL 核对',
        'table': '3. SQL 表结构核对',
        'proc': '4. 存储过程 (Proc) 核对',
        'init': '5. 初始化脚本 (Init) 核对',
        'upgraderemark': '6. 升级备注核对'
    }

    ordered_sections = ['cli', 'dll', 'table', 'proc', 'init', 'upgraderemark']
    for sec in ordered_sections:
        if sec not in by_section:
            continue
        items = by_section[sec]
        
        has_errors = any(i['status'] == 'FAIL' for i in items)
        has_warnings = any(i['status'] == 'WARN' for i in items)
        
        if has_errors:
            sec_status = f"🔴 {sum(1 for i in items if i['status'] == 'FAIL')} 项缺失"
            badge_class = "fail"
        elif has_warnings:
            sec_status = "🟡 存在警告"
            badge_class = "warn"
        else:
            sec_status = "🟢 全部通过"
            badge_class = "pass"
            
        title = section_titles.get(sec, f"{sec.upper()} 核对")
        html += f"""
    <!-- Section {sec} -->
    <div class="section-card">
      <div class="section-header">
        <span>{title}</span>
        <span class="status-badge {badge_class}">{sec_status}</span>
      </div>
      <div class="section-body">
"""
        if sec == 'dll':
            html += """        <div class="desc-text">以下 LBM 模块的 DLL 文件均已正确存放在 lbm/ 文件夹中：</div>\n"""
            
        html += """        <ul class="item-list">\n"""
        for item in items:
            symbol = "🟢" if item['status'] == 'PASS' else "🟡" if item['status'] == 'WARN' else "🔴"
            item_name = item.get('item_name') or ''
            if item_name:
                html += f"""          <li>
            <span class="item-icon">{symbol}</span>
            <span class="item-name">{item_name}</span>
            <span class="item-arrow">➔</span>
            <span class="item-msg">{item['message']}</span>
          </li>\n"""
            else:
                html += f"""          <li>
            <span class="item-icon">{symbol}</span>
            <span class="item-msg">{item['message']}</span>
          </li>\n"""
        html += """        </ul>\n      </div>\n    </div>\n"""

    # Reverse Audit
    has_extras = any(len(files) > 0 for files in extra_files.values())
    if has_extras:
        html += f"""
    <!-- Reverse Audit -->
    <div class="reverse-card">
      <div class="reverse-header">🟡 Reverse Audit (发现未在 excel_output.txt 中声明的额外文件)</div>
      <div class="reverse-body">
"""
        for folder, files in extra_files.items():
            if files:
                html += f"""        <div class="reverse-folder">
          <div class="reverse-folder-title">{folder}/ 目录:</div>
          <ul class="reverse-folder-files">
"""
                for f in files:
                    html += f"            <li>{f}</li>\n"
                html += """          </ul>\n        </div>\n"""
        html += """      </div>\n    </div>\n"""
    else:
        html += """
    <div class="section-card">
      <div class="section-header">
        <span>Reverse Audit</span>
        <span class="status-badge pass">🟢 无多余文件</span>
      </div>
      <div class="section-body">
        <p>未在包内发现未声明的额外文件。</p>
      </div>
    </div>
"""

    html += """
  </div>
</body>
</html>
"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[OK] HTML 报告 → {output_path}")

if __name__ == '__main__':
    main()
