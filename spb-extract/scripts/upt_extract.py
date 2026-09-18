# -*- coding: utf-8 -*-
"""
SPB版本升级包内容提取模板
用法：python upt_extract.py <版本文件夹路径>
用法：python upt_extract.py <快捷名称> [版本号]
快捷名称：jzjy, cszx
示例：
  python upt_extract.py "D:\\WorkFiles\\2001 版本发布\\集中交易\\autotools\\SPB_V2.2.19_20260515"
  python upt_extract.py jzjy
  python upt_extract.py jzjy 20260529
  python upt_extract.py cszx 20260529_hoth
"""

import os
import sys
import glob


def resolve_path(name, ver=None):
    """根据快捷名称+版本号解析为实际目录路径"""
    base = os.path.dirname(os.path.abspath(__name__))

    mapping = {
        'jzjy': {'parent': 'jzjy', 'prefixes': ['SPB-V0.26.', 'SPB_V2.2.19_']},
        'cszx': {'parent': 'jygl', 'prefixes': ['CSZX-']},
    }

    name_lower = name.lower()
    if name_lower not in mapping:
        # 当作直接路径
        return os.path.abspath(name)

    parent = mapping[name_lower]['parent']
    prefixes = mapping[name_lower]['prefixes']
    parent_dir = os.path.join(base, parent)

    if not os.path.isdir(parent_dir):
        print(f"错误：父目录不存在 {parent_dir}")
        sys.exit(1)

    if ver:
        # 依次尝试每个前缀
        for prefix in prefixes:
            target = os.path.join(parent_dir, prefix + ver)
            if os.path.isdir(target):
                return os.path.abspath(target)
        print(f"错误：未找到匹配目录（尝试了以下前缀）")
        for prefix in prefixes:
            target = os.path.join(parent_dir, prefix + ver)
            print(f"  {target}")
        # 列出所有匹配项提示
        all_matches = []
        for prefix in prefixes:
            all_matches.extend(glob.glob(os.path.join(parent_dir, prefix + '*')))
        dirs = [d for d in all_matches if os.path.isdir(d)]
        if dirs:
            print("匹配到的目录：")
            for d in sorted(set(dirs)):
                print(f"  {d}")
        sys.exit(1)
    else:
        # 无参数，找唯一一个匹配的文件夹（遍历所有前缀）
        all_dirs = []
        for prefix in prefixes:
            pattern = os.path.join(parent_dir, prefix + '*')
            matches = glob.glob(pattern)
            dirs = [d for d in matches if os.path.isdir(d)]
            all_dirs.extend(dirs)
        all_dirs = sorted(set(all_dirs))
        if len(all_dirs) == 1:
            return os.path.abspath(all_dirs[0])
        elif len(all_dirs) == 0:
            print(f"错误：未找到匹配目录（尝试了以下前缀）")
            for prefix in prefixes:
                print(f"  {os.path.join(parent_dir, prefix + '*')}")
            sys.exit(1)
        else:
            print(f"错误：匹配到多个目录 {len(all_dirs)} 个，请指定版本号参数")
            for d in all_dirs:
                print(f"  {d}")
            sys.exit(1)


def get_files(dir_path, ext_filter=None, prefix_filter=None):
    """获取目录下的文件，支持后缀和前缀过滤"""
    if not os.path.isdir(dir_path):
        return []
    files = [f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))]
    if ext_filter:
        files = [f for f in files if f.lower().endswith(ext_filter)]
    if prefix_filter:
        files = [f for f in files if f.startswith(prefix_filter)]
    return sorted(files)


def section(title, files_text, location, method, note=None, is_cszx=False):
    """构建一个分类段落的行列表"""
    if is_cszx:
        sys_name = '交易参数管理后台系统'
        cmdb_group = '交易参数管理后台系统'
        # Determine the cszx location based on title
        if title in ['lbm', 'init2', 'init3', 'memlbm', 'client', 'adaptor']:
            location = 'ZJJ1,ZJJ2'
        elif title in ['init1', 'table', 'proc', 'proc1', 'proc2']:
            location = '参数中心主库，参数中心备库'

        # Special customization for table section in cszx
        if title == 'table':
            if note:
                if '按目录下脚本序号执行' not in note:
                    note = f'按目录下脚本序号执行；{note}'
            else:
                note = '按目录下脚本序号执行'
    else:
        sys_name = '主系统'
        cmdb_group = '集中交易系统'

    lines = [
        f'{title}:',
        f'主系统/灾备    {sys_name}',
        f'CMDB维护组名称 {cmdb_group}',
        f'变更文件     {files_text}',
        f'cmdb变更部位 不适用',
        f'变更部位   {location}',
        f'变更方式  {method}'
    ]
    if note:
        lines.append(f'备注         {note}')
    return lines


