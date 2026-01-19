# Python Capability Service - Deployment Guide

本指南提供多种部署方式，包括 Dokploy、Docker 和传统服务器部署。

## 📋 目录
11
- [快速开始](#快速开始)
- [部署方式](#部署方式)
- [环境配置](#环境配置)
- [监控和日志](#监控和日志)
- [故障排查](#故障排查)

---

## 🚀 快速开始

### 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件

# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker 本地测试

```bash
# 使用开发配置
docker-compose up --build

# 或使用生产配置
docker-compose -f docker-compose.prod.yml up --build
```

---

## 🌐 部署方式

### 1. Dokploy 部署（推荐用于生产）

**适用场景**: 需要 CI/CD、自动扩展、简单管理的生产环境

**详细指南**: 查看 [DOKPLOY_DEPLOYMENT.md](./DOKPLOY_DEPLOYMENT.md)

**快速步骤**:

1. **推送代码到 Git**
   ```bash
   git init
   git add .
   git commit -m "Ready for Dokploy deployment"
   git push origin main
   ```

2. **在 Dokploy 创建应用**
   - 应用类型: Docker Compose 或 Dockerfile
   - Dockerfile: `Dockerfile.prod`
   - 端口: 8000

3. **配置环境变量**
   ```
   R2_ACCOUNT_ID=your_account_id
   R2_ACCESS_KEY_ID=your_access_key
   R2_SECRET_ACCESS_KEY=your_secret_key
   R2_BUCKET_NAME=your_bucket_name
   R2_PUBLIC_URL=https://your-r2-domain.com
   PYTHON_SERVICE_API_KEY=your_strong_api_key
   ```

4. **部署**
   - 点击 "Deploy" 按钮
   - 访问 `https://your-domain.com/api/v1/health` 验证

**优势**:
- ✅ 自动 CI/CD
- ✅ 简单的 Web UI
- ✅ 自动 SSL 证书
- ✅ 容器编排
- ✅ 监控和日志

---

### 2. Docker Compose 部署

**适用场景**: 单服务器部署、需要完整控制

```bash
# 使用生产配置
docker-compose -f docker-compose.prod.yml up -d

# 查看日志
docker-compose -f docker-compose.prod.yml logs -f

# 停止服务
docker-compose -f docker-compose.prod.yml down
```

**反向代理配置 (Nginx)**:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

### 3. 传统服务器部署

**适用场景**: 虚拟机、裸金属服务器

```bash
# 安装 Python 3.11+
apt update
apt install -y python3.11 python3.11-venv python3-pip

# 创建虚拟环境
python3.11 -m venv /opt/python-service
source /opt/python-service/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.production.example /opt/python-service/.env
# 编辑 .env 文件

# 使用 systemd 服务
cat > /etc/systemd/system/python-service.service <<EOF
[Unit]
Description=Python Capability Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/python-service
Environment="PATH=/opt/python-service/bin"
EnvironmentFile=/opt/python-service/.env
ExecStart=/opt/python-service/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
systemctl daemon-reload
systemctl enable python-service
systemctl start python-service
systemctl status python-service
```

---

## ⚙️ 环境配置

### 必需环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `R2_ACCOUNT_ID` | Cloudflare R2 账户ID | `131b8472f4f5e378b93d7736179a1702` |
| `R2_ACCESS_KEY_ID` | R2 访问密钥ID | `72b40db471f8ea67f1862919642e8bff` |
| `R2_SECRET_ACCESS_KEY` | R2 密钥 | `d014df05410c...` |
| `R2_BUCKET_NAME` | 存储桶名称 | `my-bucket` |
| `R2_PUBLIC_URL` | R2 公共URL | `https://r2.example.com` |
| `PYTHON_SERVICE_API_KEY` | API 认证密钥 | 生成强随机密钥 |

### 可选环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `ENVIRONMENT` | 运行环境 | `production` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `WORKERS_COUNT` | Worker 数量 | `4` |

### 生成生产 API Key

```bash
# Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# OpenSSL
openssl rand -base64 32

# 在线工具
# https://generate-random.org/api-key-generator
```

---

## 📊 监控和日志

### 健康检查

```bash
# 基本健康检查
curl http://localhost:8000/api/v1/health

# 带认证的健康检查
curl -H "X-API-Key: your_api_key" http://localhost:8000/api/v1/health

# JSON 格式化输出
curl http://localhost:8000/api/v1/health | jq
```

**预期响应**:
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "plugins": [
    {
      "name": "image-compress",
      "display_name": "图片压缩",
      "category": "image",
      "enabled": true,
      "healthy": true
    }
  ]
}
```

### 查看日志

**Docker Compose**:
```bash
# 实时日志
docker-compose -f docker-compose.prod.yml logs -f

# 最近100行
docker-compose -f docker-compose.prod.yml logs --tail=100

# 特定服务
docker-compose -f docker-compose.prod.yml logs -f python-service
```

**Systemd**:
```bash
# 实时日志
journalctl -u python-service -f

# 最近日志
journalctl -u python-service -n 100
```

**Dokploy**: 在 Web UI 的 Logs 标签页查看

### 性能监控

**使用 Docker Stats**:
```bash
docker stats python-capability-service
```

**推荐工具**:
- Prometheus + Grafana
- Datadog
- New Relic
- Uptime Robot

---

## 🔧 故障排查

### 常见问题

#### 1. 容器无法启动

**症状**: `docker ps` 看不到容器

**解决**:
```bash
# 查看详细日志
docker-compose -f docker-compose.prod.yml logs

# 检查端口占用
netstat -tulpn | grep 8000

# 检查环境变量
docker-compose -f docker-compose.prod.yml config
```

#### 2. 健康检查失败

**症状**: `/api/v1/health` 返回错误

**解决**:
```bash
# 检查服务是否在运行
curl -v http://localhost:8000/api/v1/health

# 检查容器内部
docker exec -it python-capability-service bash
curl http://localhost:8000/api/v1/health

# 检查环境变量
docker exec python-capability-service env | grep R2
```

#### 3. R2 连接失败

**症状**: 上传到 R2 时超时或失败

**解决**:
```bash
# 验证 R2 凭证
docker exec -it python-capability-service python -c "
import boto3
client = boto3.client('s3', ...)
print(client.list_buckets())
"

# 检查网络连接
docker exec python-capability-service ping r2.cloudflarestorage.com
```

#### 4. 内存不足

**症状**: 容器频繁重启，OOM 错误

**解决**:
```yaml
# 在 docker-compose.prod.yml 中增加内存限制
services:
  python-service:
    deploy:
      resources:
        limits:
          memory: 2G  # 增加到 2GB
```

---

## 🔄 更新和维护

### 更新应用

**Dokploy**: 自动或手动点击 "Redeploy"

**Docker Compose**:
```bash
# 拉取最新代码
git pull

# 重新构建和部署
docker-compose -f docker-compose.prod.yml up -d --build

# 或使用部署脚本
chmod +x deploy-local.sh
./deploy-local.sh
```

**Systemd**:
```bash
# 拉取最新代码
cd /opt/python-service
git pull

# 重启服务
systemctl restart python-service
```

### 备份

**环境变量**:
```bash
# 导出
docker-compose -f docker-compose.prod.yml exec -T python-service env > backup.env

# 恢复
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d --env-file backup.env
```

**配置文件**:
```bash
# 备份
tar -czf config-backup-$(date +%Y%m%d).tar.gz .env config/

# 恢复
tar -xzf config-backup-20250119.tar.gz
```

---

## 📚 相关文档

- [DOKPLOY_DEPLOYMENT.md](./DOKPLOY_DEPLOYMENT.md) - Dokploy 详细部署指南
- [README.md](./README.md) - 项目文档和架构
- [API 文档](http://localhost:8000/docs) - Swagger/OpenAPI 文档

---

## 🆘 获取帮助

- **GitHub Issues**: [提交问题](https://github.com/your-repo/issues)
- **文档**: 查看 [README.md](./README.md)
- **API 测试**: 访问 `/docs` 端点

---

**版本**: 2.0.0
**最后更新**: 2025-01-19
