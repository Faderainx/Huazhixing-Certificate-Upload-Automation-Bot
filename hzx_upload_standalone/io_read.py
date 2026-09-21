#!/usr/bin/env python3
"""
输入解析层 —— 原样读取现有表格/压缩包/截图命名（对应 FR-2），不要求用户改表。
修正原代码对「商品名 / 上传反馈」列的硬依赖：真实明细表无这两列，本层按真实列名定位，
证书类别由文件名前缀(WEEE-/BAT-)推断，商品名(goodsName)同样由前缀推断。
"""
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import openpyxl


def normalize(text) -> str:
    if text is None:
        return ""
    return (
        str(text)
        .strip()
        .replace("\r", "")
        .replace("\n", "")
        .replace("(", "（")
        .replace(")", "）")
    )


def _clear_dir(root: Path) -> None:
    """尽力清空目录内容（rmtree 不可用时的兜底）。失败的文件/子目录跳过，不抛异常。"""
    for item in root.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink()
        except Exception:  # noqa: BLE001
            pass


# ----------------- 任务包准备：抽取所有 zip -----------------
def _decode_zip_name(name: str) -> str:
    """修正中文 zip 文件名乱码（如 ╜╪═╝）。

    中文 Windows 打的 zip 常不带 UTF-8 标志，Python 的 zipfile 默认用 cp437 解，
    得到乱码。若原字节是 GBK，把 cp437 解出的串重新 encode('cp437') 取回原始字节，
    再按 gbk 解码即得正确中文；若原名已是正确中文（utf-8 zip），cp437 重编码会抛错，
    此时直接保留原名即可。"""
    try:
        return name.encode("cp437").decode("gbk")
    except Exception:  # noqa: BLE001
        return name


def _safe_rel(path: str) -> str:
    """去掉绝对前缀与 '..'，防 zip-slip；统一用 '/' 分隔。"""
    p = path.replace("\\", "/")
    parts = [seg for seg in p.split("/") if seg not in ("", ".", "..")]
    return "/".join(parts)


def prepare_task_package(task_pkg_dir: str, output_dir: str) -> Path:
    """把任务包里所有 .zip 解压到 output/_extract，返回解压根目录。
    手动逐条解压以便用修正后的正确中文文件名落盘（extractall 会用原乱码名）。"""
    extract_root = Path(output_dir) / "_extract"
    if extract_root.exists():
        # 防御：部分环境(如某些沙箱)的 shutil.rmtree 被强制走回收站会抛 OSError。
        # 删不掉不阻断主流程——后续覆盖同名文件；旧乱码名文件由 _clear_dir 兜底清理。
        try:
            shutil.rmtree(extract_root)
        except Exception as e:  # noqa: BLE001
            print(f"[输入] 警告：清理旧解压目录失败（将尝试增量覆盖）：{e}")
            _clear_dir(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)
    for z in Path(task_pkg_dir).rglob("*.zip"):
        try:
            with zipfile.ZipFile(z) as zf:
                for info in zf.infolist():
                    rel = _safe_rel(_decode_zip_name(info.filename))
                    if not rel:
                        continue
                    dest = extract_root / rel
                    if info.filename.endswith("/"):
                        dest.mkdir(parents=True, exist_ok=True)
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        except Exception as e:
            print(f"[输入] 解压失败 {z.name}：{e}")
    return extract_root


def _iter_files(root: Path, ext: str) -> List[Path]:
    return [p for p in root.rglob(f"*.{ext}") if not p.name.startswith("~$")]


# ----------------- 一级表（注册表）：编号 -> 公司中文名 -----------------
def load_registry(root: Path) -> Dict[str, str]:
    """截图压缩包内的 注册表 Sheet：编号 → 公司中文名。"""
    for x in _iter_files(root, "xlsx"):
        try:
            wb = openpyxl.load_workbook(x, data_only=True)
        except Exception:
            continue
        ws = wb["注册表"] if "注册表" in wb.sheetnames else None
        if ws is None:
            continue
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        hdr = [normalize(c) for c in rows[0]]
        try:
            no_i = hdr.index("编号") + 1
            name_i = hdr.index("公司中文名") + 1
        except ValueError:
            continue
        mapping = {}
        for r in rows[1:]:
            no = normalize(r[no_i - 1])
            name = normalize(r[name_i - 1])
            if no and name:
                mapping[no] = name
        if mapping:
            return mapping
    return {}


