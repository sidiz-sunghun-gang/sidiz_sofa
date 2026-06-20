"""사용자 수동 배정 — 미지정 품목을 특정 라인에 수동 할당.

마스터에 없거나 매칭 안 된 품목코드를 사용자가 화면에서 라인으로 이동하면
이 파일에 영구 저장되어 다음 분배에도 자동 적용된다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict


@dataclass
class ManualAssignments:
    # 품목코드 → 라인 번호
    by_code: Dict[str, int] = field(default_factory=dict)

    def get(self, item_code: str) -> int | None:
        if not item_code:
            return None
        return self.by_code.get(str(item_code).strip())

    def set(self, item_code: str, line_no: int) -> None:
        code = str(item_code).strip()
        if code:
            self.by_code[code] = int(line_no)

    def remove(self, item_code: str) -> None:
        self.by_code.pop(str(item_code).strip(), None)

    def to_dict(self) -> dict:
        return {"by_code": {k: int(v) for k, v in self.by_code.items()}}

    @classmethod
    def from_dict(cls, d: dict | None) -> "ManualAssignments":
        if not d:
            return cls()
        out: Dict[str, int] = {}
        for code, line in (d.get("by_code") or {}).items():
            try:
                ln = int(re.search(r"\d+", str(line)).group())
                out[str(code).strip()] = ln
            except (TypeError, ValueError, AttributeError):
                continue
        return cls(by_code=out)


def load_manual(path: Path) -> ManualAssignments:
    if not path.exists():
        return ManualAssignments()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return ManualAssignments.from_dict(json.load(f))
    except Exception:
        return ManualAssignments()


def save_manual(path: Path, manual: ManualAssignments) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manual.to_dict(), f, ensure_ascii=False, indent=2)
