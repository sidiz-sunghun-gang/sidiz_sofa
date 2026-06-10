"""라인별 분배 계획 서버 (Streamlit).

사용:
    streamlit run app/app.py
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# Streamlit이 'app/app.py'를 실행하면 app/ 가 sys.path[0]에 추가되므로
# core 패키지는 직접 import 가능. 'app.' 접두사는 스크립트명과 충돌해서 사용하지 않는다.
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.loader import read_grd_excel  # noqa: E402
from core.cumulative import process_cumulative  # noqa: E402
from core.daily import distribute_daily, DAILY_TARGET_LINES, LINE_HEADCOUNT  # noqa: E402
from core.rules import LineRules, load_rules, save_rules, rules_from_dataframe  # noqa: E402
from core.policy import GroupPolicy, load_policy, save_policy, DEFAULT_SPLIT_KEYWORDS  # noqa: E402
from core.split import (  # noqa: E402
    SplitLock, load_split_lock, save_split_lock, split_lock_from_dataframe,
)
from core.master import (  # noqa: E402
    ItemMaster, load_master_from_folder,
    pattern_common_name, exact_short_name,
)
from core.integrity import build_integrity  # noqa: E402
from core import storage  # noqa: E402


st.set_page_config(
    page_title="라인별 분배 계획 · 소파 생산",
    page_icon="🛋️",
    layout="wide",
)

# === 가구·소파 제조 브랜드 톤 ===
# 팔레트: 크림 배경 + 다크 우드 브라운 + 카멜 골드 액센트 + 차분한 슬레이트
st.markdown(
    """
<style>
/* ========== 전체 배경 ========== */
.stApp {
    background: linear-gradient(180deg, #faf7f2 0%, #f5ede0 100%);
}
/* 메인 컨테이너 패딩 정리 */
.block-container { padding-top: 1.6rem; }

/* ========== 타이포그래피 ========== */
h1, h2, h3, h4 {
    color: #4a3424;
    font-family: "Pretendard", -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", sans-serif;
    letter-spacing: -0.3px;
}
h1 { font-weight: 800; }
h2, h3 { font-weight: 700; }

/* 본문 텍스트 톤 */
.stMarkdown, .stCaption, p, label, span { color: #3a2c1f; }

/* ========== 사이드바 ========== */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #4a3424 0%, #2d2017 100%);
    border-right: 1px solid #6b4a30;
}
section[data-testid="stSidebar"] * { color: #f5ede0 !important; }
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 { color: #ffffff !important; }
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
    color: #c8b89e !important;
}
/* 사이드바 파일 업로더 — 미니멀 */
section[data-testid="stSidebar"] [data-testid="stFileUploader"] {
    background: transparent;
    border: none;
    padding: 0;
    margin-bottom: 10px;
}
section[data-testid="stSidebar"] [data-testid="stFileUploader"] > label {
    font-size: 12px !important;
    color: #c8b89e !important;
    font-weight: 600 !important;
    margin-bottom: 4px !important;
}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(200, 148, 90, 0.25) !important;
    border-radius: 8px !important;
    padding: 8px 10px !important;
    min-height: auto !important;
}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] small {
    display: none !important;  /* "50MB per file - XLS,..." 부가설명 숨김 */
}
section[data-testid="stSidebar"] [data-testid="stFileUploader"] button {
    background: rgba(200, 148, 90, 0.9) !important;
    color: #2d2017 !important;
    border: none !important;
    font-weight: 700 !important;
    font-size: 12px !important;
    padding: 4px 14px !important;
    border-radius: 6px !important;
    min-height: 30px !important;
    height: 30px !important;
}
section[data-testid="stSidebar"] [data-testid="stFileUploader"] button:hover {
    background: #c8945a !important;
}
/* 사이드바 알림(파일 저장됨) */
section[data-testid="stSidebar"] [data-testid="stAlertContainer"] {
    background: rgba(200, 148, 90, 0.12) !important;
    border-left: 3px solid #c8945a !important;
    color: #f5ede0 !important;
    padding: 6px 10px !important;
    font-size: 12px !important;
}

/* ========== 메트릭 카드 ========== */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e8dcc8;
    border-radius: 14px;
    padding: 16px 20px;
    box-shadow: 0 1px 4px rgba(74, 52, 36, 0.06);
}
[data-testid="stMetricLabel"] {
    color: #8b6f4e;
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 0.3px;
}
[data-testid="stMetricValue"] {
    color: #4a3424;
    font-weight: 800;
}
[data-testid="stMetricDelta"] { color: #c8945a; }

/* ========== 탭 ========== */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: rgba(255,255,255,0.5);
    border-radius: 10px;
    padding: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    font-weight: 600;
    padding: 8px 16px;
}
.stTabs [data-baseweb="tab"] p {
    color: #6b4a30 !important;
    font-weight: 600 !important;
}
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
    background: #4a3424 !important;
}
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] p,
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] span {
    color: #f5ede0 !important;
    font-weight: 700 !important;
}

/* ========== 버튼 ========== */
.stButton > button,
.stDownloadButton > button,
[data-testid="stFormSubmitButton"] > button {
    background: #4a3424;
    color: #f5ede0 !important;
    border: 1px solid #4a3424;
    border-radius: 8px;
    font-weight: 600;
    transition: all 0.15s;
}
/* 버튼 내부 <p>/<span> 텍스트가 전역 색에 묻히는 것 방지 */
.stButton > button p,
.stButton > button span,
.stDownloadButton > button p,
.stDownloadButton > button span,
[data-testid="stFormSubmitButton"] > button p,
[data-testid="stFormSubmitButton"] > button span {
    color: #f5ede0 !important;
    font-weight: 600 !important;
}
.stButton > button:hover,
.stDownloadButton > button:hover,
[data-testid="stFormSubmitButton"] > button:hover {
    background: #c8945a;
    border-color: #c8945a;
    color: #2d2017 !important;
}
.stButton > button:hover p,
.stButton > button:hover span,
.stDownloadButton > button:hover p,
.stDownloadButton > button:hover span {
    color: #2d2017 !important;
}
.stButton > button:focus {
    box-shadow: 0 0 0 3px rgba(200, 148, 90, 0.25) !important;
}

/* ========== 입력 위젯 ========== */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input,
.stSelectbox > div > div {
    border-radius: 8px !important;
    border-color: #e8dcc8 !important;
    background: #ffffff !important;
}
.stTextInput input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus {
    border-color: #c8945a !important;
    box-shadow: 0 0 0 2px rgba(200, 148, 90, 0.15) !important;
}

/* ========== 컨테이너 / Expander ========== */
[data-testid="stExpander"] {
    background: rgba(255, 255, 255, 0.6);
    border: 1px solid #e8dcc8;
    border-radius: 12px;
}
[data-testid="stExpander"] summary {
    color: #4a3424;
    font-weight: 600;
}
.element-container .stContainer,
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px;
}

/* ========== 알림(Alert) ========== */
[data-testid="stAlertContainer"] {
    border-radius: 10px;
    border-left-width: 4px;
}

/* ========== 데이터프레임 ========== */
[data-testid="stDataFrame"] table { font-variant-numeric: tabular-nums; }
[data-testid="stDataFrame"] [role="columnheader"] {
    font-weight: 800 !important;
    color: #f5ede0 !important;
    background-color: #4a3424 !important;
}
[data-testid="stDataFrame"] [role="gridcell"] {
    text-align: center !important;
    justify-content: center !important;
}

/* ========== 다이얼로그 ========== */
div[data-testid="stDialog"] > div > div { max-width: 1100px; }
div[data-testid="stDialog"] [data-testid="stDataFrame"] [role="columnheader"] {
    background-color: #4a3424 !important;
    color: #ffffff !important;
    font-weight: 700 !important;
    padding-top: 8px !important;
    padding-bottom: 8px !important;
}
div[data-testid="stDialog"] [data-testid="stDataFrame"] [role="gridcell"] {
    padding-top: 6px !important;
    padding-bottom: 6px !important;
    line-height: 1.4;
}
div[data-testid="stDialog"] [data-testid="stDataFrame"] [role="gridcell"][aria-colindex="2"],
div[data-testid="stDialog"] [data-testid="stDataFrame"] [role="gridcell"][aria-colindex="3"] {
    text-align: right;
}

