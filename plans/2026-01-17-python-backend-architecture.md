# Python 能力服务架构设计文档

**项目**: image2url - Python 能力服务（无状态）
**日期**: 2026-01-17
**版本**: 2.0 (能力服务模式)
**作者**: Claude & Abel

---

## 1. 架构核心理念

### 1.1 设计原则

本架构采用**能力服务模式**，Python 作为无状态处理能力提供者：

- **无状态服务**: Python 不存储任何业务数据
- **能力输出**: 只做重活，返回处理结果
- **业务自治**: Next.js 完全控制用户、权限、配额、计费
- **多站复用**: Python 能力可被多个站点共享
- **零耦合**: Python 不关心业务逻辑，Next.js 不关心处理细节

### 1.2 为什么选择能力服务模式？

**传统模式的问题**：
- ❌ Python 存储业务数据 → 与各站点业务逻辑耦合
- ❌ 需要同步用户、权限、配额等数据 → 复杂度高
- ❌ 新增站点需要修改 Python 数据库 → 扩展困难

**能力服务模式的优势**：
- ✅ **业务自治**: 每个站点控制自己的业务数据
- ✅ **能力复用**: 多个站点共享 Python 能力，避免重复建设
- ✅ **扩展简单**: 新增站点只需接入 Python API
- ✅ **解耦清晰**: Python 不关心业务，Next.js 不关心处理
- ✅ **独立扩展**: Python 服务可以独立扩容
- ✅ **故障隔离**: Python 故障不影响站点业务逻辑

### 1.3 架构分层图

```
┌──────────────────────────────────────────────────────────┐
│                   Next.js (业务控制层)                     │
│  - 用户鉴权、权限校验                                      │
│  - 配额管理、计费、审计                                     │
│  - 业务数据持久化（PostgreSQL）                            │
│  - Stable URL 映射关系                                    │
└────────────────┬─────────────────────────────────────────┘
                 │ 1. 发送任务
                 ▼
┌──────────────────────────────────────────────────────────┐
│              Python 能力服务 (无状态)                      │
│  - 图片处理：压缩、转码、多尺寸、hash 去重                   │
│  - 内容审核：NSFW、OCR、分类                               │
│  - AI 能力：摘要、打标、embedding                          │
│  - 第三方集成：CDN purge、对象存储、支付 webhook            │
│                                                          │
│  ⚡ 不存储业务数据                                         │
│  ⚡ 不关心用户身份和权限                                   │
│  ⚡ 只做重活，返回结果                                     │
└────────────────┬─────────────────────────────────────────┘
                 │ 2. 返回结果
                 ▼
┌──────────────────────────────────────────────────────────┐
│              Next.js (写入数据库)                          │
│  - 入库处理结果                                            │
│  - 更新业务状态                                            │
│  - 记录审计日志                                            │
└──────────────────────────────────────────────────────────┘
```

### 1.4 多站点复用架构

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Site A      │     │  Site B      │     │  Site N      │
│  (Next.js)   │     │  (Next.js)   │     │  (Next.js)   │
│              │     │              │     │              │
│  各自业务：   │     │  各自业务：   │     │  各自业务：   │
│  - 用户表     │     │  - 用户表     │     │  - 用户表     │
│  - 权限管理   │     │  - 权限管理   │     │  - 权限管理   │
│  - 配额计费   │     │  - 配额计费   │     │  - 配额计费   │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │  共享 Python 能力服务    │
              │                         │
              │  - 图片处理              │
              │  - 视频转码              │
              │  - AI 推理               │
              │  - CDN 操作              │
              │                         │
              │  🔒 无业务数据           │
              │  🔒 可独立扩展           │
              └─────────────────────────┘
```

---

## 2. 数据流设计

### 2.1 同步处理场景（图片压缩）

```
1. 用户上传图片
   ↓
2. Next.js 处理：
   - 鉴权：用户登录了吗？
   - 权限：有上传权限吗？
   - 配额：剩余配额够吗？
   - 计费：记录此次操作成本
   ↓
3. Next.js 调用 Python API：
   POST http://python-service:8000/api/v1/image/compress
   {
     "image_url": "https://r2.example.com/original.jpg",
     "options": {
       "quality": 80,
       "format": "webp",
       "max_width": 1920
     }
   }
   ↓
4. Python 能力服务：
   - 下载图片
   - 压缩处理
   - 上传到 R2
   - 返回结果（不存数据库）
   ↓
