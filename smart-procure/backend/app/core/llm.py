import json
import logging
import os
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from openai import OpenAI

from .config import settings

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None

LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
LLM_RETRY_BACKOFF_SECONDS = float(os.getenv("LLM_RETRY_BACKOFF_SECONDS", "0.8"))

_METRICS_LOCK = threading.Lock()
_LLM_METRICS = {
    "total_requests": 0,
    "success_requests": 0,
    "fallback_requests": 0,
    "mock_requests": 0,
    "total_attempts": 0,
    "failed_attempts": 0,
    "parse_failures": 0,
}


def _record_metric(name: str, amount: int = 1) -> None:
    with _METRICS_LOCK:
        _LLM_METRICS[name] = _LLM_METRICS.get(name, 0) + amount


def get_llm_gateway_stats() -> Dict[str, Any]:
    with _METRICS_LOCK:
        stats = dict(_LLM_METRICS)

    total = stats.get("total_requests", 0)
    attempts = stats.get("total_attempts", 0)
    stats["success_rate"] = round((stats.get("success_requests", 0) / total), 4) if total else 0.0
    stats["fallback_rate"] = round((stats.get("fallback_requests", 0) / total), 4) if total else 0.0
    stats["parse_failure_rate"] = round((stats.get("parse_failures", 0) / attempts), 4) if attempts else 0.0
    return stats


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.API_KEY,
            base_url="https://api.deepseek.com",
            timeout=LLM_TIMEOUT_SECONDS,
        )
    return _client


def _extract_first_json(text: str) -> Optional[str]:
    if not isinstance(text, str):
        return None
    cleaned = text.strip().replace("```json", "").replace("```", "").strip()
    decoder = json.JSONDecoder()
    for i, ch in enumerate(cleaned):
        if ch not in "{[":
            continue
        try:
            _, end = decoder.raw_decode(cleaned[i:])
            return cleaned[i : i + end]
        except Exception:
            continue
    return None


def _ask_fallback(message: str) -> str:
    return json.dumps({"action": "ASK", "content": message}, ensure_ascii=False)


def _sanitize_json_content(content: Any) -> Optional[str]:
    if not isinstance(content, str):
        return None

    clean_content = content.replace("```json", "").replace("```", "").strip()
    try:
        obj = json.loads(clean_content)
        if isinstance(obj, dict):
            return json.dumps(obj, ensure_ascii=False)
    except Exception:
        pass

    extracted = _extract_first_json(content)
    if extracted is None:
        return None

    try:
        obj = json.loads(extracted)
        if isinstance(obj, dict):
            return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return None
    return None


def _build_messages(
    system_prompt: str,
    user_message: str,
    history_messages: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if history_messages:
        for m in history_messages:
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def _call_llm_once(messages: List[Dict[str, str]]) -> str:
    response = get_client().chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        stream=False,
        timeout=LLM_TIMEOUT_SECONDS,
    )
    content = response.choices[0].message.content
    normalized = _sanitize_json_content(content)
    if normalized is None:
        _record_metric("parse_failures")
        raise ValueError("LLM returned invalid JSON payload")
    return normalized


