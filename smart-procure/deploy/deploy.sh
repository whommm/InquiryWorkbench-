#!/bin/bash

# Smart Procure 生产环境部署脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo "错误: 未找到 .env 文件"
    echo "请复制 .env.example 为 .env 并填写配置"
    echo "  cp .env.example .env"
    exit 1
fi

# 检查必要的环境变量
source .env
if [ -z "$POSTGRES_PASSWORD" ] || [ "$POSTGRES_PASSWORD" = "your-secure-password-here" ]; then
    echo "错误: 请在 .env 中设置安全的 POSTGRES_PASSWORD"
    exit 1
fi

if [ -z "$JWT_SECRET" ] || [ "$JWT_SECRET" = "your-super-secret-jwt-key-change-in-production" ]; then
    echo "错误: 请在 .env 中设置安全的 JWT_SECRET"
    exit 1
fi

echo "=== Smart Procure 部署开始 ==="

# 构建并启动服务
echo "正在构建镜像..."
docker-compose -f docker-compose.prod.yml build

echo "正在启动服务..."
docker-compose -f docker-compose.prod.yml up -d

echo "等待服务启动..."
sleep 5

# 检查服务状态
echo "检查服务状态..."
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "=== 部署完成 ==="
echo "应用已在 http://localhost:80 运行"
echo ""
echo "常用命令:"
echo "  查看日志: docker-compose -f docker-compose.prod.yml logs -f"
echo "  停止服务: docker-compose -f docker-compose.prod.yml down"
echo "  重启服务: docker-compose -f docker-compose.prod.yml restart"
