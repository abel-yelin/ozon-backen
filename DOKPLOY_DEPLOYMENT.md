# Dokploy 部署指南

本文档介绍如何将 Python Capability Service 部署到 Dokploy。

## 前置要求

- Dokploy 服务器已安装并运行
- Git 仓库（GitHub、GitLab等）
- Docker 镜像仓库（Docker Hub、GitHub Container Registry等）
- Cloudflare R2 账户和凭证

## 部署步骤

### 1. 推送代码到 Git 仓库

```bash
cd D:\workplace\image2url-main\dev\back-end\image2url-backend
git init
git add .
git commit -m "Initial commit: Python Capability Service for Dokploy"
git remote add origin <your-git-repository-url>
git push -u origin main
```

### 2. 在 Dokploy 中创建新应用

1. 登录 Dokploy 控制面板
2. 点击 "Create Application" 或 "新建应用"
3. 选择应用类型：**Docker Compose** 或 **Dockerfile**

### 3. 配置应用

#### 方式 A: 使用 Dockerfile（推荐）

**构建配置**:
- **Dockerfile Path**: `Dockerfile.prod` (使用优化的生产配置)
- **Context Path**: `/` (根目录)
- **Image Name**: `python-capability-service` (或你自定义的名称)

#### 方式 B: 使用 docker-compose.yml

直接使用现有的 `docker-compose.yml` 文件。

### 4. 配置环境变量

在 Dokploy 应用设置中添加以下环境变量：

```bash
# Cloudflare R2 配置 (必需)
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET_NAME=your_bucket_name
R2_PUBLIC_URL=https://your-r2-domain.com

# 服务认证 (必需)
PYTHON_SERVICE_API_KEY=your_production_api_key_here

# 可选：环境标识
ENVIRONMENT=production
```

**重要提示**:
- `R2_ACCOUNT_ID`: Cloudflare 账户ID
- `R2_ACCESS_KEY_ID`: R2访问密钥ID
- `R2_SECRET_ACCESS_KEY`: R2密钥
- `R2_BUCKET_NAME`: 存储桶名称
- `R2_PUBLIC_URL`: R2公共URL
- `PYTHON_SERVICE_API_KEY`: 强烈建议更改默认值！

### 5. 配置端口和域名

**端口配置**:
- **Container Port**: `8000`
- **Protocol**: `HTTP`

**域名配置**（可选）:
- 在 Dokploy 中为应用配置域名
- 设置 SSL/TLS 证书（Let's Encrypt 自动）

### 6. 部署应用

1. 点击 "Deploy" 或 "部署" 按钮
2. Dokploy 会：
   - 从 Git 仓库拉取代码
   - 根据 Dockerfile 构建镜像
   - 启动容器
   - 配置反向代理和SSL

### 7. 验证部署

部署完成后，验证服务状态：

```bash
# 健康检查
curl https://your-domain.com/api/v1/health

# 预期响应
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

## 监控和日志

### 查看日志
在 Dokploy 控制面板中：
- 应用 → Logs（日志）
- 可以实时查看容器输出

### 健康检查
- 应用自动每30秒检查一次健康状态
- 访问 `/api/v1/health` 端点

### 资源监控
- Dokploy Dashboard 查看CPU、内存使用情况
- 设置资源限制（可选）

## 更新部署

### 自动部署（推荐）
配置 Git webhook：
1. 在 Dokploy 应用设置中找到 Webhook URL
2. 在 Git 仓库中添加 webhook
3. 推送代码时自动触发部署

### 手动部署
1. 在 Dokploy 控制面板点击 "Redeploy"
2. 或使用 CLI/API 触发重新部署

## 生产环境优化

### 1. 资源限制
在 Dokploy 中设置：
- **CPU Limit**: 1-2 cores
- **Memory Limit**: 512MB - 1GB
- **Restart Policy**: always 或 on-failure

### 2. 日志管理
配置日志驱动和轮转：
```yaml
# docker-compose.yml
services:
  python-service:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 3. 安全配置
- 使用强随机 `PYTHON_SERVICE_API_KEY`
- 配置防火墙规则
- 定期更新依赖
- 监控访问日志

### 4. 性能优化
Dockerfile.prod 已包含：
- 多阶段构建减小镜像大小
- 4个 worker 进程
- 健康检查

可根据负载调整 workers 数量：
```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "8"]
```

## 故障排查

### 容器无法启动
1. 检查环境变量是否正确配置
2. 查看容器日志：`docker logs <container-id>`
3. 验证 R2 凭证是否有效

### 健康检查失败
1. 确认服务在 8000 端口监听
2. 检查防火墙规则
3. 验证环境变量加载

### API 错误
```bash
# 测试 R2 连接
curl https://your-r2-domain.com

# 检查 API Key
curl -H "X-API-Key: your_api_key" https://your-domain.com/api/v1/health
```

## 扩展功能（Phase 2）

### 添加 Redis 缓存
1. 在 Dokploy 中创建 Redis 服务
2. 添加环境变量：`REDIS_URL=redis://redis:6379/0`
3. 重启应用

### 添加更多插件
在 `app/plugins/` 目录添加新插件，参考现有插件结构。

## 备份和恢复

### 环境变量备份
```bash
# 导出环境变量
dokploy config export > backup.env

# 恢复环境变量
dokploy config import < backup.env
```

### 数据备份
此服务无状态，无需数据库备份。R2中的文件由Cloudflare管理。

## 支持

- **文档**: 查看项目 README.md
- **问题**: 在 GitHub Issues 提交
- **状态**: `/api/v1/health`

---

**版本**: 2.0.0
**最后更新**: 2025-01-19
