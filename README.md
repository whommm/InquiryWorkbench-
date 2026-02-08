# SmartProcure 智能采购工作台

企业级智能采购管理系统，采用两阶段 Agent 架构，支持多用户协作、AI 辅助报价处理、供应商管理、网络搜索和浏览器自动化等功能。

## 项目概述

SmartProcure 是一个基于 Web 的智能采购管理工具，旨在提升企业采购效率。核心功能包括：

- **智能报价处理**：通过 AI 对话自动解析和填充报价信息
- **两阶段 Agent 架构**：Planner（规划器）+ Writer（执行器）协同工作
- **AI 工具配置**：支持动态开关 AI 工具（行定位、槽位查询、供应商查询、网络搜索、网页浏览）
- **多用户支持**：用户注册/登录，数据按用户隔离
- **供应商管理**：自动沉淀供应商信息，支持来源追踪和品牌别名映射
- **供应商推荐**：基于 RAG 向量检索增强的智能供应商推荐（Qdrant + Embedding）
- **网络搜索**：集成 Tavily API，支持互联网信息搜索
- **浏览器自动化**：集成 Playwright，支持无头浏览器访问网页提取信息
- **Excel 兼容**：支持导入/导出 Excel 文件

## 技术栈

### 后端
- **框架**: FastAPI (Python 3.9+)
- **数据库**: PostgreSQL 15
- **向量数据库**: Qdrant（RAG 向量检索）
- **认证**: JWT (python-jose + passlib + bcrypt)
- **ORM**: SQLAlchemy + Alembic（数据库迁移）
- **AI**: OpenAI API 兼容接口（DeepSeek）
- **Embedding**: OpenRouter API（Gemini Embedding）
- **网络搜索**: Tavily API
- **浏览器自动化**: Playwright（无头浏览器）
- **数据处理**: pandas + openpyxl

### 前端
- **框架**: React 19 + TypeScript 5.9
- **状态管理**: Zustand 5.0
- **表格组件**: Univer 0.15.3（类 Excel 编辑器）
- **样式**: Tailwind CSS 4
- **构建工具**: Vite (rolldown)
- **HTTP 客户端**: Axios
- **本地存储**: IndexedDB（按用户隔离）

### 部署
- **容器化**: Docker + Docker Compose
- **反向代理**: Nginx
- **运行时**: Python 3.9 + Node.js 20

## 项目结构

```
InquiryWorkbench/
└── smart-procure/
    ├── backend/                 # 后端服务
    │   ├── app/
    │   │   ├── api/            # API 路由
    │   │   ├── auth/           # 认证模块
    │   │   ├── core/           # 核心配置 (config, llm)
    │   │   ├── mcp/            # MCP 浏览器自动化模块
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
        ├── Dockerfile.backend          # 后端镜像
        ├── Dockerfile.frontend         # 前端镜像
        ├── nginx.conf                  # Nginx 配置
        └── deploy.sh                   # 部署脚本
```

## AI 工具系统

系统采用两阶段 Agent 架构（Planner + Writer），支持以下工具：

| 工具 ID | 工具名 | 功能 | 说明 |
|---------|--------|------|------|
| locate_row | 行定位 | 按物料/品牌/型号定位表格行 | 支持模糊匹配 |
| get_row_slot_snapshot | 槽位查询 | 获取行的报价槽位状态 | 查看已填充的供应商位置 |
| supplier_lookup | 供应商查询 | 从数据库查询供应商信息 | 支持品牌别名映射 |
| web_search_supplier | 网络搜索 | 在互联网上搜索供应商信息 | 基于 Tavily API |
| web_browse | 网页浏览 | 使用浏览器访问网页提取信息 | 基于 Playwright |

用户可在聊天面板通过"工具"按钮动态开关这些工具。

### Agent 工作流程

1. **Planner 阶段**：分析用户意图，调用工具收集信息，生成执行计划
2. **Writer 阶段**：根据计划执行表格更新操作，返回结果给用户

## 快速开始

### 环境要求

- Docker 20.10+
- Docker Compose 2.0+
- Node.js 20+（本地开发）
- Python 3.9+（本地开发）

### Docker 部署（推荐）

```bash
# 进入部署目录
cd smart-procure/deploy

# 启动开发环境
docker compose up -d

# 查看日志
docker compose logs -f
```

访问地址：
- 前端: http://localhost:6789
- 后端 API: http://localhost:18000
- API 文档: http://localhost:18000/docs

### 生产部署

```bash
cd smart-procure/deploy

# 复制环境变量模板
cp .env.example .env

# 编辑 .env 配置必要的环境变量
vim .env

# 执行部署脚本
./deploy.sh
```

### 本地开发（不使用 Docker）

**后端：**
```bash
cd smart-procure/backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium

# 启动服务
uvicorn app.main:app --reload --port 18000
```

**前端：**
```bash
cd smart-procure/frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

## 环境变量

### 必需变量

| 变量 | 说明 | 示例 |
|------|------|------|
| DATABASE_URL | PostgreSQL 连接字符串 | `postgresql://user:pass@localhost/db` |
| JWT_SECRET | JWT 签名密钥 | 任意长随机字符串 |
| API_KEY | OpenAI API 密钥 | `sk-...` |

### 可选变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| TAVILY_API_KEY | - | Tavily 搜索 API 密钥，不配置则搜索功能禁用 |
| OPENROUTER_API_KEY | - | OpenRouter API 密钥，用于 Embedding 生成 |
| QDRANT_HOST | localhost | Qdrant 向量数据库主机 |
| QDRANT_PORT | 6333 | Qdrant 向量数据库端口 |
| EMBEDDING_MODEL | google/gemini-embedding-exp | Embedding 模型 |
| DEBUG | false | 调试模式 |
| JWT_ALGORITHM | HS256 | JWT 算法 |
| JWT_EXPIRE_MINUTES | 1440 | Token 过期时间（分钟） |
| ALLOWED_ORIGINS | http://localhost:6789 | CORS 允许的域名 |
| POSTGRES_USER | smartprocure | 数据库用户名 |
| POSTGRES_PASSWORD | smartprocure123 | 数据库密码 |
| POSTGRES_DB | smartprocure | 数据库名称 |

## 数据库设计

### 核心数据表

| 表名 | 说明 |
|------|------|
| users | 用户账户信息 |
| inquiry_sheets | 采购询价单（按用户隔离） |
| suppliers | 供应商信息（全局共享） |
| supplier_products | 供应商产品关联 |

### 数据隔离策略

- **用户数据隔离**：inquiry_sheets 通过 user_id 外键关联，确保用户只能访问自己的数据
- **前端本地存储**：使用 IndexedDB 按用户隔离本地缓存数据
- **供应商共享**：suppliers 表全局共享，支持按标签过滤

## API 接口

主要 API 端点：

| 端点 | 方法 | 说明 |
|------|------|------|
| /api/auth/register | POST | 用户注册 |
| /api/auth/login | POST | 用户登录 |
| /api/sheets | GET/POST | 获取/保存询价单列表 |
| /api/sheets/{id} | GET/PUT/DELETE | 单个询价单操作 |
| /api/chat | POST | AI 聊天接口 |
| /api/suppliers | GET/POST | 供应商管理 |
| /api/suppliers/recommend | POST | 供应商推荐 |
| /api/upload | POST | 文件上传 |
| /api/export | POST | 导出 Excel |

完整 API 文档请访问：http://localhost:18000/docs

## 许可证

MIT License
