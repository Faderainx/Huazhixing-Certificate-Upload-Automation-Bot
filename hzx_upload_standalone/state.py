#!/usr/bin/env python3
"""
状态层 —— 断点重跑（对应 FR-8）。
把每家公司/每行的上传结果持久化到 state.json，重跑时跳过已完成，
避免重复提交。替代原代码的手动 --pre-done 列表。
"""
import json
from pathlib import Path
from typing import Dict, Optional


def load_state(path: str) -> Dict:
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(path: str, state: Dict) -> None:
    Path(path).write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def mark(state: Dict, key: str, status: str, reason: str = "") -> None:
    state[key] = {"status": status, "reason": reason}


def is_done(state: Dict, key: str) -> bool:
    return state.get(key, {}).get("status") == "success"