5. Python 响应：
   {
     "success": true,
     "output_url": "https://r2.example.com/compressed.webp",
     "metadata": {
       "original_size": 5242880,
       "compressed_size": 1048576,
       "compression_ratio": 0.8,
       "width": 1920,
       "height": 1080,
       "format": "webp"
     }
   }
   ↓
6. Next.js 入库：
   - 写入 Upload 表
   - 写入 UploadVersion 表
   - 更新用户配额
   - 记录审计日志
   ↓
7. 返回给用户
```

### 2.2 异步处理场景（视频转码）

```
1. 用户上传视频
   ↓
2. Next.js 处理（鉴权、权限、配额）
   ↓
3. Next.js 调用 Python API（同步创建任务）：
   POST http://python-service:8000/api/v1/video/transcode
   {
     "video_url": "https://r2.example.com/video.mp4",
     "options": {
       "format": "hls",
       "resolutions": [720, 1080]
     },
     "callback_url": "https://site-a.com/webhooks/transcode",
     "webhook_secret": "secret_from_nextjs"
   }
   ↓
4. Python 立即返回任务信息（不入库）：
   {
     "success": true,
     "job_id": "job_abc123",
     "status": "pending",
     "estimated_duration": 300  // 秒
   }
   ↓
5. Next.js 入库：
   - 写入 processing_jobs 表（Next.js 自己的表）
   - 返回 job_id 给用户
   ↓
6. Python 后台处理（Celery Worker）：
   - 下载视频
   - 转码处理
   - 上传到 R2
   - 发送 Webhook 通知 Next.js
   ↓
7. Python 发送 Webhook：
   POST https://site-a.com/webhooks/transcode
   {
     "job_id": "job_abc123",
     "status": "completed",
     "output_url": "https://r2.example.com/video_hls/",
     "metadata": {...}
   }
   Headers:
     X-Webhook-Secret: secret_from_nextjs
     X-Job-ID: job_abc123
   ↓
8. Next.js 收到 Webhook：
   - 验证签名
   - 更新 processing_jobs 状态
   - 记录审计日志
   ↓
9. 用户查询时从 Next.js 获取状态
```

---

## 3. Python 服务能力清单

### 3.1 图片处理能力

| 能力 | API 端点 | 处理模式 | 说明 |
|------|----------|----------|------|
| 图片压缩 | `/api/v1/image/compress` | 同步 | 降低图片质量、格式转换 |
| 图片缩放 | `/api/v1/image/resize` | 同步 | 调整尺寸、裁剪 |
| 图片去背景 | `/api/v1/image/remove-background` | 异步 | AI 移除背景 |
| 图片翻译 | `/api/v1/image/translate` | 异步 | 翻译图片中的文字 |
| 图片扩展 | `/api/v1/image/expand` | 异步 | AI 扩展图片边界 |
| 图片放大 | `/api/v1/image/upscale` | 异步 | AI 超分辨率放大 |
| 图片哈希 | `/api/v1/image/hash` | 同步 | 计算感知哈希（去重） |
| NSFW 检测 | `/api/v1/image/nsfw-check` | 同步 | 内容安全检测 |
| OCR 文字提取 | `/api/v1/image/ocr` | 同步 | 提取图片中的文字 |
| 图片元数据 | `/api/v1/image/metadata` | 同步 | 提取 EXIF 等元数据 |

### 3.2 视频处理能力

| 能力 | API 端点 | 处理模式 | 说明 |
|------|----------|----------|------|
| 视频转码 | `/api/v1/video/transcode` | 异步 | 格式转换、HLS/DASH |
| 视频压缩 | `/api/v1/video/compress` | 异步 | 降低码率、分辨率 |
| 提取帧 | `/api/v1/video/extract-frames` | 异步 | 提取关键帧 |
| 视频截图 | `/api/v1/video/screenshot` | 同步 | 生成封面图 |
| 添加水印 | `/api/v1/video/add-watermark` | 异步 | 添加图片/文字水印 |

### 3.3 文档处理能力

| 能力 | API 端点 | 处理模式 | 说明 |
|------|----------|----------|------|
| PDF 转图片 | `/api/v1/document/pdf-to-images` | 异步 | 每页转为图片 |
| PDF 提取文本 | `/api/v1/document/pdf-to-text` | 同步 | 提取文字内容 |
| 文档合并 | `/api/v1/document/merge` | 同步 | 合并多个 PDF |
| 文档转换 | `/api/v1/document/convert` | 异步 | 格式互转（PDF/DOCX） |

### 3.4 AI 能力

| 能力 | API 端点 | 处理模式 | 说明 |
|------|----------|----------|------|
| 文本摘要 | `/api/v1/ai/summary` | 异步 | 生成文章摘要 |
| 文本打标 | `/api/v1/ai/tag` | 同步 | 自动生成标签 |
| 向量嵌入 | `/api/v1/ai/embedding` | 同步 | 生成 embedding |
| 内容分类 | `/api/v1/ai/classify` | 同步 | 自动分类 |

### 3.5 存储与 CDN 能力

| 能力 | API 端点 | 处理模式 | 说明 |
|------|----------|----------|------|
| R2 上传 | `/api/v1/storage/upload` | 同步 | 上传文件到 R2 |
| CDN 缓存清除 | `/api/v1/storage/purge` | 同步 | 清除 CDN 缓存 |
| 批量删除 | `/api/v1/storage/batch-delete` | 异步 | 批量删除文件 |

---

## 4. API 设计规范

### 4.1 请求格式

**同步 API 请求**：
```json
POST /api/v1/image/compress
Content-Type: application/json
X-API-Key: your_api_key

