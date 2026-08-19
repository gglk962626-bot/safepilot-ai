# 🦺 SafePilot AI

**스스로 검토하는 위험성평가 코파일럿**

작업 정보를 입력하면 AI가 위험성평가, 예방대책, 개인보호구(PPE), 작업 전 TBM, 체크리스트를 생성하고,
2차 AI가 누락·모순을 교차검토하여 보완된 최종 결과와 PDF 보고서를 제공하는 독립 웹 서비스입니다.

> ⚠️ 본 서비스의 결과는 **AI가 작성한 초안**이며, 반드시 **현장 책임자의 최종 확인**이 필요합니다.
> 산업안전보건법상 위험성평가의 법적 요건을 대체하지 않습니다.

---

## 주요 기능

1. 위험성평가 자동 생성 (작업 단계 분해 → 위험요인 도출)
2. 위험요인별 발생 가능성(1~5) / 피해 심각도(1~5) 평가
3. 위험도 점수 자동 계산 (가능성 × 심각도, **Python에서 직접 계산**)
4. 예방대책 및 개인보호구 제안
5. 작업 전 TBM(Tool Box Meeting) 브리핑 항목 생성
6. 작업 전 체크리스트 생성
7. **2차 AI 교차검토**: 20개 위험 범주 기준 누락·모순·PPE 불일치 점검
8. 검토 전후 변경사항 이력 표시
9. 현장 책임자 확인 후 PDF 보고서 다운로드 (한글 지원)
10. API 키 없이 체험 가능한 **데모 모드**

## 파일 구성

| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit 웹 화면 (메인 앱) |
| `models.py` | 데이터 모델(Pydantic), 위험도 계산 규칙 |
| `ai_service.py` | Google Gemini AI 호출, JSON 파싱·재시도, 오류 처리 |
| `prompts.py` | 1차 생성 / 2차 검토 AI 프롬프트 |
| `pdf_service.py` | PDF/HTML 보고서 생성 (한글 폰트 자동 탐색) |
| `demo_data.py` | 데모 모드 샘플 데이터 |
| `requirements.txt` | Python 패키지 목록 |
| `packages.txt` | Streamlit Cloud용 시스템 패키지 (한글 폰트) |
| `.env.example` | API 키 설정 예시 |
| `tests/` | SafePilot 전용 회귀 테스트 |

---

## 로컬 실행 방법 (Windows)

1. 패키지 설치 (최초 1회):

```bash
py -m pip install -r requirements.txt
```

2. (실제 AI 모드를 쓰려면) `.env.example`을 복사해 `.env` 파일을 만들고 API 키 입력:

```
GEMINI_API_KEY=발급받은_키
```

3. 앱 실행:

```bash
py -m streamlit run app.py
```

4. 브라우저에서 http://localhost:8501 접속
   (API 키가 없어도 **데모 모드**로 모든 기능을 체험할 수 있습니다.)

---

## Streamlit Community Cloud 무료 배포 방법

1. 이 폴더를 GitHub 저장소에 올립니다. (`.env`는 자동으로 제외됩니다)
2. https://share.streamlit.io 에 GitHub 계정으로 로그인합니다.
3. **New app** → 저장소 선택 → Main file path에 `app.py` 입력 → **Deploy**
4. 배포된 앱의 **Settings → Secrets** 메뉴에 아래 내용을 입력하고 저장합니다:

```toml
GEMINI_API_KEY = "발급받은_키"
```

5. 발급된 URL(`https://앱이름.streamlit.app`)로 다른 PC와 휴대폰에서 접속할 수 있습니다.

> 한글 PDF는 `packages.txt`의 `fonts-nanum` 폰트로 자동 지원됩니다.

---

## 회귀 테스트

```bash
py -m pip install -r requirements.txt
py tests\test_regression.py
```

API 키 없이도 데모 데이터, 위험도 재계산 로직, JSON 파싱/재시도, PDF·HTML 생성 등을 검증합니다.

---

## 보안 안내

- API 키는 코드에 직접 넣지 않습니다.
- 로컬: `.env` 파일 / 배포: Streamlit **Secrets** 사용
- `.env`와 `.streamlit/secrets.toml`은 `.gitignore`에 포함되어 GitHub에 올라가지 않습니다.