/* ========== 브랜드 헤더 ========== */
.brand-header {
    background: linear-gradient(135deg, #ffffff 0%, #faf7f2 100%);
    border: 1px solid #e8dcc8;
    border-left: 6px solid #c8945a;
    border-radius: 14px;
    padding: 20px 28px;
    margin-bottom: 20px;
    box-shadow: 0 2px 8px rgba(74, 52, 36, 0.06);
}
.brand-header .brand-title {
    font-size: 28px;
    font-weight: 800;
    color: #4a3424;
    letter-spacing: -0.5px;
    margin: 0;
}
.brand-header .brand-sub {
    font-size: 12px;
    color: #8b6f4e;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-top: 4px;
    font-weight: 600;
}
.brand-header .brand-tag {
    display: inline-block;
    background: #c8945a;
    color: #2d2017;
    font-size: 11px;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 12px;
    margin-left: 12px;
    vertical-align: middle;
}

/* ========== 사이드바 브랜드 ========== */
.sidebar-brand {
    padding: 8px 0 18px 0;
    border-bottom: 1px solid rgba(200, 148, 90, 0.3);
    margin-bottom: 18px;
}
.sidebar-brand .sb-logo {
    font-size: 22px;
    font-weight: 800;
    color: #f5ede0;
    letter-spacing: -0.3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.sidebar-brand .sb-sub {
    font-size: 10px;
    color: #c8945a;
    letter-spacing: 2px;
    font-weight: 700;
    margin-top: 3px;
    white-space: nowrap;
}
.sb-section-title {
    color: #c8945a !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    letter-spacing: 1.5px;
    margin: 14px 0 8px 0;
}
.sb-file-card {
    background: rgba(255,255,255,0.05);
    border-radius: 6px;
    padding: 7px 10px;
    margin-top: 4px;
    border-left: 2px solid #c8945a;
}
.sb-file-name {
    font-size: 11px;
    font-weight: 600;
    color: #f5ede0;
    word-break: break-all;
    line-height: 1.3;
}
.sb-file-meta {
    font-size: 10px;
    color: #a89478;
    margin-top: 2px;
    line-height: 1.2;
}
/* 사이드바 안의 액션 버튼 (삭제 등) — 작고 톤다운 */
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.04) !important;
    color: #c8b89e !important;
    border: 1px solid rgba(200, 148, 90, 0.3) !important;
    padding: 4px 0 !important;
    min-height: 28px !important;
    height: 28px !important;
    font-size: 13px !important;
    margin-top: 4px;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(231, 111, 81, 0.18) !important;
    border-color: #e76f51 !important;
    color: #ffffff !important;
}
</style>
    """,
    unsafe_allow_html=True,
)


def _load_df(kind: storage.Kind):
    raw = storage.load_latest_bytes(kind)
    if raw is None:
        return None
    try:
        return read_grd_excel(raw)
    except Exception as e:
        st.error(f"{kind} 파일을 읽지 못했습니다: {e}")
        return None


# ---- 표 스타일링 ----
_NUM_RE_COLS = ("합계",)  # 강조 컬럼 키워드


def _style_combined_pivot(df: pd.DataFrame, *, line_col: str):
    """수량/시간 2줄 묶음 표를 보기 좋게 꾸민다.

    - 천단위 콤마 / 0은 회색 흐리게
    - '수량' 행 옅은 황색, '시간' 행 옅은 청색
    - '합계' 행/열 굵게 + 진한 배경
    """
    if df is None or df.empty:
        return df

    numeric_cols = [c for c in df.columns if c not in (line_col, "구분")]

    def _format_num(v):
        if pd.isna(v):
            return ""
        try:
            n = int(v)
        except (TypeError, ValueError):
            return v
        return f"{n:,}"

    def _row_style(row):
        styles = [""] * len(row)
        is_total = str(row[line_col]) == "합계"
        is_qty = str(row.get("구분", "")) == "수량"
        is_sec = str(row.get("구분", "")) == "시간"
        bg = ""
        if is_total:
            bg = "background-color:#e8edf5; font-weight:700; color:#1f2a44;"
        elif is_qty:
            bg = "background-color:#fff7e0;"
        elif is_sec:
            bg = "background-color:#e7f1ff;"
        for i, col in enumerate(row.index):
            s = bg
            if col == "합계":
                s += " font-weight:700;"
            # 0 값을 흐리게
            try:
                if col in numeric_cols and not is_total and float(row[col]) == 0:
                    s += " color:#b5bdca;"
            except (TypeError, ValueError):
                pass
            styles[i] = s
        return styles

    sty = (
        df.style
        .format({c: _format_num for c in numeric_cols})
        .apply(_row_style, axis=1)
        .set_table_styles(
            [
                # 헤더 — 굵고 진하게
                {"selector": "thead th", "props":
                    "background-color:#1f2a44; color:#ffffff; font-weight:800;"
                    " font-size:14px; text-align:center; padding:10px 8px;"
                    " border-bottom:2px solid #1f2a44; letter-spacing:0.2px;"},
                # 본문 셀 — 가운데 정렬
                {"selector": "tbody td", "props":
                    "text-align:center; padding:8px 8px;"
                    " border-bottom:1px solid #e3e8ef;"},
            ]
        )
        .hide(axis="index")
    )
    return sty


def _style_plain_table(
    df: pd.DataFrame,
    *,
    numeric_cols: list[str] | None = None,
    bold_cols: list[str] | None = None,
    nan_text: str = "—",
):
    """일반 표용 스타일러: 네이비 헤더 + 가운데 정렬 + 천단위 콤마 + NaN→대시.

    bold_cols 에 들어간 컬럼은 옅은 배경 + 굵은 글씨로 강조한다 (종합/합계 컬럼 등).
    """
    if df is None or df.empty:
        return None

    if numeric_cols is None:
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    bold_cols = bold_cols or []

    def _fmt(v):
        if pd.isna(v):
            return nan_text
        try:
            return f"{int(v):,}"
        except (TypeError, ValueError):
            return v

    def _cell_style(_):
        # 컬럼별로 강조 (값 dataframe과 동일 shape의 style dataframe 반환)
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        for c in bold_cols:
            if c in styles.columns:
                styles[c] = "background-color:#eef2f7; font-weight:700;"
        return styles

    sty = (
        df.style
        .format({c: _fmt for c in numeric_cols})
        .apply(_cell_style, axis=None)
        .set_table_styles([
            {"selector": "thead th", "props":
                "background-color:#1f2a44; color:#ffffff; font-weight:800;"
                " font-size:14px; text-align:center; padding:10px 8px;"
                " border-bottom:2px solid #1f2a44; letter-spacing:0.2px;"},
            {"selector": "tbody td", "props":
                "text-align:center; padding:8px 8px;"
                " border-bottom:1px solid #e3e8ef;"},
        ])
        .hide(axis="index")
    )
    return sty


def _render_merged_combined(
    df: pd.DataFrame,
    *,
    line_col: str,
    key: str = "tbl_merged",
):
    """라인 셀을 rowspan=2로 병합한 깔끔한 HTML 표를 직접 렌더링.

    입력 df 컬럼 구조: [line_col, "구분", <date1>, <date2>, ..., "합계"]
    - 같은 라인의 (수량, 시간) 2줄을 한 묶음으로 표시 (라인 셀은 가운데 정렬 + 굵게)
    - 수량 행 = 옅은 노랑, 시간 행 = 옅은 파랑, 합계 행 = 진한 슬레이트
    - 0 값은 흐리게, 합계 열은 굵게
    """
    if df is None or df.empty:
        st.info("표시할 데이터가 없습니다.")
        return

    cols = list(df.columns)
    if line_col not in cols or "구분" not in cols:
        st.info("표시 데이터 구조가 올바르지 않습니다.")
        return
    data_cols = [c for c in cols if c not in (line_col, "구분")]

    # 라인별 연속 블록 그룹화 (df는 이미 라인별로 정렬돼 있음)
    blocks: list[list[pd.Series]] = []
    current_line = None
    current_block: list[pd.Series] = []
    for _, row in df.iterrows():
        ln = row[line_col]
        if ln != current_line:
            if current_block:
                blocks.append(current_block)
            current_block = [row]
            current_line = ln
        else:
            current_block.append(row)
    if current_block:
        blocks.append(current_block)

    # HTML 빌드
    parts: list[str] = [f'<div class="merged-wrap" id="{key}"><table class="merged-tbl">']
    # 헤더
    parts.append("<thead><tr>")
    for c in cols:
        parts.append(f"<th>{c}</th>")
    parts.append("</tr></thead><tbody>")

    for block in blocks:
        n = len(block)
        line_val = str(block[0][line_col])
        is_total_block = line_val == "합계"
        for i, row in enumerate(block):
            gubun = str(row.get("구분", ""))
            if is_total_block:
                row_cls = "row-total"
            elif gubun == "수량":
                row_cls = "row-qty"
            elif gubun == "시간":
                row_cls = "row-sec"
            else:
                row_cls = ""

            parts.append(f'<tr class="{row_cls}">')
            if i == 0:
                line_cell_cls = "line-cell total" if is_total_block else "line-cell"
                parts.append(f'<td rowspan="{n}" class="{line_cell_cls}">{line_val}</td>')
            parts.append(f"<td>{gubun}</td>")

            for c in data_cols:
                v = row[c]
                cls_parts = []
                if c == "합계":
                    cls_parts.append("sum-col")
                if pd.isna(v):
                    text = ""
                else:
                    try:
                        n_val = int(v)
                        text = f"{n_val:,}"
                        if n_val == 0 and not is_total_block:
                            cls_parts.append("zero")
                    except (TypeError, ValueError):
                        text = str(v)
                cls = " ".join(cls_parts)
                parts.append(f'<td class="{cls}">{text}</td>')
            parts.append("</tr>")

    parts.append("</tbody></table></div>")

    css = """
