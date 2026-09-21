#!/usr/bin/env python3
"""
一级代办（截图上传）—— 接口占位。
原 hzx_certificate_upload.py 完全未实现一级代办。此处给出清晰接口与 dry-run 映射，
真实上传需先确认「上传ID和截图」是否有等价 API（阶段0 待确认项）。
若确认走浏览器自动化，则在此填充 Playwright 逻辑（控件见 GUI进程抽象文档）。
"""
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger("hzx")


def plan_level1(registry: Dict[str, str], screenshots: List[Tuple[str, object]]) -> List[dict]:
    """构造一级代办执行计划：编号 -> 公司中文名 -> 截图文件。"""
    plan = []
    for no, path in screenshots:
        plan.append(
            {
                "no": no,
                "company": registry.get(no, "（注册表未找到）"),
                "screenshot": str(path),
            }
        )
    return plan


def run_level1(client, registry, screenshots, date: str, dry_run: bool = False) -> dict:
    """
    执行一级代办。dry_run 仅输出计划；真实上传需 API/浏览器控件确认后实现。
    """
    plan = plan_level1(registry, screenshots)
    logger.info("一级代办计划：%d 个截图任务", len(plan))
    for item in plan:
        logger.info("  [%s] %s <- %s", item["no"], item["company"], item["screenshot"])

    stats = {"total": len(plan), "success": 0, "skip": 0, "error": 0}
    if dry_run:
        logger.info("一级代办 dry-run 完成（未实际上传）")
        return stats

    # TODO(阶段0)：确认「上传ID和截图」接口后实现
    # 接口候选：
    #   A. API：仿 client.upload_certificate 增加 upload_screenshot(order, img, date)
    #   B. 浏览器：Playwright 定位「上传ID和截图」-> 文件input -> ID输入框(填date) -> 确认
    raise NotImplementedError(
        "一级代办真实上传尚未实现：需先确认「上传ID和截图」是否为 API（见待确认清单#7）。"
        "当前仅支持 dry-run 计划输出。"
    )
