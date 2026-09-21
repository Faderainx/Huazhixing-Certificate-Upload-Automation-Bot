#!/usr/bin/env python3
"""
安全护栏 —— 防封域名 / 防限流的策略层（与业务解耦）。
包含：上传间隔+随机抖动、每小时速率帽、断路器(连错即停)、业务时间窗。
全部由 config.json 参数化，默认保守。仅在真实上传模式启用，dry-run 不触发。
"""
import logging
import random
import time
from datetime import datetime

logger = logging.getLogger("hzx")

# 命中这些关键词/状态码视为「硬性封禁/限流」，应立刻中止整批而非重试
HARD_BLOCK_KEYWORDS = ("频繁", "限流", "封", "rate", "limit", "too many", "forbidden", "403")


def is_hard_block(resp) -> bool:
    """判断上传响应是否为硬性封禁/限流信号。"""
    if not isinstance(resp, dict):
        return False
    code = resp.get("code")
    if code in (401, 403):
        return True
    msg = str(resp.get("msg", "")).lower()
    return any(k in msg for k in HARD_BLOCK_KEYWORDS)


class SafetyGuard:
    def __init__(self, cfg: dict):
        self.interval = float(cfg.get("request_interval", 1.0))
        self.jitter = float(cfg.get("request_jitter", 0.5))      # 抖动比例 0~1
        self.circuit = int(cfg.get("circuit_breaker", 3))        # 连错达到即停
        self.max_per_hour = int(cfg.get("max_per_hour", 0))      # 0=不限
        self.business_hours = cfg.get("business_hours")          # [起, 止) 或 None
        self.max_wait = int(cfg.get("max_schedule_wait", 7200))  # 非窗口最多等待秒
        self._consecutive_fail = 0
        self._hour_ts: list = []

    # ---- 业务时间窗：开跑前检查一次 ----
    def check_schedule(self):
        if not self.business_hours:
            return
        start, end = int(self.business_hours[0]), int(self.business_hours[1])
        now_h = datetime.now().hour
        if start <= now_h < end:
            return
        wait_sec = self._wait_to_next_window(now_h, start, end)
        if wait_sec > self.max_wait:
            raise RuntimeError(
                f"当前 {now_h:02d}:00 不在业务时间窗 {start:02d}:00-{end:02d}:00，"
                f"且等待({wait_sec}s)超上限({self.max_wait}s)，中止以免违规"
            )
        logger.warning("非业务时间窗，将休眠 %d 秒至 %02d:00 再开始", wait_sec, start)
        time.sleep(wait_sec)

    @staticmethod
    def _wait_to_next_window(now_h, start, end):
        if now_h >= end:
            return (24 - now_h + start) * 3600
        return (start - now_h) * 3600

    # ---- 每次请求前：速率帽 + 间隔抖动 ----
    def wait_before_request(self):
        if self.max_per_hour > 0:
            now = time.time()
            self._hour_ts = [t for t in self._hour_ts if now - t < 3600]
            if len(self._hour_ts) >= self.max_per_hour:
                sleep_to = 3600 - (now - self._hour_ts[0]) + 1
                logger.warning("已达每小时上限 %d 条，休眠 %.0f 秒", self.max_per_hour, sleep_to)
                time.sleep(sleep_to)
                self._hour_ts = []
        wait = self.interval + self.interval * self.jitter * random.random()
        if wait > 0:
            time.sleep(wait)

    # ---- 结果记账：成功 / 失败 ----
    def note_success(self):
        self._consecutive_fail = 0
        self._hour_ts.append(time.time())

    def note_failure(self, hard_block: bool = False):
        self._consecutive_fail += 1
        if hard_block:
            self._consecutive_fail += self.circuit  # 硬封直接触发断路器
        return self.should_abort()

    def should_abort(self) -> bool:
        return self.circuit > 0 and self._consecutive_fail >= self.circuit
