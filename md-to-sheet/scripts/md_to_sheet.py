#!/usr/bin/env python3
"""
Obsidian 需求 MD 文件 批量写入 腾讯文档在线表格
有则更新，无则追加，默认仅读取当日文件，支持业务参数和模糊子表名匹配
"""

import argparse
import concurrent.futures
import csv
import datetime
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path



# ── 配置 ──────────────────────────────────────────────────────────────
# 引入公共 SDK
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_COMMON_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, '..', '..', 'common'))
if _COMMON_DIR not in sys.path:
    sys.path.append(_COMMON_DIR)

try:
    from sync_utils import (
        call_mcp, load_dept_map, get_path, get_biz_file_map,
        extract_systems, lcs_len, MDIndex, find_md_file
    )
    _HAS_SYNC_UTILS = True
except ImportError:
    _HAS_SYNC_UTILS = False

if not _HAS_SYNC_UTILS:
    DEFAULT_MD_DIR = "/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析/"
    DEFAULT_DEPT_CSV = "/Volumes/Macintosh HD_Data/WorkBuddy/会议纪要/人员部门对应关系表.csv"
    DEFAULT_FILE_ID = "TkOIzsYMsasb"
    MCP_PORTER_PATH = "/Users/wujin/.npm-global/bin/mcporter"

    def call_mcp(tool_name: str, args: dict) -> dict:
        cmd = [MCP_PORTER_PATH, "call", "tencent-docs", tool_name, "--args", json.dumps(args)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise Exception(f"MCP 调用失败 (工具: {tool_name}):\nError: {res.stderr}\nOutput: {res.stdout}")
        try:
            return json.loads(res.stdout)
        except json.JSONDecodeError:
            raise Exception(f"MCP 返回的数据无法解析为 JSON:\n{res.stdout}")

    def load_dept_map(csv_path: str) -> dict:
        dept_map = {}
        if not csv_path or not Path(csv_path).is_file():
            return dept_map
        try:
            text = Path(csv_path).read_text(encoding='utf-8')
            reader = csv.reader(io.StringIO(text))
            next(reader)
            for line in reader:
                if len(line) < 2: continue
                name, dept = line[0].strip(), line[1].strip()
                if name and dept: dept_map[name] = dept
        except Exception as e:
            print(f"⚠️  加载部门映射失败: {e}", file=sys.stderr)
        return dept_map
else:
    DEFAULT_MD_DIR = get_path("md_dir_md_to_sheet", "/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析/")
    DEFAULT_DEPT_CSV = get_path("dept_csv", "/Volumes/Macintosh HD_Data/WorkBuddy/会议纪要/人员部门对应关系表.csv")
    DEFAULT_FILE_ID = "TkOIzsYMsasb"

# ── 文本提取与解析 ──────────────────────────────────────────────────────
def parse_md_file(file_path: Path, dept_map: dict[str, str]) -> dict:
    """解析单个 MD 文件，提取字段"""
    content = file_path.read_text(encoding='utf-8')
    
    # 1. 提出日期与需求名称（从文件名）
    # 格式：YYYYMMDD-需求-【系统名】需求标题.md 或 YYYYMMDD-需求-需求标题.md
    filename = file_path.name
    date_match = re.match(r'^(\d{8})-需求-', filename)
    if not date_match:
        raise ValueError(f"文件名不符合规范 (必须为 YYYYMMDD-需求-...): {filename}")
    
    raw_date = date_match.group(1)
    formatted_date = f"{raw_date[:4]}/{int(raw_date[4:6])}/{int(raw_date[6:8])}"
    
    # 需求名称：文件名中 需求- 后的部分（去掉扩展名）
    name = filename[date_match.end():].replace('.md', '').strip()
    
    # 2. 提取需求描述（一、需求背景 + 二、需求内容）
    bg_match = re.search(r'####\s*\*\*?[一二三四五六七八九十]+、\s*需求背景\*\*?', content)
    content_match = re.search(r'####\s*\*\*?[原基二三四五六七八九十]+、\s*需求内容\*\*?', content)  # 兼容"二、需求内容"
    # 如果没匹配到，可以用更宽泛的正则
    if not content_match:
        content_match = re.search(r'####\s*\*\*?[一二三四五六七八九十]+、\s*需求内容\*\*?', content)
    
    bg_text = ""
    content_text = ""
    if bg_match and content_match:
        bg_start = bg_match.end()
        bg_end = content_match.start()
        bg_text = content[bg_start:bg_end].strip()
        
        content_start = content_match.end()
        next_matches = []
        for m in re.finditer(r'(####\s*\*\*?[一二三四五六七八九十]+、|---|##\s+)', content):
            if m.start() > content_start:
                next_matches.append(m.start())
        content_end = min(next_matches) if next_matches else len(content)
        content_text = content[content_start:content_end].strip()
        
    description = f"一、需求背景\n{bg_text}\n\n二、需求内容\n{content_text}"
    
    # 3. 涉及系统
    systems_list = []
    # 扫描整个内容中的系统关键字
    if "低延时" in content or "低延迟" in content:
        systems_list.append("低延时")
    if "集中交易" in content or "交易系统" in content:
        systems_list.append("集中交易")
    if "参数中心" in content or "参数系统" in content or "参数" in content:
        systems_list.append("参数中心")
    if "清算" in content:
        systems_list.append("集中清算")
    if "核心98" in content or "98节点" in content or "98交易节点" in content:
        systems_list.append("核心98节点")
        
    systems = "\n".join(systems_list)
    
    # 4. 关联系统
    related_match = re.search(r'关联系统[：:]\s*(.+)', content)
    related = related_match.group(1).strip() if related_match else ""
    
    # 5. 计划排期
    schedule_match = re.search(r'预计完成时间[：:]\s*计划\s*(\d{4}年)?(\d{1,2})月', content)
    if schedule_match:
        schedule = f"{int(schedule_match.group(2))}月份"
    else:
        schedule = ""
        
    # 6. 评审状态与参会人员 (从评审纪要)
    review_match = re.search(r'####\s*\*\*?评审纪要\*\*?', content)
    review_status = "待评审"
    attendees = ""
    
    if review_match:
        review_text = content[review_match.end():].strip()
        first_line = review_text.split('\n')[0].strip() if review_text else ""
        
        # 校验是否含有占位符如 [部门名称A] [人员X] 等
        has_placeholders = "[" in first_line and "]" in first_line
        if not has_placeholders and "沟通评审通过" in first_line:
            review_status = "通过"
            
        # 提取真实姓名
        found_names = []
        for emp_name in dept_map.keys():
            pos = first_line.find(emp_name)
            if pos != -1:
                found_names.append((pos, emp_name))
        found_names.sort()
        attendees = "\n".join([name for pos, name in found_names])

    # 7. 需求链接
    link_match = re.search(r'https://fintech\.gtht\.com\.cn/kjpt/DemandManage/details\?demandId=(R\d+)', content)
    if link_match:
        demand_id = link_match.group(1)
        link = f"https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId={demand_id}&templateId=8888&flag=1"
    else:
        id_match = re.search(r'R\d{10}', content)
        if id_match:
            link = f"https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId={id_match.group(0)}&templateId=8888&flag=1"
        else:
            link = ""
            
    return {
        "date": formatted_date,
        "name": name,
        "description": description,
        "systems": systems,
        "related": related,
        "schedule": schedule,
        "review_status": review_status,
        "link": link,
        "attendees": attendees
    }

def match_month_to_sheet(month_str: str, sheet_names: list[str]) -> str | None:
    """匹配月份（如 202606）到子表名称（如 202606, 2026006, 2026-06 等）"""
    m = re.match(r'^(\d{4})(\d{2})$', month_str)
    if not m:
        return None
    year, month = m.group(1), m.group(2)
    
    # 精确匹配
    if month_str in sheet_names:
        return month_str
        
    # 模糊匹配
    for s in sheet_names:
        s_match = re.match(r'^(\d{4})0*(\d{1,2})$', s)
        if s_match:
            s_year, s_month = s_match.group(1), s_match.group(2)
            if s_year == year and int(s_month) == int(month):
                return s

    return None

def get_biz_type(filename: str, content: str) -> str:
    """根据文件名 and 内容智能识别业务类型: gpzy (股票质押), rzrq (融资融券) 或 qt (其他)"""
    full_text = (filename + "\n" + content).lower()
    if "质押" in full_text or "股质" in full_text or "gpzy" in full_text:
        return "gpzy"
    if "两融" in full_text or "融资融券" in full_text or "融券" in full_text or "rzrq" in full_text:
        return "rzrq"
    return "qt"

# ── 主流程 ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Obsidian 需求 MD 文件 批量写入 腾讯文档在线表格")
    parser.add_argument("biz", nargs="?", default="rzrq", choices=["rzrq", "gpzy", "qt"], help="业务类型: rzrq (融资融券), gpzy (股票质押) 或 qt (其他)，默认为 rzrq")
    parser.add_argument("--md-dir", default=DEFAULT_MD_DIR, help="Obsidian MD需求文档目录")
    parser.add_argument("--file-id", help="腾讯文档表格 File ID (不指定时根据 biz 参数自动映射)")
    parser.add_argument("--dept-csv", default=DEFAULT_DEPT_CSV, help="人员部门对应关系表路径")
    parser.add_argument("--dry-run", action="store_true", help="只预览解析结果，不写入在线表格")
    parser.add_argument("--date", help="指定要读取的需求文件日期 (格式 YYYYMMDD)，若为 'all' 则读取所有，不指定则默认仅读取当日")
    args = parser.parse_args()

    biz_file_map = get_biz_file_map() if _HAS_SYNC_UTILS else {
        "rzrq": "DVGtPSXpzWU1zYXNi",
        "gpzy": "DVEtyb05taEFDc0xL",
        "qt": "DVE9Gb0daTmtzUE9H"
    }
    file_id = args.file_id if args.file_id else biz_file_map[args.biz]

    md_dir_path = Path(args.md_dir)
    if not md_dir_path.is_dir():
        print(f"❌ 本地 MD 目录不存在: {args.md_dir}", file=sys.stderr)
        sys.exit(1)

    target_date = args.date
    if not target_date:
        target_date = datetime.date.today().strftime('%Y%m%d')
        print(f"📅 未指定日期，默认只读取当日 ({target_date}) 的需求文件")
    elif target_date.lower() == 'all':
        print("📅 指定日期为 'all'，将读取所有需求文件")
        target_date = None
    else:
        print(f"📅 指定读取日期: {target_date}")

    print("📋 加载人员部门对应关系表...")
    dept_map = load_dept_map(args.dept_csv)
    print(f"   已加载 {len(dept_map)} 条映射记录")

    # 1. 获取在线表格子表列表
    print(f"📡 正在获取在线表格结构 ({file_id})...")
    try:
        sheet_info = call_mcp("sheet.get_sheet_info", {"file_id": file_id})
    except Exception as e:
        print(f"❌ 无法连接到腾讯文档或获取表格结构:\n{e}", file=sys.stderr)
        sys.exit(1)

    sheets = sheet_info.get("sheets", [])
    if not sheets:
        print("❌ 未在目标表格中找到子表", file=sys.stderr)
        sys.exit(1)

    sheet_map = {s["sheet_name"]: s for s in sheets}
    print(f"   已找到子表: {', '.join(sheet_map.keys())}")

    # 2. 扫描 MD 需求文档并分类（优化：若指定特定日期，直接精确查找目标日期文件）
    print(f"🔍 扫描目录: {args.md_dir} (过滤业务类型: {args.biz}) ...")
    if target_date:
        md_files = list(md_dir_path.glob(f"{target_date}-需求-*.md"))
    else:
        md_files = list(md_dir_path.glob("*.md"))
    
    # 提取有效需求 MD 文件
    valid_demands = []
    for f in md_files:
        if not re.match(r'^\d{8}-需求-', f.name):
            continue
        try:
            content = f.read_text(encoding='utf-8')
            biz_type = get_biz_type(f.name, content)
            if biz_type != args.biz:
                continue
                
            parsed = parse_md_file(f, dept_map)
            # 月份用于匹配子表，如 20260602 -> 202606
            month_prefix = f.name[:6]
            parsed["month"] = month_prefix
            parsed["file_path"] = f
            valid_demands.append(parsed)
        except Exception as e:
            print(f"⚠️  解析文件 {f.name} 失败: {e}", file=sys.stderr)

    if not valid_demands:
        print(f"ℹ️  未找到任何符合 YYYYMMDD-需求-... 格式且业务类型为 {args.biz} 的 MD 文件")
        sys.exit(0)

    print(f"   共解析出 {len(valid_demands)} 个有效需求文档")

    # 3. 按子表（月份）分组处理
    grouped_demands = {}
    for d in valid_demands:
        grouped_demands.setdefault(d["month"], []).append(d)

    for month, demands in grouped_demands.items():
        print(f"\n📁 正在处理月份: {month} ...")
        target_sheet_name = match_month_to_sheet(month, sheet_map.keys())
        if not target_sheet_name:
            print(f"📡 子表 '{month}' 不存在，正在自动创建并初始化表头...")
            try:
                # 1. 创建子表
                add_res = call_mcp("sheet.add_sheet", {"file_id": file_id, "name": month})
                sheet_id = add_res.get("sheet_id")
                if not sheet_id:
                    raise Exception(f"创建子表失败，未返回 sheet_id: {add_res}")
                
                # 2. 获取默认表头
                headers = ["提出日期", "优先级", "需求链接", "需求名称", "需求描述", "涉及系统", "关联系统", "计划排期", "story拆分", "评审状态", "备注", "参会人员"]
                if sheets:
                    first_existing_sheet = sheets[0]
                    try:
                        header_res = call_mcp("sheet.get_cell_data", {
                            "file_id": file_id,
                            "sheet_id": first_existing_sheet["sheet_id"],
                            "start_row": 0,
                            "end_row": 0,
                            "start_col": 0,
                            "end_col": 12,
                            "return_csv": True
                        })
                        csv_text = header_res.get("csv_data", "")
                        if csv_text:
                            # 分割CSV格式表头
                            import csv as csv_parser
                            csv_reader = csv_parser.reader(io.StringIO(csv_text))
                            extracted_headers = next(csv_reader)
                            if len(extracted_headers) >= 11:
                                headers = [h.strip() for h in extracted_headers[:12]]
                    except Exception as he:
                        print(f"⚠️  读取默认子表表头失败，使用硬编码表头: {he}")
                
                # 3. 写入表头数据
                values = [{"row": 0, "col": idx, "value_type": "STRING", "string_value": h} for idx, h in enumerate(headers)]
                call_mcp("sheet.set_range_value", {"file_id": file_id, "sheet_id": sheet_id, "values": values})
                
                # 4. 设置表头样式
                call_mcp("sheet.set_cell_style", {
                    "file_id": file_id,
                    "sheet_id": sheet_id,
                    "start_row": 0,
                    "end_row": 0,
                    "start_col": 0,
                    "end_col": 11,
                    "bold": True,
                    "horizontal_align": "center",
                    "vertical_align": "center",
                    "bg_color": "FFF2F2F2"
                })
                
                target_sheet_name = month
                row_count = 1
                print(f"   已成功创建并初始化子表 '{month}'")
            except Exception as e:
                print(f"❌ 自动创建子表 '{month}' 失败:\n{e}", file=sys.stderr)
                continue
        else:
            target_sheet = sheet_map[target_sheet_name]
            sheet_id = target_sheet["sheet_id"]
            row_count = target_sheet["row_count"]


        # 读取已有行数据用于去重 and 确定写入行数
        print(f"📡 读取子表 '{target_sheet_name}' 数据进行去重...")
        try:
            cell_data = call_mcp("sheet.get_cell_data", {
                "file_id": file_id,
                "sheet_id": sheet_id,
                "start_row": 0,
                "end_row": row_count,
                "start_col": 0,
                "end_col": 12,
                "return_csv": True
            })
        except Exception as e:
            print(f"❌ 读取子表数据失败:\n{e}", file=sys.stderr)
            continue

        csv_text = cell_data.get("csv_data", "")
        reader = csv.reader(io.StringIO(csv_text))
        existing_rows = list(reader)

        # 整理已有需求名称 (C列/Col 3是需求名称) -> 映射为 {名称: (行索引, 行数据)}
        existing_names_map = {}
        first_empty_row = len(existing_rows)

        # 检查第一行空行并提取已有需求
        for idx, r in enumerate(existing_rows):
            if idx == 0:
                continue # 跳过表头
            # 补足列数避免索引溢出
            while len(r) < 12:
                r.append('')
            
            name_val = r[3].strip()
            if name_val:
                existing_names_map[name_val] = (idx, r)
            
            # 找到第一个全空的行作为新行开始写入
            if not r[0].strip() and not r[3].strip():
                if idx < first_empty_row:
                    first_empty_row = idx

        print(f"   已有记录数: {len(existing_names_map)}，第一个空行位置: {first_empty_row}")

        # 进行写入
        added_count = 0
        updated_count = 0
        new_row_index = first_empty_row

        all_values_payload = []
        ops_data = []

        for d in demands:
            name = d["name"]
            
            # 判断是更新还是追加
            is_update = name in existing_names_map
            if is_update:
                target_row_index, existing_row_data = existing_names_map[name]
                print(f"🔄 [{name}]: 表格中已存在，准备更新行 {target_row_index}...")
                
                # 保留已有的 优先级、story拆分、备注(K列)、参会人员(L列) 字段，避免覆盖人工修改
                priority = existing_row_data[1].strip() or "正常"
                story = existing_row_data[8].strip() or "否"
                remark = existing_row_data[10].strip()
                attendees = existing_row_data[11].strip()
                updated_count += 1
            else:
                target_row_index = new_row_index
                new_row_index += 1
                priority = "正常"
                story = "否"
                remark = ""
                attendees = d["attendees"]
                print(f"➕ [{name}]: 表格中不存在，准备追加到行 {target_row_index}...")
                added_count += 1

            if args.dry_run:
                action_str = "[Dry Run - 更新]" if is_update else "[Dry Run - 追加]"
                print(f"   {action_str} 预览数据:")
                print(f"     目标行号: {target_row_index}")
                print(f"     提出日期: {d['date']}")
                print(f"     涉及系统:\n{d['systems']}")
                print(f"     计划排期: {d['schedule']}")
                print(f"     评审状态: {d['review_status']}")
                print(f"     需求链接: {d['link']}")
                print(f"     参会人员:\n{attendees}")
                continue

            # 收集单元格数据
            all_values_payload.extend([
                {"row": target_row_index, "col": 0, "value_type": "STRING", "string_value": d["date"]},
                {"row": target_row_index, "col": 1, "value_type": "STRING", "string_value": priority},
                {"row": target_row_index, "col": 3, "value_type": "STRING", "string_value": d["name"]},
                {"row": target_row_index, "col": 4, "value_type": "STRING", "string_value": d["description"]},
                {"row": target_row_index, "col": 5, "value_type": "STRING", "string_value": d["systems"]},
                {"row": target_row_index, "col": 6, "value_type": "STRING", "string_value": d["related"]},
                {"row": target_row_index, "col": 7, "value_type": "STRING", "string_value": d["schedule"]},
                {"row": target_row_index, "col": 8, "value_type": "STRING", "string_value": story},
                {"row": target_row_index, "col": 9, "value_type": "STRING", "string_value": d["review_status"]},
                {"row": target_row_index, "col": 10, "value_type": "STRING", "string_value": remark},
                {"row": target_row_index, "col": 11, "value_type": "STRING", "string_value": attendees}
            ])

            ops_data.append({
                "row": target_row_index,
                "isUpdate": is_update,
                "link": d["link"],
                "description": d["description"]
            })

        if not args.dry_run and all_values_payload:
            # 1. 批量写入所有单元格数据 (合并为一个请求)
            print(f"   📡 正在批量写入单元格数据 ({len(all_values_payload)} 个单元格)...")
            try:
                call_mcp("sheet.set_range_value", {
                    "file_id": file_id,
                    "sheet_id": sheet_id,
                    "values": all_values_payload
                })
            except Exception as e:
                print(f"❌ 批量写入单元格数据失败: {e}", file=sys.stderr)
                continue

            # 2. 批量并发设置超链接 (使用 ThreadPoolExecutor 提升速度)
            links_to_set = [op for op in ops_data if op["link"]]
            if links_to_set:
                print(f"   📡 正在并发设置 {len(links_to_set)} 个 C列 超链接...")
                def set_single_link(op):
                    try:
                        call_mcp("sheet.set_link", {
                            "file_id": file_id,
                            "sheet_id": sheet_id,
                            "row": op["row"],
                            "col": 2,
                            "url": op["link"],
                            "display_text": op["link"]
                        })
                        return True, op["row"]
                    except Exception as e:
                        return False, f"行 {op['row']}: {e}"

                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    results = list(executor.map(set_single_link, links_to_set))
                
                for success, res in results:
                    if not success:
                        print(f"⚠️ 设置超链接失败: {res}", file=sys.stderr)

            # 3. 批量同步样式和背景色
            if ops_data:
                min_row = min(op["row"] for op in ops_data)
                max_row = max(op["row"] for op in ops_data)
                
                print(f"   📡 正在批量设置行 {min_row} 至 {max_row} 的垂直居中与自动换行...")
                try:
                    call_mcp("sheet.set_cell_style", {
                        "file_id": file_id,
                        "sheet_id": sheet_id,
                        "start_row": min_row,
                        "end_row": max_row,
                        "start_col": 0,
                        "end_col": 11,
                        "vertical_align": "center",
                        "wrap_text": True
                    })
                except Exception as e:
                    print(f"⚠️ 批量设置自动换行与居中失败: {e}", file=sys.stderr)

                print(f"   📡 正在批量设置行 {min_row} 至 {max_row} 的 Column C 蓝色下划线链接样式...")
                try:
                    call_mcp("sheet.set_cell_style", {
                        "file_id": file_id,
                        "sheet_id": sheet_id,
                        "start_row": min_row,
                        "end_row": max_row,
                        "start_col": 2,
                        "end_col": 2,
                        "horizontal_align": "left",
                        "vertical_align": "center",
                        "font_color": "FF1A73E8",
                        "underline": "single"
                    })
                except Exception as e:
                    print(f"⚠️ 批量设置 Column C 样式失败: {e}", file=sys.stderr)



                print(f"   📡 正在批量设置行 {min_row} 至 {max_row} 的 Column E 顶端对齐与底色...")
                try:
                    call_mcp("sheet.set_cell_style", {
                        "file_id": file_id,
                        "sheet_id": sheet_id,
                        "start_row": min_row,
                        "end_row": max_row,
                        "start_col": 4,
                        "end_col": 4,
                        "vertical_align": "top",
                        "horizontal_align": "left",
                        "bg_color": "FFFFF9E3",
                        "wrap_text": True
                    })
                except Exception as e:
                    print(f"⚠️ 批量设置 Column E 样式失败: {e}", file=sys.stderr)



                # 4. 根据需求描述行数自适应计算并批量设置行高（解决新追加/更新行 E列文本被裁剪问题）
                row_dims = []
                for op in ops_data:
                    desc_text = op.get("description", "")
                    line_count = sum(max(1, (len(l) // 38) + 1) for l in desc_text.split("\n"))
                    calculated_height = max(50, min(500, line_count * 18 + 25))
                    row_dims.append({
                        "dimension_type": "row",
                        "index": op["row"],
                        "size": calculated_height
                    })
                
                if row_dims:
                    print(f"   📡 正在批量调整行高 ({len(row_dims)} 行)...")
                    try:
                        call_mcp("sheet.set_dimension_size", {
                            "file_id": file_id,
                            "sheet_id": sheet_id,
                            "dimensions": row_dims
                        })
                    except Exception as e:
                        print(f"⚠️ 批量调整行高失败: {e}", file=sys.stderr)

        print(f"📊 月份 {month} 处理完毕: 追加 {added_count} 条记录, 更新 {updated_count} 条记录")

    print("\n🏁 所有处理已完成。")

if __name__ == "__main__":
    main()


