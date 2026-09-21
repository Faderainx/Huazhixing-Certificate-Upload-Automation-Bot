#!/usr/bin/env python3
"""
二级代办（证书上传）—— 保留原代码的逐行上传逻辑，修正列假设，支持断点重跑。
类别(goodsName)由证书文件名前缀推断：WEEE->德国WEEE注册，BAT->德国电池法BattG。
匹配：公司中文名 + goodsName 定位订单；证书按 公司名⊂文件名 且 RV⊂文件名 选取。
"""
import logging
import time
from collections import defaultdict
from typing import Dict, List

from client import HzxClient
from config import load_config
from io_read import normalize, match_certs_for_row
from ratelimit import is_hard_block

logger = logging.getLogger("hzx")


def _goods_name(prefix: str) -> str:
    return "德国WEEE注册" if prefix == "weee" else "德国电池法BattG"


def match_orders(rows, orders, prefix: str) -> Dict[str, list]:
    """按 公司中文名 + goodsName 匹配系统订单。"""
    expected = _goods_name(prefix)
    by_company = defaultdict(list)
    for o in orders:
        c = normalize(o.get("userRemark") or "")
        by_company[c].append(o)
        for alt in (o.get("companyAddressUs"), o.get("companyNameUs")):
            if alt and normalize(alt) != c:
                by_company[normalize(alt)].append(o)

    matched = defaultdict(list)
    for row in rows:
        cands = by_company.get(row["company"], [])
        if not cands and "（" in row["company"]:
            cands = by_company.get(row["company"].split("（")[0], [])
        for o in cands:
            if o.get("goodsName") == expected:
                matched[row["company"]].append(o)
    return matched


def run_level2(client: HzxClient, rows: List[dict], certs: List[dict],
               state: Dict, dry_run: bool = False, guard=None) -> dict:
    stats = {"total": len(rows), "success": 0, "not_found": 0, "no_file": 0, "error": 0}

    # 上传重试参数（config.json 可覆盖）；间隔/抖动/断路器由 SafetyGuard 统一管
    cfg = load_config()
    max_retries = int(cfg.get("max_retries", 3))
    backoff = float(cfg.get("retry_backoff", 2.0))

    # 按证书前缀分组行（WEEE / BAT），各自匹配对应 goodsName
    weee_rows = [r for r in rows]  # 明细表每行即一个证书任务，按该行匹配到的证书前缀判定
    # 先给每行找证书，确定其前缀
    rows_by_key = defaultdict(list)
    for r in rows:
        mc = match_certs_for_row(r, certs)
        if mc:
            prefix = mc[0]["prefix"]
            rows_by_key[prefix].append((r, mc))
        else:
            rows_by_key["__nofile"].append((r, []))

    # dry-run 不需要系统订单，直接按本地映射汇报
    orders = None
    if not dry_run:
        orders = client.get_secondary_orders()
        logger.info("二级待办列表订单数：%d", len(orders))

    aborted = False
    for prefix, group in rows_by_key.items():
        if aborted:
            break
        if prefix == "__nofile":
            for r, _ in group:
                if state.get(r["company"], {}).get("status") == "success":
                    stats["success"] += 1
                    continue
                logger.warning("【%s】未找到对应证书文件（RV=%s）", r["company"], r["rv"])
                stats["no_file"] += 1
            continue

        if not dry_run:
            matched_orders = match_orders([g[0] for g in group], orders, prefix)

        for r, mc in group:
            if aborted:
                break
            key = f"{r['company']}#{r['rv']}"
            if state.get(key, {}).get("status") == "success":
                logger.info("【%s】已成功，跳过（断点重跑）", r["company"])
                stats["success"] += 1
                continue

            if dry_run:
                logger.info("【dry-run】%s -> 将上传 %d 个证书（%s）",
                            r["company"], len(mc), _goods_name(prefix))
                stats["success"] += 1
                continue

            order_list = matched_orders.get(r["company"], [])
            if not order_list:
                logger.warning("【%s】未在二级待办找到对应订单", r["company"])
                state[key] = {"status": "fail", "reason": "未找到该公司订单"}
                stats["not_found"] += 1
                continue

            order = order_list[0]
            files = [(c["path"].name, str(c["path"]), r["cert_no"]) for c in mc]
            try:
                if guard:
                    guard.wait_before_request()
                resp = client.upload_certificate(
                    order, files, max_retries=max_retries, backoff=backoff
                )
                if resp.get("code") == 200:
                    logger.info("【%s】上传成功：%s", r["company"], resp.get("msg"))
                    state[key] = {"status": "success", "reason": ""}
                    stats["success"] += 1
                    if guard:
                        guard.note_success()
                else:
                    logger.error("【%s】上传失败：%s", r["company"], resp)
                    state[key] = {"status": "fail", "reason": str(resp.get("msg"))}
                    stats["error"] += 1
                    if guard and guard.note_failure(is_hard_block(resp)):
                        logger.error("触发硬封/连续失败，中止剩余任务（重跑可续跑）")
                        aborted = True
                        break
            except Exception as e:
                logger.exception("【%s】上传异常：%s", r["company"], e)
                state[key] = {"status": "fail", "reason": str(e)}
                stats["error"] += 1
                if guard and guard.note_failure(hard_block=False):
                    logger.error("连续异常，中止剩余任务（重跑可续跑）")
                    aborted = True
                    break

    return stats
