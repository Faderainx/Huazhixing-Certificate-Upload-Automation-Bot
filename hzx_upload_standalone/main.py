#!/usr/bin/env python3
"""
华之星证书上传 —— 独立命令行入口。
用法：
    python main.py --task-package "任务包目录" [--level1] [--level2] [--dry-run] [--date 2026/8/25]
双击 启动.bat 即以上述默认参数运行当前目录为任务包。
"""
import argparse
import logging
import sys
from pathlib import Path

# 让同目录模块可被 import（无论在哪运行）
PACKAGE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE_DIR))

from config import load_config, get_password  # noqa: E402
from logger import setup_logger  # noqa: E402
from crypto_cred import load_credentials, save_credentials  # noqa: E402
from state import load_state, save_state  # noqa: E402
from io_read import (  # noqa: E402
    prepare_task_package, load_registry, load_screenshots,
    find_detail_xlsx, load_detail, load_certs,
)
from client import HzxClient  # noqa: E402
from level1 import run_level1  # noqa: E402
from level2 import run_level2  # noqa: E402
from ratelimit import SafetyGuard  # noqa: E402


class _GuiHandler(logging.Handler):
    """把日志转发给 GUI 的回调（level, message）。emit 内异常静默，绝不拖垮主流程。"""

    def __init__(self, sink):
        super().__init__()
        self.sink = sink

    def emit(self, record):
        try:
            self.sink(record.levelname, self.format(record))
        except Exception:  # noqa: BLE001
            pass


def run_pipeline(opts: dict, log_sink=None):
    """
    核心流程（CLI 与 GUI 共用）。
    opts 键：task_package, level1, level2, dry_run, date, username, password, save_cred
    log_sink: 可选 (level:str, message:str) 回调；GUI 用于实时显示。为 None 则只写文件/控制台。
    返回：二级代办汇总 dict 或 None
    """
    cfg = load_config()
    logger = setup_logger(cfg["output_dir"])
    guard = SafetyGuard(cfg)
    if log_sink:
        gh = _GuiHandler(log_sink)
        gh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s", "%H:%M:%S"))
        logger.addHandler(gh)

    # 凭证：命令行/界面 > 加密文件 > 环境变量 > 默认
    username = opts.get("username") or cfg.get("username")
    password = opts.get("password") or get_password()
    cu, cp = load_credentials()
    if cu:
        username = username or cu
        password = password or cp
    if opts.get("save_cred"):
        save_credentials(username, password)

    task_pkg = Path(opts["task_package"])
    if not task_pkg.exists():
        logger.error("任务包目录不存在：%s", task_pkg)
        return None

    logger.info("任务包：%s", task_pkg)
    extract_root = prepare_task_package(str(task_pkg), cfg["output_dir"])

    # ---- 输入解析 ----
    registry = load_registry(extract_root)
    screenshots = load_screenshots(extract_root)
    detail_xlsx = find_detail_xlsx(str(task_pkg))
    rows = load_detail(detail_xlsx) if detail_xlsx else []
    certs = load_certs(extract_root)
    logger.info("注册表公司数=%d，截图=%d，明细行=%d，证书=%d",
                len(registry), len(screenshots), len(rows), len(certs))

    state_path = str(Path(cfg["output_dir"]) / "state.json")
    state = load_state(state_path)

    # ---- 一级代办 ----
    if opts.get("level1"):
        try:
            run_level1(None, registry, screenshots, opts.get("date", ""), dry_run=opts.get("dry_run", False))
        except NotImplementedError as e:
            logger.warning("一级代办跳过：%s", e)

    # ---- 二级代办 ----
    summary = None
    if opts.get("level2"):
        if opts.get("dry_run"):
            stats = run_level2(None, rows, certs, state, dry_run=True, guard=guard)
        else:
            client = HzxClient(username, password, cfg["base_url"])
            client.login()
            # 首包探针：登录后立即验证会话健康，避免在已限流/封禁态下继续上传扩大风险
            if cfg.get("probe_first", True):
                try:
                    client.get_secondary_orders()
                    logger.info("探针通过：会话正常，开始上传")
                except Exception as e:
                    logger.error("探针失败（可能已被限流/封禁）：%s —— 中止以免扩大风险", e)
                    save_state(state_path, state)
                    return None
            # 业务时间窗检查（非窗口则等待或中止）
            guard.check_schedule()
            stats = run_level2(client, rows, certs, state, dry_run=False, guard=guard)
        save_state(state_path, state)
        logger.info("二级代办汇总：%s", stats)
        summary = stats

    logger.info("完成。结果目录：%s", cfg["output_dir"])
    return summary


def main():
    parser = argparse.ArgumentParser(description="华之星证书批量上传（独立版）")
    parser.add_argument("--task-package", default=str(PACKAGE_DIR),
                        help="任务包目录（含明细表 xlsx、截图 zip、证书 zip）")
    parser.add_argument("--level1", action="store_true", help="执行一级代办（截图上传）")
    parser.add_argument("--level2", action="store_true", help="执行二级代办（证书上传）")
    parser.add_argument("--dry-run", action="store_true", help="仅解析与匹配，不上传")
    parser.add_argument("--date", default="", help="一级代办 ID 栏填写的日期，如 2026/8/25")
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--save-cred", action="store_true", help="把账号密码加密保存（下次免输）")
    args = parser.parse_args()

    # 默认两级都跑
    if not args.level1 and not args.level2:
        args.level2 = True

    opts = {
        "task_package": args.task_package,
        "level1": args.level1,
        "level2": args.level2,
        "dry_run": args.dry_run,
        "date": args.date,
        "username": args.username,
        "password": args.password,
        "save_cred": args.save_cred,
    }
    run_pipeline(opts)


if __name__ == "__main__":
    main()
