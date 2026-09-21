#!/usr/bin/env python3
"""
华之星后台 - 批量上传注册证书（二级待办列表）

使用方式：
    python hzx_certificate_upload.py "C:/.../7.24 德国WEEE注册证书" "C:/.../7.24 德国电池法注册证书"

脚本会根据文件夹名判断证书类型（WEEE / 电池法），读取其中的名单 Excel 和 PDF 证书，
自动登录华之星后台，进入二级待办列表，按公司名匹配订单，上传证书并回填结果到 Excel 的“上传反馈”列。

账号密码从环境变量 HZX_USERNAME / HZX_PASSWORD 读取，也可通过命令行参数传入；源码不保存默认凭据。
"""

import os
import re
import sys
import json
import logging
import argparse
import shutil
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Optional, Tuple, Any

import openpyxl
import requests

# ----------------- 配置 -----------------
BASE_URL = os.environ.get("HZX_BASE_URL", "https://example.invalid")
LOGIN_URL = f"{BASE_URL}/appservice/login"
SECONDARY_LIST_URL = f"{BASE_URL}/appservice/hyz/ServiceOrderRecord/getUploadCertList"
UPLOAD_CERT_URL = f"{BASE_URL}/appservice/hyz/Servicecertificate/uploadCert"

USERNAME = os.environ.get("HZX_USERNAME", "")
PASSWORD = os.environ.get("HZX_PASSWORD", "")

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
}

