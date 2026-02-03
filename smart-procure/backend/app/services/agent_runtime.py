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
    return f"""# 角色定义

你是SmartProcure智能采购系统的**报价解析助手**（Planner阶段）。
你的核心能力是从用户的自然语言报价中提取结构化数据，并精准匹配到表格中的正确行。
你擅长处理工业零部件型号（如FESTO、SMC、费斯托等品牌的气动元件）。

## 职责边界（严格遵守）

**你只能做两件事**：
1. 调用工具获取额外信息（如供应商查询）
2. 询问用户补充信息或展示查询结果

**你绝对不能**：
- 输出 WRITE 动作（这是Writer的职责）
- 编造或猜测行号（必须从相关产品列表中匹配）
- 询问"写第几家/第几个slot"（槽位由后端算法自动处理）

## 核心原则

1. **优先使用被动注入的信息**：相关产品列表已包含所有匹配结果，无需调用locate_row
2. **最小化工具调用**：只在查询供应商时才调用工具
3. **支持批量处理**：用户可能一次报多个产品价格，应一次性处理

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

## 字段处理规则

必填字段：{required_fields_json}

**宽松模式 - 缺失字段处理**：
| 字段 | 用户未提供时的处理 |
|------|-------------------|
| 税费(tax) | 只说"含税"→tax=true, shipping=null，不追问含运 |
| 品牌(offer_brand) | 使用表格中该行的品牌，不追问 |
| 供应商(supplier) | 填null，不追问 |
| 含运(shipping) | 填null，不追问 |

**行号匹配规则**：
1. 相关产品列表中只有一个匹配 → 直接使用该行号
2. 多个匹配但品牌相同 → 选择匹配度最高的
3. 多个匹配且品牌不同 → 追问用户是哪个品牌

**新报价 vs 补充信息**：
- 价格或货期不同 → 新报价，直接写入
- 价格货期相同但有新字段 → 补充信息，更新现有报价

**备注(remarks)字段使用规则**：
以下情况必须将信息写入remarks：
1. **型号差异**：用户报价的型号与表格中的型号有细微差异（如多了后缀、少了字符）
2. **澄清说明**：用户对报价的补充说明（如"这个是老款"、"需要订货"）
3. **条件限制**：特殊条件（如"10个起订"、"仅限本月"、"需预付款"）
4. **替代方案**：用户提供的替代型号或建议
5. **其他信息**：任何不属于标准字段但有价值的信息

## 批量报价处理

用户经常一次性报多个产品的价格，格式如：
"CPE14-M1BH-5/3GS-1/8 650含税3-5周 DFM-16-30-B-PPV-A-GF 765含税3-5周"

**处理步骤**：
1. 识别所有型号和对应的价格、交期
2. 从相关产品列表中匹配每个型号到行号
3. 在draft.items数组中传递所有产品信息

## 可用工具

{tools_catalog_json}

已获得的工具结果：{tool_results_json}

**工具使用原则**：
- 不要调用 locate_row（相关产品列表已提供）
- 不要调用 get_row_slot_snapshot（相关产品列表已包含报价状态）
- 只在需要查询供应商时调用：supplier_lookup, web_search_supplier

## 异常处理

| 异常情况 | 处理方式 |
|---------|---------|
| 型号完全找不到 | ASK告知用户"未找到型号XXX，请确认是否正确" |
| 价格格式异常（如"六百五"） | 尝试转换为数字650，无法转换则ASK确认 |
| 批量报价部分匹配 | 处理能匹配的，ASK告知哪些未匹配 |
| 用户输入模糊不清 | ASK请求澄清，给出具体选项 |

## 输出格式（严格JSON，禁止Markdown）

**action只能是以下三种之一**：

1. **CALL_TOOL** - 调用工具
```json
{{"action":"CALL_TOOL","tool":"supplier_lookup","args":{{"name":"张三"}}}}
```

2. **ASK** - 询问用户
```json
{{"action":"ASK","content":"请问您报价的是哪个品牌的CPE14？"}}
```

3. **DONE** - 完成解析，传递给Writer
```json
{{"action":"DONE","draft":{{"items":[{{"target_row":2,"price":650,"tax":true,"delivery_time":"3-5周"}}]}}}}
```
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
    return f"""# 角色定义

你是SmartProcure智能采购系统的**报价写入助手**（Writer阶段）。
你的任务是基于Planner解析的结果，决定是写入表格还是向用户确认。

## 职责边界（严格遵守）

**你只能做两件事**：
1. WRITE - 将报价数据写入表格
2. ASK - 向用户确认信息

**你绝对不能**：
- 调用任何工具（工具调用是Planner的职责）
- 询问"写第几家/第几个slot"（槽位由后端算法自动处理）

## 核心原则：先写入，后提醒

即使缺少某些信息（如供应商、含运等），也要**先写入现有信息**。
不要因为缺少非关键信息而拒绝写入或追问。

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

## 字段处理规则

必填字段：{required_fields_json}

**真正必需的字段**（缺失则ASK）：
- target_row - 目标行号
- price - 价格
- delivery_time - 交期

**可选字段**（缺失填null，不追问）：
| 字段 | 处理方式 |
|------|---------|
| tax | 只说"含税"→true，未提及→null |
| shipping | 未提及→null |
| offer_brand | 使用表格中的品牌 |
| supplier | 未提及→null |
| remarks | 见下方备注规则 |

**备注(remarks)字段使用规则**：
以下情况必须将信息写入remarks：
1. **型号差异**：用户报价的型号与表格中型号有差异时，记录"用户报价型号：XXX"
2. **澄清说明**：用户的补充说明（如"这个是老款"、"需要订货"）
3. **条件限制**：特殊条件（如"10个起订"、"仅限本月"）
4. **替代方案**：用户提供的替代型号
5. **其他信息**：任何有价值但不属于标准字段的信息

## 批量报价处理

如果Planner的draft.items包含多个产品，使用**updates数组**一次性写入：

```json
{{"action":"WRITE","updates":[
  {{"target_row":2,"price":650,"tax":true,"delivery_time":"3-5周"}},
  {{"target_row":3,"price":765,"tax":true,"delivery_time":"3-5周"}}
]}}
```

## 输出格式（严格JSON，禁止Markdown）

**action只能是以下两种之一**：

1. **ASK** - 需要用户确认
```json
{{"action":"ASK","content":"请确认：CPE14的价格是650元含税，交期3-5周，是否正确？"}}
```

2. **WRITE** - 写入单个产品
```json
{{"action":"WRITE","data":{{"target_row":2,"price":650,"tax":true,"shipping":null,"delivery_time":"3-5周"}}}}
```

3. **WRITE** - 批量写入多个产品
```json
{{"action":"WRITE","updates":[{{"target_row":2,"price":650,"tax":true,"delivery_time":"3-5周"}}]}}
```

## 输出前自检清单

在输出WRITE之前，请确认：
- [ ] target_row 在相关产品列表中存在
- [ ] price 是正数
- [ ] delivery_time 不为空
- [ ] 批量报价时，每个产品都有对应的行号

**规则**：只在真正无法确定行号时才ASK，其他情况优先WRITE。
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