{
  "image_url": "https://r2.example.com/image.jpg",
  "options": {
    "quality": 80,
    "format": "webp"
  }
}
```

**异步 API 请求**：
```json
POST /api/v1/video/transcode
Content-Type: application/json
X-API-Key: your_api_key

{
  "video_url": "https://r2.example.com/video.mp4",
  "options": {
    "format": "hls",
    "resolutions": [720, 1080]
  },
  "callback_url": "https://your-site.com/webhooks/jobs",
  "webhook_secret": "your_webhook_secret",
  "client_job_id": "your_internal_job_id"  // 可选：你的任务ID
}
```

### 4.2 响应格式

**成功响应（同步）**：
```json
{
  "success": true,
  "data": {
    "output_url": "https://r2.example.com/output.jpg",
    "metadata": {
      "width": 1920,
      "height": 1080,
      "size": 1048576,
      "format": "webp"
    }
  },
  "execution_time_ms": 1234
}
```

**成功响应（异步创建）**：
```json
{
  "success": true,
  "data": {
    "job_id": "job_abc123",
    "status": "pending",
    "estimated_duration": 300,
    "poll_url": "/api/v1/jobs/job_abc123"
  }
}
```

**错误响应**：
```json
{
  "success": false,
  "error": {
    "code": "INVALID_FILE_FORMAT",
    "message": "Unsupported file format. Only JPG, PNG, WEBP are supported.",
    "details": {
      "provided_format": "tiff",
      "supported_formats": ["jpg", "png", "webp"]
    }
  },
  "request_id": "req_xyz789"
}
```

### 4.3 认证方式

**API Key 认证**（推荐用于服务间调用）：
```http
X-API-Key: your_shared_secret_key
```

**JWT Token 认证**（可选，用于需要用户上下文的场景）：
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 4.4 Webhook 规范

**Python 发送的 Webhook 格式**：
```json
POST https://your-site.com/webhooks/jobs
Content-Type: application/json
X-Webhook-Secret: your_webhook_secret
X-Job-ID: job_abc123
X-Status: completed

{
  "job_id": "job_abc123",
  "client_job_id": "your_internal_job_id",  // 回传你的ID
  "status": "completed",
  "result": {
    "output_url": "https://r2.example.com/output.mp4",
    "metadata": {...}
  },
  "started_at": "2026-01-17T10:00:00Z",
  "completed_at": "2026-01-17T10:05:00Z",
  "execution_time_ms": 300000
}
```

**Next.js 验证 Webhook**：
```typescript
// 验证 webhook 签名
import crypto from 'crypto';

