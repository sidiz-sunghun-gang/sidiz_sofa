"""업로드 파일 영속화 (최신 파일만 유지).

서버 디스크의 app/storage/latest/ 에 두 파일을 고정 파일명으로 저장한다.
- cumulative.xls : 누적분배 최신본
- daily.xls      : 당일분배 최신본
앱이 재시작되어도 디스크에 남아있으면 자동으로 로드한다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from typing import Literal, Optional

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
LATEST_DIR = STORAGE_DIR / "latest"
CONFIG_DIR = STORAGE_DIR / "config"
META_PATH = LATEST_DIR / "meta.json"

LATEST_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

Kind = Literal["cumulative", "daily"]
_FILENAME = {"cumulative": "cumulative.xls", "daily": "daily.xls"}


def save_upload(kind: Kind, data: bytes, original_name: str) -> Path:
    """원자적으로 저장. 임시 파일에 먼저 쓴 뒤 os.replace로 교체.

    Windows에서 같은 파일이 잠시 잠겨 있어도 안전하게 동작한다.
    """
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    final_path = LATEST_DIR / _FILENAME[kind]

    # 같은 폴더에 임시 파일 생성 (다른 드라이브로 가지 않도록 dir 지정)
    fd, tmp = tempfile.mkstemp(prefix=f".{kind}_", suffix=".tmp", dir=str(LATEST_DIR))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, final_path)  # atomic on Windows & POSIX
    except Exception:
        # 임시 파일 정리
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass
        raise

    _update_meta(kind, original_name, len(data))
    return final_path


def delete_upload(kind: Kind) -> bool:
    """저장된 최신 파일 + 메타에서 해당 종류 삭제. 삭제했으면 True."""
    path = LATEST_DIR / _FILENAME[kind]
    removed = False
    if path.exists():
        try:
            path.unlink()
            removed = True
        except OSError:
            pass
    # 메타에서도 제거
    meta = latest_meta()
    if kind in meta:
        meta.pop(kind, None)
        if meta:
            with open(META_PATH, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        else:
            # 메타가 비면 파일도 삭제
            try:
                if META_PATH.exists():
                    META_PATH.unlink()
            except OSError:
                pass
        removed = True
    return removed


def load_latest_bytes(kind: Kind) -> Optional[bytes]:
    path = LATEST_DIR / _FILENAME[kind]
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return f.read()


def latest_meta() -> dict:
    if not META_PATH.exists():
        return {}
    try:
        with open(META_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _update_meta(kind: Kind, original_name: str, size: int) -> None:
    meta = latest_meta()
    meta[kind] = {
        "original_name": original_name,
        "size": size,
        "uploaded_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    # meta도 원자적으로
    fd, tmp = tempfile.mkstemp(prefix=".meta_", suffix=".tmp", dir=str(META_PATH.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        os.replace(tmp, META_PATH)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass
        raise


RULES_PATH = CONFIG_DIR / "line_rules.json"
GROUP_POLICY_PATH = CONFIG_DIR / "group_policy.json"
SPLIT_LOCK_PATH = CONFIG_DIR / "split_lock.json"
ITEM_MASTER_PATH = CONFIG_DIR / "item_master.json"  # (deprecated 호환용)

# 품목 마스터 폴더 — 사용자가 엑셀/CSV 파일을 두면 자동 로드됨
MASTER_FOLDER = Path(__file__).resolve().parent.parent.parent / "품목마스터"
MASTER_FOLDER.mkdir(parents=True, exist_ok=True)
