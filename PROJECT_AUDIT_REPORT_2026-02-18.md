# SmartProcure 项目深度审查报告

审查日期：2026-02-18  
审查范围：`smart-procure/backend`、`smart-procure/frontend`、`smart-procure/admin-frontend`、`smart-procure/deploy`  
审查方式：代码走查 + 构建/测试验证 + 配置与运行链路检查

## 1. 执行摘要

项目主体可运行，但存在若干高风险问题，尤其是权限控制与发布链路完整性。  
建议先处理 P0/P1，再做性能与可维护性优化。

### 当前验证结果

- 后端测试：通过（26/26）
- 主前端 `frontend`：`lint` 通过，`build` 通过
- 管理端 `admin-frontend`：`build` 失败（见 P0-1）

## 2. 关键问题清单（按优先级）

## P0（必须优先处理）

### P0-1 管理端构建失败，阻断发布

- 现象：`admin-frontend` 执行 `npm run build` 失败
- 错误：
  - `TS2688: Cannot find type definition file for 'vite/client'`
  - `TS18003: No inputs were found in config file ... tsconfig.node.json`
- 证据文件：
  - `smart-procure/admin-frontend/tsconfig.app.json:8`
  - `smart-procure/admin-frontend/tsconfig.node.json:16`
  - `smart-procure/admin-frontend/tsconfig.json:3`
- 风险：生产构建不可用，管理端无法稳定发布

### P0-2 供应商删除接口权限过宽

- 现象：删除供应商接口仅校验“已登录”，未限制管理员
- 证据文件：
  - `smart-procure/backend/app/api/suppliers.py:92`
  - `smart-procure/backend/app/api/suppliers.py:96`
- 风险：任意普通用户可删除全局供应商数据，属于高危业务权限缺陷

### P0-3 SSE 使用 URL Query 传 Token

- 现象：通知流和管理进度流都通过 query 参数传 token
- 证据文件：
  - `smart-procure/backend/app/api/notifications.py:80`
  - `smart-procure/backend/app/api/admin.py:117`
  - `smart-procure/frontend/src/utils/api.ts:178`
  - `smart-procure/admin-frontend/src/api.ts:86`
- 风险：token 容易泄露到日志、历史、监控链路

## P1（重要问题）

### P1-1 时间戳格式潜在不规范

- 现象：`isoformat()` 后再次拼接 `"Z"`
- 证据文件：
  - `smart-procure/backend/app/api/sheets.py:142`
  - `smart-procure/backend/app/api/sheets.py:143`
- 风险：可能出现 `+00:00Z` 等非标准字符串，导致前端解析兼容性问题

### P1-2 500 错误回传内部异常细节

- 现象：多个 API 直接将 `str(exception)` 返回客户端
- 证据文件：
  - `smart-procure/backend/app/api/sheets.py:119`
  - `smart-procure/backend/app/api/suppliers.py:49`
  - `smart-procure/backend/app/api/routes.py:151`
- 风险：泄露内部实现细节，不利于安全

### P1-3 推荐算法 V1 全表扫描

- 现象：`SupplierProduct` 全量加载后再 Python 层匹配
- 证据文件：
  - `smart-procure/backend/app/services/supplier_service.py:278`
- 风险：数据量增长后接口响应退化明显

## P2（优化与一致性）

### P2-1 排行方向疑似反向

- 现象：后台与前端都按 `today_progress` 升序排序
- 证据文件：
  - `smart-procure/backend/app/services/admin_progress_service.py:231`
  - `smart-procure/admin-frontend/src/App.tsx:153`
- 风险：若业务预期是高进度优先，则当前展示与预期相反

### P2-2 历史面板“清空记录”语义不清

- 现象：按钮文案像“清空历史单”，实际调用聊天清空逻辑
- 证据文件：
  - `smart-procure/frontend/src/components/HistoryPanel.tsx:151`
  - `smart-procure/frontend/src/components/HistoryPanel.tsx:230`
- 风险：用户误解、误操作

### P2-3 前端主包过大

- 现象：`frontend` 生产构建主包约 10.4MB（gzip 约 2.67MB）
- 风险：首屏加载慢、弱网体验差

### P2-4 MCP 子进程管理存在稳定性隐患

- 现象：`stderr` 管道未消费；停止流程缺少超时后强制 kill 兜底
- 证据文件：
  - `smart-procure/backend/app/mcp/client.py:101`
  - `smart-procure/backend/app/mcp/client.py:105`
  - `smart-procure/backend/app/mcp/client.py:136`
- 风险：长期运行下可能阻塞或残留子进程

## 3. 修复优先顺序建议

1. 修复权限与令牌传输（P0-2、P0-3）  
2. 修复管理端构建问题（P0-1）  
3. 统一错误处理与时间格式（P1-1、P1-2）  
4. 优化推荐查询与前端拆包（P1-3、P2-3）  
5. 补齐交互语义与进程健壮性（P2-1、P2-2、P2-4）

## 4. 建议落地项（可直接建任务）

- `SEC-01`：`/suppliers/{id}` 改为管理员权限校验  
- `SEC-02`：SSE 改为短时票据或会话方案，避免 URL 挂 token  
- `BUILD-01`：修正 `admin-frontend` tsconfig 构建链路  
- `API-01`：500 响应改通用错误码，异常细节仅记录日志  
- `API-02`：统一 RFC3339 时间序列化，不手工拼接 `Z`  
- `PERF-01`：推荐接口改 DB 过滤/分页 + 索引策略  
- `PERF-02`：前端对大依赖做懒加载和分包策略  

## 5. 附：本次执行的关键验证

- `python -m unittest discover -s smart-procure/backend/app/tests -p "test_*.py"` -> 通过  
- `npm run lint`（`smart-procure/frontend`）-> 通过  
- `npm run build`（`smart-procure/frontend`）-> 通过（有 chunk size 警告）  
- `npm run build`（`smart-procure/admin-frontend`）-> 失败（见 P0-1）