function verifyWebhook(
  payload: string,
  signature: string,
  secret: string
): boolean {
  const hmac = crypto.createHmac('sha256', secret);
  const digest = hmac.update(payload).digest('hex');
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(digest)
  );
}
```

---

## 5. 插件化架构

### 5.1 插件系统架构

```
┌─────────────────────────────────────────────────────┐
│              FastAPI Application                    │
│  ┌──────────────────────────────────────────────┐   │
│  │        Plugin Manager (插件管理器)            │   │
│  │  - 发现插件                                   │   │
│  │  - 路由注册                                   │   │
│  │  - 生命周期管理                               │   │
│  └──────────────────────────────────────────────┘   │
│                      │                               │
│      ┌───────────────┼───────────────┐               │
│      │               │               │               │
│  ┌───▼─────┐   ┌───▼─────┐    ┌───▼─────┐          │
│  │Plugin 1 │   │Plugin 2 │    │Plugin N │          │
│  │Compress │   │Translate│    │NSFW     │          │
│  └────┬────┘   └────┬────┘    └────┬────┘          │
│       │             │              │                │
│  ┌────▼─────────────▼──────────────▼─────────┐      │
│  │       AI Provider Layer (统一抽象)         │      │
│  │  - OpenAI                                │      │
│  │  - Stability AI                          │      │
│  │  - Replicate                             │      │
│  │  - Local Processing                      │      │
│  └──────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────┘
```

### 5.2 插件基类设计

```python
# app/plugins/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from enum import Enum

class ProcessingMode(str, Enum):
    SYNC = "sync"      # 同步处理
    ASYNC = "async"    # 异步处理

class BasePlugin(ABC):
    """所有插件必须继承的基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """插件唯一标识，如 'image-compress'"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """显示名称，如 '图片压缩'"""
        pass

    @property
    @abstractmethod
    def category(self) -> str:
        """分类：image, video, document, ai, storage"""
        pass

    @property
    def processing_mode(self) -> ProcessingMode:
        """处理模式：同步或异步"""
        return ProcessingMode.SYNC

    @property
    def enabled(self) -> bool:
        """是否启用"""
        return True

    @abstractmethod
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理逻辑（不写入数据库）

        Args:
            input_data: 输入数据

        Returns:
            处理结果
        """
        pass

    @abstractmethod
    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """输入验证"""
        pass

    async def health_check(self) -> bool:
        """健康检查"""
        return True
```

### 5.3 插件实现示例

```python
# app/plugins/image/compress.py
from typing import Dict, Any, Optional, Tuple
from app.plugins.base import BasePlugin, ProcessingMode
from app.services.storage import R2Service
from PIL import Image
import io
import aiohttp

class ImageCompressPlugin(BasePlugin):
    """图片压缩插件"""

    name = "image-compress"
    display_name = "图片压缩"
    category = "image"
    processing_mode = ProcessingMode.SYNC

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.r2 = R2Service()
        self.max_file_size = config.get("max_file_size", 52428800)  # 50MB

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """压缩图片（不入库）"""
        # 1. 验证输入
        is_valid, error = self.validate_input(input_data)
        if not is_valid:
            return {"success": False, "error": error}

        # 2. 下载图片
        image_url = input_data["image_url"]
        options = input_data.get("options", {})

        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    return {"success": False, "error": "Failed to download image"}
                image_data = await resp.read()

        # 3. 压缩处理
        original_size = len(image_data)
        img = Image.open(io.BytesIO(image_data))

        quality = options.get("quality", 80)
        target_format = options.get("format", img.format).lower()
        max_width = options.get("max_width")
        max_height = options.get("max_height")

        # 调整尺寸
        if max_width or max_height:
            img.thumbnail((max_width or img.width, max_height or img.height))

        # 压缩
        output = io.BytesIO()
        img.save(output, format=target_format, quality=quality, optimize=True)
        compressed_data = output.getvalue()
        compressed_size = len(compressed_data)

        # 4. 上传到 R2
        output_url = await self.r2.upload(
            data=compressed_data,
            filename=f"compressed_{hash(image_url)}.{target_format}",
            content_type=f"image/{target_format}"
        )

        # 5. 返回结果（不入库）
        return {
            "success": True,
            "data": {
                "output_url": output_url,
                "metadata": {
                    "original_size": original_size,
                    "compressed_size": compressed_size,
                    "compression_ratio": round(1 - compressed_size / original_size, 2),
                    "width": img.width,
                    "height": img.height,
                    "format": target_format
                }
            }
        }

    def validate_input(self, input_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """输入验证"""
        if "image_url" not in input_data:
            return False, "Missing required parameter: image_url"

        # 可选：检查文件大小
        file_size = input_data.get("file_size", 0)
        if file_size > self.max_file_size:
            return False, f"File size exceeds maximum of {self.max_file_size} bytes"

        return True, None
```

### 5.4 插件配置

```yaml
# config/plugins.yaml
plugins:
  image-compress:
    enabled: true
    max_file_size: 52428800  # 50MB
    supported_formats: ["jpg", "jpeg", "png", "webp"]

  image-remove-background:
    enabled: true
    provider: remove.bg
    max_file_size: 10485760  # 10MB

  image-translate:
    enabled: true
    provider: openai
    model: "gpt-4-vision"

  video-transcode:
    enabled: true
    max_file_size: 524288000  # 500MB
    supported_formats: ["mp4", "mov", "avi"]

# AI Provider 配置
ai_providers:
  openai:
    api_key_env: OPENAI_API_KEY
    base_url: "https://api.openai.com/v1"
    timeout: 30
    max_retries: 3

  remove.bg:
    api_key_env: REMOVEBG_API_KEY
    base_url: "https://api.remove.bg/v1.0"

  stability:
    api_key_env: STABILITY_API_KEY
    base_url: "https://api.stability.ai/v1"
```

---

## 6. Next.js 端设计

### 6.1 数据库表设计（可选）

如果需要异步任务，Next.js 可以添加自己的任务表：

```sql
-- Next.js 的新表（Python 不感知）
CREATE TABLE processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 任务信息
    job_id VARCHAR(100) UNIQUE NOT NULL,              -- Python 返回的 job_id
    client_job_id VARCHAR(100),                       -- 站点内部任务ID
    plugin_name VARCHAR(100) NOT NULL,                -- 使用的插件
    status VARCHAR(20) DEFAULT 'pending',             -- pending, processing, completed, failed

    -- 输入输出
    input_data JSONB,
    output_data JSONB,

    -- 业务关联
    user_id UUID REFERENCES User(id),
    upload_id UUID REFERENCES Upload(id),

    -- 时间戳
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,

    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_job_id (job_id)
);
```

### 6.2 Python API 调用封装

```typescript
// src/lib/python-service.ts
import { HTTPException } from 'http-exception';

