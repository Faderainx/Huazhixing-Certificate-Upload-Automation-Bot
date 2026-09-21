#!/usr/bin/env python3
"""
配置层 —— 独立运行，不依赖外部自动化环境。
所有路径、账号、URL 均可配置，不写入个人电脑路径或运行环境。
优先级：config.json > 环境变量 > 内置默认值。
"""
import json
import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def load_config() -> dict:
    cfg_path = PACKAGE_DIR / "config.json"
    cfg: dict = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[配置] 读取 config.json 失败，使用默认配置：{e}")

    # 默认值（服务地址请通过 config.json 或 HZX_BASE_URL 提供）
    cfg.setdefault("base_url", os.environ.get("HZX_BASE_URL", "https://example.invalid"))
    cfg.setdefault("output_dir", str(PACKAGE_DIR / "results"))
    cfg.setdefault("username", os.environ.get("HZX_USERNAME", ""))
    # 密码不在此明文保存，改由 crypto_cred 提供（env / 加密文件 / 默认）
    # —— 防封/防限流参数（保守默认，可在 config.json 覆盖）——
    cfg.setdefault("request_interval", 1.0)   # 两次上传之间的间隔(秒)
    cfg.setdefault("max_retries", 3)          # 单次上传失败的网络重试次数
    cfg.setdefault("retry_backoff", 2.0)      # 重试退避基数(秒)，按指数 2^(n-1) 增长
    # —— 防封强化层（默认保守，config.json 可覆盖）——
    cfg.setdefault("request_jitter", 0.5)      # 间隔随机抖动比例(0~1)，节奏更像人工
    cfg.setdefault("circuit_breaker", 3)       # 连续失败达此数，立即中止整批(避免硬扛被封)
    cfg.setdefault("max_per_hour", 60)         # 每小时最多上传数(0=不限)，防瞬间超量
    cfg.setdefault("business_hours", [9, 18])  # 业务时间窗[起, 止)；null=不限
    cfg.setdefault("probe_first", True)        # 开跑前先探测会话健康，异常则中止
    cfg.setdefault("max_schedule_wait", 7200)  # 非窗口最多等待秒数，超出则中止
    return cfg


def get_password(default: str = "") -> str:
    """密码来源：环境变量或加密文件，不保存默认密码。"""
    return os.environ.get("HZX_PASSWORD", default)