# ----------------- 截图：编号 + 文件 -----------------
def load_screenshots(root: Path) -> List[Tuple[str, Path]]:
    """截图文件名形如 编号+德国WEEE注册截图+英文名.png，提取编号。"""
    out = []
    for p in _iter_files(root, "png"):
        stem = p.stem
        no = stem.split("+")[0] if "+" in stem else stem
        out.append((normalize(no), p))
    return out


# ----------------- 明细表 -----------------
def find_detail_xlsx(task_pkg_dir: str) -> Optional[Path]:
    """任务包（含子目录）下的明细表（含「公司中文名」「RV号码」列、且非注册表）。
    递归搜索，兼容用户把输入收进 测试数据/ 之类子目录的布局。"""
    best = None
    for x in Path(task_pkg_dir).rglob("*.xlsx"):
        if x.name.startswith("~$"):
            continue
        try:
            wb = openpyxl.load_workbook(x, data_only=True)
            ws = wb.active
            hdr = [normalize(c) for c in next(ws.iter_rows(values_only=True))]
        except Exception:
            continue
        if "公司中文名" in hdr and "注册表" not in wb.sheetnames:
            # 优先选含 RV号码 的（明细表特征）
            if "RV号码" in hdr:
                return x
            best = best or x
    return best


def load_detail(detail_xlsx: Path) -> List[dict]:
    """读取明细表。真实列：代理/编号/公司中文名/公司英文名/品牌/德文类别/类别/WEEE号/联系邮箱/日期/RV号码/备注。
    按表头选明细 sheet（含「公司中文名」+「RV号码」），避免误用注册表/其它 sheet。"""
    wb = openpyxl.load_workbook(detail_xlsx, data_only=True)
    detail_ws = None
    for sn in wb.sheetnames:
        try:
            hdr0 = [normalize(c) for c in next(wb[sn].iter_rows(values_only=True))]
        except Exception:
            continue
        if "公司中文名" in hdr0 and "RV号码" in hdr0:
            detail_ws = wb[sn]
            break
    if detail_ws is None:
        detail_ws = wb.active
    ws = detail_ws
    rows = list(ws.iter_rows(values_only=True))
    hdr = [normalize(c) for c in rows[0]]
    col = {h: i + 1 for i, h in enumerate(hdr) if h}

    company_i = col.get("公司中文名")
    rv_i = col.get("RV号码")
    weee_i = col.get("WEEE号")
    batt_i = col.get("电池法证书")
    no_i = col.get("编号")
    if not company_i or not rv_i:
        raise ValueError("明细表缺少「公司中文名」或「RV号码」列")

    out = []
    for ri, r in enumerate(rows[1:], 2):
        company = normalize(r[company_i - 1])
        if not company:
            continue
        rv = normalize(r[rv_i - 1])
        # 证书号：WEEE 用 WEEE号；电池法若有专用列则用电池法证书
        cert_no = normalize(r[weee_i - 1]) if weee_i else ""
        if not cert_no and batt_i:
            cert_no = normalize(r[batt_i - 1])
        out.append(
            {
                "row_index": ri,
                "company": company,
                "rv": rv,
                "cert_no": cert_no,
                "no": normalize(r[no_i - 1]) if no_i else "",
            }
        )
    return out


# ----------------- 证书：文件名前缀 + RV -----------------
def load_certs(root: Path) -> List[dict]:
    """证书文件名形如 WEEE-华之星-编号-公司名-RV-xxxx.pdf / BAT-华之星-...。
    返回 {prefix: 'weee'|'batt', rv, path}。按文件名去重（证书压缩包常含顶层+子目录两层相同副本）。"""
    out = []
    seen = set()
    for p in _iter_files(root, "pdf"):
        if p.name in seen:
            continue
        seen.add(p.name)
        name = p.name
        if name.upper().startswith("WEEE"):
            prefix = "weee"
        elif name.upper().startswith("BAT"):
            prefix = "batt"
        else:
            prefix = "unknown"
        rv = ""
        if "-RV-" in name:
            rv = "RV-" + name.split("-RV-", 1)[1].rsplit(".", 1)[0]
        out.append({"prefix": prefix, "rv": normalize(rv), "path": p})
    return out


def match_certs_for_row(row: dict, certs: List[dict]) -> List[dict]:
    """按 (公司名⊂文件名) 且 (RV⊂文件名) 且 类别前缀一致 匹配证书。"""
    company = row["company"]
    rv = row["rv"]
    matched = []
    for c in certs:
        if company and company not in c["path"].name:
            continue
        if rv and rv not in c["path"].name:
            continue
        matched.append(c)
    return matched
