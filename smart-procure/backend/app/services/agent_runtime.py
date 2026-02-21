import json
import logging
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple


ToolFn = Callable[[Dict[str, Any]], Dict[str, Any]]
logger = logging.getLogger(__name__)

_TOOL_METRICS_LOCK = threading.Lock()
_TOOL_METRICS = {
    "total_calls": 0,
    "success_calls": 0,
    "failed_calls": 0,
}


def _record_tool_metric(name: str, amount: int = 1) -> None:
    with _TOOL_METRICS_LOCK:
        _TOOL_METRICS[name] = _TOOL_METRICS.get(name, 0) + amount


def get_tool_runtime_stats() -> Dict[str, Any]:
    with _TOOL_METRICS_LOCK:
        stats = dict(_TOOL_METRICS)
    total = stats.get("total_calls", 0)
    stats["success_rate"] = round((stats.get("success_calls", 0) / total), 4) if total else 0.0
    return stats


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tuple[Dict[str, Any], ToolFn]] = {}

    def register(self, name: str, spec: Dict[str, Any], fn: ToolFn):
        self._tools[name] = (spec, fn)

    def describe(self) -> List[Dict[str, Any]]:
        return [{"name": n, **spec} for n, (spec, _) in self._tools.items()]

    def execute(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        _record_tool_metric("total_calls")
        item = self._tools.get(name)
        if not item:
            _record_tool_metric("failed_calls")
            return {"ok": False, "tool": name, "error": f"unknown tool: {name}"}
        _, fn = item
        try:
            result = fn(args or {})
            _record_tool_metric("success_calls")
            return {"ok": True, "tool": name, "result": result}
        except Exception as e:
            _record_tool_metric("failed_calls")
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


def _looks_like_clarification_prompt(content: Any) -> bool:
    if not isinstance(content, str):
        return True
    text = content.strip()
    if not text:
        return True
    lowered = text.lower()
    hints = [
        "请从搜索结果中选择",
        "希望我深入搜索哪家",
        "更具体的搜索要求",
        "which one",
        "choose one",
        "more specific",
    ]
    return any(h in text or h in lowered for h in hints)


def _is_noise_url(url: str) -> bool:
    lowered = (url or "").strip().lower()
    if not lowered:
        return True
    if lowered.startswith("javascript:"):
        return True
    if "baidu.com/link?" in lowered:
        return True
    if "/baidu.php?url=" in lowered:
        return True
    return False


def _build_search_result_reply(tool_results: List[Dict[str, Any]], max_items: int = 5) -> Optional[str]:
    # Prefer structured browser search results when available.
    collected: List[Dict[str, str]] = []
    latest_query = ""
    for item in reversed(tool_results):
        if not isinstance(item, dict) or not item.get("ok"):
            continue
        if item.get("tool") != "web_browse":
            continue
        result = item.get("result")
        if not isinstance(result, dict):
            continue
        if not latest_query and isinstance(result.get("query"), str):
            latest_query = result["query"].strip()
        results = result.get("results")
        if not isinstance(results, list):
            continue
        for row in results:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            url = str(row.get("url") or "").strip()
            abstract = str(row.get("abstract") or "").strip()
            if not title or _is_noise_url(url):
                continue
            collected.append({"title": title, "url": url, "abstract": abstract})
            if len(collected) >= max_items:
                break
        if len(collected) >= max_items:
            break

    if collected:
        head = "已为您完成深入搜索，当前可用结果如下："
        if latest_query:
            head = f"已为您完成深入搜索（关键词：{latest_query}），当前可用结果如下："
        lines = [head, ""]
        for idx, row in enumerate(collected, start=1):
            lines.append(f"{idx}. [{row['title']}]({row['url']})")
            lines.append(f"   链接：{row['url']}")
            if row["abstract"]:
                lines.append(f"   摘要：{row['abstract']}")
            lines.append("")
        lines.append("如果你要，我可以继续基于这几条逐个打开并提取：公司名称、是否授权、联系人、电话、地区。")
        return "\n".join(lines).strip()

    # Fallback to supplier search message text.
    for item in reversed(tool_results):
        if not isinstance(item, dict) or not item.get("ok"):
            continue
        if item.get("tool") != "web_search_supplier":
            continue
        result = item.get("result")
        if isinstance(result, dict):
            message = result.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
    return None


def _should_normalize_search_ask(content: Any, tool_results: List[Dict[str, Any]]) -> bool:
    if not isinstance(content, str):
        return False
    # Only normalize when we do have search results from tools.
    has_search_result = any(
        isinstance(item, dict)
        and item.get("ok")
        and item.get("tool") in ("web_browse", "web_search_supplier")
        for item in tool_results
    )
    if not has_search_result:
        return False

    text = content.strip()
    if not text:
        return True
    lowered = text.lower()
    hints = [
        "https://www.baidu.com/link?url=...",
        "http://www.baidu.com/link?url=...",
        "由于搜索结果较多",
        "建议您：",
        "无法一次性获取所有页面的详细内容",
    ]
    return any(h in text or h in lowered for h in hints)


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

你是SmartProcure智能采购系统的**智能采购助手**（Planner阶段）。
你的核心能力包括：
1. 从用户的自然语言报价中提取结构化数据，并精准匹配到表格中的正确行
2. 帮助用户搜索产品价格、供应商信息等采购相关内容
3. 处理工业零部件型号（如FESTO、SMC、费斯托等品牌的气动元件）

## 职责边界

**你可以做以下事情**：
1. 调用工具获取信息（如供应商查询、网络搜索、网页浏览）
2. 询问用户补充信息或展示查询结果
3. **响应用户的临时搜索请求**（即使表格为空或请求与当前表格无关）

**你绝对不能**：
- 输出 WRITE 动作（这是Writer的职责）
- 编造或猜测行号（必须从相关产品列表中匹配）
- 询问"写第几家/第几个slot"（槽位由后端算法自动处理）
- **拒绝用户的合理搜索请求**（如搜索产品价格、供应商等）

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

**价格(price)提取规则 - 最重要**：
用户报价中的价格表达方式多样，你必须智能识别：
1. 找出文本中的数字（整数或小数），这通常就是价格
2. 价格可能出现在任何位置，可能带有"元"、"块"、"￥"等单位，也可能不带
3. "含税"、"含运"、"含税运"等词可能在价格前面或后面
4. 中文数字需转换：如"一千八"→1800，"六百五"→650

**核心原则**：只要文本中有数字，就要提取为price字段！

**宽松模式 - 缺失字段处理**：
| 字段 | 用户未提供时的处理 |
|------|-------------------|
| 税费(tax) | 只说"含税"→tax=true, shipping=null，不追问含运 |
| 品牌(offer_brand) | 使用表格中该行的品牌，不追问 |
| 供应商(supplier) | 见下方供应商识别规则 |
| 含运(shipping) | 填null，不追问 |

**供应商(supplier)识别规则**：
用户报价中经常包含供应商信息，格式多样，需要智能识别：
1. **公司名称**：包含"公司"、"有限"、"厂"、"店"等关键词，如"黎明液压有限公司"
2. **联系人**：中文姓名（2-4个字），常跟在公司名后或电话前，如"张先生"、"李经理"
3. **联系电话**：11位手机号或座机号，如"18765431241"

**识别示例**：
- "黎明液压有限公司张先生18765431241" → supplier="黎明液压有限公司 张先生 18765431241"
- "张三 13800138000" → supplier="张三 13800138000"
- "深圳XX贸易公司" → supplier="深圳XX贸易公司"

**重要**：当识别到供应商信息时，必须提取到supplier字段，不要写入remarks！

**行号匹配规则（严格遵守）**：
1. 相关产品列表中只有一个匹配 → 直接使用该行号
2. **多个匹配时必须ASK追问**：即使品牌相同，如果有多个产品匹配，必须询问用户是哪个具体产品
3. **绝对禁止**：用户只报了一个价格时，把同一个价格写入多行！这是严重错误！

**示例**：
- 用户说"滤芯1800元"，相关产品有4个滤芯 → 必须ASK"请问是哪个滤芯？"
- 用户说"TFX-160x180 1800元"，只匹配到一个 → 直接写入

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
- 需要访问具体网页或搜索详细信息时调用：web_browse

**搜索结果处理规则（非常重要）**：
当工具结果中已经包含 web_browse 的搜索结果时：
1. **不要重复调用相同的搜索**，直接使用 ASK 动作展示结果给用户
2. 将搜索结果整理成易读的格式，包括标题、链接、摘要
3. 如果搜索结果为空或失败，告知用户并建议其他方式

示例 - 当已获得搜索结果时的正确响应：
```json
{{"action":"ASK","content":"为您搜索到以下黎明滤芯相关信息：\\n\\n1. **标题1**\\n   链接：url1\\n\\n2. **标题2**\\n   链接：url2\\n\\n如需了解具体价格，建议点击链接查看或联系供应商。"}}
```

**供应商搜索请求识别**：
当用户的消息包含以下关键词时，应调用 web_search_supplier 工具：
- "搜索"、"查找"、"找一下"、"帮我找"
- "代理商"、"经销商"、"供应商"
- "哪里买"、"哪里有卖"、"谁家有"

示例：
- "帮我搜索一下西门子的代理商" → 调用 web_search_supplier，args: {{"brand": "西门子"}}
- "找一下FESTO的供应商" → 调用 web_search_supplier，args: {{"brand": "FESTO"}}
- "SMC哪里有卖" → 调用 web_search_supplier，args: {{"brand": "SMC"}}

**网页浏览请求识别**：
当用户的消息包含以下关键词时，应调用 web_browse 工具：
- "看看"、"访问"、"打开"、"浏览" + 网址/链接/网页/页面
- "搜索"、"查一下"、"帮我查"、"帮我搜" + 具体信息（价格、参数、详情等）
- "百度一下"、"百度搜索"、"搜一搜"、"查询"
- "XXX的价格"、"XXX多少钱"、"XXX报价"

**重要**：即使表格为空或用户的请求与当前表格无关，也应该响应用户的搜索请求！
这是临时查询需求，直接调用 web_browse 工具帮助用户搜索即可。

示例：
- "帮我看看这个链接 https://xxx.com" → web_browse, args: {{"url": "https://xxx.com"}}
- "打开这个网页" → web_browse, args: {{"url": "..."}}
- "帮我搜索一下FESTO气缸的价格" → web_browse, args: {{"action": "search", "query": "FESTO气缸价格"}}
- "百度一下SMC电磁阀参数" → web_browse, args: {{"action": "search", "query": "SMC电磁阀参数"}}
- "帮我查一下这个型号的详细信息" → web_browse, args: {{"action": "search", "query": "型号 详细信息"}}
- "帮我在百度搜索一下黎明滤芯的价格" → web_browse, args: {{"action": "search", "query": "黎明滤芯价格"}}
- "搜索一下西门子PLC的报价" → web_browse, args: {{"action": "search", "query": "西门子PLC报价"}}

**迭代式浏览器工具（深度搜索）**：
当需要深入搜索、点击链接查看详情时，使用迭代式浏览器工具：

| 工具 | 功能 | 参数 |
|------|------|------|
| browser_goto | 导航到URL（自动启动会话） | url: 目标网址 |
| browser_click | 点击页面元素 | element: 元素描述 |
| browser_input | 输入文本 | element: 输入框描述, text: 内容 |
| browser_snapshot | 获取页面快照 | 无 |
| browser_scroll | 滚动页面 | direction: up/down |
| browser_back | 返回上一页 | 无 |

**迭代搜索流程示例**：
用户说"帮我搜索黎明滤芯的价格，找到具体报价"：
1. browser_goto → https://www.baidu.com
2. browser_input → element: "搜索框", text: "黎明滤芯价格"
3. browser_click → element: "百度一下"
4. browser_snapshot → 查看搜索结果
5. browser_click → element: "第一个搜索结果链接"
6. browser_snapshot → 获取详情页内容
7. 整理信息后 ASK 展示给用户

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

**价格(price)提取规则 - 最重要**：
用户报价中的价格表达方式多样，你必须智能识别：
1. 找出文本中的数字（整数或小数），这通常就是价格
2. 价格可能出现在任何位置，可能带有"元"、"块"、"￥"等单位，也可能不带
3. "含税"、"含运"、"含税运"等词可能在价格前面或后面
4. 中文数字需转换：如"一千八"→1800，"六百五"→650

**核心原则**：只要文本中有数字，就要提取为price字段！

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
| supplier | 见下方供应商识别规则 |
| remarks | 见下方备注规则 |

**供应商(supplier)识别规则**：
用户报价中经常包含供应商信息，格式多样，需要智能识别：
1. **公司名称**：包含"公司"、"有限"、"厂"、"店"等关键词
2. **联系人**：中文姓名（2-4个字），常跟在公司名后或电话前
3. **联系电话**：11位手机号或座机号

**重要**：当识别到供应商信息时，必须提取到supplier字段，不要写入remarks！

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
- [ ] **相关产品列表中只有一个匹配，或者用户明确指定了具体型号**
- [ ] **绝对禁止**：把同一个价格写入多行！

**关键规则**：
- 相关产品列表有多个匹配 + 用户只报了一个价格 → 必须ASK追问是哪个产品
- 只有一个匹配 → 直接WRITE
"""


def run_two_stage_agent(
    *,
    call_llm: Callable[..., str],
    user_message: str,
    history_messages: Optional[List[Dict[str, Any]]],
    context: Dict[str, str],
    tools: ToolRegistry,
    max_tool_steps: int = 3,
) -> Dict[str, Any]:
    tools_catalog_json = json.dumps(tools.describe(), ensure_ascii=False)
    tool_results: List[Dict[str, Any]] = []
    draft: Dict[str, Any] = {}
    request_id = uuid.uuid4().hex[:12]

    for step_idx in range(max_tool_steps + 1):
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
        planner_out_str = call_llm(
            planner_prompt,
            user_message,
            history_messages,
            request_id=request_id,
            step=f"planner_{step_idx + 1}",
        )
        logger.warning("[DEBUG] Planner LLM 响应: %s...", planner_out_str[:500])
        planner_out = _safe_json_loads(planner_out_str) or {}
        logger.warning(
            "[DEBUG] Planner 解析结果: request_id=%s action=%s tool=%s",
            request_id,
            planner_out.get("action"),
            planner_out.get("tool"),
        )

        action = planner_out.get("action")
        if action == "ASK":
            ask_content = planner_out.get("content")
            if _looks_like_clarification_prompt(ask_content):
                fallback_reply = _build_search_result_reply(tool_results)
                if fallback_reply:
                    return {"action": "ASK", "content": fallback_reply}
            return {"action": "ASK", "content": ask_content}

        if action == "CALL_TOOL":
            tool_name = planner_out.get("tool")
            args = planner_out.get("args") or {}
            if not isinstance(tool_name, str) or not tool_name.strip():
                return {"action": "ASK", "content": "Planner未提供有效的tool名称"}
            if not isinstance(args, dict):
                args = {}
            tool_result = tools.execute(tool_name.strip(), args)
            logger.warning("[DEBUG] 工具执行结果: request_id=%s %s", request_id, str(tool_result)[:500])
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
    writer_out_str = call_llm(
        writer_prompt,
        user_message,
        history_messages,
        request_id=request_id,
        step="writer",
    )
    writer_out = _safe_json_loads(writer_out_str) or {}
    w_action = writer_out.get("action")
    if w_action == "ASK":
        ask_content = writer_out.get("content")
        if _should_normalize_search_ask(ask_content, tool_results):
            fallback_reply = _build_search_result_reply(tool_results)
            if fallback_reply:
                return {"action": "ASK", "content": fallback_reply}
        return {"action": "ASK", "content": ask_content}
    if w_action == "WRITE":
        updates = writer_out.get("updates")
        if isinstance(updates, list):
            return {"action": "WRITE", "updates": updates, "draft": draft, "tool_results": tool_results}
        data = writer_out.get("data") or {}
        return {"action": "WRITE", "data": data, "draft": draft, "tool_results": tool_results}
    return {"action": "ASK", "content": "Writer返回了未知指令"}

