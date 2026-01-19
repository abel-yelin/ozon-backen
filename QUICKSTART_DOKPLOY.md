# 🚀 Dokploy 快速部署指南

这是一个5分钟快速部署指南，帮助你将 Python Capability Service 部署到 Dokploy。

## 前置准备

1. ✅ Dokpley 服务器已安装运行
2. ✅ Git 仓库（GitHub/GitLab）
3. ✅ Cloudflare R2 账户
4. ✅ 5分钟时间

---

## 步骤 1: 推送代码到 Git (2分钟)

```bash
# 在项目目录执行
cd D:\workplace\image2url-main\dev\back-end\image2url-backend

# 初始化 Git（如果还没有）
git init

# 添加所有文件
git add .

# 提交
git commit -m "feat: Ready for Dokploy deployment"

# 推送到远程仓库（替换为你的仓库地址）
git remote add origin https://github.com/your-username/your-repo.git
git branch -M main
git push -u origin main
```

---

## 步骤 2: 在 Dokploy 创建应用 (1分钟)

1. **登录 Dokploy** - 打开你的 Dokpley 控制面板

2. **创建新应用**
   - 点击 "New Application" 或 "新建应用"
   - 应用名称: `python-capability-service`
   - 选择类型: **Dockerfile**

3. **配置 Docker 设置**
   - **Git Repository**: 粘贴你的 Git 仓库 URL
   - **Branch**: `main`
   - **Dockerfile Path**: `Dockerfile.prod`
   - **Context Path**: `/` (根目录)
   - **Port**: `8000`

---

## 步骤 3: 配置环境变量 (2分钟)

在 Dokploy 应用的 "Environment Variables" 部分添加以下变量：

```bash
# ============================================
# 复制下面的变量到 Dokploy，替换为你的实际值
# ============================================

# Cloudflare R2 配置（必需）
R2_ACCOUNT_ID=131b8472f4f5e378b93d7736179a1702
R2_ACCESS_KEY_ID=72b40db471f8ea67f1862919642e8bff
R2_SECRET_ACCESS_KEY=d014df05410c077c244f2d2511d06d64532cf42ef7040b3e592450f9c179f5b2
R2_BUCKET_NAME=aigxt
R2_PUBLIC_URL=https://r0.image2url.com

# API 认证密钥（必需 - 生产环境请更改！）
PYTHON_SERVICE_API_KEY=dev-api-key-123
```

**⚠️ 重要提示**:
- 替换上面的值为你自己的 R2 凭证
- `PYTHON_SERVICE_API_KEY` 在生产环境使用强密钥！

**生成强密钥**:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 步骤 4: 部署 (10秒)

1. 点击 "Deploy" 或 "部署" 按钮
2. 等待 Dokploy 构建和启动（通常1-3分钟）
3. 查看实时日志确认启动成功

---

## 步骤 5: 验证部署 (30秒)

```bash
# 测试健康检查
curl https://your-domain.com/api/v1/health

# 预期响应
{
  "status": "healthy",
  "version": "2.0.0",
  "plugins": [...]
}
```

或访问浏览器:
- 🌐 API 文档: `https://your-domain.com/docs`
- 🏥 健康检查: `https://your-domain.com/api/v1/health`

---

## ✅ 完成！

你的服务现在已成功部署到 Dokploy！

### 接下来可以做什么？

1. **配置域名** - 在 Dokploy 中为应用添加自定义域名
2. **启用 SSL** - Dokploy 自动配置 Let's Encrypt 证书
3. **监控** - 在 Dokploy Dashboard 查看资源使用情况
4. **自动部署** - 配置 Git webhook 自动触发部署

---

## 🔄 更新部署

### 方式 1: 自动部署（推荐）

配置 Git Webhook:
1. 在 Dokploy 应用设置找到 Webhook URL
2. 在 Git 仓库设置中添加此 URL
3. 每次 `git push` 自动触发部署

### 方式 2: 手动部署

```bash
# 修改代码后
git add .
git commit -m "feat: New feature"
git push

# 在 Dokploy 点击 "Redeploy"
```

---

## 📚 更多信息

- **完整部署文档**: [DOKPLOY_DEPLOYMENT.md](./DOKPLOY_DEPLOYMENT.md)
- **所有部署方式**: [DEPLOYMENT.md](./DEPLOYMENT.md)
- **项目文档**: [README.md](./README.md)

---

## 🆘 遇到问题？

### 容器无法启动
```bash
# 在 Dokploy 查看日志
# 检查环境变量是否正确配置
# 验证 R2 凭证是否有效
```

### API 返回 401/403
```bash
# 检查 PYTHON_SERVICE_API_KEY 是否正确
# 测试时添加 header:
curl -H "X-API-Key: your_api_key" https://your-domain.com/api/v1/health
```

### R2 连接失败
```bash
# 验证 R2 凭证
# 检查 R2_BUCKET_NAME 是否存在
# 确认 R2_PUBLIC_URL 可以访问
```

---

**版本**: 2.0.0
**更新时间**: 2025-01-19

祝部署顺利！🎉