def call_llm(
    system_prompt: str,
    user_message: str,
    history_messages: Optional[List[Dict[str, Any]]] = None,
    request_id: Optional[str] = None,
    step: str = "default",
):
    req_id = request_id or uuid.uuid4().hex[:12]
    _record_metric("total_requests")

    # Mock behavior if no valid key
    if not settings.API_KEY or "placeholder" in settings.API_KEY:
        _record_metric("mock_requests")
        _record_metric("success_requests")
        logger.info(
            "llm_call_mock request_id=%s step=%s retry_count=%s",
            req_id,
            step,
            0,
        )
        history_text = ""
        if history_messages:
            history_text = " ".join(
                [str(m.get("content", "")) for m in history_messages if m.get("role") == "user"]
            )
        combined = (history_text + " " + user_message).strip()
        return mock_llm_response(combined)

    messages = _build_messages(system_prompt, user_message, history_messages)
    retries = max(0, LLM_MAX_RETRIES)
    started = time.perf_counter()

    for attempt in range(retries + 1):
        _record_metric("total_attempts")
        try:
            result = _call_llm_once(messages)
            _record_metric("success_requests")
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "llm_call_success request_id=%s step=%s retry_count=%s elapsed_ms=%s",
                req_id,
                step,
                attempt,
                elapsed_ms,
            )
            return result
        except Exception as e:
            _record_metric("failed_attempts")
            logger.warning(
                "llm_call_attempt_failed request_id=%s step=%s attempt=%s/%s retry_count=%s error=%s",
                req_id,
                step,
                attempt + 1,
                retries + 1,
                attempt,
                e,
            )
            if attempt >= retries:
                _record_metric("fallback_requests")
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                logger.error(
                    "llm_call_fallback request_id=%s step=%s retry_count=%s elapsed_ms=%s",
                    req_id,
                    step,
                    attempt,
                    elapsed_ms,
                )
                return _ask_fallback(f"LLM调用失败: {str(e)}")
            sleep_seconds = LLM_RETRY_BACKOFF_SECONDS * (2**attempt)
            time.sleep(sleep_seconds)

    _record_metric("fallback_requests")
    return _ask_fallback("LLM调用失败: 未知错误")


def mock_llm_response(message: str):
    # Simple regex mock for testing without API Key
    match = re.search(r"(\d+)\s*(?:行|号)?[^\d]*(\d+(?:\.\d+)?)", message)
    if match:
        row = int(match.group(1))
        price = float(match.group(2))
        return json.dumps(
            {
                "action": "WRITE",
                "data": {
                    "target_row": row,
                    "price": price,
                    "tax": True if "含税" in message else False,
                    "shipping": True if "含运" in message else False,
                    "delivery_time": "3天",
                    "remarks": "Mock Data",
                },
            },
            ensure_ascii=False,
        )

    if "张三" in message:
        return json.dumps(
            {
                "action": "WRITE",
                "data": {
                    "target_row": 2,
                    "price": 8800,
                    "delivery_time": "现货",
                    "lookup_supplier": "张三",
                },
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "action": "ASK",
            "content": "（Mock模式）未检测到 API Key。请提供报价，例如：第2行 100元，或配置 backend/.env 的 API_KEY。",
        },
        ensure_ascii=False,
    )


def extract_suppliers_with_llm(supplier_texts: List[str]) -> List[Dict[str, Any]]:
    """使用 LLM 从供应商文本列表中提取结构化信息。"""
    if not supplier_texts:
        return []

    unique_texts = list(set([t.strip() for t in supplier_texts if t and t.strip()]))
    if not unique_texts:
        return []

    if not settings.API_KEY or "placeholder" in settings.API_KEY:
        logger.warning("extract_suppliers_with_llm skipped: API key is not configured")
        return []

    request_id = uuid.uuid4().hex[:12]
    logger.info(
        "llm_extract_suppliers_start request_id=%s step=%s retry_count=%s batch_size=%s",
        request_id,
        "extract_suppliers",
        0,
        len(unique_texts),
    )

    system_prompt = """你是供应商信息提取助手。请从输入文本中提取：
- company_name（公司名，不明确时填“未知公司”）
- contact_name（联系人姓名，不明确时为 null）
- contact_phone（电话，不明确时为 null）
- original_text（原始文本）

仅返回 JSON 数组，不要输出额外说明。"""

    user_message = "请提取以下供应商文本信息：\n\n" + "\n".join(
        [f"{i+1}. {t}" for i, t in enumerate(unique_texts[:50])]
    )

    try:
        response = get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            stream=False,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        content = response.choices[0].message.content
        extracted = _extract_first_json(content or "")
        if extracted:
            result = json.loads(extracted)
            if isinstance(result, list):
                logger.info(
                    "llm_extract_suppliers_success request_id=%s step=%s retry_count=%s extracted=%s",
                    request_id,
                    "extract_suppliers",
                    0,
                    len(result),
                )
                return result
        return []
    except Exception as e:
        logger.error(
            "llm_extract_suppliers_failed request_id=%s step=%s retry_count=%s error=%s",
            request_id,
            "extract_suppliers",
            0,
            e,
        )
        return []
