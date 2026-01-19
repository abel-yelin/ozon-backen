# Dokploy 部署指南

本文档指导如何将 Python Capability Service 部署到 Dokploy 平台。

## 前置准备

### 1. 确认 R2 配置
确保你已经拥有 Cloudflare R2 的以下信息：
- R2 Account ID: `131b8472f4f5e378b93d7736179a1702`
- R2 Access Key ID: `72b40db471f8ea67f1862919642e8bff`
- R2 Secret Access Key: `d014df05410c077c244f2d2511d06d64532cf42ef7040b3e592450f9c179f5b2`
- R2 Bucket Name: `aigxt`
- R2 Public URL: `https://r0.image2url.com`

### 2. 生成生产环境 API Key
使用以下命令生成一个强密码：
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 部署步骤

### 步骤 1: 准备代码仓库

1. 确保所有更改已提交到 Git
2. 推送到你的 Git 仓库（GitHub/GitLab）

### 步骤 2: 在 Dokploy 创建应用

1. 登录 Dokploy 控制面板
2. 点击 "Create Application" 或 "新建应用"
3. 选择 "Docker" 部署类型
4. 配置基本信息：
   - 应用名称: `python-capability-service` (或自定义)
   - Git 仓库: 你的仓库 URL
   - 分支: `main` (或你的生产分支)

### 步骤 3: 配置环境变量

在 Dokploy 应用设置中，添加以下环境变量：

#### 必需的环境变量

```bash
# ==========================================
# CLOUDFLARE R2 配置 (必需)
# ==========================================
R2_ACCOUNT_ID=131b8472f4f5e378b93d7736179a1702
R2_ACCESS_KEY_ID=72b40db471f8ea67f1862919642e8bff
R2_SECRET_ACCESS_KEY=d014df05410c077c244f2d2511d06d64532cf42ef7040b3e592450f9c179f5b2
R2_BUCKET_NAME=aigxt
R2_PUBLIC_URL=https://r0.image2url.com

# ==========================================
# 服务认证 (必需)
# ==========================================
# 使用步骤 2 生成的强密码
PYTHON_SERVICE_API_KEY=your_production_api_key_here

# ==========================================
# CORS 配置 (生产环境推荐)
# ==========================================
# 设置允许的前端域名(逗号分隔)，或者使用 * 允许所有
CORS_ORIGINS=https://your-frontend.com,https://app.your-frontend.com

# ==========================================
# 环境配置
# ==========================================
ENVIRONMENT=production
DEBUG=false
```

### 步骤 4: 配置部署设置

在 Dokploy 的部署配置中：

1. **Docker Context**: 设置为项目根目录
2. **Dockerfile Path**: `Dockerfile` (已存在)
3. **Port**: `8000` (容器内部端口)

### 步骤 5: 配置域名 (可选)

1. 在 Dokploy 应用中添加自定义域名
2. 配置 SSL 证书（Let's Encrypt 自动证书）
3. 示例: `api.yourdomain.com`

### 步骤 6: 部署

1. 点击 "Deploy" 或 "部署" 按钮
2. 等待构建完成（首次部署可能需要几分钟）
3. 查看日志确认启动成功

## 验证部署

### 1. 健康检查
访问健康检查端点：
```bash
curl https://your-domain.com/api/v1/health
```

预期响应：
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
    },
    {
      "name": "ozon-download",
      "display_name": "Ozon 图片下载",
      "category": "platform",
      "enabled": true,
      "healthy": true
    }
  ]
}
```

### 2. 测试 API 端点

使用你的 API Key 测试：
```bash
curl -X POST "https://your-domain.com/api/v1/ozon/download" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_production_api_key" \
  -d '{
    "credential": {
      "client_id": "test",
      "api_key": "test"
    },
    "articles": ["123456"],
    "field": "offer_id",
    "user_id": "test_user"
  }'
```

## 监控和日志

### 查看日志
在 Dokploy 控制面板中：
1. 进入应用详情
2. 点击 "Logs" 或 "日志"
3. 实时查看应用日志

### 健康检查
应用配置了健康检查端点：
- 端点: `/api/v1/health`
- 间隔: 30秒
- 超时: 10秒
- 重试: 3次

Dokploy 会根据健康检查自动重启失败的容器。

## 安全建议

### 1. API Key 安全
- ✅ 使用强密码（32+ 字符随机字符串）
- ✅ 定期轮换 API Key
- ✅ 不要在代码中硬编码
- ✅ 使用环境变量管理

### 2. CORS 配置
- ⚠️ 生产环境不要使用 `*`
- ✅ 明确指定允许的前端域名
- ✅ 使用 HTTPS

### 3. HTTPS
- ✅ 在 Dokploy 中配置 SSL 证书
- ✅ 强制 HTTPS 重定向

### 4. 速率限制 (可选)
如需添加速率限制，可以在 Nginx 反向代理中配置：
```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
limit_req zone=api burst=20 nodelay;
```

## 故障排查

### 问题 1: 容器启动失败
**检查方法**: 查看日志
**可能原因**:
- 环境变量配置错误
- R2 连接失败
- 端口冲突

**解决方案**:
```bash
# 检查日志
docker logs <container_id>

# 验证环境变量
echo $R2_ACCOUNT_ID
```

### 问题 2: API 返回 401 Unauthorized
**原因**: API Key 不正确
**解决方案**:
- 检查 `PYTHON_SERVICE_API_KEY` 环境变量
- 确认请求头中的 `X-API-Key` 正确

### 问题 3: CORS 错误
**原因**: CORS 配置不正确
**解决方案**:
- 检查 `CORS_ORIGINS` 环境变量
- 确保前端域名在允许列表中
- 确保使用 HTTPS

### 问题 4: 健康检查失败
**原因**: 应用未正确启动
**解决方案**:
- 查看启动日志
- 检查端口 8000 是否正常监听
- 验证 `/api/v1/health` 端点可访问

## 性能优化 (可选)

### 使用 Gunicorn (生产环境推荐)

如果需要更高的并发性能，可以修改 Dockerfile 中的启动命令：

```dockerfile
# 安装 gunicorn
RUN pip install gunicorn

# 使用 gunicorn 启动
CMD ["gunicorn", "app.main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
```

### 资源限制

在 Dokploy 中设置资源限制：
- CPU: 1-2 cores
- Memory: 512MB - 2GB
- 根据实际负载调整

## 更新部署

### 自动部署
配置 Git webhook 后，每次 push 到主分支会自动触发部署。

### 手动部署
1. 在 Dokploy 控制面板点击 "Redeploy"
2. 或推送新代码后等待自动部署

## 回滚

如果部署出现问题：
1. 在 Dokploy 中查看部署历史
2. 选择之前的稳定版本
3. 点击 "Rollback" 或 "回滚"

## 联系和支持

如有问题，请检查：
1. [项目 README.md](README.md)
2. [Ozon 集成文档](docs/OZON_DOWNLOAD_INTEGRATION.md)
3. [前端集成指南](docs/FRONTEND_INTEGRATION_GUIDE.md)

---

**部署清单**:
- [ ] 环境变量已配置
- [ ] API Key 已生成并设置
- [ ] CORS 已正确配置
- [ ] R2 配置已验证
- [ ] 健康检查通过
- [ ] API 测试成功
- [ ] SSL 证书已配置
- [ ] 日志监控已设置

祝你部署顺利！🚀
