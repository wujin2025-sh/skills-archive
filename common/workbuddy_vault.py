#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy Secret Vault - 统一安全凭据与解密模块
提供安全的凭据存储、解密、Session 保持和隔离管理能力。
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None


class WorkBuddyVault:
    """WorkBuddy 统一凭据安全管理类"""

    DEFAULT_KEY_PATH = Path.home() / ".workbuddy" / ".meeting_skill_key"

    def __init__(self, key_path: Optional[Path] = None):
        self.key_path = Path(key_path) if key_path else self.DEFAULT_KEY_PATH
        self._fernet: Optional[Any] = None
        self._init_fernet()

    def _init_fernet(self):
        """初始化 Fernet 解密器"""
        if not Fernet:
            return

        if self.key_path.exists():
            try:
                key = self.key_path.read_bytes().strip()
                if key:
                    self._fernet = Fernet(key)
            except Exception as e:
                print(f"[Vault Warning] Failed to read key file {self.key_path}: {e}", file=sys.stderr)

    def decrypt_password(self, encrypted_password: str) -> str:
        """
        解密带有 ENC: 前缀的密码。如果不是 ENC: 前缀，则原样返回。
        """
        if not encrypted_password:
            return ""

        if not encrypted_password.startswith("ENC:"):
            return encrypted_password

        if not self._fernet:
            print("[Vault Error] Cryptography/Fernet key missing or invalid, cannot decrypt ENC: password", file=sys.stderr)
            return encrypted_password

        raw_cipher = encrypted_password[4:]
        try:
            decrypted = self._fernet.decrypt(raw_cipher.encode("utf-8")).decode("utf-8")
            return decrypted
        except Exception as e:
            print(f"[Vault Error] Password decryption failed: {e}", file=sys.stderr)
            return encrypted_password

    @staticmethod
    def load_config(config_path: Path) -> Dict[str, Any]:
        """读取并解析 JSON 配置文件"""
        if not config_path.exists():
            return {}
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Vault Warning] Failed to load config {config_path}: {e}", file=sys.stderr)
            return {}


_default_vault = WorkBuddyVault()

def decrypt_secret(secret_str: str) -> str:
    """快捷解密接口"""
    return _default_vault.decrypt_password(secret_str)
