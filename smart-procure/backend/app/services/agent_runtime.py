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
    candidate_rows_summary: str,
    tools_catalog_json: str,
    tool_results_json: str,
) -> str:
    return f"""你是一个采购Agent的Planner阶段。
你只能做两件事：1) 调用工具获取信息；2) 询问用户补充信息或展示查询结果。
你绝对不允许输出 WRITE，也不允许编造行号。
槽位(slot)的选择/顺移/按价格排序完全由后端确定性算法处理，你不需要也不允许询问"写第几家/第几个slot"。

特殊规则 - 供应商信息查询：
- 当用户的意图是查询供应商信息（例如"帮我查查XX品牌的商家"、"搜索XX的供应商"），而不是写入报价时：
  1) 先调用 web_search_supplier 工具搜索供应商信息
  2) 工具返回后，将工具结果中的 message 字段作为回复内容，使用 ASK 动作展示给用户
  3) 不要继续询问用户要为哪个物料询价，除非用户明确表示要写入报价

被动注入（表格状态摘要，不是工具）：{sheet_state_summary}
当前待询价物品：{pending_items_summary}
表头预览：{headers_preview_json}
报价字段映射（槽位 -> 列名）：{writable_fields_json}
必填字段（按表结构动态生成）：{required_fields_json}
候选行（仅供参考，最终必须靠工具确认/去歧义）：{candidate_rows_summary}

可用工具（JSON）：{tools_catalog_json}
已获得的工具结果（JSON）：{tool_results_json}

输出必须是严格 JSON（不要 Markdown），action 只能是以下之一：
1) CALL_TOOL：{{\"action\":\"CALL_TOOL\",\"tool\":\"tool_name\",\"args\":{{...}}}}
2) ASK：{{\"action\":\"ASK\",\"content\":\"...\"}}
3) DONE：{{\"action\":\"DONE\",\"draft\":{{...}}}}

draft 用于把你从用户输入中解析出的字段传递给 Writer（不要猜测缺失值）：
- target_row（仅当用户明确说第X行）
- lookup_item / lookup_brand / lookup_model（用于定位行）
- quoted_model（用户报价里给出的型号）
- quoted_spec（仅当用户在本轮消息里明确给出规格/功率等才填，例如 2KW；不要从表格或候选行“推断/复述”规格，更不要因为大小写差异（1kw vs 1KW）填入 quoted_spec）
- price / tax / shipping / delivery_time
- offer_brand（报价槽位品牌，若用户明确给出则传；否则可省略，后端会默认用物料品牌填充）
- supplier（若用户直接给了供应商完整字符串）
- lookup_supplier（若用户说“找张三”这类模糊供应商）
- remarks（用户明确给出的备注）

去歧义规则：
- 如果 locate_row 返回多个候选且用户没有提供足够区分信息（型号/规格/行号），必须 ASK，让用户选择候选行或补充型号/规格。
- 如果表里目标物料唯一且用户给的 quoted_spec/quoted_model 与表内不一致，不要追问“是否另一个型号/是否新增物料”，直接写入报价，并把不一致写入备注（后端也会自动追加备注）。
"""


def build_writer_prompt(
    *,
    sheet_state_summary: str,
    pending_items_summary: str,
    headers_preview_json: str,
    writable_fields_json: str,
    required_fields_json: str,
    candidate_rows_summary: str,
    tool_results_json: str,
    draft_json: str,
) -> str:
    return f"""你是一个采购Agent的Writer阶段。
你不能调用工具；你只能在已有工具结果基础上做决定：ASK 或 WRITE。
槽位(slot)的选择/顺移/按价格排序完全由后端确定性算法处理：\n- 如果所有slot为空，默认写入slot1。\n- 如果已有报价，按单价排序插入并顺移。\n因此你不需要也不允许询问“写第几家/第几个slot”。不要在输出中出现 slot/slot1/slot2 等字段。

被动注入（表格状态摘要，不是工具）：{sheet_state_summary}
当前待询价物品：{pending_items_summary}
表头预览：{headers_preview_json}
报价字段映射（槽位 -> 列名）：{writable_fields_json}
必填字段（按表结构动态生成）：{required_fields_json}
候选行：{candidate_rows_summary}
工具结果（JSON）：{tool_results_json}
Planner草稿（JSON）：{draft_json}

输出必须是严格 JSON（不要 Markdown），action 只能是：
1) ASK：{{\"action\":\"ASK\",\"content\":\"...\"}}
2) WRITE：{{\"action\":\"WRITE\",\"data\":{{...}}}} 或 {{\"action\":\"WRITE\",\"updates\":[{{...}},{{...}}]}}

WRITE 的 data 需要包含：
- target_row（必须有且唯一）
- price / tax / shipping / delivery_time
- offer_brand（可选；若省略后端默认用物料品牌填充）
- supplier（单个字符串，一个单元格内写“供应商全称 姓名 手机”等，若没有就省略）
- quoted_model（仅当用户在本轮消息里明确给出型号才传递；不要从表格“复述/推断”型号）
- quoted_spec（仅当用户在本轮消息里明确给出规格/功率才传递；不要因大小写差异传递）
- remarks（可选）
- lookup_supplier（可选：若需要后端补全供应商字符串）

规则：
- 如果无法确定唯一 target_row，必须 ASK（列出候选行让用户选，或让用户补充型号/规格）。\n"""


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
            candidate_rows_summary=context["candidate_rows_summary"],
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
        candidate_rows_summary=context["candidate_rows_summary"],
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

