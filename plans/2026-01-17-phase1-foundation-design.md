# Python 能力服务 - Phase 1 基础架构设计文档

**项目**: image2url - Python 能力服务（Phase 1: Foundation）
**日期**: 2026-01-17
**版本**: 1.0
**状态**: 设计确认
**作者**: Claude & Abel

---

## 1. 概述

### 1.1 Phase 1 目标

本阶段专注于构建**坚实的基础架构**，为后续功能扩展打下基础：

- ✅ 搭建 FastAPI 项目基础结构
- ✅ 实现插件系统核心架构（BasePlugin + PluginManager）
- ✅ 实现第一个插件：图片压缩（同步处理）
- ✅ Docker 容器化部署
- ✅ R2 存储集成
- ✅ API Key 认证
- ✅ 基础测试框架

### 1.2 架构原则

- **无状态服务**: Python 不存储业务数据，只做处理
- **插件化**: 所有能力都是插件，易于扩展
- **异步优先**: 使用 async/await 模式
- **简单优先**: YAGNI 原则，只实现必需功能

---

## 2. 项目结构

### 2.1 目录结构

```
dev/back-end/
├── app/
│   ├── api/
│   │   ├── deps.py                    # 依赖注入：API Key 认证
│   │   └── v1/
│   │       ├── health.py              # GET /health - 健康检查
│   │       └── image.py               # POST /compress - 图片压缩
│   ├── core/
│   │   ├── config.py                  # 配置管理（从环境变量加载）
│   │   ├── logger.py                  # 日志配置
│   │   └── security.py                # 安全相关工具（可选）
│   ├── plugins/
│   │   ├── base.py                    # BasePlugin 抽象类
│   │   ├── plugin_manager.py          # 插件管理器
│   │   └── image/
│   │       └── compress.py            # ImageCompressPlugin 实现
│   ├── services/
│   │   ├── storage.py                 # R2Service - R2 存储服务
│   │   └── http.py                    # HttpClient - HTTP 连接池
│   └── main.py                        # FastAPI 应用入口
├── config/
│   └── plugins.yaml                   # 插件配置文件
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # Pytest fixtures
│   └── test_compress.py               # 图片压缩插件测试
├── .env.example                        # 环境变量模板
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
└── README.md
```

### 2.2 设计说明

**目录组织**:
- `app/api/` - API 路由层，按版本分组
- `app/core/` - 核心基础设施（配置、日志、安全）
- `app/plugins/` - 插件实现，按类别分组（image/, video/ 等）
- `app/services/` - 外部服务集成（R2、HTTP 客户端）
- `tests/` - 测试代码

---

## 3. 插件系统设计

### 3.1 BasePlugin 抽象类

```python
# app/plugins/base.py
from abc import ABC, abstractmethod
from enum import Enum

class ProcessingMode(str, Enum):
    """处理模式"""
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
        """处理模式：默认同步"""
        return ProcessingMode.SYNC

    @property
    def enabled(self) -> bool:
        """是否启用"""
        return True

    @abstractmethod
    async def process(self, input_data: dict) -> dict:
        """处理逻辑（不写入数据库）

        Args:
            input_data: 输入数据

        Returns:
            处理结果字典，包含 success、data、error 等字段
        """
        pass

    @abstractmethod
    def validate_input(self, input_data: dict) -> tuple[bool, str | None]:
        """输入验证

        Returns:
            (is_valid, error_message)
        """
        pass

    async def health_check(self) -> bool:
        """健康检查（默认返回 True）"""
        return True
```

### 3.2 PluginManager 管理器

```python
# app/plugins/plugin_manager.py
from typing import Dict
from app.plugins.base import BasePlugin

class PluginManager:
    """插件管理器 - 负责插件注册和查找"""

    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}

    def register(self, plugin: BasePlugin):
        """注册插件"""
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> BasePlugin | None:
        """根据名称获取插件"""
        return self._plugins.get(name)

    def list_plugins(self) -> list[BasePlugin]:
        """列出所有插件"""
        return list(self._plugins.values())

    def get_by_category(self, category: str) -> list[BasePlugin]:
        """根据分类获取插件"""
        return [p for p in self._plugins.values() if p.category == category]
```

---

## 4. 图片压缩插件实现

### 4.1 完整实现

