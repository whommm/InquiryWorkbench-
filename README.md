# SmartProcure 智能采购工作台

企业级智能采购管理系统，支持多用户协作、AI辅助报价处理、供应商管理等功能。

## 项目概述

SmartProcure 是一个基于 Web 的采购管理工具，主要功能包括：

- **智能报价处理**：通过 AI 对话自动解析和填充报价信息
- **AI 工具配置**：支持动态开关 AI 工具（行定位、槽位查询、供应商查询、网络搜索）
- **多用户支持**：用户注册/登录，数据按用户隔离
- **供应商管理**：自动沉淀供应商信息，支持来源追踪
- **供应商推荐**：基于历史报价数据智能推荐供应商
- **Excel 兼容**：支持导入/导出 Excel 文件

## 技术栈

### 后端
- **框架**: FastAPI (Python 3.9+)
- **数据库**: PostgreSQL 15
- **认证**: JWT (python-jose + passlib)
- **ORM**: SQLAlchemy
- **AI**: OpenAI API 兼容接口

### 前端
- **框架**: React 19 + TypeScript
- **状态管理**: Zustand
- **表格组件**: Univer 0.15.3
- **样式**: Tailwind CSS 4
- **本地存储**: IndexedDB (按用户隔离)

### 部署
- **容器化**: Docker + Docker Compose
- **反向代理**: Nginx

## 项目结构

```
InquiryWorkbench/
└── smart-procure/
    ├── backend/                 # 后端服务
    │   ├── app/
    │   │   ├── api/            # API 路由
    │   │   ├── auth/           # 认证模块
    │   │   ├── core/           # 核心配置 (config, llm)
    │   │   ├── models/         # 数据模型
    │   │   ├── services/       # 业务逻辑
    │   │   └── main.py         # 应用入口
    │   ├── data/               # SQLite 数据 (开发用)
    │   ├── requirements.txt    # Python 依赖
    │   └── .env                # 环境变量
    ├── frontend/               # 前端应用
    │   ├── src/
    │   │   ├── components/     # React 组件
    │   │   ├── hooks/          # 自定义 Hooks
    │   │   ├── pages/          # 页面组件
    │   │   ├── stores/         # Zustand 状态
    │   │   └── utils/          # 工具函数
    │   └── package.json
    └── deploy/                 # 部署配置
        ├── docker-compose.yml          # 开发环境
        ├── docker-compose.prod.yml     # 生产环境
        ├── nginx.conf                  # Nginx 配置
        └── deploy.sh                   # 部署脚本
```

## AI 工具系统

系统采用两阶段 Agent 架构（Planner + Writer），支持以下工具：

| 工具名 | 功能 | 说明 |
|--------|------|------|
| locate_row | 行定位 | 按物料/品牌/型号定位表格行 |
| get_row_slot_snapshot | 槽位查询 | 获取行的报价槽位状态 |
| supplier_lookup | 供应商查询 | 从数据库查询供应商信息 |
| web_search_supplier | 网络搜索 | 在互联网上搜索供应商信息 |

用户可在聊天面板通过"工具"按钮动态开关这些工具。

## 快速开始

### 本地开发

```bash
cd smart-procure/deploy
docker compose up -d
```

- 前端: http://localhost:6789
- 后端: http://localhost:18000

### 生产部署

```bash
cd smart-procure/deploy
cp .env.example .env
# 编辑 .env 配置
./deploy.sh
```

## 环境变量

| 变量 | 说明 | 必填 |
|------|------|------|
| POSTGRES_PASSWORD | 数据库密码 | 是 |
| JWT_SECRET | JWT 密钥 | 是 |
| API_KEY | AI API 密钥 | 是 |
| TAVILY_API_KEY | 网络搜索 API 密钥 | 否 |

## 许可证

MIT License
