# 🚀 Streamlit Cloud 배포 가이드

## 0. 사전 준비
- **GitHub 무료 계정** (https://github.com/signup)
- **Git for Windows** 설치 (https://git-scm.com/download/win)

설치 확인:
```powershell
git --version
```

---

## 1. 로컬 비밀번호 결정
`.streamlit/secrets.toml` 파일을 메모장으로 열어 비밀번호 변경:
```toml
[auth]
password = "원하는-비밀번호로-변경"
```
이 파일은 `.gitignore` 에 의해 **GitHub 에는 올라가지 않습니다**.

---

## 2. Git 초기화 + 첫 커밋
PowerShell에서:
```powershell
cd c:\Users\FURSYS\Desktop\계획및분배

git init
git branch -M main

# 사용자 정보 (처음 1회)
git config user.name  "본인이름"
git config user.email "본인이메일@example.com"

git add .
git commit -m "initial deploy: sofa atelier dispatching system"
```

---

## 3. GitHub 레포 생성 + 푸시
1. https://github.com/new 접속
2. **Repository name**: 예) `sofa-atelier`
3. **Public** 선택 (Streamlit Cloud 무료 티어는 public 만 자동 연결 가능)
4. README/`.gitignore` 추가 옵션 모두 **체크 해제**
5. Create repository

그 다음 PowerShell에서 (URL은 GitHub가 안내하는 그대로):
```powershell
git remote add origin https://github.com/<본인계정>/sofa-atelier.git
git push -u origin main
```

---

## 4. Streamlit Cloud 앱 등록
1. https://share.streamlit.io 접속 → **Continue with GitHub**
2. 우상단 **New app**
3. 입력:
   - **Repository**: 위에서 만든 레포
   - **Branch**: `main`
   - **Main file path**: `app/app.py`
   - **App URL (선택)**: `fursys-sofa-line` 등 원하는 슬러그
4. **⚙️ Advanced settings** 클릭 (또는 Deploy 후 우상단 톱니바퀴 → Settings)
5. **Secrets** 탭에 다음 내용 붙여넣기 (비밀번호는 본인이 정한 값으로):
   ```toml
   [auth]
   password = "원하는-비밀번호"
   ```
6. **Save** → **Deploy**

3~5분 후 빌드 완료, 공개 URL 발급:
```
https://fursys-sofa-line.streamlit.app
```

---

## 5. 팀 공유
위 URL을 팀에 공유합니다. 접속 시 비밀번호 화면이 먼저 뜨고, 통과하면 대시보드.

---

## 6. 운영
- **매일 데이터 업로드**: 사용자가 사이드바에서 누적분배/당일분배 .xls 업로드
- **설정 변경**: 라인 규칙·분할 락·그룹 정책은 변경 후 GitHub에 푸시하면 영구 반영
- **마스터 추가/변경**: `품목마스터/` 폴더의 파일을 갱신 후 git push

### 코드 수정 후 재배포
```powershell
git add -A
git commit -m "수정 내용 한 줄 요약"
git push
```
Streamlit Cloud 가 자동 재빌드(약 1~2분).

---

## ⚠️ 주의사항

### 데이터 영속성
- Streamlit Cloud 컨테이너는 가끔 재시작되며 디스크가 초기화될 수 있습니다.
- **GitHub 커밋 항목 → 영구 유지** (마스터 파일, 설정 JSON)
- **앱 내 업로드 항목 → 휘발 가능** (누적/당일 grd_list — 어차피 매일 새 데이터)

### 비밀번호 변경
- 로컬: `.streamlit/secrets.toml` 수정
- Cloud: 앱 페이지 → ⚙️ Settings → Secrets 수정 → Save

### 무료 한도
- RAM 1GB / CPU 1
- 일정 시간 미접속 시 슬립 (재접속 시 10~30초 부팅)
- 동시 앱 최대 4개

---

## ❓ 문제 해결

| 증상 | 해결 |
|---|---|
| `Build failed` | `requirements.txt` 의존성 확인. 로그에서 패키지 누락 확인. |
| 비밀번호 화면 안 뜸 | Cloud Secrets에 `[auth] password = "..."` 저장됐는지 확인 |
| 한글 깨짐 | 파일 UTF-8 인코딩 확인 (대부분 정상) |
| `app/core` 모듈 못 찾음 | `Main file path`가 `app/app.py`로 설정됐는지 확인 |