# 更新后的 Excel 输出目录（默认放到工作区，不覆盖用户桌面原始文件）。
# 如需直接写回原 Excel，可将 HZX_OUTPUT_DIR 指向原文件所在目录并自行授权。
OUTPUT_DIR = Path(os.environ.get("HZX_OUTPUT_DIR", "results"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ----------------- 工具函数 -----------------
def normalize_text(text: str) -> str:
    """去掉首尾空白及回车符，统一中文括号。"""
    if text is None:
        return ""
    text = str(text).strip().replace("\r", "").replace("\n", "")
    # 统一括号为中文全角（Excel 与文件名可能混用）
    text = text.replace("(", "（").replace(")", "）")
    return text


def detect_cert_type(folder_name: str) -> str:
    """根据文件夹名判断证书类型。"""
    if "WEEE" in folder_name.upper():
        return "weee"
    if "电池法" in folder_name or "BattG" in folder_name or "BAT" in folder_name.upper():
        return "batt"
    raise ValueError(f"无法识别文件夹对应的证书类型：{folder_name}")


def find_inner_cert_folder(folder: Path) -> Tuple[Path, List[Path]]:
    """
    华之星的文件夹里通常还有一层同名子文件夹，返回真正包含文件的目录及文件列表。
    """
    candidates = [folder]
    for child in folder.iterdir():
        if child.is_dir():
            candidates.append(child)

    # 优先选择包含 .xlsx 且包含 .pdf 的子目录
    best = None
    for c in candidates:
        xlsx_count = sum(1 for f in c.iterdir() if f.is_file() and f.suffix.lower() == ".xlsx")
        pdf_count = sum(1 for f in c.iterdir() if f.is_file() and f.suffix.lower() == ".pdf")
        if xlsx_count and pdf_count:
            if best is None or pdf_count > sum(1 for f in best.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"):
                best = c
    if best is None:
        raise FileNotFoundError(f"在 {folder} 下未找到同时包含 .xlsx 和 .pdf 的目录")
    files = [f for f in best.iterdir() if f.is_file()]
    return best, files


def find_excel_and_pdfs(files: List[Path]) -> Tuple[Path, List[Path]]:
    """从文件列表中找出名单 Excel 和 PDF 证书。"""
    excels = [f for f in files if f.suffix.lower() == ".xlsx" and "名单" in f.name]
    pdfs = [f for f in files if f.suffix.lower() == ".pdf"]
    if not excels:
        raise FileNotFoundError("未找到名单 Excel（文件名需包含“名单”）")
    if not pdfs:
        raise FileNotFoundError("未找到 PDF 证书文件")
    # 如果有多个 Excel，优先选文件名带“名单”的；如果还有多个，取修改时间最新的
    excel = max(excels, key=lambda p: p.stat().st_mtime)
    return excel, pdfs


def read_excel_list(excel_path: Path, cert_type: str) -> Tuple[openpyxl.Workbook, Any, List[Dict], int]:
    """
    读取名单 Excel，返回 workbook、sheet、以及按行组织的字典列表。
    字典包含：row_index, 公司中文名, 商品名, RV号码, 证书编号, 当前反馈。
    """
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb.active

    header = [normalize_text(cell.value) for cell in ws[1]]
    if not header:
        raise ValueError("Excel 首行没有表头")

    # 定位关键列（按表头名匹配）
    col_idx = {}
    for idx, h in enumerate(header, 1):
        if h in col_idx:
            continue
        col_idx[h] = idx

    def col(name: str) -> Optional[int]:
        return col_idx.get(name)

    company_col = col("公司中文名")
    product_col = col("商品名")
    rv_col = col("RV号码")
    feedback_col = col("上传反馈")

    if not company_col:
        raise ValueError("Excel 缺少“公司中文名”列")
    if not product_col:
        raise ValueError("Excel 缺少“商品名”列")
    if not rv_col:
        raise ValueError("Excel 缺少“RV号码”列")
    if not feedback_col:
        raise ValueError("Excel 缺少“上传反馈”列")

    if cert_type == "weee":
        cert_no_col = col("WEEE号")
    else:
        cert_no_col = col("电池法证书")
    if not cert_no_col:
        raise ValueError(f"Excel 缺少对应证书编号列：WEEE号 / 电池法证书")

    rows = []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        company = normalize_text(row[company_col - 1])
        product = normalize_text(row[product_col - 1])
        rv = normalize_text(row[rv_col - 1])
        cert_no = normalize_text(row[cert_no_col - 1])
        feedback = normalize_text(row[feedback_col - 1])
        if not company:
            continue
        rows.append({
            "row_index": row_idx,
            "company": company,
            "product": product,
            "rv": rv,
            "cert_no": cert_no,
            "feedback": feedback,
        })
    return wb, ws, rows, feedback_col


# ----------------- 华之星 API -----------------
class HzxClient:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.token: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def login(self) -> None:
        logger.info("正在登录华之星后台...")
        resp = self.session.post(
            LOGIN_URL,
            json={"username": self.username, "password": self.password, "code": "", "uuid": ""},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(f"登录失败：{data}")
        self.token = data["data"]
        self.session.headers["Authorization"] = f"Bearer {self.token}"
        logger.info("登录成功")

    def get_secondary_orders(self, page_size: int = 200) -> List[Dict]:
        """获取二级待办列表所有订单。"""
        resp = self.session.get(
            SECONDARY_LIST_URL,
            params={"pageNum": 1, "pageSize": page_size},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(f"获取二级待办列表失败：{data}")
        return data["data"]["result"]

    def upload_certificate(self, order: Dict, files: List[Tuple[str, Path, str]]) -> Dict:
        """
        上传证书到指定订单。
        files: [(filename_on_disk, file_path, certificate_number), ...]
        """
        form = {}
        form["recordData"] = json.dumps(order, ensure_ascii=False)

        no_list = []
        for filename, path, cert_no in files:
            no_list.append({filename: cert_no})
        form["certificateNOList"] = json.dumps(no_list, ensure_ascii=False)
        form["remark"] = form["certificateNOList"]

        mfiles = [("cert", (os.path.basename(path), open(path, "rb"), "application/pdf")) for _, path, _ in files]
        try:
            resp = self.session.post(UPLOAD_CERT_URL, data=form, files=mfiles, timeout=60)
            resp.raise_for_status()
            return resp.json()
        finally:
            for _, fobj in [(f[0], f[1][1]) for f in mfiles]:
                fobj.close()


# ----------------- 主流程 -----------------
def match_orders(rows: List[Dict], orders: List[Dict], cert_type: str) -> Dict[str, List[Dict]]:
    """
    按公司名 + 商品名匹配订单。
    返回：company -> [orders]
    """
    # 按公司名分组订单
    orders_by_company = defaultdict(list)
    for order in orders:
        company = normalize_text(order.get("userRemark") or "")
        orders_by_company[company].append(order)
        # 同时尝试 companyAddressUs / companyNameUs 作为辅助匹配（部分订单公司名可能在其他字段）
        for alt in [order.get("companyAddressUs"), order.get("companyNameUs")]:
            if alt and normalize_text(alt) != company:
                orders_by_company[normalize_text(alt)].append(order)

    matched = defaultdict(list)
    for row in rows:
        company = row["company"]
        product = row["product"]
        # 证书类型与系统商品名对应
        if cert_type == "weee":
            expected = "德国WEEE注册"
        else:
            expected = "德国电池法BattG"

        # 先精确匹配公司名
        candidates = orders_by_company.get(company, [])
        # 如果没找到，尝试用公司名中的核心部分（不含括号外）匹配 userRemark
        if not candidates and "（" in company:
            short = company.split("（")[0]
            candidates = orders_by_company.get(short, [])

        # 再过滤商品名
        for order in candidates:
            if order.get("goodsName") == expected:
                matched[company].append(order)
    return matched


def find_cert_files_for_rows(rows: List[Dict], pdfs: List[Path]) -> Dict[str, List[Tuple[str, Path, str]]]:
    """
    为每个公司找出所有匹配的证书文件。
    返回：company -> [(filename, path, cert_no), ...]
    """
    result = defaultdict(list)
    for row in rows:
        company = row["company"]
        rv = row["rv"]
        cert_no = row["cert_no"]
        for pdf in pdfs:
            filename = pdf.name
            # 文件名中需同时包含公司名和 RV 编号
            if company in filename and rv in filename:
                result[company].append((filename, pdf, cert_no))
                break
    return result


def process_folder(folder: Path, client: HzxClient, dry_run: bool = False, pre_done: Optional[List[str]] = None) -> Dict:
    """处理一个证书文件夹，返回统计信息。
    pre_done: 已知已提交成功的公司名片段列表（在列表中已找不到，但确已上传，避免误标“未找到”）。
    """
    logger.info("=" * 60)
    logger.info("处理文件夹：%s", folder)
    cert_type = detect_cert_type(folder.name)
    logger.info("识别为证书类型：%s", "WEEE" if cert_type == "weee" else "德国电池法")

    inner, files = find_inner_cert_folder(folder)
    excel, pdfs = find_excel_and_pdfs(files)
    logger.info("名单 Excel：%s", excel)
    logger.info("PDF 证书数量：%d", len(pdfs))

    wb, ws, rows, feedback_col = read_excel_list(excel, cert_type)
    logger.info("Excel 有效行数：%d", len(rows))

    # 备份 Excel（仅复制到输出目录，不修改原始文件）
    backup_path = OUTPUT_DIR / (excel.stem + ".backup" + excel.suffix)
    if not dry_run:
        shutil.copy2(excel, backup_path)
        logger.info("已备份 Excel 副本到：%s", backup_path)

    # 拉取二级待办列表
    orders = client.get_secondary_orders()
    logger.info("二级待办列表当前订单数量：%d", len(orders))

    matched_orders = match_orders(rows, orders, cert_type)
    matched_files = find_cert_files_for_rows(rows, pdfs)

    stats = {"total": len(rows), "success": 0, "not_found": 0, "no_file": 0, "error": 0}

    # 已知已提交成功的公司：在内存与输出 Excel 中标记为“已提交成功”，并跳过上传
    if pre_done:
        for row in rows:
            if any(pd and pd in row["company"] for pd in pre_done):
                ws.cell(row=row["row_index"], column=feedback_col, value="已提交成功")
                row["feedback"] = "已提交成功"
                logger.info("【%s】按已知已提交名单预标记为已提交成功", row["company"])

    # 按公司分组行，方便一次性上传同一订单的多个证书
    rows_by_company = defaultdict(list)
    for row in rows:
        rows_by_company[row["company"]].append(row)

    for company, company_rows in rows_by_company.items():
        # 如果已经全部提交成功，跳过
        if all(row["feedback"] == "已提交成功" for row in company_rows):
            logger.info("【%s】已标记为提交成功，跳过", company)
            continue

        orders_for_company = matched_orders.get(company, [])
        if not orders_for_company:
            logger.warning("【%s】未在二级待办列表找到对应订单", company)
            for row in company_rows:
                ws.cell(row=row["row_index"], column=feedback_col, value="未找到该公司订单")
            stats["not_found"] += len(company_rows)
            continue

        order = orders_for_company[0]
        order_sn = order.get("orderSn")
        logger.info("【%s】匹配到订单 %s，商品：%s", company, order_sn, order.get("goodsName"))

        files_to_upload = matched_files.get(company, [])
        if not files_to_upload:
            logger.warning("【%s】匹配到订单但未找到对应证书文件", company)
            for row in company_rows:
                ws.cell(row=row["row_index"], column=feedback_col, value="未找到对应证书文件")
            stats["no_file"] += len(company_rows)
            continue

        logger.info("【%s】准备上传 %d 个证书：%s", company, len(files_to_upload),
                    ", ".join(f[0] for f in files_to_upload))

        if dry_run:
            logger.info("【%s】dry-run，未实际上传", company)
            continue

        try:
            resp = client.upload_certificate(order, files_to_upload)
            if resp.get("code") == 200:
                logger.info("【%s】上传成功：%s", company, resp.get("msg"))
                for row in company_rows:
                    ws.cell(row=row["row_index"], column=feedback_col, value="已提交成功")
                stats["success"] += len(company_rows)
            else:
                logger.error("【%s】上传失败：%s", company, resp)
                for row in company_rows:
                    ws.cell(row=row["row_index"], column=feedback_col, value=f"上传失败：{resp.get('msg')}")
                stats["error"] += len(company_rows)
        except Exception as e:
            logger.exception("【%s】上传异常：%s", company, e)
            for row in company_rows:
                ws.cell(row=row["row_index"], column=feedback_col, value=f"上传异常：{e}")
            stats["error"] += len(company_rows)

    # 保存 Excel（写入输出目录，不覆盖原始文件）
    if not dry_run:
        out_path = OUTPUT_DIR / excel.name
        wb.save(out_path)
        logger.info("Excel 已更新并保存到：%s", out_path)

    return stats


def main():
    parser = argparse.ArgumentParser(description="华之星证书批量上传")
    parser.add_argument("folders", nargs="+", help="证书文件夹路径，支持多个")
    parser.add_argument("--dry-run", action="store_true", help="只匹配不上传")
    parser.add_argument("--user", default=USERNAME, help="登录账号")
    parser.add_argument("--password", default=PASSWORD, help="登录密码")
    parser.add_argument("--pre-done", default="", help="已知已上传成功的公司名片段，逗号分隔（避免误标未找到）")
    args = parser.parse_args()

    pre_done = [x.strip() for x in args.pre_done.split(",") if x.strip()]

    client = HzxClient(args.user, args.password)
    client.login()

    total_stats = defaultdict(int)
    for folder_str in args.folders:
        folder = Path(folder_str)
        if not folder.exists():
            logger.error("文件夹不存在：%s", folder)
            continue
        stats = process_folder(folder, client, dry_run=args.dry_run, pre_done=pre_done)
        for k, v in stats.items():
            total_stats[k] += v

    logger.info("=" * 60)
    logger.info("汇总：%s", dict(total_stats))


if __name__ == "__main__":
    main()
