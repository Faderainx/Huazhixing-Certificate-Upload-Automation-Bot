#!/usr/bin/env python3
"""
日志层 —— 控制台 + 文件双输出，失败明细可查（对应 FR-7）。
使用独立日志体系，输出到自己配置的 output_dir。
"""
import logging
import sys
from pathlib import Path


def setup_logger(output_dir: str) -> logging.Logger:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "run.log"

    logger = logging.getLogger("hzx")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s", "%H:%M:%S")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.info("日志文件：%s", log_path)
    return logger
