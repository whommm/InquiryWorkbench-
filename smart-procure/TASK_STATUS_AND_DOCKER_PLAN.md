# SmartProcure 任务状态与 Docker 验证说明

- 更新时间: `2026-02-16`
- 适用范围: `E:\InquiryWorkbench\smart-procure`

## 1. 当前任务状态

本轮目标是基于优化清单持续落地并完成验证，目前状态为“核心实现与 Docker 冒烟验证均已完成”。

### 1.1 已完成

1. 后端安全与结构优化
- 已完成 RBAC（`users.role`、`require_admin_user`、`/api/admin/*` 收口）
- 已完成通知持久化（`notifications` 表 + `notification_service`）
- 已完成路由模块化第二步（新增 `api/sheets.py`、`api/suppliers.py`，并在 `main.py` 注册）

2. AI 稳定性与可观测
- `llm.py` 已具备超时、重试、指数退避、统一 ASK 兜底
- 新增 LLM 结构化日志字段: `request_id`、`step`、`retry_count`
- 新增 LLM 指标统计: 总请求、成功率、fallback 率、解析失败率
- 新增工具调用指标统计: 调用总数、成功数、失败数、成功率
- 新增管理接口: `GET /api/admin/runtime/stats`

3. 前端性能与构建修复
- `UniverSheet` 高频变更防抖已完成
- IndexedDB 已改为延迟落盘策略（debounce），降低大对象高频写入
- 已修复前端 TS 报错
  - `ErrorBoundary.tsx` 类型导入修复
  - `HistoryPanel.tsx` 未使用参数清理
  - `SupplierPanel.tsx` 未使用参数清理

4. 回归修复
- 已修复 `sheet_schema` 槽位映射逻辑（支持“字段+槽位号”识别与别名）
- 已修复 `excel_core` 相关回归并移除调试噪音输出

### 1.2 测试结果

以下命令均已通过：

1. 后端全量测试
```bash
python -m unittest discover smart-procure/backend/app/tests -v
```
- 结果: `18/18` 通过

2. 回归专项
```bash
python -m unittest smart-procure/backend/app/tests/test_regressions.py -v
```
- 结果: 全通过

3. 应用导入检查
```bash
import app.main
```
- 结果: `import_ok`

### 1.3 尚未完成

1. 文档治理待持续
- 可选：将 `docker-compose*.yml` 中过时的 `version` 字段清理掉（当前仅告警，不影响运行）

## 2. Docker 已执行内容（目的与结果）

你提到项目是 Docker 部署，这一步的目的不是“本机开发构建”，而是验证真实交付路径：

1. 验证镜像可构建（已完成）
```bash
docker compose -f smart-procure/deploy/docker-compose.yml build frontend
docker compose -f smart-procure/deploy/docker-compose.yml build backend
```

2. 验证服务可启动（已完成）
```bash
docker compose -f smart-procure/deploy/docker-compose.yml up -d
docker compose -f smart-procure/deploy/docker-compose.yml ps
```

3. 验证关键接口可用（已完成）
```bash
curl http://localhost:18000/api/init
curl http://localhost:18000/api/notifications
curl http://localhost:18000/api/admin/runtime/stats
```

4. 验证完成后清理（按需）
```bash
docker compose -f smart-procure/deploy/docker-compose.yml down
```

## 3. 当前关键变更文件（本轮）

1. 后端
- `smart-procure/backend/app/services/sheet_schema.py`
- `smart-procure/backend/app/services/excel_core.py`
- `smart-procure/backend/app/core/llm.py`
- `smart-procure/backend/app/services/agent_runtime.py`
- `smart-procure/backend/app/api/sheets.py`
- `smart-procure/backend/app/api/suppliers.py`
- `smart-procure/backend/app/api/admin.py`
- `smart-procure/backend/app/main.py`

2. 前端
- `smart-procure/frontend/src/utils/indexedDB.ts`
- `smart-procure/frontend/src/stores/useTabsStore.ts`
- `smart-procure/frontend/src/components/ErrorBoundary.tsx`
- `smart-procure/frontend/src/components/HistoryPanel.tsx`
- `smart-procure/frontend/src/components/SupplierPanel.tsx`

3. 测试
- `smart-procure/backend/app/tests/test_regressions.py`（已通过）
- `smart-procure/backend/app/tests/test_llm_gateway.py`
- `smart-procure/backend/app/tests/test_agent_runtime_metrics.py`

## 4. 建议下一步

1. 将 `version` 字段从 `docker-compose.yml` 与 `docker-compose.prod.yml` 移除，消除 Compose 告警。
2. 为 `GET /api/admin/runtime/stats` 增加鉴权集成测试（401/403/200）。