<style>
.merged-wrap { overflow-x: auto; }
.merged-tbl {
    width: 100%;
    border-collapse: collapse;
    font-variant-numeric: tabular-nums;
    font-size: 13.5px;
    background: #ffffff;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 1px 4px rgba(74, 52, 36, 0.06);
}
.merged-tbl thead th {
    background-color: #4a3424;
    color: #f5ede0 !important;
    font-weight: 800;
    font-size: 14px;
    text-align: center;
    padding: 10px 8px;
    border: 1px solid #3a2818;
    border-bottom: 2px solid #c8945a;
    letter-spacing: 0.2px;
}
.merged-tbl tbody td {
    text-align: center;
    padding: 8px 10px;
    border: 1px solid #ece1cd;
    color: #3a2c1f;
}
/* 라인 셀 (rowspan 병합) — 크림 배경 + 카멜 액센트 보더 */
.merged-tbl td.line-cell {
    font-weight: 800;
    color: #4a3424 !important;
    background-color: #f5ede0;
    vertical-align: middle;
    border-right: 2px solid #c8945a;
}
.merged-tbl td.line-cell.total {
    background-color: #ebe1d0;
}
/* 행 색상 — 가구 톤 (수량=옅은 카멜, 시간=옅은 베이지 그레이) */
.merged-tbl tr.row-qty td:not(.line-cell) { background-color: #fdf2e0; }
.merged-tbl tr.row-sec td:not(.line-cell) { background-color: #f5f1ea; }
.merged-tbl tr.row-total td:not(.line-cell) {
    background-color: #ebe1d0;
    font-weight: 700;
    color: #4a3424;
}
/* 0 흐리게 — 베이지 톤 */
.merged-tbl td.zero { color: #c8b89e; }
/* 합계 열 굵게 */
.merged-tbl td.sum-col { font-weight: 700; color: #4a3424; }
</style>
    """
    # CSS는 페이지당 한 번만 주입 (NotFoundError 방지)
    if not st.session_state.get("_merged_css_injected"):
        st.markdown(css, unsafe_allow_html=True)
        st.session_state["_merged_css_injected"] = True
    # 표 HTML은 markdown으로 통일 (st.html() 사용 시 DOM 추적 충돌 사례 있음)
    st.markdown("".join(parts), unsafe_allow_html=True)


def _render_styled_table(styled, *, key: str = "tbl"):
    """Styler를 HTML로 직접 렌더링해 모든 CSS가 적용되도록 한다.

    st.dataframe은 set_table_styles 일부를 무시하므로,
    조회용 표는 이 방식으로 출력해 시각적 일관성을 확보한다.
    """
    if styled is None:
        st.info("표시할 데이터가 없습니다.")
        return
    html = styled.to_html()
    st.markdown(
        f"""
<style>
.combined-table-wrap {{ overflow-x: auto; }}
.combined-table-wrap table {{
    width: 100% !important;
    border-collapse: collapse !important;
    font-variant-numeric: tabular-nums;
    font-size: 13.5px;
}}
.combined-table-wrap th,
.combined-table-wrap td {{
    border: 1px solid #e3e8ef;
}}
</style>
<div class="combined-table-wrap" id="{key}">{html}</div>
        """,
        unsafe_allow_html=True,
    )


def _kpi_card(col, label, value, delta=None, *, help_text=None):
    with col:
        st.metric(label, value, delta=delta, help=help_text)


# --- 스택형 막대 — 세련된 톤다운 팔레트 (Tableau 10 기반) ---
_STACK_PALETTE = [
    "#4E79A7",  # blue
    "#F28E2B",  # orange
    "#59A14F",  # green
    "#76B7B2",  # teal
    "#B07AA1",  # purple
    "#EDC948",  # gold
    "#E15759",  # red (마지막에 배치 — 강조 효과)
    "#9C755F",  # brown
    "#FF9DA7",  # pink
]
_RESERVE_COLOR = "#BAB0AC"  # 재고생산 — 뉴트럴 그레이


def _combo_line_totals(
    qty_by_line: list[int],
    sec_by_line: list[int],
    lines: list[str],
    *,
    bar_color: str = "#5b7a9c",
    title: str = "라인별 시간 + 수량",
    height: int = 380,
):
    """라인별 콤보 차트 — 시간(막대, 왼쪽 축) + 수량(선, 오른쪽 축).

    정합성 탭의 그래프와 동일한 디자인 언어로 통일.
    """
    if not lines:
        return None
    COLOR_QTY = "#e76f51"

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    # 시간 막대
    fig.add_trace(go.Bar(
        name="총 계획시간(초)",
        x=lines, y=sec_by_line,
        marker_color=bar_color,
        marker_line_color="rgba(255,255,255,0.9)",
        marker_line_width=1.0,
        text=[f"{v:,}" if v > 0 else "" for v in sec_by_line],
        textposition="inside", insidetextanchor="middle",
        textfont=dict(color="#ffffff", size=10),
        hovertemplate="<b>%{x}</b><br>시간 %{y:,}초<extra></extra>",
    ), secondary_y=False)

    # 수량 선
    fig.add_trace(go.Scatter(
        name="총 계획량(개)",
        x=lines, y=qty_by_line,
        mode="lines+markers+text",
        line=dict(color=COLOR_QTY, width=2.2, shape="spline", smoothing=0.6),
        marker=dict(size=9, color=COLOR_QTY, line=dict(color="#ffffff", width=2)),
        text=[f"{v:,}" if v > 0 else "" for v in qty_by_line],
        textposition="top center",
        textfont=dict(color=COLOR_QTY, size=11, family="-apple-system, sans-serif"),
        cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>수량 %{y:,}개<extra></extra>",
    ), secondary_y=True)

    annotations = [
        dict(x=l, y=s, text=f"<b>{s:,}</b>", showarrow=False,
             yshift=14, font=dict(size=12, color="#334155"), yref="y")
        for l, s in zip(lines, sec_by_line)
    ]

    fig.update_layout(
        height=height,
        margin=dict(t=70, b=50, l=60, r=60),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0,
                    font=dict(size=11, color="#475569"), bgcolor="rgba(0,0,0,0)"),
        annotations=annotations,
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        bargap=0.62,
        hoverlabel=dict(bgcolor="#1f2a44", font=dict(color="#ffffff", size=12)),
        font=dict(family="-apple-system, BlinkMacSystemFont, sans-serif"),
        title=dict(
            text=f"<span style='color:#1f2a44;font-weight:700'>{title}</span>",
            x=0.0, y=0.97, font=dict(size=14),
        ),
    )
    fig.update_xaxes(showgrid=False, showline=False, ticks="",
                     tickfont=dict(size=12, color="#334155"))
    fig.update_yaxes(
        title_text="시간(초)",
        title_font=dict(color="#94a3b8", size=11),
        tickfont=dict(color="#94a3b8", size=10),
        range=[0, max(sec_by_line + [1]) * 1.22],
        showgrid=True, gridcolor="#f1f5f9", zeroline=False,
        secondary_y=False,
    )
    fig.update_yaxes(
        title_text="수량(개)",
        title_font=dict(color=COLOR_QTY, size=11),
        tickfont=dict(color=COLOR_QTY, size=10),
        range=[0, max(qty_by_line + [1]) * 1.35],
        showgrid=False, zeroline=False,
        secondary_y=True,
    )
    return fig


def _line_totals_from_combined(combined: pd.DataFrame, line_col: str):
    """combined 표의 '합계' 컬럼에서 라인별 (수량 합계, 시간 합계)를 뽑는다."""
    if combined is None or combined.empty:
        return [], [], []
    qty_rows = combined[(combined[line_col] != "합계") & (combined["구분"] == "수량")]
    sec_rows = combined[(combined[line_col] != "합계") & (combined["구분"] == "시간")]
    if qty_rows.empty or sec_rows.empty:
        return [], [], []
    import re as _re
    def _k(s: str):
        m = _re.search(r"(\d+)\s*라인", str(s))
        return (int(m.group(1)) if m else 99, str(s))
    raw_lines = qty_rows[line_col].astype(str).tolist()
    order = sorted(range(len(raw_lines)), key=lambda i: _k(raw_lines[i]))
    lines = [raw_lines[i] for i in order]
    qty_vals = pd.to_numeric(qty_rows.iloc[order]["합계"], errors="coerce").fillna(0).astype(int).tolist()
    sec_vals = pd.to_numeric(sec_rows.iloc[order]["합계"], errors="coerce").fillna(0).astype(int).tolist()
    return lines, qty_vals, sec_vals


def _to_kor_date(s) -> str:
    """'2026-06-04' → '6월 4일'. 매칭 실패 시 원본 그대로 (예: '재고생산')."""
    import re as _re
    m = _re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", str(s))
    if not m:
        return str(s)
    return f"{int(m.group(2))}월 {int(m.group(3))}일"


def _combo_chart(
    combined: pd.DataFrame,
    *,
    line_col: str,
    line_filter: str | None = None,
    title: str = "출고일자별 추이",
    height: int = 380,
):
    """막대(수량) + 선(시간) 콤보 차트.

    line_filter=None 이면 "합계" 행 사용 (전체 추이).
    line_filter="1라인" 등이면 해당 라인의 출고일별 부하.
    """
    if combined is None or combined.empty:
        return None
    pick = line_filter if line_filter else "합계"
    qty_row = combined[(combined[line_col] == pick) & (combined["구분"] == "수량")]
    sec_row = combined[(combined[line_col] == pick) & (combined["구분"] == "시간")]
    if qty_row.empty or sec_row.empty:
        return None

    date_cols = [c for c in qty_row.columns if c not in (line_col, "구분", "합계")]
    sorted_dates = sorted([d for d in date_cols if d != "재고생산"])
    if "재고생산" in date_cols:
        sorted_dates += ["재고생산"]
    if not sorted_dates:
        return None

    qty_vals = [int(qty_row[d].iloc[0]) for d in sorted_dates]
    sec_vals = [int(sec_row[d].iloc[0]) for d in sorted_dates]
    x_labels = [_to_kor_date(d) for d in sorted_dates]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    # 막대 — 수량 (왼쪽 축)
    fig.add_trace(go.Bar(
        x=x_labels, y=qty_vals,
        name="계획량 (개)",
        marker_color="#F28E2B",
        marker_line_color="rgba(255,255,255,0.7)",
        marker_line_width=1.5,
        text=[f"{v:,}" if v > 0 else "" for v in qty_vals],
        textposition="inside",
        insidetextanchor="middle",
        textfont=dict(color="#ffffff", size=12),
        hovertemplate="<b>%{x}</b><br>수량 %{y:,}개<extra></extra>",
    ), secondary_y=False)
    # 선 — 시간 (오른쪽 축)
    fig.add_trace(go.Scatter(
        x=x_labels, y=sec_vals,
        name="계획시간 (초)",
        mode="lines+markers+text",
        line=dict(color="#1f2a44", width=2.5),
        marker=dict(size=11, color="#1f2a44", line=dict(color="#ffffff", width=2)),
        text=[f"{v:,}" if v > 0 else "" for v in sec_vals],
        textposition="top center",
        textfont=dict(color="#1f2a44", size=11),
        hovertemplate="<b>%{x}</b><br>시간 %{y:,}초<extra></extra>",
    ), secondary_y=True)

    ymax_q = max(qty_vals + [1])
    ymax_s = max(sec_vals + [1])

    fig.update_layout(
        title=dict(
            text=f"<span style='color:#1f2a44;font-weight:700'>{title}</span>",
            x=0.0, y=0.97, font=dict(size=14),
        ),
        height=height,
        margin=dict(t=70, b=40, l=60, r=60),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        bargap=0.30,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.06,
            xanchor="left", x=0,
            font=dict(size=11, color="#475569"),
            bgcolor="rgba(0,0,0,0)",
        ),
        hoverlabel=dict(bgcolor="#1f2a44", font=dict(color="#ffffff", size=12)),
    )
    fig.update_xaxes(
        showgrid=False, showline=False, ticks="",
        tickfont=dict(size=12, color="#475569"),
    )
    fig.update_yaxes(
        title_text="수량 (개)",
        title_font=dict(color="#F28E2B", size=11),
        tickfont=dict(color="#F28E2B", size=11),
        range=[0, ymax_q * 1.25],
        showgrid=True, gridcolor="#f1f5f9", zeroline=False,
        secondary_y=False,
    )
    fig.update_yaxes(
        title_text="시간 (초)",
        title_font=dict(color="#1f2a44", size=11),
        tickfont=dict(color="#1f2a44", size=11),
        range=[0, ymax_s * 1.25],
        showgrid=False, zeroline=False,
        secondary_y=True,
    )
    return fig


def _combo_small_multiples(
    combined: pd.DataFrame,
    *,
    line_col: str,
    cols: int = 3,
    row_height: int = 240,
):
    """라인별 콤보 차트를 격자로 배치 (Small multiples).

    각 셀: 한 라인의 출고일자 × (수량 막대 / 시간 선) 콤보.
    각 라인은 독립 Y축 (수량 스케일이 라인마다 달라도 패턴 잘 보임).
    """
    if combined is None or combined.empty:
        return None

    qty_rows = combined[(combined[line_col] != "합계") & (combined["구분"] == "수량")]
    if qty_rows.empty:
        return None

    import re as _re
    def _key(s: str):
        m = _re.search(r"(\d+)\s*라인", str(s))
        return (int(m.group(1)) if m else 99, str(s))

    lines = sorted(qty_rows[line_col].astype(str).unique(), key=_key)
    n = len(lines)
    rows = (n + cols - 1) // cols

    date_cols = [c for c in combined.columns if c not in (line_col, "구분", "합계")]
    sorted_dates = sorted([d for d in date_cols if d != "재고생산"])
    if "재고생산" in date_cols:
        sorted_dates += ["재고생산"]
    if not sorted_dates:
        return None

    specs = [[{"secondary_y": True} for _ in range(cols)] for _ in range(rows)]
    titles = [f"<span style='color:#1f2a44;font-weight:700'>{ln}</span>" for ln in lines]
    titles += [""] * (rows * cols - n)

    fig = make_subplots(
        rows=rows, cols=cols,
        specs=specs,
        subplot_titles=titles,
        vertical_spacing=0.18,
        horizontal_spacing=0.09,
    )

    for idx, ln in enumerate(lines):
        r = idx // cols + 1
        c = idx % cols + 1
        qty_row = combined[(combined[line_col] == ln) & (combined["구분"] == "수량")]
        sec_row = combined[(combined[line_col] == ln) & (combined["구분"] == "시간")]
        if qty_row.empty or sec_row.empty:
            continue

        qty_vals = [int(qty_row[d].iloc[0]) for d in sorted_dates]
        sec_vals = [int(sec_row[d].iloc[0]) for d in sorted_dates]
        x_labels = [_to_kor_date(d) for d in sorted_dates]

        fig.add_trace(go.Bar(
            x=x_labels, y=qty_vals,
            marker_color="#F28E2B",
            marker_line_color="rgba(255,255,255,0.7)",
            marker_line_width=1.2,
            text=[f"{v}" if v > 0 else "" for v in qty_vals],
            textposition="inside", insidetextanchor="middle",
            textfont=dict(color="#ffffff", size=10),
            showlegend=(idx == 0),
            name="계획량(개)",
            hovertemplate=f"<b>{ln}</b><br>%{{x}}<br>수량 %{{y:,}}개<extra></extra>",
        ), row=r, col=c, secondary_y=False)

        fig.add_trace(go.Scatter(
            x=x_labels, y=sec_vals,
            mode="lines+markers",
            line=dict(color="#1f2a44", width=2),
            marker=dict(size=7, color="#1f2a44", line=dict(color="#ffffff", width=1.5)),
            showlegend=(idx == 0),
            name="계획시간(초)",
            hovertemplate=f"<b>{ln}</b><br>%{{x}}<br>시간 %{{y:,}}초<extra></extra>",
        ), row=r, col=c, secondary_y=True)

    fig.update_layout(
        height=row_height * rows + 100,
        margin=dict(t=80, b=40, l=40, r=20),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        bargap=0.30,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="left", x=0,
            font=dict(size=11, color="#475569"),
            bgcolor="rgba(0,0,0,0)",
        ),
        hoverlabel=dict(bgcolor="#1f2a44", font=dict(color="#ffffff", size=11)),
    )

    fig.update_xaxes(
        showgrid=False, showline=False, ticks="",
        tickfont=dict(size=10, color="#475569"),
        tickangle=-30,
    )
    fig.update_yaxes(
        secondary_y=False,
        tickfont=dict(color="#F28E2B", size=10),
        showgrid=True, gridcolor="#f1f5f9", zeroline=False,
    )
    fig.update_yaxes(
        secondary_y=True,
        tickfont=dict(color="#1f2a44", size=10),
        showgrid=False, zeroline=False,
    )
    # 서브플롯 타이틀 위치 보정
    for ann in fig.layout.annotations:
        ann.font.size = 12
    return fig


def _heatmap_combined(
    combined: pd.DataFrame,
    *,
    line_col: str,
    title_qty: str = "수량 (개)",
    title_sec: str = "시간 (초)",
    height: int = 560,
):
    """라인 × 출고일자 히트맵 — 수량/시간을 위아래 서브플롯에 동시 표시.

    - 수량: 옅은 옐로우 → 진한 오렌지
    - 시간: 옅은 블루 → 진한 네이비
    - 0 셀은 텍스트 숨김 (노이즈 제거)
    - 진한 셀은 흰색 글씨, 옅은 셀은 어두운 글씨 (자동)
    """
    if combined is None or combined.empty:
        return None
    qty_row = combined[(combined[line_col] != "합계") & (combined["구분"] == "수량")]
    sec_row = combined[(combined[line_col] != "합계") & (combined["구분"] == "시간")]
    if qty_row.empty or sec_row.empty:
        return None

    date_cols = [c for c in qty_row.columns if c not in (line_col, "구분", "합계")]
    if not date_cols:
        return None
    # 정렬: 날짜 오름차순 + 재고생산 맨 뒤
    sorted_dates = sorted([d for d in date_cols if d != "재고생산"])
    if "재고생산" in date_cols:
        sorted_dates = sorted_dates + ["재고생산"]

    # 라인 정렬 (라인번호 오름차순)
    import re as _re
    def _line_key(s: str):
        m = _re.search(r"(\d+)\s*라인", str(s))
        return (int(m.group(1)) if m else 99, str(s))
    raw_lines = qty_row[line_col].astype(str).tolist()
    order = sorted(range(len(raw_lines)), key=lambda i: _line_key(raw_lines[i]))
    lines = [raw_lines[i] for i in order]

    qty_mat = (
        qty_row.iloc[order][sorted_dates]
        .apply(pd.to_numeric, errors="coerce").fillna(0).astype(int).values
    )
    sec_mat = (
        sec_row.iloc[order][sorted_dates]
        .apply(pd.to_numeric, errors="coerce").fillna(0).astype(int).values
    )

    # 0 값 텍스트 숨기기 + 천단위 콤마
    qty_text = [[(f"{v:,}" if v > 0 else "") for v in row] for row in qty_mat]
    sec_text = [[(f"{v:,}" if v > 0 else "") for v in row] for row in sec_mat]

    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=(
            f"<span style='color:#1f2a44;font-weight:700'>{title_qty}</span>",
            f"<span style='color:#1f2a44;font-weight:700'>{title_sec}</span>",
        ),
        vertical_spacing=0.16,
        shared_xaxes=False,
    )

    # 수량 히트맵 — 워머 톤
    qty_scale = [
        [0.00, "#ffffff"],
        [0.15, "#fff4e6"],
        [0.40, "#ffd9a8"],
        [0.70, "#f59e0b"],
        [1.00, "#b45309"],
    ]
    fig.add_trace(go.Heatmap(
        z=qty_mat, x=sorted_dates, y=lines,
        colorscale=qty_scale,
        text=qty_text, texttemplate="%{text}",
        textfont=dict(size=12, color="#1f2a44"),
        showscale=False,
        xgap=2, ygap=2,
        hovertemplate="<b>%{y}</b><br>%{x}<br>수량 %{z:,}개<extra></extra>",
        zmin=0, zmax=max(int(qty_mat.max()) if qty_mat.size else 1, 1),
    ), row=1, col=1)

    # 시간 히트맵 — 쿨러 톤
    sec_scale = [
        [0.00, "#ffffff"],
        [0.15, "#e0ecff"],
        [0.40, "#a5c4f5"],
        [0.70, "#3b82f6"],
        [1.00, "#1e3a8a"],
    ]
    fig.add_trace(go.Heatmap(
        z=sec_mat, x=sorted_dates, y=lines,
        colorscale=sec_scale,
        text=sec_text, texttemplate="%{text}",
        textfont=dict(size=11, color="#1f2a44"),
        showscale=False,
        xgap=2, ygap=2,
        hovertemplate="<b>%{y}</b><br>%{x}<br>시간 %{z:,}초<extra></extra>",
        zmin=0, zmax=max(int(sec_mat.max()) if sec_mat.size else 1, 1),
    ), row=2, col=1)

    fig.update_layout(
        height=height,
        margin=dict(t=60, b=30, l=130, r=30),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(family="-apple-system, sans-serif"),
    )
    # 공통 축 스타일
    fig.update_xaxes(
        side="top", showgrid=False, showline=False, ticks="",
        tickfont=dict(size=11, color="#475569"),
    )
    fig.update_yaxes(
        autorange="reversed", showgrid=False, showline=False, ticks="",
        tickfont=dict(size=12, color="#1f2a44"),
    )
    # 서브플롯 제목 위치 보정
    for ann in fig.layout.annotations:
        ann.font.size = 13
        ann.x = 0
        ann.xanchor = "left"

    return fig


def _is_dark_color(hex_color: str) -> bool:
    """막대 색에 따라 흰 글씨/검은 글씨 자동 결정 (WCAG 휘도 근사)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return lum < 150


def _stack_bar(
    combined: pd.DataFrame,
    *,
    line_col: str,
    kind: str,
    title: str,
    height: int = 380,
    label_min_ratio: float = 0.06,  # 합계 대비 6% 미만은 라벨 숨김 (노이즈 제거)
):
    """라인 × 출고일자 스택 바.

    세련화 포인트
    - 톤다운된 카테고리컬 팔레트 (Tableau 10 기반)
    - 작은 값(합계의 6% 미만) 라벨 숨김 → 노이즈 제거
    - 배경/그리드 채도 낮춤, 막대 사이 여백 ↑
    - 막대 색에 따라 텍스트 색 자동(밝은 막대=어두운 글씨, 어두운 막대=흰 글씨)
    """
    if combined is None or combined.empty:
        return None
    row = combined[(combined[line_col] != "합계") & (combined["구분"] == kind)].copy()
    if row.empty:
        return None

    date_cols = [c for c in row.columns if c not in (line_col, "구분", "합계")]
    if not date_cols:
        return None

    # 컬럼 순서: 날짜 오름차순 + 재고생산 맨 뒤
    sorted_dates = [d for d in date_cols if d != "재고생산"]
    if "재고생산" in date_cols:
        sorted_dates = sorted_dates + ["재고생산"]

    lines = row[line_col].astype(str).tolist()
    totals = pd.to_numeric(row["합계"], errors="coerce").fillna(0).astype(int).tolist()

    # 색상 매핑 — 한 그래프 안에서 출고일자별 고유 색
    color_map: dict[str, str] = {}
    palette_idx = 0
    for d in sorted_dates:
        if d == "재고생산":
            color_map[d] = _RESERVE_COLOR
        else:
            color_map[d] = _STACK_PALETTE[palette_idx % len(_STACK_PALETTE)]
            palette_idx += 1

    unit_label = "개" if kind == "수량" else "초"

    fig = go.Figure()
    for d in sorted_dates:
        vals = pd.to_numeric(row[d], errors="coerce").fillna(0).astype(int).tolist()
        # 작은 조각은 라벨 숨김
        text_inside = [
            f"{v:,}" if v > 0 and (totals[i] > 0 and v / totals[i] >= label_min_ratio) else ""
            for i, v in enumerate(vals)
        ]
        bar_color = color_map[d]
        text_color = "#ffffff" if _is_dark_color(bar_color) else "#1f2a44"
        fig.add_trace(go.Bar(
            name=str(d),
            x=lines, y=vals,
            marker_color=bar_color,
            marker_line_color="rgba(255,255,255,0.85)",
            marker_line_width=1.5,
            text=text_inside,
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(size=11, color=text_color, family="-apple-system, sans-serif"),
            hovertemplate=f"<b>%{{x}}</b><br>{d}  ·  %{{y:,}}{unit_label}<extra></extra>",
        ))

    # 막대 위 합계 라벨
    ymax = max(totals + [1])
    annotations = [
        dict(x=x, y=t, text=f"<b>{t:,}</b>", showarrow=False,
             yshift=14, font=dict(size=14, color="#1f2a44"))
        for x, t in zip(lines, totals)
    ]

    fig.update_layout(
        title=dict(
            text=f"<span style='color:#1f2a44;font-weight:700'>{title}</span>",
            x=0.0, y=0.97,
            font=dict(size=14),
        ),
        height=height,
        margin=dict(t=70, b=40, l=55, r=20),
        barmode="stack",
        bargap=0.38,
        xaxis=dict(
            title="",
            tickfont=dict(size=12, color="#475569"),
            showline=False,
            showgrid=False,
            ticks="",
        ),
        yaxis=dict(
            title=dict(text=f"{kind} ({unit_label})",
                       font=dict(size=11, color="#94a3b8")),
            range=[0, ymax * 1.20],
            showgrid=True,
            gridcolor="#f1f5f9",
            zeroline=False,
            showline=False,
            ticks="",
            tickfont=dict(size=11, color="#94a3b8"),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.06,
            xanchor="left", x=0,
            font=dict(size=11, color="#475569"),
            bgcolor="rgba(0,0,0,0)",
            title=dict(text=""),
            itemsizing="constant",
            traceorder="normal",
        ),
        annotations=annotations,
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        hoverlabel=dict(bgcolor="#1f2a44", font=dict(color="#ffffff", size=12)),
    )
    return fig


@st.dialog("라인 배정 상세", width="large")
def _show_line_dialog(detail_df: pd.DataFrame, line_name: str):
    """선택된 라인의 출고일자별 수주건 상세를 모달로 표시."""
    st.markdown(f"### 🚚 {line_name}")

    if detail_df is None or detail_df.empty:
        st.info("배정된 품목이 없습니다.")
        return

    total_qty = int(detail_df["수량"].fillna(0).sum()) if "수량" in detail_df.columns else 0
    total_sec = int(detail_df["작업시간(초)"].fillna(0).sum()) if "작업시간(초)" in detail_df.columns else 0
    n_orders = detail_df["수주건명"].dropna().nunique() if "수주건명" in detail_df.columns else 0

    m1, m2, m3 = st.columns(3)
    m1.metric("총 수량", f"{total_qty:,}")
    m2.metric("총 작업시간", f"{total_sec:,} 초")
    m3.metric("수주건 수", f"{n_orders}")

    st.divider()

    # 출고일자별 그룹
    ship_col = "출고일자" if "출고일자" in detail_df.columns else None
    if ship_col is None:
        st.dataframe(detail_df, use_container_width=True, hide_index=True)
        return

    df = detail_df.copy()
    df[ship_col] = df[ship_col].fillna("재고생산")
    groups = df.groupby(ship_col, sort=True, dropna=False)

    for date, sub in groups:
        sub_qty = int(sub["수량"].fillna(0).sum())
        sub_sec = int(sub["작업시간(초)"].fillna(0).sum())
        with st.expander(f"📅 **{date}** — 수량 {sub_qty}개 / 시간 {sub_sec:,}초", expanded=True):
            agg_kwargs = {
                "수량": ("수량", "sum"),
                "작업시간_초": ("작업시간(초)", "sum"),
                "품목코드": ("제품코드", lambda s: ", ".join(s.dropna().astype(str).unique()[:8])),
            }
            if "품목명칭" in sub.columns:
                agg_kwargs["품목명칭"] = (
                    "품목명칭",
                    lambda s: ", ".join(s.dropna().astype(str).unique()[:8]),
                )
            if "색상" in sub.columns:
                agg_kwargs["색상"] = (
                    "색상",
                    lambda s: ", ".join(s.dropna().astype(str).unique()[:8]),
                )
            order_summary = (
                sub.groupby("수주건명", dropna=False)
                .agg(**agg_kwargs)
                .reset_index()
                .sort_values("수량", ascending=False)
            )
            order_summary["수량"] = order_summary["수량"].fillna(0).astype(int)
            order_summary["작업시간_초"] = order_summary["작업시간_초"].fillna(0).astype(int)
            order_summary["수주건명"] = order_summary["수주건명"].fillna("(미지정)")

            # 컬럼 순서: 수주건명 · 수량 · 작업시간 · 품목명칭 · 품목코드 · 색상
            preferred = ["수주건명", "수량", "작업시간_초", "품목명칭", "품목코드", "색상"]
            cols = [c for c in preferred if c in order_summary.columns] + [
                c for c in order_summary.columns if c not in preferred
            ]
            order_summary = order_summary[cols]

            st.dataframe(
                order_summary,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "수주건명": st.column_config.TextColumn(
                        "수주건명", width="medium",
                        help="같은 수주건명은 한 라인에 묶여 배정됩니다.",
                    ),
                    "수량": st.column_config.NumberColumn(
                        "수량", width="small", format="%d",
                    ),
                    "작업시간_초": st.column_config.NumberColumn(
                        "작업시간(초)", width="small", format="%d",
                    ),
                    "품목명칭": st.column_config.TextColumn(
                        "품목명칭", width="large",
                    ),
                    "품목코드": st.column_config.TextColumn(
                        "품목코드", width="medium",
                    ),
                    "색상": st.column_config.TextColumn(
                        "색상", width="small",
                    ),
                },
            )


def _handle_upload(kind: storage.Kind, uploaded, label: str):
    """동일 파일이 rerun 사이에 다시 저장되지 않도록 file_id로 가드한다."""
    if uploaded is None:
        return
    seen_key = f"_saved_id_{kind}"
    # streamlit UploadedFile에는 .file_id 또는 .id 가 있다. 없으면 (name,size)로 키 생성.
    fid = getattr(uploaded, "file_id", None) or getattr(uploaded, "id", None) or f"{uploaded.name}:{uploaded.size}"
    if st.session_state.get(seen_key) == fid:
        return  # 이미 저장 완료된 업로드
    try:
        storage.save_upload(kind, uploaded.getvalue(), uploaded.name)
        st.session_state[seen_key] = fid
        st.sidebar.success(f"{label} 저장됨: {uploaded.name}")
    except Exception as e:
        st.sidebar.error(f"{label} 저장 실패: {e}")


def sidebar_uploads():
    # 브랜드 헤더 + 모드 배지
    role_badge = (
        "<span style='background:#c8945a;color:#2d2017;font-size:9px;"
        "font-weight:700;padding:2px 8px;border-radius:8px;letter-spacing:1px;'>"
        "ADMIN</span>"
        if is_admin() else
        "<span style='background:#5b7a9c;color:#f5ede0;font-size:9px;"
        "font-weight:700;padding:2px 8px;border-radius:8px;letter-spacing:1px;'>"
        "VIEWER</span>"
    )
    st.sidebar.markdown(
        f"""
<div class='sidebar-brand'>
    <div class='sb-logo'>🛋️ SIDIZ SOFA</div>
    <div class='sb-sub'>PRODUCTION DISPATCH</div>
    <div style='margin-top:6px;'>{role_badge}</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # 파일 업로드 — 관리자만
    if is_admin():
        st.sidebar.markdown("<div class='sb-section-title'>📤 데이터 업로드</div>", unsafe_allow_html=True)
        st.sidebar.caption("최신 파일 1개만 유지됩니다.")

        cu = st.sidebar.file_uploader(
            "누적분배",
            type=["xls", "xlsx"], key="up_cu",
            help="grd_list_*.xls (누적 생산 데이터)",
        )
        _handle_upload("cumulative", cu, "누적분배")

        da = st.sidebar.file_uploader(
            "당일분배",
            type=["xls", "xlsx"], key="up_da",
            help="grd_list_*.xls (당일 생산 데이터)",
        )
        _handle_upload("daily", da, "당일분배")

    # 저장 후 최신 메타 표시 — 카드 형태 + 삭제 버튼
    meta = storage.latest_meta()
    if meta.get("cumulative") or meta.get("daily"):
        st.sidebar.markdown(
            "<div class='sb-section-title'>📁 현재 데이터</div>",
            unsafe_allow_html=True,
        )

    def _file_card_with_delete(kind: str, label_emoji: str, label_text: str):
        m = meta.get(kind)
        if not m:
            return
        with st.sidebar.container():
            if is_admin():
                col_card, col_btn = st.columns([4, 1], gap="small")
                with col_card:
                    st.markdown(
                        f"<div class='sb-file-card'>"
                        f"<div class='sb-file-meta'>{label_emoji} {label_text}</div>"
                        f"<div class='sb-file-name'>{m['original_name']}</div>"
                        f"<div class='sb-file-meta'>업로드 {m['uploaded_at']}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                with col_btn:
                    if st.button("🗑️", key=f"del_{kind}",
                                 help=f"{label_text} 데이터 삭제",
                                 use_container_width=True):
                        storage.delete_upload(kind)  # type: ignore[arg-type]
                        st.session_state.pop(f"_saved_id_{kind}", None)
                        st.rerun()
            else:
                # 뷰어 — 삭제 버튼 없이 카드만
                st.sidebar.markdown(
                    f"<div class='sb-file-card'>"
                    f"<div class='sb-file-meta'>{label_emoji} {label_text}</div>"
                    f"<div class='sb-file-name'>{m['original_name']}</div>"
                    f"<div class='sb-file-meta'>업로드 {m['uploaded_at']}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    _file_card_with_delete("cumulative", "📊", "누적분배")
    _file_card_with_delete("daily", "🚚", "당일분배")

    # 라인 인원
    st.sidebar.markdown(
        "<div class='sb-section-title'>👥 라인 인원 (고정)</div>",
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        """
<div style='font-size: 12px; line-height: 1.8;'>
&nbsp;&nbsp;🪡 <b>1·3·4라인</b> · 2명<br>
&nbsp;&nbsp;✂️ <b>5라인</b> · 1명
</div>
        """,
        unsafe_allow_html=True,
    )

    # 하단 로그아웃 / 모드 전환
    st.sidebar.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)
    if st.sidebar.button("🚪 로그아웃 / 모드 변경", use_container_width=True,
                         key="btn_logout"):
        st.session_state.pop("_authed", None)
        st.session_state.pop("_role", None)
        st.session_state.pop("_show_admin_form", None)
        st.rerun()


def tab_cumulative():
    df = _load_df("cumulative")
    if df is None:
        st.info("좌측에서 **누적분배 파일**을 업로드하세요.")
        return

    res = process_cumulative(df)
    combined = res["combined"]
    detail = res["detail"]

    # --- KPI 카드 ---
    total_sec = int(detail["작업시간(초)"].fillna(0).sum()) if "작업시간(초)" in detail.columns else 0
    total_qty = int(detail["수량"].fillna(0).sum()) if "수량" in detail.columns else 0
    active_lines = combined[combined["생산라인"] != "합계"]["생산라인"].nunique() if not combined.empty else 0
    ship_dates = [c for c in combined.columns if c not in ("생산라인", "구분", "합계", "재고생산")]

    c1, c2, c3, c4 = st.columns(4)
    _kpi_card(c1, "총 계획시간", f"{total_sec:,} 초", help_text="필터링 후 detail 기준")
    _kpi_card(c2, "총 계획량", f"{total_qty:,} 개")
    _kpi_card(c3, "활성 라인", f"{active_lines} 개")
    _kpi_card(c4, "출고 예정일", f"{len(ship_dates)} 일")

    st.divider()

    # --- 라인별 종합 콤보 (시간 막대 + 수량 선) ---
    st.markdown("#### 라인별 시간 + 수량")
    if combined is not None and not combined.empty:
        lines_x, qty_v, sec_v = _line_totals_from_combined(combined, line_col="생산라인")
        if lines_x:
            fig_total = _combo_line_totals(
                qty_v, sec_v, lines_x,
                bar_color="#cfd8e3",
                title="누적 — 라인별 시간(막대) + 수량(선)",
            )
            if fig_total is not None:
                st.plotly_chart(fig_total, use_container_width=True)

    # --- 출고일자별 추이 (드릴다운) ---
    st.markdown("#### 출고일자별 추이")
    if combined is not None and not combined.empty:
        line_opts = [l for l in combined["생산라인"].unique() if l != "합계"]
        sel_line = st.selectbox(
            "표시 모드",
            options=["📊 라인별 (전체 그리드)", "📈 전체 합계만"] + [f"🔎 {l}" for l in line_opts],
            key="cumulative_combo_filter",
            label_visibility="collapsed",
        )
        if sel_line.startswith("📊"):
            fig = _combo_small_multiples(combined, line_col="생산라인")
        else:
            lf = None if sel_line.startswith("📈") else sel_line.replace("🔎 ", "")
            title = "전체 합계 추이" if lf is None else f"{lf} 추이"
            fig = _combo_chart(combined, line_col="생산라인", line_filter=lf, title=title)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        st.caption("주황 막대 = 계획량 · 네이비 선 = 계획시간 · '라인별' 모드는 모든 라인을 동시에 비교")

    st.markdown("#### 생산라인 × 출고일자 — 수량/시간")
    st.caption("재공완료(Y) 제외 · 1·3·4·5라인(분배 대상) + 8·9라인(참고) · 라인 셀이 (수량/시간) 두 줄을 묶어서 표시")
    _render_merged_combined(combined, line_col="생산라인", key="cumulative_merged")

    # 라인 선택 — 팝업 호출 (조회용)
    if combined is not None and not combined.empty:
        line_options = [l for l in combined["생산라인"].unique() if l != "합계"]
        sel = st.selectbox(
            "🔎 라인 선택 — 수주건 상세 팝업",
            options=["(선택)"] + list(line_options),
            key="cumulative_line_picker",
        )
        _dlg_key = "_last_dlg_cumul"
        if sel and sel != "(선택)":
            if st.session_state.get(_dlg_key) != sel:
                st.session_state[_dlg_key] = sel
                line_detail = detail[detail["라인"] == sel] if "라인" in detail.columns else detail.iloc[0:0]
                _show_line_dialog(line_detail, sel)
        else:
            st.session_state.pop(_dlg_key, None)

    with st.expander(f"📄 상세 데이터 ({len(detail)}건)", expanded=False):
        st.dataframe(detail, use_container_width=True, hide_index=True)

    cdl1, cdl2 = st.columns(2)
    with cdl1:
        st.download_button("⬇️ 상세 CSV",
                           detail.to_csv(index=False).encode("utf-8-sig"),
                           "누적분배_상세.csv", "text/csv")
    with cdl2:
        st.download_button("⬇️ 라인×출고일자 CSV",
                           combined.to_csv(index=False).encode("utf-8-sig"),
                           "누적분배_라인별.csv", "text/csv")


def tab_daily(rules: LineRules, policy: GroupPolicy, split_lock: SplitLock):
    df = _load_df("daily")
    if df is None:
        st.info("좌측에서 **당일분배 파일**을 업로드하세요.")
        return

    res = distribute_daily(df, rules, group_policy=policy, split_lock=split_lock)
    summary = res["summary"]
    combined = res["combined"]
    detail = res["detail"]
    unassigned = res.get("unassigned_count", 0)

    # --- KPI 카드 ---
    dist_rows = summary[summary["구분"] == "분배"] if "구분" in summary.columns else summary
    excl_rows = summary[summary["구분"] == "제외"] if "구분" in summary.columns else pd.DataFrame()

    total_dist_sec = int(dist_rows["총 계획시간(초)"].sum()) if not dist_rows.empty else 0
    total_dist_qty = int(dist_rows["총 계획량"].sum()) if not dist_rows.empty else 0
    total_excl_sec = int(excl_rows["총 계획시간(초)"].sum()) if not excl_rows.empty else 0

    # 인당 평균 부하 (분배 라인만, 인원 수 합으로 가중평균)
    if not dist_rows.empty:
        weights = pd.to_numeric(dist_rows["인원"], errors="coerce").fillna(0)
        loads = pd.to_numeric(dist_rows["인당 부하(초)"], errors="coerce").fillna(0)
        avg_load = int((loads * weights).sum() / max(1, weights.sum()))
    else:
        avg_load = 0

    c1, c2, c3, c4 = st.columns(4)
    _kpi_card(c1, "분배 계획시간", f"{total_dist_sec:,} 초",
              help_text="1·3·4·5라인 합계")
    _kpi_card(c2, "분배 계획량", f"{total_dist_qty:,} 개")
    _kpi_card(c3, "인당 평균부하", f"{avg_load:,} 초")
    _kpi_card(c4, "미배정 / 제외시간",
              f"{unassigned} / {total_excl_sec:,}",
              delta=("⚠️ 작업불가 품목" if unassigned else "정상"),
              help_text="미배정 = 어느 라인에서도 작업 불가한 품목 수")

    st.divider()

    # --- 라인별 종합 콤보 (시간 막대 + 수량 선) ---
    st.markdown("#### 라인별 시간 + 수량")
    if combined is not None and not combined.empty:
        lines_x, qty_v, sec_v = _line_totals_from_combined(combined, line_col="배정라인")
        if lines_x:
            fig_total = _combo_line_totals(
                qty_v, sec_v, lines_x,
                bar_color="#5b7a9c",
                title="당일 — 라인별 시간(막대) + 수량(선)",
            )
            if fig_total is not None:
                st.plotly_chart(fig_total, use_container_width=True)

    # --- 출고일자별 추이 (드릴다운) ---
    st.markdown("#### 출고일자별 추이")
    if combined is not None and not combined.empty:
        line_opts = [l for l in combined["배정라인"].unique() if l != "합계"]
        sel_line = st.selectbox(
            "표시 모드",
            options=["📊 라인별 (전체 그리드)", "📈 전체 합계만"] + [f"🔎 {l}" for l in line_opts],
            key="daily_combo_filter",
            label_visibility="collapsed",
        )
        if sel_line.startswith("📊"):
            fig = _combo_small_multiples(combined, line_col="배정라인")
        else:
            lf = None if sel_line.startswith("📈") else sel_line.replace("🔎 ", "")
            title = "전체 합계 추이" if lf is None else f"{lf} 추이"
            fig = _combo_chart(combined, line_col="배정라인", line_filter=lf, title=title)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        st.caption("주황 막대 = 계획량 · 네이비 선 = 계획시간 · '라인별' 모드는 모든 라인을 동시에 비교")

    # --- 부하 요약 표 (행 클릭 → 팝업) ---
    st.markdown("#### 라인별 부하 요약")
    st.caption("'분배' = 1·3·4·5라인 자동분배 · '제외' = 8·9라인 등 원본 라인 유지 · 💡 **행을 클릭하면** 해당 라인의 수주건 상세 팝업")

    summary_disp = summary.copy()
    # Streamlit dataframe selection은 Styler와 동시 사용이 불완전해 일반 DataFrame을 우선
    event_sum = st.dataframe(
        summary_disp,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="daily_summary_select",
        column_config={
            "라인": st.column_config.TextColumn("라인", width="small"),
            "구분": st.column_config.TextColumn("구분", width="small"),
            "인원": st.column_config.TextColumn("인원", width="small"),
            "총 계획시간(초)": st.column_config.NumberColumn("총 계획시간(초)", format="%d", width="medium"),
            "총 계획량": st.column_config.NumberColumn("총 계획량", format="%d", width="medium"),
            "인당 부하(초)": st.column_config.NumberColumn("인당 부하(초)", format="%d", width="medium"),
        },
    )
    sel_rows = []
    if event_sum is not None and getattr(event_sum, "selection", None) is not None:
        sel_rows = list(getattr(event_sum.selection, "rows", []) or [])
    # 가드: 같은 선택이 유지된 상태로 다른 탭 작업의 rerun이 일어나도 다이얼로그가 재호출되지 않도록
    _dlg_key = "_last_dlg_daily"
    if sel_rows:
        row_idx = sel_rows[0]
        if 0 <= row_idx < len(summary_disp):
            line_name = str(summary_disp.iloc[row_idx]["라인"])
            if line_name and line_name != "미배정":
                if st.session_state.get(_dlg_key) != line_name:
                    st.session_state[_dlg_key] = line_name
                    line_detail = detail[detail["배정라인"] == line_name]
                    _show_line_dialog(line_detail, line_name)
    else:
        st.session_state.pop(_dlg_key, None)

    # --- 배정 결과 표 (조회용) ---
    st.markdown("#### 배정 결과 — 라인 × 출고일자 (수량/시간)")
    _render_merged_combined(combined, line_col="배정라인", key="daily_merged")

    # --- 배정 상세 ---
    with st.expander(f"📄 배정 상세 ({len(detail)}건)", expanded=False):
        lines_filter = st.multiselect(
            "라인 필터",
            options=sorted(detail["배정라인"].dropna().unique().tolist()),
        )
        show = detail
        if lines_filter:
            show = show[show["배정라인"].isin(lines_filter)]
        st.dataframe(show, use_container_width=True, hide_index=True)

    cdl1, cdl2 = st.columns(2)
    with cdl1:
        st.download_button("⬇️ 배정 상세 CSV",
                           detail.to_csv(index=False).encode("utf-8-sig"),
                           "당일분배_배정상세.csv", "text/csv")
    with cdl2:
        st.download_button("⬇️ 라인×출고일자 CSV",
                           combined.to_csv(index=False).encode("utf-8-sig"),
                           "당일분배_라인별.csv", "text/csv")


def tab_rules(rules: LineRules, split_lock: SplitLock, master: ItemMaster):
    st.caption(
        "라인 단위 규칙을 한 곳에서 관리합니다.\n"
        "• **작업불가**: 특정 라인에서 못 하는 품목코드/패턴을 차단\n"
        "• **분할 락**: 품목코드를 라인별 비율로 강제 배정"
    )

    top = st.tabs(["🚫 작업불가 규칙", "🎯 분할 락 (라인 비율)"])

    # === 작업불가 규칙 ===
    with top[0]:
        _tab_forbid_rules(rules)

    # === 분할 락 ===
    with top[1]:
        _tab_split_lock(split_lock, master)


def _tab_forbid_rules(rules: LineRules):
    st.caption("각 라인이 '작업 불가'인 품목코드를 등록합니다. 즉시 분배에 반영됩니다.")

    tabs = st.tabs(["UI 편집", "파일 업로드", "현재 규칙(JSON)"])

    # --- UI 편집 ---
    with tabs[0]:
        for ln in DAILY_TARGET_LINES:
            with st.expander(f"{ln}라인 (인원 {LINE_HEADCOUNT[ln]}명)", expanded=False):
                key = str(ln)
                exact = rules.exact.get(key, [])
                patt = rules.pattern.get(key, [])

                exact_text = st.text_area(
                    f"{ln}라인 — 작업 불가 품목코드 (한 줄에 하나)",
                    value="\n".join(exact),
                    key=f"exact_{ln}",
                    height=120,
                )
                patt_text = st.text_area(
                    f"{ln}라인 — 작업 불가 패턴(정규식, 한 줄에 하나) — 예: ^ACSF, .*HN$",
                    value="\n".join(patt),
                    key=f"patt_{ln}",
                    height=80,
                )
                if st.button(f"💾 {ln}라인 규칙 저장", key=f"save_{ln}"):
                    rules.exact[key] = [s.strip() for s in exact_text.splitlines() if s.strip()]
                    rules.pattern[key] = [s.strip() for s in patt_text.splitlines() if s.strip()]
                    save_rules(storage.RULES_PATH, rules)
                    st.success(f"{ln}라인 규칙 저장 완료")
                    st.rerun()

    # --- 파일 업로드 ---
    with tabs[1]:
        with st.expander("📖 파일 업로드 사용법", expanded=True):
            st.markdown("""
**필수 컬럼 3개** (한 행 = 한 규칙):

| 컬럼 | 의미 | 예시 |
|---|---|---|
| `line` | 작업 불가인 라인 번호 | `1`, `3`, `4`, `5` |
| `item_code` | 차단할 품목코드 또는 정규식 패턴 | `ACSB0271BN`, `^ACSF` |
| `type` | `exact` (정확 일치) / `pattern` (정규식). 생략 시 `exact` | `exact`, `pattern` |

**예시 CSV** (메모장으로도 작성 가능, UTF-8 권장):
```
line,item_code,type
1,ACSB0271BN,exact
1,ACSB3004HN,exact
3,ACSF0461JN,exact
5,^ACSF,pattern
4,HN$,pattern
```
의미:
- 1라인 → `ACSB0271BN`, `ACSB3004HN` 작업 불가
- 3라인 → `ACSF0461JN` 작업 불가
- 5라인 → `ACSF`로 시작하는 모든 품목 작업 불가
- 4라인 → `HN`으로 끝나는 모든 품목 작업 불가

**엑셀(.xlsx)도 가능** — 첫 시트의 컬럼명이 위와 같으면 됩니다.

**병합 vs 대체**:
- ✅ `기존 규칙을 모두 대체` **체크 해제** (기본): 기존 규칙에 **추가 병합**
- ✅ **체크**: 기존 규칙을 **전부 삭제** 후 새 파일로 교체
""")
        up = st.file_uploader("규칙 파일 업로드 (.xlsx / .csv)", type=["xlsx", "csv"], key="up_rules")
        replace = st.checkbox("기존 규칙을 모두 대체", value=False)
        if up is not None:
            try:
                if up.name.lower().endswith(".csv"):
                    rdf = pd.read_csv(up)
                else:
                    rdf = pd.read_excel(up)
                new_rules = rules_from_dataframe(rdf)
                if replace:
                    merged = new_rules
                else:
                    merged = LineRules(
                        exact={**rules.exact},
                        pattern={**rules.pattern},
                    )
                    for k, v in new_rules.exact.items():
                        merged.exact[k] = sorted(set(merged.exact.get(k, []) + v))
                    for k, v in new_rules.pattern.items():
                        merged.pattern[k] = sorted(set(merged.pattern.get(k, []) + v))
                save_rules(storage.RULES_PATH, merged)
                st.success(f"{len(rdf)}건 규칙 반영 완료 ({'대체' if replace else '병합'})")
                st.rerun()
            except Exception as e:
                st.error(f"규칙 파일 읽기 실패: {e}")

    # --- 현재 규칙 JSON ---
    with tabs[2]:
        st.json(rules.to_dict())
        st.download_button(
            "⬇️ line_rules.json 다운로드",
            data=json.dumps(rules.to_dict(), ensure_ascii=False, indent=2),
            file_name="line_rules.json",
            mime="application/json",
        )
        if st.button("🧹 모든 규칙 초기화", type="secondary"):
            save_rules(storage.RULES_PATH, LineRules())
            st.rerun()


def _tab_split_lock(lock: SplitLock, master: ItemMaster):
    st.markdown(
        """
특정 품목코드를 **라인별 비율**로 강제 배정합니다.

- **🎯 정확 일치**: `ACSB3201BN` 같은 단일 품목코드 (코드 100% 일치 시 적용)
- **🔍 정규식 패턴**: `^ACSB3201` (같은 모델 모든 색상 한꺼번에) · `BN$` (모든 BN 색상)

매칭되는 모든 행이 한 풀로 합쳐져 비율대로 분배됩니다. **우선순위: 정확 일치 > 패턴.**
"""
    )

    # 마스터 안내 (관리 UI는 없음 — 폴더에 파일만 두면 자동 로드)
    folder_path = str(storage.MASTER_FOLDER)
    if len(master) > 0:
        st.caption(
            f"📚 품목 마스터 자동 로드 — **{len(master)}개** 매핑  ·  "
            f"폴더: `{folder_path}`"
        )
    else:
        st.info(
            f"📚 품목 마스터가 비어있어 이름이 표시되지 않습니다.  \n"
            f"`{folder_path}` 폴더에 **품목코드 / 품목명** 컬럼이 있는 엑셀 또는 CSV 파일을 두면 자동 로드됩니다."
        )

    sub = st.tabs(["UI 편집", "파일 업로드", "현재 락(JSON)"])

    # --- UI 편집 ---
    with sub[0]:
        with st.form("split_lock_bulk_form", clear_on_submit=True, border=True):
            st.markdown("**➕ 항목 추가** — 여러 줄 입력하면 같은 비중으로 일괄 등록")

            c1, c2 = st.columns([1, 4])
            with c1:
                new_type = st.radio(
                    "유형",
                    options=["exact", "pattern"],
                    format_func=lambda x: "🎯 정확 일치" if x == "exact" else "🔍 정규식 패턴",
                    horizontal=False,
                )
            with c2:
                codes_text = st.text_area(
                    "품목코드 또는 정규식 (한 줄에 하나)",
                    height=140,
                    placeholder=(
                        "예) 정확 일치\n"
                        "ACSB2301\nACSB2308\nACSB2307\nACSB2311\n...\n\n"
                        "예) 패턴\n^ACSB23\n^RCSB"
                    ),
                )

            st.markdown("**라인별 비중** (생략 시 0으로 등록 — 추후 카드에서 설정 가능)")
            wcols = st.columns(len(DAILY_TARGET_LINES))
            bulk_w: dict[int, float] = {}
            for i, ln in enumerate(DAILY_TARGET_LINES):
                with wcols[i]:
                    bulk_w[ln] = st.number_input(
                        f"{ln}라인",
                        min_value=0.0, max_value=999.0, step=1.0,
                        value=0.0,
                        key=f"bulk_w_{ln}",
                    )
            total_pre = sum(bulk_w.values())
            if total_pre > 0:
                ratio_pre = " : ".join(
                    f"{int(bulk_w[l])}" if bulk_w[l] == int(bulk_w[l]) else f"{bulk_w[l]:.1f}"
                    for l in DAILY_TARGET_LINES
                )
                st.caption(f"📐 비율 미리보기 — {ratio_pre}")

            submitted = st.form_submit_button("➕ 일괄 추가", use_container_width=False)

            if submitted:
                codes = [c.strip() for c in (codes_text or "").splitlines() if c.strip()]
                if not codes:
                    st.warning("최소 한 개 이상의 코드/패턴을 입력하세요.")
                else:
                    import re as _re
                    bucket = lock.exact if new_type == "exact" else lock.pattern
                    weights = {l: float(w) for l, w in bulk_w.items() if w > 0}
                    if not weights:
                        weights = {l: 0.0 for l in DAILY_TARGET_LINES}
                    added: list[str] = []
                    skipped: list[str] = []
                    for code in codes:
                        if new_type == "pattern":
                            try:
                                _re.compile(code)
                            except _re.error as e:
                                skipped.append(f"{code} (정규식 오류: {e})")
                                continue
                        if code in bucket:
                            skipped.append(f"{code} (이미 등록됨)")
                            continue
                        bucket[code] = dict(weights)
                        added.append(code)
                    if added:
                        try:
                            save_split_lock(storage.SPLIT_LOCK_PATH, lock)
                            msg = f"✅ {len(added)}개 일괄 추가됨"
                            if skipped:
                                msg += f" · 건너뜀 {len(skipped)}건"
                            st.success(msg)
                            if skipped:
                                with st.expander("건너뛴 항목 보기"):
                                    for s in skipped:
                                        st.write(f"• {s}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"저장 실패: {e}")
                    else:
                        st.warning("추가된 항목이 없습니다.")
                        if skipped:
                            with st.expander("건너뛴 항목 보기"):
                                for s in skipped:
                                    st.write(f"• {s}")

        entries = lock.all_entries()
        if not entries:
            st.info("등록된 항목이 없습니다. 위에서 추가하세요.")
        else:
            entries_sorted = sorted(entries, key=lambda x: (0 if x[0] == "exact" else 1, x[1]))

            # === 요약 통계 ===
            n_exact = len(lock.exact)
            n_pat = len(lock.pattern)
            n_active = sum(1 for _, _, w in entries if any(v > 0 for v in w.values()))
            kc1, kc2, kc3 = st.columns(3)
            kc1.metric("🎯 정확 일치", n_exact)
            kc2.metric("🔍 패턴", n_pat)
            kc3.metric("✅ 적용 중 (비중>0)", n_active, help=f"총 {len(entries)}개 중 비중이 설정된 항목")

            # === 요약 표 (한눈에 확인) ===
            st.markdown("##### 📋 등록 항목 요약")
            st.caption("모든 락의 비중과 비율을 한눈에 확인 · 품목명칭은 품목 마스터에서 자동 매칭")
            summary_rows = []
            for lk_type, key, w in entries_sorted:
                total = sum(w.values())
                # 품목명칭 — exact는 짧은 이름(첫 구분자 앞), pattern은 공통 prefix
                if lk_type == "exact":
                    item_label = exact_short_name(master, key) or "—"
                else:
                    item_label = pattern_common_name(master, key) or "—"
                row = {
                    "유형": "🎯 정확" if lk_type == "exact" else "🔍 패턴",
                    "키": key,
                    "품목명칭": item_label,
                }
                for ln in DAILY_TARGET_LINES:
                    v = float(w.get(ln, 0))
                    row[f"{ln}라인"] = int(v) if v == int(v) else round(v, 1)
                if total > 0:
                    row["비율(%)"] = " / ".join(
                        f"{ln}라인 {w.get(ln, 0)/total*100:.0f}%"
                        for ln in DAILY_TARGET_LINES if w.get(ln, 0) > 0
                    )
                    row["상태"] = "✅ 활성"
                else:
                    row["비율(%)"] = "—"
                    row["상태"] = "⚠️ 미설정"
                summary_rows.append(row)
            summary_df = pd.DataFrame(summary_rows)
            st.dataframe(
                summary_df, use_container_width=True, hide_index=True,
                column_config={
                    "유형": st.column_config.TextColumn(width="small"),
                    "키": st.column_config.TextColumn(width="medium"),
                    "품목명칭": st.column_config.TextColumn(width="large"),
                    **{f"{ln}라인": st.column_config.NumberColumn(format="%g", width="small")
                       for ln in DAILY_TARGET_LINES},
                    "비율(%)": st.column_config.TextColumn(width="medium"),
                    "상태": st.column_config.TextColumn(width="small"),
                },
            )

            st.divider()

            # === 개별 편집 (expander로 압축) ===
            st.markdown("##### ✏️ 개별 편집")
            search = st.text_input(
                "🔎 검색 (키 일부 입력)",
                placeholder="예: ACSB23, ^ACSB",
                key="lock_search",
            ).strip()
            filtered = [
                e for e in entries_sorted
                if not search or search.lower() in e[1].lower()
            ]
            if not filtered:
                st.caption(f"검색 결과 없음 ({len(entries_sorted)}개 중 0개)")
            else:
                st.caption(f"표시 중: {len(filtered)}개 / 전체 {len(entries_sorted)}개")
                for lk_type, key, weights in filtered:
                    bucket = lock.exact if lk_type == "exact" else lock.pattern
                    badge = "🎯" if lk_type == "exact" else "🔍"
                    total_w = sum(weights.values())
                    if total_w > 0:
                        ratio_text = " : ".join(
                            f"{int(weights.get(l, 0))}" if weights.get(l, 0) == int(weights.get(l, 0))
                            else f"{weights.get(l, 0):.1f}"
                            for l in DAILY_TARGET_LINES
                        )
                        header_status = f"비율 {ratio_text}"
                    else:
                        header_status = "⚠️ 비중 미설정"
                    # 품목명칭 (공통 prefix) — 있을 때만
                    if lk_type == "exact":
                        item_label = exact_short_name(master, key)
                    else:
                        item_label = pattern_common_name(master, key)
                    name_part = f"  ·  {item_label}" if item_label else ""
                    header = f"{badge}  {key}{name_part}  ·  {header_status}"

                    with st.expander(header, expanded=False):
                        cols = st.columns(len(DAILY_TARGET_LINES))
                        new_w: dict[int, float] = {}
                        for i, ln in enumerate(DAILY_TARGET_LINES):
                            with cols[i]:
                                cur = float(weights.get(ln, 0))
                                new_w[ln] = st.number_input(
                                    f"{ln}라인 비중",
                                    min_value=0.0, max_value=999.0, step=1.0,
                                    value=cur,
                                    key=f"w_{lk_type}_{key}_{ln}",
                                )
                        tnew = sum(new_w.values())
                        if tnew > 0:
                            ratios = [f"{ln}라인 {new_w[ln]/tnew*100:.0f}%"
                                      for ln in DAILY_TARGET_LINES if new_w[ln] > 0]
                            st.caption(f"📐 현재 비율 → " + " / ".join(ratios))
                        else:
                            st.caption("⚠️ 모든 가중치가 0이면 적용되지 않습니다")

                        bc1, bc2, bc3, _ = st.columns([1, 1, 1.2, 2])
                        with bc1:
                            if st.button("💾 저장", key=f"save_{lk_type}_{key}", use_container_width=True):
                                bucket[key] = {l: float(w) for l, w in new_w.items() if w > 0}
                                if not bucket[key]:
                                    bucket.pop(key, None)
                                save_split_lock(storage.SPLIT_LOCK_PATH, lock)
                                st.success(f"{key} 저장됨")
                                st.rerun()
                        with bc2:
                            if st.button("🗑️ 삭제", key=f"del_{lk_type}_{key}", use_container_width=True):
                                bucket.pop(key, None)
                                save_split_lock(storage.SPLIT_LOCK_PATH, lock)
                                st.rerun()
                        with bc3:
                            other = "pattern" if lk_type == "exact" else "exact"
                            swap_label = ("🔁 패턴으로 변경" if other == "pattern"
                                          else "🔁 정확 일치로 변경")
                            if st.button(swap_label, key=f"swap_{lk_type}_{key}",
                                         use_container_width=True,
                                         help="유형을 잘못 등록했을 때 키와 비중은 유지한 채 유형만 전환"):
                                target_bucket = lock.exact if other == "exact" else lock.pattern
                                # 정규식 변환 시 유효성 검증
                                if other == "pattern":
                                    import re as _re
                                    try:
                                        _re.compile(key)
                                    except _re.error as e:
                                        st.error(f"정규식 오류: {e} — 변환할 수 없습니다.")
                                        st.stop()
                                if key in target_bucket:
                                    st.error(
                                        f"이미 {'정규식 패턴' if other == 'pattern' else '정확 일치'} "
                                        f"쪽에 동일 키가 있어 변환할 수 없습니다: {key}"
                                    )
                                else:
                                    target_bucket[key] = dict(weights)
                                    bucket.pop(key, None)
                                    save_split_lock(storage.SPLIT_LOCK_PATH, lock)
                                    st.success(
                                        f"{key} → "
                                        f"{'🔍 정규식 패턴' if other == 'pattern' else '🎯 정확 일치'} "
                                        f"으로 변경됨"
                                    )
                                    st.rerun()

    # --- 파일 업로드 ---
    with sub[1]:
        with st.expander("📖 파일 업로드 사용법", expanded=True):
            st.markdown("""
두 가지 형식을 모두 지원합니다.

**형식 1 (Long, 행 단위) — 권장**

| 컬럼 | 의미 | 예시 |
|---|---|---|
| `item_code` | 품목코드 또는 정규식 | `ACSB3201BN`, `^ACSB3201` |
| `line` | 라인 번호 | `1`, `3`, `4`, `5` |
| `weight` | 가중치 (정수 또는 소수) | `1`, `3`, `0.5` |
| `type` | `exact` (정확 일치) / `pattern` (정규식). 생략 시 `exact` | `exact`, `pattern` |

예시 CSV:
```
item_code,line,weight,type
ACSB3201BN,1,1,exact
ACSB3201BN,3,3,exact
ACSB3201BN,4,1,exact
ACSB3201BN,5,1,exact
^ACSB3201,1,1,pattern
^ACSB3201,3,3,pattern
^ACSB3201,4,1,pattern
^ACSB3201,5,1,pattern
```
의미:
- `ACSB3201BN` 한 품목만 1:3:1:1 비율
- `^ACSB3201` 패턴 → ACSB3201으로 시작하는 모든 품목(BN/GN/HN/JN…)이 한 풀로 합쳐져 같은 비율로 배분

**형식 2 (Wide, 열 단위)**

| `item_code` | `line_1` | `line_3` | `line_4` | `line_5` | `type` |
|---|---|---|---|---|---|
| ACSB3201BN | 1 | 3 | 1 | 1 | exact |
| ^ACSB3201 | 1 | 3 | 1 | 1 | pattern |

**비율 의미**:
- 가중치 합으로 자동 정규화 (1:3:1:1 = 17%/50%/17%/17%)
- 그날 매칭되는 모든 행을 합친 풀의 N개를 비율대로 배분
- 같은 품목이 exact·pattern 양쪽 매칭이면 **exact 우선**
""")
        up = st.file_uploader("분할 락 파일 (.xlsx / .csv)", type=["xlsx", "csv"], key="up_split")
        replace = st.checkbox("기존 락을 모두 대체", value=False, key="split_replace")
        if up is not None:
            try:
                if up.name.lower().endswith(".csv"):
                    rdf = pd.read_csv(up)
                else:
                    rdf = pd.read_excel(up)
                new_lock = split_lock_from_dataframe(rdf)
                if replace:
                    merged = new_lock
                else:
                    merged = SplitLock(
                        exact={**lock.exact},
                        pattern={**lock.pattern},
                    )
                    for code, weights in new_lock.exact.items():
                        merged.exact.setdefault(code, {}).update(weights)
                    for pat, weights in new_lock.pattern.items():
                        merged.pattern.setdefault(pat, {}).update(weights)
                save_split_lock(storage.SPLIT_LOCK_PATH, merged)
                total = len(new_lock.exact) + len(new_lock.pattern)
                st.success(f"{total}개 항목 락 반영 완료 ({'대체' if replace else '병합'})")
                st.rerun()
            except Exception as e:
                st.error(f"파일 처리 실패: {e}")

    # --- JSON ---
    with sub[2]:
        st.json(lock.to_dict())
        st.download_button(
            "⬇️ split_lock.json 다운로드",
            data=json.dumps(lock.to_dict(), ensure_ascii=False, indent=2),
            file_name="split_lock.json",
            mime="application/json",
        )
        if st.button("🧹 모든 락 초기화", type="secondary", key="reset_split"):
            save_split_lock(storage.SPLIT_LOCK_PATH, SplitLock())
            st.rerun()


def tab_policy(policy: GroupPolicy):
    st.caption(
        "같은 **수주건명**은 한 라인에 묶여 배정됩니다(좌/우 단차 등 품질 이유).\n"
        "단, 아래 키워드가 포함된 수주건명은 재고·거점 출고로 보고 **분할 허용**합니다."
    )

    current = "\n".join(policy.split_keywords)
    txt = st.text_area(
        "분할 허용 키워드 (한 줄에 하나)",
        value=current,
        height=160,
        help="수주건명에 키워드가 포함되면 그룹 제약을 풀고 행 단위로 분배합니다.",
    )

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if st.button("💾 저장", type="primary"):
            kws = [s.strip() for s in txt.splitlines() if s.strip()]
            save_policy(storage.GROUP_POLICY_PATH, GroupPolicy(split_keywords=kws))
            st.success("저장되었습니다.")
            st.rerun()
    with c2:
        if st.button("🔄 기본값으로 복원"):
            save_policy(storage.GROUP_POLICY_PATH, GroupPolicy())
            st.rerun()
    with c3:
        st.caption(f"기본값: {', '.join(DEFAULT_SPLIT_KEYWORDS)}")

    st.divider()
    st.markdown("#### 현재 적용 결과 미리보기")
    df = _load_df("daily")
    if df is None:
        st.info("당일분배 파일이 없습니다.")
        return
    target = df[df["line_no"].isin(DAILY_TARGET_LINES)].copy()
    target["분할여부"] = target["order_name"].fillna("").astype(str).map(
        lambda s: "분할 허용" if policy.should_split(s) else "그룹 유지"
    )
    summary = (
        target.groupby(["order_name", "분할여부"], dropna=False)
        .agg(건수=("item_code", "size"), 총수량=("plan_qty", "sum"))
        .reset_index()
        .sort_values(["분할여부", "건수"], ascending=[True, False])
    )
    st.dataframe(summary, use_container_width=True, hide_index=True)


def tab_integrity(rules: LineRules, policy: GroupPolicy, split_lock: SplitLock):
    st.caption(
        "누적분배 + 당일분배 데이터를 결합하여 라인별 수량/시간이 타당한지 검증합니다.\n"
        "한쪽 파일만 있어도 그 데이터 기준으로 표시되며, 일관성 검증은 두 파일이 모두 있을 때만 활성화됩니다."
    )
    cu_df = _load_df("cumulative")
    da_df = _load_df("daily")

    if cu_df is None and da_df is None:
        st.warning("⚠️ 누적분배와 당일분배 파일이 모두 없습니다. 좌측에서 하나 이상 업로드하세요.")
        return
    if cu_df is None:
        st.info("ℹ️ 누적분배 데이터가 없어 **당일분배 단독** 기준으로 표시합니다.")
    elif da_df is None:
        st.info("ℹ️ 당일분배 데이터가 없어 **누적분배 단독** 기준으로 표시합니다.")

    cu_res = process_cumulative(cu_df) if cu_df is not None else {"detail": pd.DataFrame()}
    da_res = (
        distribute_daily(da_df, rules, group_policy=policy, split_lock=split_lock)
        if da_df is not None else {"detail": pd.DataFrame()}
    )

    integ = build_integrity(cu_res["detail"], da_res["detail"])
    kpi = integ["kpi"]

    # --- KPI 카드 ---
    c1, c2, c3, c4 = st.columns(4)
    _kpi_card(c1, "종합 계획시간",
              f"{kpi['총_종합_시간']:,} 초",
              delta=f"누적 {kpi['총_누적_시간']:,} + 당일 {kpi['총_당일_시간']:,}")
    _kpi_card(c2, "종합 계획량",
              f"{kpi['총_종합_수량']:,} 개",
              delta=f"누적 {kpi['총_누적_수량']:,} + 당일 {kpi['총_당일_수량']:,}")
    _kpi_card(c3, "일관성 검증 수주건",
              f"{kpi['일관성_검증된_수주건수']} 건",
              help_text="두 데이터에 동시에 존재하는 수주건명")
    _kpi_card(c4, "일관성 위반",
              f"{kpi['일관성_위반']} 건",
              delta=("⚠️ 확인 필요" if kpi['일관성_위반'] else "정상"),
              help_text="누적과 당일에 다른 라인으로 배정된 수주건")

    st.divider()

    # --- 1) 라인 종합 부하: 그래프 → 표 순 ---
    st.markdown("#### 1) 라인별 종합 부하 (누적 + 당일)")
    cl = integ["combined_load"]
    if cl.empty:
        st.info("부하 데이터가 없습니다.")
    else:
        # 그래프 — 시간 스택 막대 + 수량 선 (콤보)
        st.markdown("##### 라인별 누적/당일 시간 + 종합 수량")
        cg = cl.dropna(subset=["라인"])
        lines_x = cg["라인"].tolist()
        cumul_sec = cg["누적_시간"].tolist()
        daily_sec = cg["당일_시간"].tolist()
        total_sec = cg["종합_시간"].tolist()
        total_qty = cg["종합_수량"].tolist()

        # --- 세련된 톤다운 팔레트 ---
        COLOR_CUMUL = "#cfd8e3"   # 옅은 슬레이트
        COLOR_DAILY = "#5b7a9c"   # 차분한 슬레이트 블루
        COLOR_QTY   = "#e76f51"   # 테라코타 (액센트)
        COLOR_TEXT_INSIDE_DARK = "#ffffff"
        COLOR_TEXT_INSIDE_LIGHT = "#475569"

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        # 막대 스택 — 시간 (왼쪽 축)
        fig.add_trace(go.Bar(
            name="누적 시간",
            x=lines_x, y=cumul_sec,
            marker_color=COLOR_CUMUL,
            marker_line_color="rgba(255,255,255,0.9)",
            marker_line_width=1.0,
            text=[f"{v:,}" if v > 0 else "" for v in cumul_sec],
            textposition="inside", insidetextanchor="middle",
            textfont=dict(color=COLOR_TEXT_INSIDE_LIGHT, size=10),
            hovertemplate="<b>%{x}</b><br>누적 시간 %{y:,}초<extra></extra>",
        ), secondary_y=False)
        fig.add_trace(go.Bar(
            name="당일 시간",
            x=lines_x, y=daily_sec,
            marker_color=COLOR_DAILY,
            marker_line_color="rgba(255,255,255,0.9)",
            marker_line_width=1.0,
            text=[f"{v:,}" if v > 0 else "" for v in daily_sec],
            textposition="inside", insidetextanchor="middle",
            textfont=dict(color=COLOR_TEXT_INSIDE_DARK, size=10),
            hovertemplate="<b>%{x}</b><br>당일 시간 %{y:,}초<extra></extra>",
        ), secondary_y=False)
        # 선 — 종합 수량 (오른쪽 축)
        fig.add_trace(go.Scatter(
            name="종합 수량",
            x=lines_x, y=total_qty,
            mode="lines+markers+text",
            line=dict(color=COLOR_QTY, width=2.2, shape="spline", smoothing=0.6),
            marker=dict(size=9, color=COLOR_QTY,
                        line=dict(color="#ffffff", width=2)),
            text=[f"{v:,}" if v > 0 else "" for v in total_qty],
            textposition="top center",
            textfont=dict(color=COLOR_QTY, size=11, family="-apple-system, sans-serif"),
            cliponaxis=False,
            hovertemplate="<b>%{x}</b><br>종합 수량 %{y:,}개<extra></extra>",
        ), secondary_y=True)

        # 막대 위 종합 시간 라벨 — 더 가벼운 톤
        annotations = [
            dict(x=l, y=t, text=f"<b>{t:,}</b>", showarrow=False,
                 yshift=14, font=dict(size=12, color="#334155"), yref="y")
            for l, t in zip(lines_x, total_sec)
        ]

        fig.update_layout(
            barmode="stack",
            height=380,
            margin=dict(t=70, b=50, l=60, r=60),
            legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0,
                        font=dict(size=11, color="#475569"), bgcolor="rgba(0,0,0,0)"),
            annotations=annotations,
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            bargap=0.62,
            hoverlabel=dict(bgcolor="#1f2a44", font=dict(color="#ffffff", size=12)),
            font=dict(family="-apple-system, BlinkMacSystemFont, sans-serif"),
        )
        fig.update_xaxes(
            showgrid=False, showline=False, ticks="",
            tickfont=dict(size=12, color="#334155"),
        )
        fig.update_yaxes(
            title_text="시간(초)",
            title_font=dict(color="#94a3b8", size=11),
            tickfont=dict(color="#94a3b8", size=10),
            range=[0, max(total_sec + [1]) * 1.22],
            showgrid=True, gridcolor="#f1f5f9", zeroline=False,
            secondary_y=False,
        )
        fig.update_yaxes(
            title_text="수량(개)",
            title_font=dict(color=COLOR_QTY, size=11),
            tickfont=dict(color=COLOR_QTY, size=10),
            range=[0, max(total_qty + [1]) * 1.35],
            showgrid=False, zeroline=False,
            secondary_y=True,
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("스택 막대 = 누적(옅음) / 당일(진함) 시간 · 코랄 선 = 종합 수량 · 막대 위 숫자 = 종합 시간")

        # 표 (그래프 아래) — 매트릭스와 동일 디자인
        st.markdown("##### 라인별 부하 표")
        rename_map = {
            "누적_수량": "누적 수량",
            "당일_수량": "당일 수량",
            "종합_수량": "종합 수량",
            "누적_시간": "누적 시간(초)",
            "당일_시간": "당일 시간(초)",
            "종합_시간": "종합 시간(초)",
            "인당_종합시간": "인당 종합시간(초)",
        }
        display_df = cl.rename(columns=rename_map)
        styled_load = _style_plain_table(
            display_df,
            numeric_cols=["인원", "누적 수량", "당일 수량", "종합 수량",
                          "누적 시간(초)", "당일 시간(초)", "종합 시간(초)",
                          "인당 종합시간(초)"],
            bold_cols=["종합 수량", "종합 시간(초)", "인당 종합시간(초)"],
        )
        _render_styled_table(styled_load, key="integrity_load_html")

    st.divider()

    # --- 출고일자 × 라인 종합 매트릭스 (수량/시간 통합 표시) ---
    st.markdown("#### 2) 출고일자 × 라인 종합 매트릭스 (누적 + 당일)")
    st.caption("라인별 (수량 / 시간) 두 줄로 표시 · 노란 행 = 수량, 파란 행 = 시간")

    matrix_qty = integ["matrix_qty"]
    matrix_sec = integ["matrix_sec"]
    if matrix_qty.empty:
        st.info("매트릭스 데이터가 없습니다.")
    else:
        # 라인 정렬 (라인번호 기준)
        import re as _re
        def _key(s: str):
            m = _re.search(r"(\d+)\s*라인", str(s))
            return (int(m.group(1)) if m else 99, str(s))
        ordered_lines = sorted(matrix_qty.index, key=_key)

        date_cols = [c for c in matrix_qty.columns if c != "합계"]
        rows = []
        for ln in ordered_lines:
            row_q = {"라인": ln, "구분": "수량"}
            row_q.update({c: int(matrix_qty.loc[ln, c]) for c in matrix_qty.columns})
            rows.append(row_q)
            row_s = {"라인": ln, "구분": "시간"}
            row_s.update({c: int(matrix_sec.loc[ln, c]) for c in matrix_sec.columns})
            rows.append(row_s)
        # 합계 행
        rows.append({"라인": "합계", "구분": "수량",
                     **{c: int(matrix_qty[c].sum()) for c in matrix_qty.columns}})
        rows.append({"라인": "합계", "구분": "시간",
                     **{c: int(matrix_sec[c].sum()) for c in matrix_sec.columns}})

        combined_matrix = pd.DataFrame(rows)[["라인", "구분"] + list(matrix_qty.columns)]
        _render_merged_combined(combined_matrix, line_col="라인", key="integrity_matrix_merged")

    st.divider()

    # --- 수주건명 일관성 ---
    st.markdown("#### 3) 수주건명 라인 일관성 검증")
    st.caption("두 데이터에 동시 존재하는 수주건명이 같은 라인에 배정됐는지 확인합니다.")
    cons = integ["consistency"]
    # 한 쪽 데이터만 있으면 비교 불가
    if cu_df is None or da_df is None:
        missing = "당일분배" if da_df is None else "누적분배"
        st.info(f"ℹ️ {missing} 파일이 없어 일관성 검증은 사용할 수 없습니다. 양쪽 파일이 모두 업로드되면 활성화됩니다.")
    elif cons.empty:
        st.info("두 데이터에 공통으로 존재하는 수주건명이 없습니다.")
    else:
        filt = st.multiselect(
            "표시할 상태",
            options=["❌ 불일치", "⚠️ 일부 겹침", "✅ 일치"],
            default=["❌ 불일치", "⚠️ 일부 겹침"],
        )
        show = cons[cons["일관성"].isin(filt)] if filt else cons
        st.dataframe(
            show, use_container_width=True, hide_index=True,
            column_config={
                "수주건명": st.column_config.TextColumn(width="medium"),
                "누적_라인": st.column_config.TextColumn("누적 라인", width="small"),
                "당일_라인": st.column_config.TextColumn("당일 라인", width="small"),
                "일관성": st.column_config.TextColumn(width="small"),
            },
        )


def _get_app_password() -> str:
    """비밀번호 조회 — secrets.toml 우선, 없으면 환경변수, 그래도 없으면 빈 문자열."""
    try:
        pw = st.secrets["auth"]["password"]  # type: ignore[index]
        if pw:
            return str(pw)
    except Exception:
        pass
    return os.environ.get("APP_PASSWORD", "")


def _check_password() -> bool:
    """진입 게이트. 관리자(비번 필요) / 뷰어(비번 없음) 두 모드 지원."""
    if st.session_state.get("_authed"):
        return True

    expected = _get_app_password()
    # 비밀번호 미설정 — 자동 관리자 통과 (로컬 개발 환경)
    if not expected:
        st.session_state["_authed"] = True
        st.session_state["_role"] = "admin"
        return True

    # 로그인 화면 CSS
    st.markdown(
        """
<style>
.login-wrap {
    max-width: 460px;
    margin: 60px auto 0 auto;
    background: #ffffff;
    border: 1px solid #e8dcc8;
    border-left: 6px solid #c8945a;
    border-radius: 14px;
    padding: 28px 32px;
    box-shadow: 0 4px 18px rgba(74,52,36,0.08);
    text-align: center;
}
.login-wrap .lg-logo {
    font-size: 28px;
    font-weight: 800;
    color: #4a3424;
    letter-spacing: -0.4px;
    margin-bottom: 4px;
}
.login-wrap .lg-sub {
    font-size: 11px;
    color: #8b6f4e;
    letter-spacing: 3px;
    font-weight: 600;
    margin-bottom: 18px;
    text-transform: uppercase;
}
.login-wrap .lg-msg {
    font-size: 13px;
    color: #6b4a30;
    margin-bottom: 14px;
}
</style>
<div class='login-wrap'>
    <div class='lg-logo'>🛋️ SIDIZ SOFA</div>
    <div class='lg-sub'>PRODUCTION DISPATCH</div>
    <div class='lg-msg'>접속 방법을 선택하세요</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1, 1.6, 1])
    with c2:
        show_admin_form = st.session_state.get("_show_admin_form", False)

        # 두 진입 버튼 (사용자가 비번 form을 열기 전까지)
        if not show_admin_form:
            ba, bv = st.columns(2)
            with ba:
                if st.button("🔐 관리자 입장", use_container_width=True):
                    st.session_state["_show_admin_form"] = True
                    st.rerun()
            with bv:
                if st.button("👀 뷰어로 입장", use_container_width=True,
                             help="조회 전용 (편집·업로드 불가)"):
                    st.session_state["_authed"] = True
                    st.session_state["_role"] = "viewer"
                    st.rerun()
            st.caption(
                "🔐 **관리자**: 비밀번호 필요 · 모든 기능 사용 가능  \n"
                "👀 **뷰어**: 비밀번호 없이 즉시 접속 · 조회/다운로드만 가능"
            )
        else:
            # 관리자 비번 입력 form
            with st.form("login_form", clear_on_submit=False, border=False):
                pw = st.text_input("관리자 비밀번호", type="password",
                                   label_visibility="collapsed",
                                   placeholder="관리자 비밀번호 입력")
                fc1, fc2 = st.columns([1, 1])
                with fc1:
                    submitted = st.form_submit_button("🔐 입장", use_container_width=True)
                with fc2:
                    canceled = st.form_submit_button("← 뒤로", use_container_width=True)
                if submitted:
                    if pw == expected:
                        st.session_state["_authed"] = True
                        st.session_state["_role"] = "admin"
                        st.session_state.pop("_show_admin_form", None)
                        st.rerun()
                    else:
                        st.error("비밀번호가 올바르지 않습니다.")
                if canceled:
                    st.session_state.pop("_show_admin_form", None)
                    st.rerun()
    return False


def is_admin() -> bool:
    return st.session_state.get("_role") == "admin"


def is_viewer() -> bool:
    return st.session_state.get("_role") == "viewer"


def main():
    # 비밀번호 게이트
    if not _check_password():
        st.stop()

    st.markdown(
        """
<div class='brand-header'>
    <div class='brand-title'>🛋️ 라인별 분배 계획
        <span class='brand-tag'>SIDIZ SOFA</span>
    </div>
    <div class='brand-sub'>Sidiz Sofa Production Line Dispatching System</div>
</div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("누적분배 / 당일분배 데이터를 업로드하면 라인별로 자동 정리·분배합니다.")

    sidebar_uploads()
    rules = load_rules(storage.RULES_PATH)
    policy = load_policy(storage.GROUP_POLICY_PATH)
    split_lock = load_split_lock(storage.SPLIT_LOCK_PATH)
    # 품목마스터/ 폴더의 모든 엑셀/CSV를 자동 로드 (UI 관리 없음)
    master, master_files = load_master_from_folder(storage.MASTER_FOLDER)

    if is_admin():
        t1, t2, t3, t4, t5 = st.tabs([
            "📊 누적분배",
            "🚚 당일분배 (자동 분배)",
            "🔗 정합성 검증",
            "⚙️ 라인 규칙 관리",
            "🧩 수주건명 그룹 정책",
        ])
        with t1:
            tab_cumulative()
        with t2:
            tab_daily(rules, policy, split_lock)
        with t3:
            tab_integrity(rules, policy, split_lock)
        with t4:
            tab_rules(rules, split_lock, master)
        with t5:
            tab_policy(policy)
    else:
        # 뷰어 — 조회 전용 탭만
        st.info("👀 **뷰어 모드** — 조회/다운로드만 가능합니다. 편집·업로드는 관리자 로그인이 필요합니다.")
        t1, t2, t3 = st.tabs([
            "📊 누적분배",
            "🚚 당일분배 (자동 분배)",
            "🔗 정합성 검증",
        ])
        with t1:
            tab_cumulative()
        with t2:
            tab_daily(rules, policy, split_lock)
        with t3:
            tab_integrity(rules, policy, split_lock)


if __name__ == "__main__":
    main()
