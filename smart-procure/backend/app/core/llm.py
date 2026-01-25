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
