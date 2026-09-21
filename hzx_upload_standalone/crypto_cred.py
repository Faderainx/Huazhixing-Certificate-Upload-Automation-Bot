#!/usr/bin/env python3
"""
凭证加密层 —— 账号密码本地加密保存（对应需求 非功能·安全）。
使用 cryptography.Fernet；若环境未安装则降级为明文（仅提示，不阻塞运行）。
凭据只保存在本机加密文件中。
"""
import json
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    _HAS_CRYPTO = True
except Exception:
    _HAS_CRYPTO = False

PACKAGE_DIR = Path(__file__).resolve().parent
KEY_FILE = PACKAGE_DIR / ".hzx_key"
CRED_FILE = PACKAGE_DIR / "credentials.enc"


def _key() -> bytes:
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    k = Fernet.generate_key()
    KEY_FILE.write_bytes(k)
    return k


def save_credentials(username: str, password: str) -> bool:
    """加密保存账号密码到 credentials.enc。成功返回 True。"""
    if not _HAS_CRYPTO:
        print("[凭证] 未安装 cryptography，跳过加密保存（请用环境变量或 config 传参）")
        return False
    f = Fernet(_key())
    data = json.dumps({"username": username, "password": password}).encode("utf-8")
    CRED_FILE.write_bytes(f.encrypt(data))
    return True


def load_credentials():
    """返回 (username, password)；无加密文件时返回 (None, None)。"""
    if not _HAS_CRYPTO or not CRED_FILE.exists():
        return None, None
    try:
        f = Fernet(_key())
        d = json.loads(f.decrypt(CRED_FILE.read_bytes()))
        return d.get("username"), d.get("password")
    except Exception as e:
        print(f"[凭证] 读取失败：{e}")
        return None, None