interface PythonServiceConfig {
  baseURL: string;
  apiKey: string;
  timeout?: number;
}

export class PythonServiceClient {
  private config: PythonServiceConfig;

  constructor(config: PythonServiceConfig) {
    this.config = config;
  }

  private async request(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<any> {
    const url = `${this.config.baseURL}${endpoint}`;

    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': this.config.apiKey,
        ...options.headers,
      },
      signal: AbortSignal.timeout(this.config.timeout || 30000),
    });

    if (!response.ok) {
      throw new HTTPException(response.status, 'Python service error');
    }

    return response.json();
  }

  // 图片处理
  async imageCompress(imageUrl: string, options: any) {
    return this.request('/api/v1/image/compress', {
      method: 'POST',
      body: JSON.stringify({ image_url: imageUrl, options }),
    });
  }

  async imageRemoveBackground(imageUrl: string) {
    return this.request('/api/v1/image/remove-background', {
      method: 'POST',
      body: JSON.stringify({ image_url: imageUrl }),
    });
  }

  // 视频处理
  async videoTranscode(
    videoUrl: string,
    options: any,
    webhookUrl: string
  ) {
    return this.request('/api/v1/video/transcode', {
      method: 'POST',
      body: JSON.stringify({
        video_url: videoUrl,
        options,
        callback_url: webhookUrl,
        webhook_secret: process.env.WEBHOOK_SECRET,
      }),
    });
  }

  // AI 能力
  async aiEmbedding(text: string) {
    return this.request('/api/v1/ai/embedding', {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
  }

  async aiClassify(content: string) {
    return this.request('/api/v1/ai/classify', {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
  }
}

// 单例
const pythonClient = new PythonServiceClient({
  baseURL: process.env.PYTHON_SERVICE_URL || 'http://localhost:8000',
  apiKey: process.env.PYTHON_SERVICE_API_KEY || '',
  timeout: 60000,  // 60秒
});

export default pythonClient;
```

### 6.3 业务逻辑封装

```typescript
// src/lib/image-processing.ts
import pythonClient from './python-service';
import { db } from './db';
import { checkUserQuota } from './quota';

/**
 * 图片压缩业务逻辑
 * 1. 业务检查（鉴权、配额）
 * 2. 调用 Python 服务
 * 3. 入库
 */
export async function compressImage(
  userId: string,
  imageUrl: string,
  options: CompressOptions
): Promise<CompressResult> {
  // 1. 业务逻辑检查
  await checkUserQuota(userId, 'image_compress');
  const user = await db.user.findUnique({ where: { id: userId } });
  if (!user) {
    throw new Error('User not found');
  }

  // 2. 调用 Python 能力服务
  const result = await pythonClient.imageCompress(imageUrl, options);

  if (!result.success) {
    throw new Error(result.error);
  }

  // 3. 入库（Next.js 控制）
  const upload = await db.upload.create({
    data: {
      userId,
      url: result.data.output_url,
      size: result.data.metadata.compressed_size,
      mimeType: `image/${result.data.metadata.format}`,
      metadata: result.data.metadata,
    },
  });

  // 4. 更新配额
  await db.userQuota.update({
    where: { userId },
    data: { used: { increment: 1 } },
  });

  // 5. 记录审计日志
  await db.auditLog.create({
    data: {
      userId,
      action: 'image_compress',
      details: { originalUrl: imageUrl, result },
    },
  });

  return {
    uploadId: upload.id,
    outputUrl: result.data.output_url,
    metadata: result.data.metadata,
  };
}
```

### 6.4 Webhook 处理

```typescript
// src/app/api/webhooks/jobs/route.ts
import { NextRequest } from 'next/server';
import crypto from 'crypto';
import { db } from '@/lib/db';

export async function POST(request: NextRequest) {
  // 1. 验证签名
  const signature = request.headers.get('X-Webhook-Secret');
  const webhookSecret = process.env.WEBHOOK_SECRET;

  if (signature !== webhookSecret) {
    return Response.json({ error: 'Invalid signature' }, { status: 401 });
  }

  // 2. 解析 payload
  const payload = await request.json();
  const { job_id, status, result } = payload;

  // 3. 更新数据库（Next.js 控制）
  const job = await db.processingJob.findUnique({
    where: { jobId: job_id },
  });

  if (!job) {
    return Response.json({ error: 'Job not found' }, { status: 404 });
  }

  await db.processingJob.update({
    where: { jobId: job_id },
    data: {
      status,
      outputData: result,
      completedAt: new Date(),
    },
  });

  // 4. 记录审计日志
  await db.auditLog.create({
    data: {
      userId: job.userId,
      action: 'job_completed',
      details: { jobId: job_id, status },
    },
  });

  return Response.json({ success: true });
}
```

---

## 7. 部署架构

### 7.1 Docker Compose 配置

```yaml
# docker-compose.yml
version: '3.8'

services:
  # Python 能力服务（无状态）
  python-service:
    build: ./python-service
    ports:
      - "8000:8000"
    environment:
      - R2_ACCOUNT_ID=${R2_ACCOUNT_ID}
      - R2_ACCESS_KEY_ID=${R2_ACCESS_KEY_ID}
      - R2_SECRET_ACCESS_KEY=${R2_SECRET_ACCESS_KEY}
      - R2_BUCKET_NAME=${R2_BUCKET_NAME}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - REDIS_URL=redis://redis:6379/0
      - WORKERS=4
    depends_on:
      - redis
    restart: unless-stopped
    deploy:
      replicas: 2  # 可横向扩展

  # Celery Worker（异步任务）
  celery-worker:
    build: ./python-service
    command: celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4
    environment:
      - R2_ACCOUNT_ID=${R2_ACCOUNT_ID}
      - R2_ACCESS_KEY_ID=${R2_ACCESS_KEY_ID}
      - R2_SECRET_ACCESS_KEY=${R2_SECRET_ACCESS_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    restart: unless-stopped
    deploy:
      replicas: 2

  # Flower（任务监控）
  flower:
    build: ./python-service
    command: celery -A app.tasks.celery_app flower --port=5555
    ports:
      - "5555:5555"
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    restart: unless-stopped

  # Next.js（业务层）
  nextjs:
    build: .
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - PYTHON_SERVICE_URL=http://python-service:8000
      - PYTHON_SERVICE_API_KEY=${PYTHON_SERVICE_API_KEY}
      - WEBHOOK_SECRET=${WEBHOOK_SECRET}
    depends_on:
      - python-service
      - db
    restart: unless-stopped

  # PostgreSQL（Next.js 业务数据）
  db:
    image: postgres:16
    environment:
      - POSTGRES_USER=${DB_USER}
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=${DB_NAME}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  # Redis（Celery 消息队列）
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

### 7.2 网络架构

```
Internet
    │
    ▼
┌─────────────────────────────────────────────┐
│         Nginx/Caddy (反向代理)              │
└───────────┬─────────────────────────────────┘
            │
    ┌───────┴────────┐
    │                │
    ▼                ▼
┌─────────┐    ┌─────────────┐
│ Next.js │    │ Python API  │
│ :3000   │    │ :8000       │
│         │    │             │
│ 业务层   │    │ 能力层      │
└─────────┘    └─────────────┘
                    │
        ┌───────────┼────────────┐
        │           │            │
        ▼           ▼            ▼
    ┌──────┐  ┌─────────┐  ┌──────┐
    │Redis │  │ Celery  │  │  R2  │
    └──────┘  │ Workers │  └──────┘
              └─────────┘
```

### 7.3 多站点部署

```yaml
# 为多个站点提供 Python 能力服务
services:
  # Python 能力服务（共享）
  python-service:
    build: ./python-service
    # ... 配置

  # Site A
  site-a-nextjs:
    image: your-registry/site-a:latest
    environment:
      - PYTHON_SERVICE_URL=http://python-service:8000
      - PYTHON_SERVICE_API_KEY=${SITE_A_API_KEY}

  # Site B
  site-b-nextjs:
    image: your-registry/site-b:latest
    environment:
      - PYTHON_SERVICE_URL=http://python-service:8000
      - PYTHON_SERVICE_API_KEY=${SITE_B_API_KEY}

  # Site N
  site-n-nextjs:
    image: your-registry/site-n:latest
    environment:
      - PYTHON_SERVICE_URL=http://python-service:8000
      - PYTHON_SERVICE_API_KEY=${SITE_N_API_KEY}
```

---

## 8. 监控与可观测性

### 8.1 Prometheus 指标

```python
# app/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# API 请求指标
api_requests_total = Counter(
    'python_api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)

api_request_duration = Histogram(
    'python_api_request_duration_seconds',
    'API request duration',
    ['method', 'endpoint']
)

# 插件使用指标
plugin_usage_total = Counter(
    'python_plugin_usage_total',
    'Total plugin usage',
    ['plugin_name', 'status']
)

plugin_processing_duration = Histogram(
    'python_plugin_processing_duration_seconds',
    'Plugin processing duration',
    ['plugin_name']
)

# AI Provider 指标
ai_provider_requests = Counter(
    'python_ai_provider_requests_total',
    'Total AI provider requests',
    ['provider', 'status']
)
```

### 8.2 结构化日志

```python
# app/core/logger.py
import structlog

logger = structlog.get_logger()

# 使用示例
logger.info(
    "plugin_execution_started",
    plugin_name="image-compress",
    request_id="req_123",
    input_params={"quality": 80}
)

logger.info(
    "plugin_execution_completed",
    plugin_name="image-compress",
    request_id="req_123",
    duration_ms=1234,
    status="success",
    output_size=1048576
)
```

### 8.3 健康检查

```python
# app/api/health.py
from fastapi import APIRouter
from app.plugins.plugin_manager import plugin_manager

router = APIRouter()

@router.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "plugins": {
            plugin.name: await plugin.health_check()
            for plugin in plugin_manager.list_plugins()
        }
    }
```

---

## 9. 安全考虑

### 9.1 认证

- **API Key**: 服务间调用使用预共享密钥
- **IP 白名单**: 限制只有 Next.js 服务器可以调用
- **速率限制**: 基于 API Key 的速率限制

### 9.2 数据安全

- **加密传输**: 强制 HTTPS
- **敏感数据**: AI API 密钥使用环境变量
- **临时文件**: 处理完成后立即清理

### 9.3 Webhook 安全

- **签名验证**: 使用 HMAC-SHA256 验证 webhook
- **重放攻击**: 添加时间戳和 nonce

```python
# Python 发送 webhook 时签名
import hmac
import hashlib
import time

def send_webhook(url: str, payload: dict, secret: str):
    payload['timestamp'] = int(time.time())
    payload['nonce'] = secrets.token_hex(16)

    message = json.dumps(payload, sort_keys=True)
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    requests.post(
        url,
        json=payload,
        headers={'X-Webhook-Signature': signature}
    )
```

---

## 10. 性能优化

### 10.1 缓存策略

```python
# app/core/cache.py
from functools import lru_cache
import hashlib

def cache_key(url: str, options: dict) -> str:
    """生成缓存键"""
    data = f"{url}:{json.dumps(options, sort_keys=True)}"
    return hashlib.md5(data.encode()).hexdigest()

# Redis 缓存
async def get_cached_result(key: str):
    return await redis.get(f"cache:{key}")

async def set_cached_result(key: str, result: dict, ttl: int = 3600):
    await redis.setex(f"cache:{key}", ttl, json.dumps(result))
```

### 10.2 连接池

```python
# app/core/http.py
import aiohttp

http_session = aiohttp.ClientSession(
    timeout=aiohttp.ClientTimeout(total=30),
    connector=aiohttp.TCPConnector(
        limit=100,  # 最大连接数
        limit_per_host=10,  # 每个主机最大连接数
    )
)
```

---

## 11. 迁移策略

### 11.1 渐进式迁移

**阶段 1：基础设施（1周）**
- 搭建 FastAPI 项目
- 实现插件系统基础架构
- Docker Compose 本地环境
- 第一个插件（图片压缩）

**阶段 2：核心能力（2-3周）**
- 实现核心插件（5-10个）
- 实现异步任务系统（Celery）
- API 接口开发和测试

**阶段 3：Next.js 集成（1-2周）**
- Next.js API 调用封装
- Webhook 处理
- 渐进式替换现有功能

**阶段 4：监控和优化（1周）**
- 添加监控和日志
- 性能优化
- 文档完善

### 11.2 风险控制

- **功能开关**: 通过环境变量控制使用新/旧实现
- **并行运行**: 新旧系统同时运行，对比结果
- **快速回退**: 保留现有代码，出问题立即回退

---

## 12. Python 项目结构

```
python-service/
├── app/
│   ├── api/                    # API 路由
│   │   ├── v1/
│   │   │   ├── image.py        # 图片处理接口
│   │   │   ├── video.py        # 视频处理接口
│   │   │   ├── document.py     # 文档处理接口
│   │   │   ├── ai.py           # AI 能力接口
│   │   │   ├── storage.py      # 存储接口
│   │   │   ├── jobs.py         # 任务状态查询
│   │   │   └── health.py       # 健康检查
│   │   └── deps.py             # 依赖注入
│   ├── core/                   # 核心配置
│   │   ├── config.py           # 配置管理
│   │   ├── security.py         # 安全相关
│   │   ├── logger.py           # 日志配置
│   │   └── metrics.py          # Prometheus 指标
│   ├── plugins/                # 插件系统
│   │   ├── base.py             # 插件基类
│   │   ├── plugin_manager.py   # 插件管理器
│   │   ├── image/              # 图片处理插件
│   │   ├── video/              # 视频处理插件
│   │   ├── document/           # 文档处理插件
│   │   ├── ai/                 # AI 能力插件
│   │   └── storage/            # 存储操作插件
│   ├── services/               # 业务服务
│   │   ├── ai_providers/       # AI Provider 抽象
│   │   │   ├── base.py
│   │   │   ├── openai.py
│   │   │   ├── stability.py
│   │   │   ├── replicate.py
│   │   │   └── factory.py
│   │   ├── storage.py          # R2 存储服务
│   │   ├── cache.py            # Redis 缓存
│   │   └── http.py             # HTTP 客户端
│   ├── tasks/                  # Celery 任务
│   │   ├── celery_app.py
│   │   ├── image_tasks.py
│   │   ├── video_tasks.py
│   │   └── document_tasks.py
│   ├── utils/                  # 工具函数
│   │   ├── image.py
│   │   ├── video.py
│   │   └── file.py
│   └── main.py                 # FastAPI 应用入口
├── config/
│   ├── plugins.yaml            # 插件配置
│   └── ai_providers.yaml       # AI Provider 配置
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── scripts/
│   └── setup.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 13. 关键优势总结

✅ **业务自治**: 每个站点完全控制自己的业务数据、权限、配额
✅ **能力复用**: 多个站点共享 Python 能力，避免重复建设
✅ **扩展简单**: 新增站点只需接入 Python API，不需要修改 Python
✅ **解耦清晰**: Python 不关心业务逻辑，Next.js 不关心处理细节
✅ **独立扩展**: Python 服务可以独立扩容，不影响站点
✅ **故障隔离**: Python 故障不影响站点的业务逻辑
✅ **易于维护**: 插件化架构，新增功能不影响现有代码
✅ **成本优化**: 共享 Python 服务，降低基础设施成本

---

## 14. 下一步行动

1. ✅ 架构设计确认（能力服务模式）
2. ⏳ 搭建 FastAPI 项目基础
3. ⏳ 实现插件系统和插件管理器
4. ⏳ 实现第一个插件（图片压缩）
5. ⏳ Next.js API 调用封装
6. ⏳ 集成测试
7. ⏳ 部署和监控
8. ⏳ 文档完善

---

**文档版本**: 2.0
**最后更新**: 2026-01-17
**状态**: 已确认（能力服务模式）
**架构类型**: 无状态能力服务
