# SmartProcure 优化执行任务清单

- 基线文档: `smart-procure/OPTIMIZATION_DESIGN.md`
- 状态说明:
  - `[ ]` 未开始
  - `[~]` 进行中
  - `[x]` 已完成

## Phase 0: 基线准备

- [ ] 建立优化分支并冻结本次变更范围
- [ ] 记录当前后端关键接口可用性与耗时基线
- [ ] 记录前端大表格编辑性能基线（至少 1 次 500+ 行样本）

## Phase 1: 安全与后端结构

- [x] 为 `users` 增加 `role`（默认 `user`），兼容老库自动补列
- [x] 实现 `require_admin` 依赖并接入 `/api/admin/*`
- [x] 将通知从内存迁移为持久化表 `notifications`
- [x] 路由模块化第一步：拆分 `admin`/`notifications` 子路由并接入
- [x] 路由模块化第二步：拆分 `suppliers`/`sheets` 子路由

## Phase 2: AI 稳定性与可观测

- [x] 为 LLM 调用增加超时、重试、指数退避
- [x] 增加结构化输出兜底（无法解析时统一 ASK）
- [x] 增加关键日志字段（request id / step / retry count）
- [x] 统计并输出工具调用成功率、解析失败率

## Phase 3: 前端性能与工程链路

- [x] 降低 `UniverSheet -> onChange` 高频触发（防抖/节流）
- [x] 优化大对象写入 IndexedDB 策略（分块或延迟落盘）
- [x] 统一 UTF-8 约束（`.editorconfig` + 校验）
- [x] 清理 `deploy/Dockerfile.frontend` 的 dev/prod 混杂命令

## Phase 4: 测试与验收

- [x] 增加 RBAC 相关测试
- [x] 增加通知持久化相关测试
- [x] 增加 LLM 兜底逻辑单测
- [x] 运行后端回归测试并修复失败项
- [x] 输出验收报告（完成项、未完成项、风险项）

## 当前批次实现范围（本轮）

- [x] `Phase 1` 的 `role + require_admin + 持久化通知 + admin/notifications 路由拆分`
- [x] `Phase 2` 的 `LLM 超时/重试/兜底`
- [x] `Phase 3` 的 `UniverSheet 高频更新降噪 + Dockerfile.frontend 清理`

## 当前阻塞项

- 无（截至 `2026-02-16`，后端自动化测试与 Docker 冒烟验证已通过）
