# SmartProcure 智能采购工作台

企业级智能采购管理系统，支持多用户协作、AI辅助报价处理、供应商管理等功能。

## 项目概述

SmartProcure 是一个基于 Web 的采购管理工具，主要功能包括：

- **智能报价处理**：通过 AI 对话自动解析和填充报价信息
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

### 前端
- **框架**: React 19 + TypeScript
- **状态管理**: Zustand
- **表格组件**: Univer 0.15.3
- **样式**: Tailwind CSS 4
- **本地存储**: IndexedDB (按用户隔离)

### 部署
- **容器化**: Docker + Docker Compose
- **反向代理**: Nginx
- **镜像加速**: docker.1ms.run

## 项目结构

```
smart-procure/
├── backend/                 # 后端服务
│   ├── app/
│   │   ├── api/            # API 路由
│   │   ├── auth/           # 认证模块
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
    ├── Dockerfile.backend          # 后端镜像
    ├── Dockerfile.frontend         # 前端开发镜像
    ├── Dockerfile.frontend.prod    # 前端生产镜像
    ├── deploy.sh                   # 部署脚本
    └── .env.example                # 环境变量模板
```

## 数据库模型

### users (用户表)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(36) | 主键，UUID |
| username | VARCHAR(50) | 用户名，唯一 |
| password_hash | VARCHAR(255) | 密码哈希 |
| display_name | VARCHAR(100) | 显示名称 |
| created_at | DATETIME | 创建时间 |
| last_login_at | DATETIME | 最后登录时间 |

### inquiry_sheets (询价单表)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR | 主键 |
| user_id | VARCHAR(36) | 用户ID，外键 |
| name | VARCHAR | 询价单名称 |
| sheet_data | JSON | 表格数据 |
| chat_history | JSON | 聊天记录 |
| item_count | INTEGER | 物料数量 |
| completion_rate | FLOAT | 完成率 |

### suppliers (供应商表)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| company_name | VARCHAR | 公司名称，唯一 |
| contact_phone | VARCHAR | 联系电话 |
| contact_name | VARCHAR | 联系人 |
| created_by | VARCHAR(36) | 创建者用户ID |
| quote_count | INTEGER | 报价次数 |

## 云服务器部署指南

### 前置要求

- 云服务器 (推荐 2核4G 以上)
- 已安装 Docker 和 Docker Compose
- 开放 80 端口

### 步骤一：安装 Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 安装 Docker Compose
sudo apt install docker-compose-plugin
```

### 步骤二：上传项目到服务器

```bash
# 方式一：使用 scp
scp -r smart-procure user@your-server-ip:/home/user/

# 方式二：使用 git
git clone your-repo-url
cd smart-procure
```

### 步骤三：配置环境变量

```bash
cd /home/user/smart-procure/deploy
cp .env.example .env
vim .env
```

编辑 `.env` 文件，**必须修改以下配置**：

```env
# 数据库密码 (请使用强密码)
POSTGRES_PASSWORD=your-secure-password-here

# JWT 密钥 (请使用随机字符串)
JWT_SECRET=your-random-secret-key-here

# 可选：AI API 密钥
API_KEY=your-api-key
TAVILY_API_KEY=your-tavily-key
```

### 步骤四：启动服务

```bash
# 使用部署脚本 (推荐)
chmod +x deploy.sh
./deploy.sh

# 或手动启动
docker compose -f docker-compose.prod.yml up -d --build
```

### 步骤五：验证部署

```bash
# 查看容器状态
docker compose -f docker-compose.prod.yml ps

# 查看日志
docker compose -f docker-compose.prod.yml logs -f
```

访问 `http://服务器IP` 即可使用。

## 常用运维命令

```bash
# 进入部署目录
cd /home/user/smart-procure/deploy

# 查看服务状态
docker compose -f docker-compose.prod.yml ps

# 查看实时日志
docker compose -f docker-compose.prod.yml logs -f

# 重启所有服务
docker compose -f docker-compose.prod.yml restart

# 重启单个服务
docker compose -f docker-compose.prod.yml restart backend

# 停止服务
docker compose -f docker-compose.prod.yml down

# 更新代码后重新部署
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## 数据备份

```bash
# 备份 PostgreSQL 数据
docker exec smart-procure-postgres pg_dump -U smartprocure smartprocure > backup.sql

# 恢复数据
cat backup.sql | docker exec -i smart-procure-postgres psql -U smartprocure smartprocure
```

## 注意事项

1. **安全配置**：生产环境务必修改默认密码和 JWT 密钥
2. **HTTPS**：建议配置 SSL 证书，可使用 Let's Encrypt
3. **防火墙**：仅开放必要端口 (80/443)
4. **备份**：定期备份 PostgreSQL 数据
5. **监控**：建议配置日志监控和告警

## 本地开发

```bash
cd smart-procure/deploy
docker compose up -d
```

- 前端: http://localhost:6789
- 后端: http://localhost:18000
- 数据库: localhost:5432

## 许可证

MIT License
