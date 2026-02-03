import json
import re
import os
from typing import Any, Dict, List, Optional
from openai import OpenAI
from .config import settings

_client: Optional[OpenAI] = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.API_KEY,
            base_url="https://api.deepseek.com"
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
            return cleaned[i:i + end]
        except Exception:
            continue
    return None

def call_llm(system_prompt: str, user_message: str, history_messages: Optional[List[Dict[str, Any]]] = None):
    # Mock behavior if no valid key
    if not settings.API_KEY or "placeholder" in settings.API_KEY:
        history_text = ""
        if history_messages:
            history_text = " ".join([str(m.get("content", "")) for m in history_messages if m.get("role") == "user"])
        combined = (history_text + " " + user_message).strip()
        return mock_llm_response(combined)

    try:
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if history_messages:
            for m in history_messages:
                role = m.get("role")
                content = m.get("content")
                if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})

        response = get_client().chat.completions.create(
            model="deepseek-chat", 
            messages=messages,
            stream=False
        )
        content = response.choices[0].message.content
        # Ensure it's valid JSON
        try:
            # clear markdown code blocks if any
            clean_content = content.replace("```json", "").replace("```", "").strip()
            json.loads(clean_content)
            return clean_content
        except:
            extracted = _extract_first_json(content)
            if extracted is not None:
                try:
                    json.loads(extracted)
                    return extracted
                except Exception:
                    pass
            return json.dumps({"action": "ASK", "content": "LLM返回格式错误: 无法提取JSON"})
            
    except Exception as e:
        print(f"LLM Error: {e}")
        return json.dumps({"action": "ASK", "content": f"LLM调用失败: {str(e)}"})

def mock_llm_response(message: str):
    # Simple regex mock for testing without API Key
    
    # Check for "Row X Price Y" pattern
    # e.g. "第2行 100元"
    match = re.search(r'(\d+)\s*(?:行|号).*?(\d+(?:\.\d+)?)\s*(?:元|块)', message)
    if match:
        row = int(match.group(1))
        price = float(match.group(2))
        return json.dumps({
            "action": "WRITE",
            "data": {
                "target_row": row,
                "price": price,
                "tax": True if "含税" in message else False,
                "shipping": True if "含运" in message else False,
                "delivery_time": "3天",
                "remarks": "Mock Data"
            }
        })
    
    # "张三" -> Lookup
    if "张三" in message:
         return json.dumps({
            "action": "WRITE",
            "data": {
                "target_row": 2, # Default to row 2
                "price": 8800,
                "delivery_time": "现货",
                "lookup_supplier": "张三"
            }
        })

    return json.dumps({
        "action": "ASK",
        "content": "（Mock模式）未检测到API Key。请提供报价，例如：'2行 100元' 或 '找张三'。或在backend/.env中配置API Key。"
    })


def extract_suppliers_with_llm(supplier_texts: List[str]) -> List[Dict[str, Any]]:
    """
    使用LLM从供应商文本列表中提取结构化信息

    Args:
        supplier_texts: 供应商列的文本列表

    Returns:
        提取的供应商信息列表
    """
    if not supplier_texts:
        return []

    # 过滤空值和重复值
    unique_texts = list(set([t.strip() for t in supplier_texts if t and t.strip()]))
    if not unique_texts:
        return []

    # 构建prompt
    system_prompt = """你是一个供应商信息提取助手。从用户提供的供应商文本中提取结构化信息。

每条供应商文本可能包含：公司名称、联系人姓名、电话号码（手机或座机）。
格式可能不规范，需要你智能识别。

输出JSON数组，每个元素包含：
- company_name: 公司名称（如果没有明确公司名，填"未知公司"）
- contact_name: 联系人姓名（2-4个汉字，如果没有填null）
- contact_phone: 电话号码（手机11位或座机，如果没有填null）
- original_text: 原始文本

只输出JSON数组，不要其他内容。如果某条文本无法提取有效信息，跳过它。"""

    user_message = "请从以下供应商文本中提取信息：\n\n" + "\n".join([f"{i+1}. {t}" for i, t in enumerate(unique_texts[:50])])  # 限制50条

    # 如果没有API Key，返回空
    if not settings.API_KEY or "placeholder" in settings.API_KEY:
        print("[供应商提取] 无API Key，跳过AI提取")
        return []

    try:
        response = get_client().chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            stream=False
        )
        content = response.choices[0].message.content

        # 提取JSON
        extracted = _extract_first_json(content)
        if extracted:
            result = json.loads(extracted)
            if isinstance(result, list):
                return result

        return []
    except Exception as e:
        print(f"[供应商提取] LLM调用失败: {e}")
        return []
