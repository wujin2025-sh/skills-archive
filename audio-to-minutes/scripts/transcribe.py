#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频转写辅助工具脚本
Audio Transcription Helper Script using OpenAI Whisper CLI
"""

import sys
import os
import subprocess
import argparse
import shutil
import json
import time
import hashlib

WHISPER_MODELS_URLS = {
    "tiny": (
        "https://openaipublic.azureedge.net/main/whisper/models/65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9/tiny.pt",
        "65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9"
    ),
    "base": (
        "https://openaipublic.azureedge.net/main/whisper/models/ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b0e6c6326e34e/base.pt",
        "ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b0e6c6326e34e"
    ),
    "small": (
        "https://openaipublic.azureedge.net/main/whisper/models/9ecf779972d90ba49c06d968637d72052a74c287a66758d21d32519a7d57d29f/small.pt",
        "9ecf779972d90ba49c06d968637d72052a74c287a66758d21d32519a7d57d29f"
    ),
    "turbo": (
        "https://openaipublic.azureedge.net/main/whisper/models/aff26ae408abcba5fbf8813c21e62b0941638c5f6eebfb145be0c9839262a19a/large-v3-turbo.pt",
        "aff26ae408abcba5fbf8813c21e62b0941638c5f6eebfb145be0c9839262a19a"
    )
}

def verify_file_sha256(filepath, expected_sha256):
    if not os.path.exists(filepath):
        return False
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                hasher.update(chunk)
        return hasher.hexdigest() == expected_sha256
    except Exception:
        return False

def ensure_model_file(model_name="small"):
    cache_dir = os.path.expanduser("~/.cache/whisper")
    os.makedirs(cache_dir, exist_ok=True)
    
    target_filename = "large-v3-turbo.pt" if model_name == "turbo" else f"{model_name}.pt"
    model_path = os.path.join(cache_dir, target_filename)
    
    if model_name not in WHISPER_MODELS_URLS:
        return model_path
        
    url, expected_sha = WHISPER_MODELS_URLS[model_name]
    
    if verify_file_sha256(model_path, expected_sha):
        print(f"Whisper 模型 [{model_name}] 校验完整，直接加载。")
        return model_path
        
    print(f"正在稳定下载 Whisper [{model_name}] 模型文件...")
    if os.path.exists(model_path):
        os.remove(model_path)
        
    # 使用 curl 支持断点续传与重试
    cmd = ["curl", "-L", "-C", "-", "--retry", "5", "--retry-delay", "2", url, "-o", model_path]
    res = subprocess.run(cmd)
    if res.returncode == 0 and verify_file_sha256(model_path, expected_sha):
        print(f"模型 [{model_name}] 下载并校验成功！")
        return model_path
    else:
        print(f"网络直接下载失败，尝试降级使用 tiny/base 模型...")
        return None

def find_whisper_executable():
    """查找 whisper 可执行文件位置"""
    candidates = [
        "/usr/local/bin/whisper",
        "/opt/homebrew/bin/whisper",
        shutil.which("whisper")
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return "whisper"

def find_today_audio(search_dir=None):
    """
    在指定目录（默认当前工作目录）下查找当日音频文件。
    优先查找今日修改的音频文件，找不到则选择最新修改的音频文件。
    """
    if search_dir is None:
        search_dir = os.getcwd()
    
    audio_extensions = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".wma"}
    today_str = time.strftime("%Y-%m-%d")
    
    candidates = []
    for root, dirs, files in os.walk(search_dir):
        # 忽略隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in audio_extensions:
                full_path = os.path.join(root, f)
                mtime = os.path.getmtime(full_path)
                mdate = time.strftime("%Y-%m-%d", time.localtime(mtime))
                candidates.append((full_path, mtime, mdate))
    
    if not candidates:
        return None
    
    # 过滤出今天的音频
    today_files = [c for c in candidates if c[2] == today_str]
    if today_files:
        # 按修改时间从新到旧排序
        today_files.sort(key=lambda x: x[1], reverse=True)
        return today_files[0][0]
    
    # 无今日音频时，退而求其次选择最新修改的音频文件
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]

def transcribe_audio(audio_path, model="small", language="Chinese", output_dir=None):
    """
    使用 whisper 将音频文件转写为文本
    """
    if not audio_path or audio_path.lower() in ("auto", "today", "current", ""):
        auto_found = find_today_audio()
        if not auto_found:
            raise FileNotFoundError("未在当前工作目录下找到任何音频文件（.m4a, .mp3, .wav等）")
        audio_path = auto_found
        print(f"自动选用音频文件: {audio_path}")

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    if output_dir is None:
        output_dir = os.path.join(os.path.expanduser("~"), ".cache", "audio_transcripts")
    os.makedirs(output_dir, exist_ok=True)

    # 预先确保模型已稳定下载且 SHA256 完整
    ensure_model_file(model)

    whisper_bin = find_whisper_executable()
    
    # 构造 whisper 命令
    cmd = [
        whisper_bin,
        audio_path,
        "--model", model,
        "--output_format", "txt",
        "--output_dir", output_dir,
    ]
    
    if language:
        cmd.extend(["--language", language])

    env = os.environ.copy()
    env["PATH"] = f"/usr/local/bin:/opt/homebrew/bin:{env.get('PATH', '')}"

    print(f"Executing: {' '.join(cmd)}")
    start_time = time.time()
    
    process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )

    elapsed = time.time() - start_time

    if process.returncode != 0:
        err_msg = process.stderr
        print(f"Whisper Error Output:\n{err_msg}")
        
        # 针对 SHA256 checksum 不匹配的错误，自动清理缓存并降级为 small 模型重试一次
        if "checksum does not match" in err_msg or "SHA256" in err_msg:
            print("检测到模型文件校验失败/损坏，自动清理缓存...")
            cache_dir = os.path.expanduser("~/.cache/whisper")
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir, ignore_errors=True)
            
            if model != "base":
                fallback_model = "base" if model == "small" else "small"
                print(f"自动降级为 {fallback_model} 模型重试...")
                return transcribe_audio(audio_path, model=fallback_model, language=language, output_dir=output_dir)
        
        raise RuntimeError(f"Whisper 转写失败 (exit code {process.returncode}): {err_msg}")

    print(f"Transcription completed in {elapsed:.2f} seconds.")

    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    txt_file = os.path.join(output_dir, f"{base_name}.txt")

    if not os.path.exists(txt_file):
        matching = [f for f in os.listdir(output_dir) if f.startswith(base_name) and f.endswith(".txt")]
        if matching:
            txt_file = os.path.join(output_dir, matching[0])
        else:
            raise FileNotFoundError(f"找不到转写结果文件: {txt_file}")

    with open(txt_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read().strip()

    return {
        "audio_path": os.path.abspath(audio_path),
        "txt_file": txt_file,
        "content": content,
        "elapsed_seconds": round(elapsed, 2)
    }

def main():
    parser = argparse.ArgumentParser(description="音频文件文本转写工具")
    parser.add_argument("audio_path", nargs="?", default="auto", help="目标音频文件路径 (.m4a, .mp3, .wav等)，不传默认取当前工作目录下当日音频文件")
    parser.add_argument("--model", default="turbo", help="Whisper 模型名称 (tiny, base, small, medium, turbo, large)")
    parser.add_argument("--language", default="Chinese", help="语言指定 (Chinese, English, etc.)")
    parser.add_argument("--output_dir", default=None, help="输出文件目录")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")

    args = parser.parse_args()

    try:
        res = transcribe_audio(
            audio_path=args.audio_path,
            model=args.model,
            language=args.language,
            output_dir=args.output_dir
        )
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print("--- 转写成功 ---")
            print(f"文件: {res['audio_path']}")
            print(f"耗时: {res['elapsed_seconds']} 秒")
            print(f"文本预览 (前 200 字):\n{res['content'][:200]}...\n")
            print("--- 完整转写文件 ---")
            print(res['txt_file'])
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