```python
# app/plugins/image/compress.py
from typing import Dict, Any
from app.plugins.base import BasePlugin, ProcessingMode
from PIL import Image
import io
import aiohttp
import hashlib
from app.services.storage import R2Service

class ImageCompressPlugin(BasePlugin):
    """图片压缩插件 - Phase 1 第一个插件"""

    name = "image-compress"
    display_name = "图片压缩"
    category = "image"
    processing_mode = ProcessingMode.SYNC

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.r2 = R2Service()
        self.max_file_size = config.get("max_file_size", 52428800)  # 50MB

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """压缩图片（不入库）

        流程：
        1. 验证输入
        2. 下载图片
        3. 压缩处理
        4. 上传到 R2
        5. 返回结果
        """
        # 1. 验证输入
        is_valid, error = self.validate_input(input_data)
        if not is_valid:
            return {"success": False, "error": error}

        # 2. 下载图片
        image_url = input_data["image_url"]
        options = input_data.get("options", {})

        async with aiohttp.ClientSession() as session:
            async with session.get(str(image_url)) as resp:
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
        filename = f"compressed_{hashlib.sha256(image_data).hexdigest()[:16]}.{target_format}"
        output_url = await self.r2.upload(
            data=compressed_data,
            filename=filename,
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

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, str | None]:
        """输入验证"""
        if "image_url" not in input_data:
            return False, "Missing required parameter: image_url"

        # 可选：检查文件大小
        file_size = input_data.get("file_size", 0)
        if file_size > self.max_file_size:
            return False, f"File size exceeds maximum of {self.max_file_size} bytes"

        return True, None
```

### 4.2 处理流程

```
1. Next.js 发送请求
   ↓
2. API Key 认证
   ↓
3. 图片压缩插件处理：
   - 下载图片
   - PIL 压缩
   - 上传 R2
   - 返回结果
   ↓
4. Next.js 入库
   ↓
5. 返回给用户
```

---

## 5. API 层设计

### 5.1 主应用入口

```python
# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import health, image
from app.plugins.plugin_manager import PluginManager
from app.plugins.image.compress import ImageCompressPlugin
from app.core.config import settings
from app.core.logger import setup_logging

# Setup logging
setup_logging()

# Create FastAPI app
app = FastAPI(
    title="Python Capability Service",
    version="2.0.0",
    description="Stateless processing capabilities for image2url"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Configure in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize plugin manager
plugin_manager = PluginManager()

# Register plugins
compress_plugin = ImageCompressPlugin(config=settings.plugins_config)
plugin_manager.register(compress_plugin)

# Include routers
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(image.router, prefix="/api/v1/image", tags=["image"])

# Startup/Shutdown events
@app.on_event("startup")
async def startup():
    """应用启动时初始化"""
    # Initialize HTTP client pool, etc.
    pass

@app.on_event("shutdown")
async def shutdown():
    """应用关闭时清理"""
    # Cleanup resources
    pass
```

### 5.2 图片压缩 API 端点

```python
# app/api/v1/image.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, HttpUrl
from typing import Optional, Dict
from app.plugins.plugin_manager import plugin_manager
from app.api.deps import verify_api_key
import time

router = APIRouter()

class CompressRequest(BaseModel):
    image_url: HttpUrl
    options: Optional[Dict] = {}

class CompressResponse(BaseModel):
    success: bool
    data: Optional[Dict] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None

@router.post("/compress", response_model=CompressResponse)
async def compress_image(
    request: CompressRequest,
    authorized: bool = Depends(verify_api_key)
):
    """图片压缩 API 端点"""
    # 获取插件
    plugin = plugin_manager.get("image-compress")
    if not plugin:
        raise HTTPException(status_code=501, detail="Plugin not found")

    # 执行处理
    start = time.time()
    result = await plugin.process({
        "image_url": str(request.image_url),
        "options": request.options
    })
    execution_time = int((time.time() - start) * 1000)
    result["execution_time_ms"] = execution_time

    return result
```

### 5.3 健康检查端点

```python
# app/api/v1/health.py
from fastapi import APIRouter
from app.plugins.plugin_manager import plugin_manager

router = APIRouter()

@router.get("/health")
async def health_check():
    """健康检查 - 返回服务状态和插件信息"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "plugins": [
            {
                "name": p.name,
                "display_name": p.display_name,
                "category": p.category,
                "enabled": p.enabled,
                "healthy": await p.health_check()
            }
            for p in plugin_manager.list_plugins()
        ]
    }
```

### 5.4 API 认证依赖

```python
# app/api/deps.py
from fastapi import Header, HTTPException
from app.core.config import settings

async def verify_api_key(x_api_key: str = Header(...)):
    """验证 API Key"""
    if x_api_key != settings.python_service_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True
```

---

## 6. 服务层设计

### 6.1 配置管理

```python
# app/core/config.py
from pydantic_settings import BaseSettings
from typing import Dict, Any

class Settings(BaseSettings):
    """应用配置 - 从环境变量加载"""

    # R2 Configuration
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket_name: str
    r2_public_url: str

    # Service Auth
    python_service_api_key: str

    # Plugin Config (from YAML)
    plugins_config: Dict[str, Any] = {}

    class Config:
        env_file = ".env"

settings = Settings()
```

