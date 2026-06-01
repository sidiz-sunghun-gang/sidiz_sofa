"""Excel(.xls/.xlsx) 로더 + 컬럼 표준화.

원본 grd_list_*.xls 파일은 헤더가 여러 행에 걸쳐 있어 pandas가 읽으면
컬럼명에 줄바꿈/공백이 끼고 일부 값이 헤더 행으로 빠진다. 한 번만 정규화한다.
"""
from __future__ import annotations

import io
import re
from typing import Optional, Union

import pandas as pd


# 표준 컬럼 매핑: 원본 헤더 후보(공백/줄바꿈 제거 후) -> 표준 키
_HEADER_ALIASES = {
    "번호": "no",
    "체크": "check",
    "생산처": "factory",
    "포장일": "pack_date",
    "생산라인": "line",
    "품목코드": "item_code",
    "색상": "color",
    "계획량": "plan_qty",
    "최초포장일": "first_pack_date",
    "재공완료": "wip_done",
    "품목명": "item_name",
    "건명▼": "order_name",
    "건명": "order_name",
    "전달사항": "memo",
    "계획시간(초)": "plan_sec",
    "입고계획차수": "in_plan_seq",
    "부족수량": "short_qty",
    "자원충족률(%)": "supply_rate",
    "표준작업시간(초)": "std_work_sec",
    "생산순서": "prod_seq",
    "사전생산순서": "pre_prod_seq",
    "피딩": "feeding",
    "피딩여부": "feeding_yn",
    "박스": "box",
    "실적량": "actual_qty",
    "차이량": "diff_qty",
    "발생시간(분)": "occur_min",
    "차이코드": "diff_code",
    "잔여CUT수량": "remain_cut",
    "SHIFT": "shift",
    "P": "p",
    "계획완료(초)": "plan_done_sec",
    "총중량": "total_weight",
    "박스용적": "box_volume",
    "서비스카드(접수번호)": "service_card",
}


def _normalize_header(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    # 그리드 정렬 화살표 기호 제거 (예: "품목명▼", "건명▲")
    s = re.sub(r"[▼▲△▽↓↑]", "", s)
    return re.sub(r"\s+", "", s)


def read_grd_excel(source: Union[str, bytes, io.BytesIO]) -> pd.DataFrame:
    """grd_list_*.xls 파일을 표준 컬럼명으로 정규화하여 반환한다.

    원본은 첫 행이 헤더지만 셀 내부 줄바꿈으로 인해 첫 데이터 행과 섞인다.
    pandas의 header=0으로 일단 읽은 뒤 alias 매핑으로 컬럼을 통일한다.
    """
    if isinstance(source, (bytes, bytearray)):
        bio = io.BytesIO(source)
    else:
        bio = source

    # .xls (BIFF) 우선, 실패 시 .xlsx 시도
    try:
        df = pd.read_excel(bio, engine="xlrd", header=0, dtype=str)
    except Exception:
        if hasattr(bio, "seek"):
            bio.seek(0)
        df = pd.read_excel(bio, engine="openpyxl", header=0, dtype=str)

    # 컬럼 정규화
    new_cols = {}
    for c in df.columns:
        key = _normalize_header(c)
        new_cols[c] = _HEADER_ALIASES.get(key, key)
    df = df.rename(columns=new_cols)

    # 마지막의 Sub Total / Total 행 제거
    if "no" in df.columns:
        mask_no = df["no"].astype(str).str.match(r"^\d+$").fillna(False)
        mask_subtotal = df.get("pack_date", pd.Series([""] * len(df))).astype(str).str.contains("Sub Total|Total", na=False)
        df = df[mask_no & ~mask_subtotal].copy()

    # 숫자형 변환
    for c in ["plan_qty", "plan_sec", "std_work_sec", "actual_qty", "short_qty", "box_volume", "total_weight"]:
        if c in df.columns:
            df[c] = (
                df[c].astype(str).str.replace(",", "", regex=False).str.strip().replace({"": None, "nan": None})
            )
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # 라인 정규화: "(1라인) 김민웅" → "1라인"
    if "line" in df.columns:
        df["line_norm"] = (
            df["line"].astype(str).str.extract(r"\((\d+라인|\d+라인반제품|\d+라인\)?반제품)\)", expand=False)
        )
        df["line_no"] = df["line"].astype(str).str.extract(r"\((\d+)라인", expand=False)
        # fallback: "9라인)반제품" 같은 형태
        mask_null = df["line_no"].isna()
        if mask_null.any():
            df.loc[mask_null, "line_no"] = (
                df.loc[mask_null, "line"].astype(str).str.extract(r"(\d+)라인", expand=False)
            )
        df["line_no"] = pd.to_numeric(df["line_no"], errors="coerce").astype("Int64")
        df["line_norm"] = df["line_no"].astype(str).where(df["line_no"].notna(), None) + "라인"

    # 출고일자: 전달사항(memo) 안의 날짜 패턴 추출 (예: "6/1 출고", "5/30 출고 (대전)")
    if "memo" in df.columns:
        df["ship_date_raw"] = df["memo"].fillna("").astype(str)
        df["ship_date"] = df["ship_date_raw"].map(_parse_ship_date)

    return df.reset_index(drop=True)


_MD_RE = re.compile(r"(\d{1,2})\s*[/\-월\.]\s*(\d{1,2})")
_YMD_RE = re.compile(r"(20\d{2})[\-/\.](\d{1,2})[\-/\.](\d{1,2})")


def _parse_ship_date(s, *, year_hint: int = 2026) -> Optional[str]:
    """전달사항 텍스트에서 출고일자(YYYY-MM-DD)를 추출. 못 찾으면 None."""
    if s is None:
        return None
    s = str(s)
    if not s or s.lower() == "nan":
        return None
    m = _YMD_RE.search(s)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m = _MD_RE.search(s)
    if m:
        mo, d = m.groups()
        return f"{year_hint:04d}-{int(mo):02d}-{int(d):02d}"
    return None
