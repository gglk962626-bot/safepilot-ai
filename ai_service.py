"""SafePilot AI - AI 호출 서비스

- Google Gemini API를 호출하여 1차 위험성평가와 2차 교차검토를 수행한다.
- 응답은 구조화된 JSON으로만 처리하며, 파싱 실패 시 최대 1회 자동 재시도한다.
- API 키는 코드에 넣지 않고 .env(로컬) 또는 Streamlit secrets(배포)에서 읽는다.
"""

from __future__ import annotations

import json
import os
import re
import time

from dotenv import load_dotenv
from pydantic import ValidationError

import prompts
from models import AssessmentResult, ReviewResult, WorkInput

load_dotenv()

# 일부 사내망(SSL 검사 프록시) 환경에서는 Python 기본 인증서 목록(certifi)에
# 사내 루트 인증서가 없어 "self-signed certificate in certificate chain" 오류가 발생한다.
# truststore는 인증서 검증 자체를 끄지 않고, OS(Windows/macOS/Linux)가 신뢰하는
# 인증서 저장소를 그대로 사용하도록 안전하게 연결해 준다.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

# 기본 모델 (환경변수 GEMINI_MODEL로 변경 가능)
# 참고: gemini-2.5-flash는 신규 API 키에는 더 이상 제공되지 않아(404 NOT_FOUND),
# Google이 유지하는 최신 flash 모델 별칭인 gemini-flash-latest를 기본값으로 사용한다.
# 특정 버전을 고정하고 싶다면 .env에 GEMINI_MODEL=gemini-3.5-flash 등으로 지정하면 된다.
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
MAX_TOKENS = 16000
REQUEST_TIMEOUT = 600.0  # 초 단위. 위험성평가 생성은 수 분이 걸릴 수 있음


class AIServiceError(Exception):
    """사용자에게 그대로 보여줄 수 있는 한국어 오류 메시지를 담는 예외."""


def get_api_key() -> str | None:
    """Streamlit secrets → 환경변수(.env) 순서로 API 키를 찾는다."""
    try:
        import streamlit as st

        if "GEMINI_API_KEY" in st.secrets:
            key = st.secrets["GEMINI_API_KEY"]
            if key:
                return str(key)
    except Exception:
        # secrets.toml이 없는 로컬 환경 등에서는 조용히 넘어간다.
        pass
    return os.getenv("GEMINI_API_KEY") or None


def has_api_key() -> bool:
    return bool(get_api_key())


def _get_client():
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise AIServiceError(
            "google-genai 패키지가 설치되어 있지 않습니다. requirements.txt로 패키지를 설치해 주세요."
        ) from e

    key = get_api_key()
    if not key:
        raise AIServiceError(
            "Gemini API 키가 설정되어 있지 않습니다. "
            "로컬에서는 .env 파일에, 배포 시에는 Streamlit secrets에 GEMINI_API_KEY를 등록해 주세요. "
            "키가 없다면 데모 모드를 이용해 주세요."
        )
    return genai.Client(
        api_key=key,
        http_options=types.HttpOptions(timeout=int(REQUEST_TIMEOUT * 1000)),
    )