### 6.2 R2 存储服务

```python
# app/services/storage.py
import boto3
from botocore.client import Config as BotoConfig
import hashlib
from app.core.config import settings

class R2Service:
    """Cloudflare R2 存储服务封装"""

    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            endpoint_url=f'https://{settings.r2_account_id}.r2.cloudflarestorage.com',
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=BotoConfig(signature_version='s3v4'),
            region_name='auto'
        )
        self.bucket_name = settings.r2_bucket_name
        self.public_url = settings.r2_public_url

    async def upload(
        self,
        data: bytes,
        filename: str,
        content_type: str
    ) -> str:
        """上传文件到 R2 并返回公开 URL

        Args:
            data: 文件二进制数据
            filename: 文件名
            content_type: MIME 类型

        Returns:
            公开访问 URL
        """
        # 生成唯一键
        key = f"uploads/{hashlib.sha256(data).hexdigest()[:16]}_{filename}"

        # 上传
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type
        )

        # 返回公开 URL
        return f"{self.public_url}/{key}"

    async def delete(self, key: str) -> bool:
        """从 R2 删除文件"""
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return True
        except Exception:
            return False
```

### 6.3 HTTP 客户端连接池

```python
# app/services/http.py
import aiohttp
from aiohttp import ClientSession

class HttpClient:
    """HTTP 客户端连接池管理"""

    _session: ClientSession | None = None

    @classmethod
    async def get_session(cls) -> ClientSession:
        """获取共享的 HTTP session"""
        if cls._session is None:
            timeout = aiohttp.ClientTimeout(total=30)
            connector = aiohttp.TCPConnector(
                limit=100,           # 总连接数
                limit_per_host=10    # 每个主机最大连接数
            )
            cls._session = ClientSession(
                timeout=timeout,
                connector=connector
            )
        return cls._session

    @classmethod
    async def close(cls):
        """关闭连接池"""
        if cls._session:
            await cls._session.close()
            cls._session = None
```

---

## 7. 日志与监控

### 7.1 日志配置

```python
# app/core/logger.py
import logging
import sys

def setup_logging():
    """配置基础日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

logger = logging.getLogger(__name__)
```

---

## 8. 测试

### 8.1 测试示例

```python
# tests/test_compress.py
import pytest
from app.plugins.image.compress import ImageCompressPlugin

@pytest.fixture
def compress_plugin():
    """创建插件实例"""
    config = {"max_file_size": 52428800}
    return ImageCompressPlugin(config)

def test_validate_input_success(compress_plugin):
    """测试：输入验证成功"""
    input_data = {"image_url": "https://example.com/image.jpg"}
    is_valid, error = compress_plugin.validate_input(input_data)
    assert is_valid is True
    assert error is None

def test_validate_input_missing_url(compress_plugin):
    """测试：缺少 image_url 参数"""
    input_data = {}
    is_valid, error = compress_plugin.validate_input(input_data)
    assert is_valid is False
    assert "Missing required parameter" in error

def test_plugin_metadata(compress_plugin):
    """测试：插件元数据"""
    assert compress_plugin.name == "image-compress"
    assert compress_plugin.display_name == "图片压缩"
    assert compress_plugin.category == "image"
    assert compress_plugin.processing_mode.value == "sync"
```

---

## 9. 部署配置

### 9.1 Dockerfile

```dockerfile
# dev/back-end/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY config/ ./config/

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 9.2 docker-compose.yml

```yaml
# dev/back-end/docker-compose.yml
version: '3.8'

services:
  python-service:
    build: .
    ports:
      - "8000:8000"
    environment:
      # R2 Configuration
      - R2_ACCOUNT_ID=${R2_ACCOUNT_ID}
      - R2_ACCESS_KEY_ID=${R2_ACCESS_KEY_ID}
      - R2_SECRET_ACCESS_KEY=${R2_SECRET_ACCESS_KEY}
      - R2_BUCKET_NAME=${R2_BUCKET_NAME}
      - R2_PUBLIC_URL=${R2_PUBLIC_URL}

      # Service Auth
      - PYTHON_SERVICE_API_KEY=${PYTHON_SERVICE_API_KEY:-dev-secret-key}

      # Optional: Redis (for Phase 2)
      # - REDIS_URL=redis://redis:6379/0
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Redis (uncomment for Phase 2)
  # redis:
  #   image: redis:7-alpine
  #   ports:
  #     - "6379:6379"
  #   volumes:
  #     - redis_data:/data
  #   restart: unless-stopped

# volumes:
#   redis_data:
```

### 9.3 环境变量模板

```bash
# dev/back-end/.env.example
# Copy this to .env and fill in values