def generate(version_dir, is_cszx=False):
    """根据版本目录生成升级包内容文本"""
    current_dir = os.path.abspath(version_dir)
    if not os.path.isdir(current_dir):
        print(f"错误：目录不存在 {current_dir}")
        sys.exit(1)

    # Parse upgrade remarks from excel_output.txt in the parent directory
    remarks = {}
    parent_dir = os.path.dirname(current_dir)
    excel_output_path = os.path.join(parent_dir, 'excel_output.txt')
    if os.path.isfile(excel_output_path):
        try:
            with open(excel_output_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # Find the section starting with "# === 升级备注"
            # It ends at the next "# ===" or EOF
            import re
            match = re.search(r'# === 升级备注.*?\n(.*?)(?=\n# ===|\Z)', content, re.DOTALL)
            if match:
                section_content = match.group(1)
                for line in section_content.split('\n'):
                    line_str = line.strip()
                    if not line_str or line_str.startswith('#'):
                        continue
                    parts = line_str.split(None, 1)
                    if len(parts) == 2:
                        task_id, remark = parts
                        remarks[task_id.strip()] = remark.strip()
        except Exception as e:
            print(f"警告：读取或解析 excel_output.txt 失败: {e}")

    def get_note(title, files_text, default_note=None):
        matched = []
        for task_id, remark in remarks.items():
            if task_id in files_text:
                matched.append(remark)
        all_notes = []
        if default_note:
            all_notes.append(default_note)
        if matched:
            all_notes.extend(matched)
        return '；'.join(all_notes) if all_notes else None

    lines = []

    # ========== lbm ==========
    lbm_files = get_files(os.path.join(current_dir, 'lbm'), '.dll')
    if lbm_files:
        files_text = ' '.join(lbm_files)
        lines += section('lbm', files_text, '所有kcbp（包含公募基金）', '替换', note=get_note('lbm', files_text), is_cszx=is_cszx)
        lines.append('')

    # ========== table ==========
    table_files = get_files(os.path.join(current_dir, 'table'))
    if table_files:
        files_text = ' '.join(table_files) if is_cszx else 'table目录下文件'
        default_note = None if is_cszx else '按目录序号执行（1.bak_table、 2.build_table、3.trans_table、4.check_table）'
        lines += section('table', files_text, 'table 目录内脚本', 'SQL脚本',
                         note=get_note('table', ' '.join(table_files), default_note), is_cszx=is_cszx)
        lines.append('')

    # ========== init1 - .sql（排除 KafkaTriggerConfig）==========
    all_sql_files = get_files(os.path.join(current_dir, 'init'), '.sql')
    init1_files = [f for f in all_sql_files if not f.startswith('KafkaTriggerConfig')]
    if init1_files:
        files_text = ' '.join(init1_files)
        lines += section('init1', files_text, '所有核心、两个总控、VIP极速与融资融券1/2/3的run(包括公募', 'SQL脚本',
                         note=get_note('init1', files_text), is_cszx=is_cszx)
        lines.append('')

    # ========== init2 - .xml ==========
    init2_files = get_files(os.path.join(current_dir, 'init'), '.xml')
    if init2_files:
        files_text = ' '.join(init2_files)
        lines += section('init2', files_text, '所有kcbp(包含公募基金)', '新增',
                         note=get_note('init2', files_text), is_cszx=is_cszx)
        lines.append('')

    # ========== init3 - KafkaTriggerConfig .sql（触发器）==========
    kafka_files = [f for f in all_sql_files if f.startswith('KafkaTriggerConfig')]
    if kafka_files:
        files_text = ' '.join(kafka_files)
        lines += section('init3', files_text, '总控备库、两融备库和VIP备库', 'SQL脚本',
                         note=get_note('init3', files_text), is_cszx=is_cszx)
        lines.append('')

    # ========== init4 - .txt ==========
    init4_files = get_files(os.path.join(current_dir, 'init'), '.txt')
    if init4_files:
        files_text = ' '.join(init4_files)
        lines += section('init4', files_text, '路由配置', '新增',
                         note=get_note('init4', files_text), is_cszx=is_cszx)
        lines.append('')

    # ========== memlbm ==========
    memlbm_files = get_files(os.path.join(current_dir, 'memlbm'), '.dll')
    if memlbm_files:
        files_text = ' '.join(memlbm_files)
        lines += section('memlbm', files_text, '内存节点', '替换',
                         note=get_note('memlbm', files_text), is_cszx=is_cszx)
        lines.append('')

    # ========== client ==========
    client_files = get_files(os.path.join(current_dir, 'client'))
    client_filtered = [f for f in client_files if f.lower().endswith(('.dll', '.exe'))]
    if client_filtered:
        files_text = ' '.join(client_filtered)
        lines += section('client', files_text, '前台', '替换',
                         note=get_note('client', files_text), is_cszx=is_cszx)
        lines.append('')

    # ========== proc ==========
    if is_cszx:
        proc_files = get_files(os.path.join(current_dir, 'proc'), '.sql')
        if proc_files:
            files_text = ' '.join(proc_files)
            lines += section('proc', files_text, '参数中心主库，参数中心备库', 'SQL脚本',
                             note=get_note('proc', files_text), is_cszx=is_cszx)
            lines.append('')
    else:
        # ========== proc1 - PT_ ==========
        proc1_files = get_files(os.path.join(current_dir, 'proc'), '.sql', 'PT_')
        if proc1_files:
            files_text = ' '.join(proc1_files)
            lines += section('proc1', files_text, '所有核心、两个总控的run 与备份，包含公募基金核心和总控', 'SQL脚本',
                             note=get_note('proc1', files_text), is_cszx=is_cszx)
            lines.append('')

        # ========== proc2 - VIP_ ==========
        proc2_files = get_files(os.path.join(current_dir, 'proc'), '.sql', 'VIP_')
        if proc2_files:
            files_text = ' '.join(proc2_files)
            lines += section('proc2', files_text, 'VIP极速与融资融券1/2 /3的run与备份', 'SQL脚本',
                             note=get_note('proc2', files_text), is_cszx=is_cszx)
            lines.append('')

    # ========== adaptor ==========
    adaptor_files = get_files(os.path.join(current_dir, 'adaptor'))
    if adaptor_files:
        files_text = ' '.join(adaptor_files)
        lines += section('adaptor', files_text, '适配器升级', '替换',
                         note=get_note('adaptor', files_text), is_cszx=is_cszx)
        lines.append('')

    # 清理末尾空行
    while lines and lines[-1] == '':
        lines.pop()

    return '\n'.join(lines)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法：python upt_extract.py <版本文件夹路径>")
        print("用法：python upt_extract.py <快捷名称> [版本号]")
        print("快捷名称：jzjy, cszx")
        sys.exit(1)

    name = sys.argv[1]
    ver = sys.argv[2] if len(sys.argv) >= 3 else None

    version_dir = resolve_path(name, ver)
    
    # Determine if it is cszx mode
    is_cszx = False
    if name.lower() == 'cszx':
        is_cszx = True
    elif os.path.exists(version_dir):
        path_lower = version_dir.lower()
        if 'cszx' in path_lower or 'jygl' in path_lower:
            is_cszx = True

    result = generate(version_dir, is_cszx=is_cszx)

    # 写入 upt_content.txt 到版本目录下
    output_path = os.path.join(os.path.abspath(version_dir), 'upt_content.txt')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(result)
    print(f"已生成：{output_path}")

    # 写入 upt_content.txt 到当前目录下
    cwd_output_path = os.path.join(os.getcwd(), 'upt_content.txt')
    with open(cwd_output_path, 'w', encoding='utf-8') as f:
        f.write(result)
    print(f"已在当前目录生成：{cwd_output_path}")
    print(result)
