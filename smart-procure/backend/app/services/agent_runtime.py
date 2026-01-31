import json
from typing import Any, Callable, Dict, List, Optional, Tuple


ToolFn = Callable[[Dict[str, Any]], Dict[str, Any]]


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tuple[Dict[str, Any], ToolFn]] = {}

    def register(self, name: str, spec: Dict[str, Any], fn: ToolFn):
        self._tools[name] = (spec, fn)

    def describe(self) -> List[Dict[str, Any]]:
        return [{"name": n, **spec} for n, (spec, _) in self._tools.items()]

    def execute(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        item = self._tools.get(name)
        if not item:
            return {"ok": False, "tool": name, "error": f"unknown tool: {name}"}
        spec, fn = item
        try:
            result = fn(args or {})
            return {"ok": True, "tool": name, "result": result}
        except Exception as e:
            return {"ok": False, "tool": name, "error": str(e)}


def _safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(text, str):
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _tool_results_block(tool_results: List[Dict[str, Any]]) -> str:
    if not tool_results:
        return "[]"
    return json.dumps(tool_results, ensure_ascii=False)


def build_planner_prompt(
    *,
    sheet_state_summary: str,
    pending_items_summary: str,
    headers_preview_json: str,
    writable_fields_json: str,
    required_fields_json: str,
    brand_context: str,
    relevant_rows_json: str,
    total_relevant_rows: int,
    tools_catalog_json: str,
    tool_results_json: str,
) -> str:
    return f"""你是一个采购Agent的Planner阶段。
你只能做两件事：1) 调用工具获取信息；2) 询问用户补充信息或展示查询结果。
你绝对不允许输出 WRITE，也不允许编造行号。
槽位(slot)的选择/顺移/按价格排序完全由后端确定性算法处理，你不需要也不允许询问"写第几家/第几个slot"。

## 核心原则：优先使用被动注入的信息，减少工具调用

系统已经通过智能匹配为你提供了相关行的完整信息，你应该：
1. **优先使用被动注入的"相关产品列表"来匹配用户报价**，而不是调用 locate_row 工具
2. **只在需要查询供应商信息时调用工具**（supplier_lookup, web_search_supplier）
3. **支持批量报价处理**：用户可能一次性报多个产品的价格，你应该一次性处理所有产品

## 被动注入的信息（已通过智能匹配提供）

表格状态摘要：{sheet_state_summary}
当前待询价物品：{pending_items_summary}
表头预览：{headers_preview_json}
报价字段映射（槽位 -> 列名）：{writable_fields_json}

**品牌上下文**：{brand_context}
**相关产品列表**（共{total_relevant_rows}行，已通过模糊匹配找到）：
{relevant_rows_json}

注意：相关产品列表已经包含了所有可能匹配的行，包括：
- 精确匹配的行（匹配度100%）
- 模糊匹配的行（匹配度75%以上，可能是笔误、少字母等变体）
- 如果识别到品牌，还包含该品牌的所有产品

## 字段要求（宽松模式）

必填字段：{required_fields_json}

**重要**：字段要求已放宽，允许缺失部分信息：
- **税费处理**：如果用户只说"含税"，填 tax=true, shipping=null（不追问是否含运）
- **品牌处理**：如果用户没说品牌，使用表格中该行的品牌（不追问品牌）
  - 特殊情况：如果相关产品列表中有多个不同品牌的相同型号，需要追问用户是哪个品牌
- **供应商处理**：如果用户没说供应商，可以省略（不追问供应商）
- **新报价 vs 补充信息的判断**：
  - 如果价格或货期不同，这是**新的报价**，直接写入，不要追问
  - 如果价格和货期相同，但提供了新的字段（如供应商），这是**补充信息**，更新现有报价
  - 同一产品可以有多家供应商的报价，价格不同时直接写入即可
- **行号确定规则**：
  - 如果相关产品列表中只有一个匹配的行，直接使用该行号
  - 如果有多个匹配的行但品牌相同，选择匹配度最高的
  - 如果有多个匹配的行且品牌不同，追问用户是哪个品牌或哪一行

## 批量报价处理

用户经常一次性报多个产品的价格，格式如：
"CPE14-M1BH-5/3GS-1/8 650含税3-5周 DFM-16-30-B-PPV-A-GF 765含税3-5周 ADVUL-20-30-P-A 415含税3-5周"

你应该：
1. 识别所有型号和对应的价格、交期
2. 使用相关产品列表中的信息匹配每个型号到对应的行号
3. 在draft中传递多个产品的信息（Writer会输出updates数组）

## 可用工具（仅在必要时调用）

{tools_catalog_json}
已获得的工具结果：{tool_results_json}

**工具使用原则**：
- **不要调用 locate_row**：相关产品列表已经提供了所有信息
- **不要调用 get_row_slot_snapshot**：相关产品列表已包含报价状态
- **只在需要查询供应商时调用**：supplier_lookup, web_search_supplier

## 输出格式

输出必须是严格 JSON（不要 Markdown），action 只能是：
1) CALL_TOOL：{{\"action\":\"CALL_TOOL\",\"tool\":\"tool_name\",\"args\":{{...}}}}
2) ASK：{{\"action\":\"ASK\",\"content\":\"...\"}}
3) DONE：{{\"action\":\"DONE\",\"draft\":{{...}}}}

draft 用于传递给 Writer：
- target_row：从相关产品列表中匹配的行号
- price / tax / shipping / delivery_time：从用户消息中提取
- offer_brand：可选，如果用户明确给出
- supplier / lookup_supplier：可选
- remarks：可选

**批量处理**：如果用户报了多个产品，在draft中传递数组或多个产品的信息。
"""


def build_writer_prompt(
    *,
    sheet_state_summary: str,
    pending_items_summary: str,
    headers_preview_json: str,
    writable_fields_json: str,
    required_fields_json: str,
    brand_context: str,
    relevant_rows_json: str,
    total_relevant_rows: int,
    tool_results_json: str,
    draft_json: str,
) -> str:
    return f"""你是一个采购Agent的Writer阶段。
你不能调用工具；你只能在已有信息基础上做决定：ASK 或 WRITE。
槽位(slot)的选择/顺移/按价格排序完全由后端确定性算法处理，你不需要也不允许询问"写第几家/第几个slot"。

## 被动注入的信息

表格状态摘要：{sheet_state_summary}
当前待询价物品：{pending_items_summary}
表头预览：{headers_preview_json}
报价字段映射（槽位 -> 列名）：{writable_fields_json}

**品牌上下文**：{brand_context}
**相关产品列表**（共{total_relevant_rows}行）：
{relevant_rows_json}

工具结果（JSON）：{tool_results_json}
Planner草稿（JSON）：{draft_json}

## 字段要求（宽松模式）

必填字段：{required_fields_json}

**核心原则：先写入，后提醒**
- 即使缺少某些信息（如供应商、含运等），也要先写入现有信息
- 不要因为缺少非关键信息而拒绝写入或追问
- 只有 target_row、price、delivery_time 是真正必需的
- 其他字段缺失时可以省略或填null

**字段处理规则**：
- **税费**：只说"含税"时填 tax=true, shipping=null
- **品牌**：未明确时使用表格中的品牌
- **供应商**：未明确时填null（不要追问）
- **含运**：未明确时填null（不要追问）

## 批量报价处理（重要）

如果Planner传递了多个产品的信息，你应该使用 **updates 数组** 一次性写入所有产品：

{{
  "action": "WRITE",
  "updates": [
    {{"target_row": 2, "price": 650, "tax": true, "delivery_time": "3-5周"}},
    {{"target_row": 3, "price": 765, "tax": true, "delivery_time": "3-5周"}},
    {{"target_row": 4, "price": 415, "tax": true, "delivery_time": "3-5周"}}
  ]
}}

## 输出格式

输出必须是严格 JSON（不要 Markdown），action 只能是：
1) ASK：{{\"action\":\"ASK\",\"content\":\"...\"}}
2) WRITE：{{\"action\":\"WRITE\",\"data\":{{...}}}} 或 {{\"action\":\"WRITE\",\"updates\":[{{...}},{{...}}]}}

WRITE 的 data/updates 需要包含：
- target_row（必须有且唯一）
- price / tax / shipping / delivery_time
- offer_brand（可选）
- supplier（可选）
- remarks（可选）

**规则**：只在真正无法确定行号时才 ASK。
"""


def run_two_stage_agent(
    *,
    call_llm: Callable[[str, str, Optional[List[Dict[str, Any]]]], str],
    user_message: str,
    history_messages: Optional[List[Dict[str, Any]]],
    context: Dict[str, str],
    tools: ToolRegistry,
    max_tool_steps: int = 3,
) -> Dict[str, Any]:
    tools_catalog_json = json.dumps(tools.describe(), ensure_ascii=False)
    tool_results: List[Dict[str, Any]] = []
    draft: Dict[str, Any] = {}

    for _ in range(max_tool_steps + 1):
        planner_prompt = build_planner_prompt(
            sheet_state_summary=context["sheet_state_summary"],
            pending_items_summary=context["pending_items_summary"],
            headers_preview_json=context["headers_preview_json"],
            writable_fields_json=context["writable_fields_json"],
            required_fields_json=context["required_fields_json"],
            brand_context=context["brand_context"],
            relevant_rows_json=context["relevant_rows_json"],
            total_relevant_rows=context["total_relevant_rows"],
            tools_catalog_json=tools_catalog_json,
            tool_results_json=_tool_results_block(tool_results),
        )
        planner_out_str = call_llm(planner_prompt, user_message, history_messages)
        planner_out = _safe_json_loads(planner_out_str) or {}

        action = planner_out.get("action")
        if action == "ASK":
            return {"action": "ASK", "content": planner_out.get("content")}

        if action == "CALL_TOOL":
            tool_name = planner_out.get("tool")
            args = planner_out.get("args") or {}
            if not isinstance(tool_name, str) or not tool_name.strip():
                return {"action": "ASK", "content": "Planner未提供有效的tool名称"}
            if not isinstance(args, dict):
                args = {}
            tool_result = tools.execute(tool_name.strip(), args)
            tool_results.append(tool_result)
            continue

        if action == "DONE":
            d = planner_out.get("draft") or {}
            if isinstance(d, dict):
                draft = d
            break

        return {"action": "ASK", "content": "Planner返回了未知指令"}

    writer_prompt = build_writer_prompt(
        sheet_state_summary=context["sheet_state_summary"],
        pending_items_summary=context["pending_items_summary"],
        headers_preview_json=context["headers_preview_json"],
        writable_fields_json=context["writable_fields_json"],
        required_fields_json=context["required_fields_json"],
        brand_context=context["brand_context"],
        relevant_rows_json=context["relevant_rows_json"],
        total_relevant_rows=context["total_relevant_rows"],
        tool_results_json=_tool_results_block(tool_results),
        draft_json=json.dumps(draft, ensure_ascii=False),
    )
    writer_out_str = call_llm(writer_prompt, user_message, history_messages)
    writer_out = _safe_json_loads(writer_out_str) or {}
    w_action = writer_out.get("action")
    if w_action == "ASK":
        return {"action": "ASK", "content": writer_out.get("content")}
    if w_action == "WRITE":
        updates = writer_out.get("updates")
        if isinstance(updates, list):
            return {"action": "WRITE", "updates": updates, "draft": draft, "tool_results": tool_results}
        data = writer_out.get("data") or {}
        return {"action": "WRITE", "data": data, "draft": draft, "tool_results": tool_results}
    return {"action": "ASK", "content": "Writer返回了未知指令"}