# R2 Configuration
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET_NAME=image2url-uploads
R2_PUBLIC_URL=https://your-r2-domain.com

# Service Auth (shared secret with Next.js)
PYTHON_SERVICE_API_KEY=your_shared_secret_here
```

### 9.4 requirements.txt

```txt
# Web Framework
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
python-multipart==0.0.6

# Image Processing
Pillow==10.2.0

# R2 Storage
boto3==1.34.19

# HTTP Client
aiohttp==3.9.1

# Development
pytest==7.4.3
httpx==0.26.0
```

---

## 10. API 使用示例

### 10.1 图片压缩请求

```bash
curl -X POST "http://localhost:8000/api/v1/image/compress" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-secret-key" \
  -d '{
    "image_url": "https://example.com/image.jpg",
    "options": {
      "quality": 80,
      "format": "webp",
      "max_width": 1920,
      "max_height": 1080
    }
  }'
```

### 10.2 成功响应

```json
{
  "success": true,
  "data": {
    "output_url": "https://r2.example.com/uploads/a1b2c3d4e5f6g7h8_compressed.webp",
    "metadata": {
      "original_size": 5242880,
      "compressed_size": 1048576,
      "compression_ratio": 0.8,
      "width": 1920,
      "height": 1080,
      "format": "webp"
    }
  },
  "execution_time_ms": 1234
}
```

### 10.3 错误响应

```json
{
  "success": false,
  "error": "Missing required parameter: image_url"
}
```

---

## 11. 交付物清单

Phase 1 完成后将交付以下内容：

### 11.1 代码文件

- ✅ `app/main.py` - FastAPI 应用入口
- ✅ `app/core/config.py` - 配置管理
- ✅ `app/core/logger.py` - 日志配置
- ✅ `app/plugins/base.py` - 插件基类
- ✅ `app/plugins/plugin_manager.py` - 插件管理器
- ✅ `app/plugins/image/compress.py` - 图片压缩插件
- ✅ `app/services/storage.py` - R2 存储服务
- ✅ `app/services/http.py` - HTTP 客户端
- ✅ `app/api/deps.py` - API 认证依赖
- ✅ `app/api/v1/health.py` - 健康检查端点
- ✅ `app/api/v1/image.py` - 图片压缩 API
- ✅ `config/plugins.yaml` - 插件配置

### 11.2 部署文件

- ✅ `Dockerfile` - Docker 镜像定义
- ✅ `docker-compose.yml` - 容器编排配置
- ✅ `.env.example` - 环境变量模板
- ✅ `requirements.txt` - Python 依赖
- ✅ `.gitignore` - Git 忽略规则

### 11.3 测试文件

- ✅ `tests/test_compress.py` - 插件测试
- ✅ `tests/conftest.py` - Pytest 配置

### 11.4 文档

- ✅ `README.md` - 项目说明文档

---

## 12. 下一步计划

Phase 1 完成后，可以进入 Phase 2：

### 12.1 Phase 2 核心能力（2-3周）

- 实现多个插件（5-10 个）
- 异步任务系统（Celery + Redis）
- 完善的错误处理和重试机制
- API 响应缓存

### 12.2 Phase 2 插件列表

- 图片处理：resize, remove-background, nsfw-check, ocr
- 视频处理：transcode, compress, screenshot
- 文档处理：pdf-to-images, pdf-to-text
- AI 能力：embedding, classify

---

## 13. 关键技术决策

### 13.1 为什么选择 FastAPI？

- **异步支持**: 原生 async/await，性能优秀
- **自动文档**: 自动生成 OpenAPI 文档
- **类型安全**: Pydantic 数据验证
- **现代化**: Python 3.6+ 特性

### 13.2 为什么使用插件架构？

- **解耦**: 各能力独立，互不影响
- **扩展**: 新增能力只需添加插件
- **复用**: 插件可被多个站点共享
- **测试**: 每个插件可独立测试

### 13.3 为什么使用 boto3 + R2？

- **S3 兼容**: boto3 是成熟的 S3 SDK
- **成本低**: R2 比 S3 便宜很多
- **无出口费用**: R2 免费出口流量
- **边缘网络**: Cloudflare CDN 加速

---

## 14. 附录

### 14.1 完整文件列表

```
dev/back-end/
├── app/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── health.py
│   │       └── image.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── logger.py
│   │   └── security.py
│   ├── plugins/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── plugin_manager.py
│   │   └── image/
│   │       ├── __init__.py
│   │       └── compress.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── storage.py
│   │   └── http.py
│   └── main.py
├── config/
│   └── plugins.yaml
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_compress.py
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

**文档版本**: 1.0
**最后更新**: 2026-01-17
**状态**: 设计确认，准备实施
**下一阶段**: Phase 1 实现