def _call_model(client, system: str, user: str) -> str:
    """모델을 1회 호출하고 텍스트 응답을 반환한다. 오류는 한국어 메시지로 변환한다."""
    from google.genai import types
    from google.genai.errors import APIError, ClientError, ServerError

    try:
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                max_output_tokens=MAX_TOKENS,
            ),
        )
    except ClientError as e:
        code = getattr(e, "code", None)
        if code in (401, 403):
            raise AIServiceError(
                "API 키 인증에 실패했습니다. 키가 올바른지 확인해 주세요. "
                "문제가 계속되면 데모 모드를 이용해 주세요."
            ) from e
        if code == 429:
            raise AIServiceError(
                "API 사용량 한도에 도달했습니다. 잠시 후 다시 시도하거나 데모 모드를 이용해 주세요."
            ) from e
        raise AIServiceError(
            f"요청 처리 중 오류가 발생했습니다 (코드 {code}). "
            "작업 내용을 확인한 뒤 다시 시도해 주세요."
        ) from e
    except ServerError as e:
        raise AIServiceError(
            f"AI 서비스 서버 오류가 발생했습니다 (코드 {getattr(e, 'code', None)}). "
            "잠시 후 다시 시도하거나 데모 모드를 이용해 주세요."
        ) from e
    except APIError as e:
        raise AIServiceError(
            f"AI 서비스 오류가 발생했습니다: {e}. "
            "잠시 후 다시 시도하거나 데모 모드를 이용해 주세요."
        ) from e
    except Exception as e:
        if "timeout" in type(e).__name__.lower() or "timeout" in str(e).lower():
            raise AIServiceError(
                "AI 응답 대기 시간이 초과되었습니다. 네트워크 상태를 확인한 뒤 다시 시도해 주세요. "
                "작업 내용이 매우 길다면 조금 줄여서 시도해 보세요."
            ) from e
        raise AIServiceError(
            "AI 서버에 연결할 수 없습니다. 인터넷 연결을 확인한 뒤 다시 시도해 주세요. "
            "계속 실패하면 데모 모드를 이용해 주세요."
        ) from e

    candidates = getattr(response, "candidates", None) or []
    finish_reason = None
    if candidates:
        finish_reason = getattr(candidates[0], "finish_reason", None)
        finish_reason = str(finish_reason).upper() if finish_reason is not None else None

    if finish_reason and ("SAFETY" in finish_reason or "BLOCK" in finish_reason or "PROHIBITED" in finish_reason):
        raise AIServiceError(
            "AI가 안전 정책에 따라 이 요청에 대한 응답을 생성하지 못했습니다. "
            "작업 내용을 수정하여 다시 시도해 주세요."
        )
    if finish_reason and "MAX_TOKENS" in finish_reason:
        raise AIServiceError(
            "AI 응답이 허용 길이를 초과했습니다. 작업 내용을 조금 더 간결하게 입력해 주세요."
        )

    text = getattr(response, "text", None)
    if not text:
        raise AIServiceError("AI 응답이 비어 있습니다. 잠시 후 다시 시도해 주세요.")
    return text


def _extract_json(text: str) -> dict:
    """응답 텍스트에서 JSON 객체를 추출한다. 실패 시 ValueError."""
    cleaned = text.strip()
    # 마크다운 코드블록 제거
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # 첫 '{'부터 마지막 '}'까지 잘라서 재시도
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        return json.loads(cleaned[start : end + 1])
    raise ValueError("JSON 객체를 찾을 수 없습니다.")


def _call_and_parse(client, system: str, user: str, model_cls):
    """모델 호출 → JSON 파싱 → Pydantic 검증. 실패 시 1회만 재시도한다."""
    last_error: Exception | None = None
    for attempt in range(2):  # 최초 1회 + 재시도 1회
        prompt = user if attempt == 0 else user + prompts.RETRY_SUFFIX
        text = _call_model(client, system, prompt)
        try:
            data = _extract_json(text)
            return model_cls.model_validate(data)
        except (ValueError, json.JSONDecodeError, ValidationError) as e:
            last_error = e
            if attempt == 0:
                time.sleep(1)
                continue
    raise AIServiceError(
        "AI 응답을 해석하지 못했습니다. 자동 재시도까지 실패했습니다. "
        "잠시 후 다시 시도하거나, 작업 내용을 조금 더 구체적으로 입력해 주세요."
    ) from last_error


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------

def run_first_pass(work: WorkInput) -> AssessmentResult:
    """1차 AI: 작업 정보를 분석하여 위험성평가 초안을 생성한다."""
    client = _get_client()
    return _call_and_parse(
        client,
        prompts.FIRST_PASS_SYSTEM,
        prompts.build_first_pass_user(work),
        AssessmentResult,
    )


def run_review_pass(work: WorkInput, first: AssessmentResult) -> ReviewResult:
    """2차 AI: 원본 입력과 1차 결과를 함께 검토하여 최종 결과를 생성한다."""
    client = _get_client()
    first_json = json.dumps(first.model_dump(), ensure_ascii=False, indent=1)
    review = _call_and_parse(
        client,
        prompts.REVIEW_SYSTEM,
        prompts.build_review_user(work, first_json),
        ReviewResult,
    )
    # 2차 AI가 final을 비워서 반환하는 극단적 경우 1차 결과로 대체
    if not review.final.hazards:
        review.final = first
    return review
