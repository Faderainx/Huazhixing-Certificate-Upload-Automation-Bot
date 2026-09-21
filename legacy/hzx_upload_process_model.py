#!/usr/bin/env python3
"""
华之星证书上传 —— GUI 进程抽象（机器可读蓝图）

把《华之星系统批量上传注册截图和证书操作流程.docx》与真实样例包，
抽象成「页面 / 控件 / 数据绑定」的结构化规格，供 RPA 实现直接对照。

同时内置「场景覆盖矩阵」与「待确认项答复」，可由 main() 渲染为文本，
作为可行性报告的结构化数据源（对应交付物：GUI进程抽象 / 可行性分析 / 设计拆解）。

仅依赖标准库（dataclasses / typing / json），无第三方依赖，便于在任意 Python3.12 环境运行。
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
import json


# ----------------- 基础抽象 -----------------
@dataclass
class Control:
    """一个可操作控件（浏览器语义；若走 API 则 selector 留空、用 api 字段说明）。"""
    name: str                 # 控件中文名
    kind: str                 # button / input / file / search
    action: str               # 点击 / 输入 / 上传
    bind: Optional[str] = None  # 绑定的数据字段（数据绑定键）
    selector: Optional[str] = None  # 浏览器选择器占位（待探查填写）
    api: Optional[str] = None      # 等价 API（若有）


@dataclass
class FlowStep:
    page: str
    controls: List[Control]


# ----------------- 一级代办（截图上传） -----------------
LEVEL1_STEPS = FlowStep(
    page="待办列表（左侧=待办列表，右侧服务方框=待办列表）",
    controls=[
        Control("搜索框", "search", "输入公司中文名", bind="公司中文名(注册表映射)"),
        Control("上传ID和截图", "button", "点击", api="待确认：是否有等价 API"),
        Control("文件输入(点击这里)", "file", "上传截图", bind="截图文件"),
        Control("ID 输入框", "input", "填当天日期", bind="当天日期"),
        Control("确认", "button", "提交", api="待确认"),
    ],
)

# ----------------- 二级代办（证书上传） -----------------
LEVEL2_STEPS = FlowStep(
    page="二级待办列表（右侧服务方框=二级待办列表）",
    controls=[
        Control("搜索框", "search", "输入公司中文名", bind="明细表.公司中文名"),
        Control("搜索", "button", "点击"),
        Control("上传证书", "button", "点击(按 goodsName 选条目)",
                bind="明细表.商品名/类别", api="POST /appservice/hyz/Servicecertificate/uploadCert"),
        Control("文件输入(点击这里)", "file", "上传证书", bind="证书文件(公司名+RV)"),
        Control("证书编号", "input", "填号", bind="明细表.WEEE号"),
        Control("确定 / 提交", "button", "提交"),
    ],
)


# ----------------- 数据绑定（关键映射） -----------------
DATA_BINDINGS = {
    "一级代办": {
        "截图文件名 → 编号": "正则截取前缀编号(如 HX2304)",
        "编号 → 公司中文名": "查注册表(截图zip内 Sheet=注册表)",
        "公司中文名 → 搜索框": "系统待办列表",
        "截图文件 → 文件输入": "上传",
        "当天日期 → ID输入框": "格式 2026/7/24",
    },
    "二级代办": {
        "明细表.公司中文名 → 搜索框": "二级待办列表",
        "明细表.商品名 → goodsName匹配": "德国WEEE注册 / 德国电池法BattG",
        "证书文件(公司名+RV) → 文件输入": "上传",
        "明细表.WEEE号 → 证书编号框": "回填",
    },
}


# ----------------- 场景覆盖矩阵（可行性结论） -----------------
# status: covered / partial / missing
COVERAGE: Dict[str, Dict] = {
    "FR-1 独立运行":        {"status": "covered",  "note": "纯命令行脚本，可独立运行"},
    "FR-2 原样读表":        {"status": "missing",  "note": "硬编码列(商品名/上传反馈)，样例缺列会抛 ValueError"},
    "FR-3 一级代办":        {"status": "missing",  "note": "完全未实现"},
    "FR-4 二级逐行":        {"status": "covered",  "note": "按公司分组 N行→N次"},
    "FR-5 类别匹配":        {"status": "partial",  "note": "仅 goodsName 匹配，无 WEEE/BAT 条目级校验"},
    "FR-6 证书号填写":      {"status": "covered",  "note": "从 Excel 取号"},
    "FR-7 进度与日志":      {"status": "partial",  "note": "仅 stdout 日志，无失败文件"},
    "FR-8 断点重跑":        {"status": "partial",  "note": "仅手动 --pre-done，无持久化状态"},
    "FR-9 结果汇总":        {"status": "partial",  "note": "仅打印 dict"},
    "GUI 外壳":             {"status": "missing",  "note": "仅命令行"},
    "凭证本地加密":         {"status": "missing",  "note": "明文默认/环境变量"},
}


# ----------------- 待确认项答复（基于真实样例） -----------------
CONFIRMED = {
    "W3E/W3C→WEEE? BAT名称?": "即 WEEE(文件名 WEEE-华之星)；BAT=电池法(文件名 BAT-华之星)，系统商品名=德国电池法BattG",
    "截图映射键": "编号(B列)，非域名",
    "表列名/Sheet": "明细表 WEEE-华之星.xlsx(无商品名/上传反馈列)；一级表在截图包内 注册表 Sheet",
    "证书格式/命名": "PDF；WEEE/BAT-华之星-编号-公司名-RV编号.pdf",
    "登录/上传控件": "后台有登录/二级待办/上传证书 API(已验证)；一级代办 API 待确认",
    "国别": "需求文档写法国=误；真实为德国 WEEE注册/德国电池法BattG",
}


def render() -> str:
    lines = []
    lines.append("# 华之星证书上传 —— 进程抽象渲染\n")
    lines.append("## 一级代办控件序列")
    for c in LEVEL1_STEPS.controls:
        lines.append(f"  - [{c.kind}] {c.name}：{c.action}" + (f"  ← {c.bind}" if c.bind else ""))
    lines.append("\n## 二级代办控件序列")
    for c in LEVEL2_STEPS.controls:
        lines.append(f"  - [{c.kind}] {c.name}：{c.action}" + (f"  ← {c.bind}" if c.bind else ""))
    lines.append("\n## 场景覆盖矩阵")
    for k, v in COVERAGE.items():
        lines.append(f"  - {k}：{v['status']}（{v['note']}）")
    lines.append("\n## 待确认项答复(基于真实样例)")
    for k, v in CONFIRMED.items():
        lines.append(f"  - {k}：{v}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(render())
    # 另可导出 JSON 供其他工具消费
    model = {
        "level1": asdict(LEVEL1_STEPS),
        "level2": asdict(LEVEL2_STEPS),
        "data_bindings": DATA_BINDINGS,
        "coverage": COVERAGE,
        "confirmed": CONFIRMED,
    }
    with open("hzx_process_model.json", "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=2)
    print("\n[已导出] hzx_process_model.json")
