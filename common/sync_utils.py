#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sync Utils - sheet-to-md 与 md-to-sheet 共享工具模块
包含：
1. sync_config.json 配置加载
2. MCP 调用封装 (call_mcp)
3. 部门映射加载 (load_dept_map)
4. LCS 模糊匹配算法 (lcs_len)
5. MD 文件索引与模糊查找 (MDIndex)
"""

import csv
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path


# ── 配置加载 ─────────────────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).parent / "sync_config.json"
_CONFIG: dict = {}

def _load_config() -> dict:
    global _CONFIG
    if _CONFIG:
        return _CONFIG
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                _CONFIG = json.load(f)
        except Exception as e:
            print(f"[sync_utils] ⚠️ 无法加载 sync_config.json: {e}", file=sys.stderr)
    return _CONFIG

def get_config() -> dict:
    return _load_config()

def get_path(key: str, fallback: str = "") -> str:
    """从 sync_config.json 的 paths 段读取路径"""
    cfg = _load_config()
    return cfg.get("paths", {}).get(key, fallback)

def get_biz_file_map() -> dict:
    """从 sync_config.json 读取业务别名→文档ID映射"""
    cfg = _load_config()
    return cfg.get("biz_file_map", {})

def get_system_keywords() -> list:
    """从 sync_config.json 读取系统关键词列表"""
    cfg = _load_config()
    return cfg.get("system_keywords", [])

def get_match_stop_words() -> list:
    """从 sync_config.json 读取匹配停用词"""
    cfg = _load_config()
    return cfg.get("match_stop_words", [])


# ── MCP 调用工具 ──────────────────────────────────────────────────────────

def call_mcp(tool_name: str, args: dict, mcporter_path: str = None) -> dict:
    """通过 mcporter 调用 tencent-docs 的 MCP 工具"""
    if mcporter_path is None:
        mcporter_path = get_path("mcporter", "/Users/wujin/.npm-global/bin/mcporter")

    cmd = [
        mcporter_path,
        "call",
        "tencent-docs",
        tool_name,
        "--args",
        json.dumps(args)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise Exception(f"MCP 调用失败 (工具: {tool_name}):\nError: {res.stderr}\nOutput: {res.stdout}")

    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        raise Exception(f"MCP 返回的数据无法解析为 JSON:\n{res.stdout}")


# ── 部门映射 ────────────────────────────────────────────────────────────

def load_dept_map(csv_path: str = None) -> dict:
    """加载「人员部门对应关系表.csv」，返回 {人名: 部门} 映射。"""
    if csv_path is None:
        csv_path = get_path("dept_csv", "")

    dept_map = {}
    if not csv_path or not Path(csv_path).is_file():
        return dept_map

    try:
        text = Path(csv_path).read_text(encoding='utf-8')
        reader = csv.reader(io.StringIO(text))
        try:
            next(reader)  # 跳过表头
        except StopIteration:
            return dept_map

        for line in reader:
            if len(line) < 2:
                continue
            name = line[0].strip()
            dept = line[1].strip()
            if name and dept:
                dept_map[name] = dept
    except Exception as e:
        print(f"⚠️  加载部门映射失败: {e}", file=sys.stderr)
    return dept_map


# ── LCS 模糊匹配 ─────────────────────────────────────────────────────────

def lcs_len(s1: str, s2: str) -> int:
    """最长公共子串长度（动态规划）"""
    m = [[0] * (len(s2) + 1) for _ in range(len(s1) + 1)]
    longest = 0
    for i in range(len(s1)):
        for j in range(len(s2)):
            if s1[i] == s2[j]:
                m[i+1][j+1] = m[i][j] + 1
                if m[i+1][j+1] > longest:
                    longest = m[i+1][j+1]
    return longest


# ── MD 文件索引与查找 ──────────────────────────────────────────────────────

class MDIndex:
    """MD 文件全量索引与预计算缓存类，彻底避免重复全盘 IO 与正则反复计算"""
    def __init__(self, md_dir: str):
        self.base = Path(md_dir)
        if not self.base.is_dir():
            self.entries = []
            return

        files = sorted(list(self.base.glob("**/*.md")), key=lambda x: x.name, reverse=True)
        self.entries = []
        for f in files:
            c_all = self._clean_all(f.name)
            c_match = self._clean_for_match(f.name)
            self.entries.append((f, f.name, c_all, c_match, set(c_match)))

    @staticmethod
    def _clean_all(s: str) -> str:
        return re.sub(r'[【】\[\]\(\)\{\}\s\-—_、，。,.:：]', '', s).lower()

    @staticmethod
    def _clean_for_match(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r'^\d{8}', '', s)
        s = re.sub(r'【.+?】', '', s)
        s = re.sub(r'\[.+?\]', '', s)
        for p in get_match_stop_words():
            s = s.replace(p, '')
        s = re.sub(r'[\s\-—_、，。,.:：【】\[\]\(\)\{\}]', '', s)
        return s

    def find(self, req_name: str) -> Path | None:
        name = req_name.strip()
        if not name or not self.entries:
            return None

        # 1. 精确包含匹配
        for f, fname, _, _, _ in self.entries:
            if name in fname:
                return f

        # 2. 移除标点后包含匹配
        clean_name_val = self._clean_all(name)
        for f, _, c_all, _, _ in self.entries:
            if clean_name_val in c_all or c_all in clean_name_val:
                return f

        # 3. LCS + 字符重叠率评分
        q_stripped = self._clean_for_match(name)
        if not q_stripped:
            return None

        q_set = set(q_stripped)
        best_file = None
        best_lcs = 0
        best_overlap = 0

        for f, _, _, f_stripped, f_set in self.entries:
            lcs = lcs_len(q_stripped, f_stripped)
            overlap = len(q_set & f_set)

            if lcs > best_lcs:
                best_lcs = lcs
                best_overlap = overlap
                best_file = f
            elif lcs == best_lcs and lcs > 0:
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_file = f

        if best_file and (best_lcs >= 3 or best_overlap >= 4):
            return best_file

        return None


_INDEX_CACHE: dict = {}

def get_md_index(md_dir: str) -> MDIndex:
    resolved = str(Path(md_dir).resolve())
    if resolved not in _INDEX_CACHE:
        _INDEX_CACHE[resolved] = MDIndex(md_dir)
    return _INDEX_CACHE[resolved]


def find_md_file(req_name: str, md_dir: str, index: MDIndex | None = None) -> Path | None:
    if index is None:
        index = get_md_index(md_dir)
    return index.find(req_name)


# ── 系统关键词提取 ─────────────────────────────────────────────────────────

def extract_systems(content: str) -> list:
    """从文本内容中提取涉及的系统列表（基于 sync_config.json 的 system_keywords 配置）"""
    systems = []
    for item in get_system_keywords():
        for kw in item["keywords"]:
            if kw in content:
                systems.append(item["label"])
                break
    return systems
