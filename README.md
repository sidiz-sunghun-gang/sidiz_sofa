# 라인별 분배 계획 서버

누적분배 / 당일분배 엑셀(.xls) 데이터를 업로드하면 라인별로 자동 정리·분배해주는 Streamlit 웹앱입니다.

## 주요 기능

### 📊 누적분배 탭
- **재공완료(Y) 자동 제거**
- **1·3·4·5라인만 필터**
- 표시 컬럼: 제품코드 / 색상 / 작업시간(초) / 수량 / 품목명칭 / 수주건명 / 출고일자 / 라인
- 출고일자는 *전달사항* 텍스트에서 자동 추출 (`6/1 출고`, `2026-05-30`, `5/29` 모두 인식)
- **라인 × 출고일자** 피벗 (계획시간·계획량)

### 🚚 당일분배 탭 (자동 분배)
- 1·3·4·5라인으로 자동 배정
- 분배 기준: **계획시간(초) LPT + 인원 가중**
  - 인원: 1·3·4라인 = 2명, 5라인 = 1명
  - 인당 부하가 가장 낮은 후보 라인에 배정 → 결과적으로 인당 부하가 거의 동일해짐
- **작업 불가 라인은 후보에서 제외**
- 어느 라인에서도 불가한 품목은 ⚠️ 미배정으로 분리 표시

### ⚙️ 라인별 작업불가 규칙 탭
- UI에서 라인별로 품목코드 추가/삭제 (즉시 분배에 반영)
- 정규식 패턴 지원 (예: `^ACSF` → ACSF로 시작하는 모든 품목)
- 엑셀/CSV 일괄 업로드 (컬럼: `line, item_code, type`)

## 로컬 실행

```powershell
pip install -r requirements.txt
streamlit run app/app.py
```

기본 포트 8501에서 열립니다. 브라우저에서 `http://localhost:8501` 접속.

## Streamlit Community Cloud 무료 배포

> 제3자도 공개 URL로 접속 가능. 무료. 사용량 한도 내 자동 슬립/웨이크.

### 1) GitHub 레포 준비
```powershell
cd c:\Users\FURSYS\Desktop\계획및분배
git init
git add app/ requirements.txt .streamlit/ README.md .gitignore
git commit -m "Initial line distribution app"
git branch -M main
git remote add origin https://github.com/<your-id>/line-dispatch.git
git push -u origin main
```

> `.gitignore`에 의해 `당일분배/*.xls`, `누적분배/*.xls`, `app/storage/latest/*` 는 커밋되지 않습니다. 샘플 데이터를 함께 올리고 싶다면 해당 라인을 주석 처리하세요.

### 2) Streamlit Cloud 연결
1. https://share.streamlit.io 접속 → GitHub 계정으로 로그인
2. **New app** → 위에서 만든 레포 선택
3. **Main file path**: `app/app.py`
4. Python 버전: 3.11 권장
5. **Deploy** 클릭

배포가 끝나면 `https://<your-app>.streamlit.app` 형식의 공개 URL이 발급됩니다. 이 URL을 팀에 공유하면 됩니다.

### 3) 데이터 영속성 안내
- **최신 파일만 유지** 정책: 누적/당일 각 1개의 최신 파일이 서버 디스크(`app/storage/latest/`)에 저장됩니다.
- Streamlit Cloud는 컨테이너 재기동 시 디스크가 초기화될 수 있습니다. 영구 보관이 필요하면 추후 GitHub 자동 커밋 / S3 / Google Drive 연동을 추가하시면 됩니다.
- 같은 카테고리에 새 파일을 올리면 즉시 덮어쓰기 → 모든 사용자에게 반영.

## 디렉토리 구조

```
계획및분배/
├── app/
│   ├── app.py                # Streamlit 진입점
│   ├── core/
│   │   ├── loader.py         # .xls 파싱·정규화
│   │   ├── cumulative.py     # 누적분배 처리
│   │   ├── daily.py          # 당일분배 분배 알고리즘
│   │   ├── rules.py          # 작업불가 규칙 모델
│   │   └── storage.py        # 최신 파일/규칙 영속화
│   └── storage/
│       ├── latest/           # cumulative.xls, daily.xls
│       └── config/           # line_rules.json
├── tests/
│   └── smoke.py              # 모듈 동작 점검 스크립트
├── 누적분배/                  # 원본 샘플
├── 당일분배/                  # 원본 샘플
├── requirements.txt
├── .streamlit/config.toml
├── .gitignore
└── README.md
```

## 분배 알고리즘 검증 결과 (샘플 데이터 기준)

83건 / 총 계획시간 419,340초 입력:

| 라인 | 인원 | 총 계획시간(초) | 인당 부하(초) |
|------|------|----------------|----------------|
| 1라인 | 2 | 120,000 | **60,000** |
| 3라인 | 2 | 119,700 | **59,850** |
| 4라인 | 2 | 119,760 | **59,880** |
| 5라인 | 1 |  59,880 | **59,880** |

→ 인당 부하 편차 0.25% 이내, 인원 가중 균등 분배가 의도대로 동작합니다.

## 작업불가 규칙 파일 예시

`line_rules.csv`:
```csv
line,item_code,type
1,ACSB0271BN,exact
3,ACSF2442BN,exact
5,^ACSF,pattern
4,.*HN$,pattern
```
- `exact`: 품목코드 완전 일치
- `pattern`: 정규식 매칭

## 향후 확장 아이디어
- 업로드 이력 보관 (날짜별 아카이브)
- GitHub Actions로 매일 정해진 시간에 데이터 자동 수집
- 라인별 인원/근무시간 동적 설정
- 분배 결과 PDF/엑셀 리포트 출력
