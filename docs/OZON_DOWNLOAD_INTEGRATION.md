# Ozon 图片下载功能 - 前后端集成文档

**版本**: 2.0.0 (无状态架构)
**最后更新**: 2026-01-19
**架构原则**: 后端只干重活，前端管理数据

---

## 目录

1. [架构设计](#1-架构设计)
2. [职责划分](#2-职责划分)
3. [后端 API](#3-后端-api)
4. [前端集成指南](#4-前端集成指南)
5. [安全设计](#5-安全设计)

---

## 1. 架构设计

### 1.1 核心原则

**后端只干重活，前端管理数据**

- 后端专注于**计算密集型**和**IO 密集型**任务
- 前端负责**数据存储**、**用户管理**、**业务逻辑**
- 后端**无状态**，不存储任何业务数据

### 1.2 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js 前端 (数据层)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ 用户认证     │  │ 凭证管理     │  │ 任务记录     │      │
│  │ (NextAuth)   │  │ (数据库存储)  │  │ (数据库存储)  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────┬───────────────────────────────┘
                              │ HTTP API (X-API-Key + 凭证)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI 后端 (计算层)                       │
│  ┌────────────────────────────────────────────────────┐     │
│  │ POST /api/v1/ozon/download                           │     │
│  │   ┌──────────────────────────────────────────────┐  │     │
│  │   │ 1. Ozon API 调用 (查找产品)                    │  │     │
│  │   │ 2. 图片下载 (并发)                             │  │     │
│  │   │ 3. R2 上传 (流式，不写磁盘)                    │  │     │
│  │   │ 4. 返回结果 (直接返回，不存储)                  │  │     │
│  │   └──────────────────────────────────────────────┘  │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
                    ┌──────────────┐
                    │ Cloudflare   │
                    │     R2       │
                    └──────────────┘
```

### 1.3 数据流

```
1. 用户在前端配置 Ozon 凭证
   前端数据库 → 加密存储

2. 用户创建下载任务
   前端 → POST /api/v1/ozon/download
        {
          "credential": { "client_id": "xxx", "api_key": "xxx" },
          "articles": ["123", "456"],
          "user_id": "user_123"
        }

3. 后端处理（重活）
   a. 调用 Ozon API 查找 product_id
   b. 获取图片 URL 列表
   c. 并发下载图片（内存中）
   d. 直接上传到 R2（不写磁盘）
   e. 返回 R2 URL 列表

4. 前端接收结果并存储
   前端数据库 → 保存任务记录和结果
```

---

## 2. 职责划分

### 2.1 后端职责（重活）

| 功能 | 说明 |
|------|------|
| ✅ Ozon API 调用 | 查找产品、获取图片列表 |
| ✅ 图片下载 | HTTP 请求、并发控制 |
| ✅ R2 文件上传 | 流式上传，不写磁盘 |
| ✅ 图片处理 | 压缩、格式转换等 |
| ✅ AI 图片增强 | 背景移除、智能优化 |

### 2.2 前端职责（数据管理）

| 功能 | 说明 |
|------|------|
| ✅ 用户认证 | NextAuth.js / JWT |
| ✅ 凭证存储 | 加密存储在数据库 |
| ✅ 任务管理 | 创建、查询、更新任务状态 |
| ✅ 业务逻辑 | 配额管理、计费逻辑 |
| ✅ UI 展示 | 进度条、结果列表 |

---

## 3. 后端 API

### 3.1 下载图片

```http
POST /api/v1/ozon/download
X-API-Key: your-api-key
Content-Type: application/json

{
  "credential": {
    "client_id": "ozon_client_id",
    "api_key": "ozon_api_key"
  },
  "articles": ["123456", "789012"],
  "field": "offer_id",
  "user_id": "user_123"
}
```

**请求参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| credential.client_id | string | ✅ | Ozon Client-Id（从前端传入） |
| credential.api_key | string | ✅ | Ozon Api-Key（从前端传入） |
| articles | string[] | ✅ | 货号列表（1-100个） |
| field | string | ❌ | 查询字段（offer_id/sku/vendor_code） |
| user_id | string | ✅ | 用户ID（用于R2路径隔离） |

**响应（成功）：**

```json
{
  "success": true,
  "data": {
    "total_articles": 2,
    "processed": 2,
    "total_images": 16,
    "success_images": 15,
    "failed_images": 1,
    "items": [
      {
        "article": "123456",
        "product_id": 123456789,
        "status": "success",
        "total_images": 8,
        "success_images": 8,
        "failed_images": 0,
        "urls": [
          "https://r2.example.com/users/user_123/ozon/123456/123456_1.jpg",
          "https://r2.example.com/users/user_123/ozon/123456/123456_2.jpg"
        ]
      },
      {
        "article": "789012",
        "product_id": 987654321,
        "status": "success",
        "total_images": 8,
        "success_images": 7,
        "failed_images": 1,
        "urls": [
          "https://r2.example.com/users/user_123/ozon/789012/789012_1.jpg"
        ]
      }
    ]
  }
}
```

**响应（失败）：**

```json
{
  "success": false,
  "data": null,
  "error": "Invalid Ozon credentials"
}
```

### 3.2 健康检查

```http
GET /api/v1/ozon/health
```

**响应：**

```json
{
  "status": "healthy",
  "plugin": "ozon-download",
  "version": "1.0.0"
}
```

---

## 4. 前端集成指南

### 4.1 环境变量

```env
# .env.local
NEXT_PUBLIC_API_URL=https://your-api.com
NEXT_PUBLIC_API_KEY=your-api-key
```

### 4.2 TypeScript 类型定义

```typescript
// types/ozon.ts

export interface OzonDownloadRequest {
  credential: {
    client_id: string;
    api_key: string;
  };
  articles: string[];
  field?: 'offer_id' | 'sku' | 'vendor_code';
  user_id: string;
}

export interface OzonDownloadResponse {
  success: boolean;
  data?: {
    total_articles: number;
    processed: number;
    total_images: number;
    success_images: number;
    failed_images: number;
    items: OzonDownloadItem[];
  };
  error?: string;
}

export interface OzonDownloadItem {
  article: string;
  product_id?: number;
  status: 'success' | 'failed';
  total_images: number;
  success_images: number;
  failed_images: number;
  urls: string[];
  error?: string;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}
```

### 4.3 API 客户端

```typescript
// lib/api/ozon.ts

import type { OzonDownloadRequest, OzonDownloadResponse } from '@/types/ozon';

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

export async function downloadOzonImages(
  request: OzonDownloadRequest
): Promise<OzonDownloadResponse> {
  const response = await fetch(`${API_URL}/api/v1/ozon/download`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`API Error: ${response.status}`);
  }

  return response.json();
}
```

### 4.4 React Hook 示例

```typescript
// hooks/useOzonDownload.ts

import { useState } from 'react';
import { downloadOzonImages } from '@/lib/api/ozon';
import type { OzonDownloadRequest } from '@/types/ozon';

export function useOzonDownload() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const download = async (request: OzonDownloadRequest) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await downloadOzonImages(request);

      if (response.success && response.data) {
        // 保存到前端数据库
        await saveTaskToDatabase(response.data);
        return response.data;
      } else {
        setError(response.error || 'Download failed');
        return null;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return null;
    } finally {
      setIsLoading(false);
    }
  };

  return { download, isLoading, error };
}

// 前端数据库操作（示例）
async function saveTaskToDatabase(data: any) {
  // 保存到 Prisma/Supabase/等
  // await prisma.ozonTask.create({ data });
}
```

### 4.5 页面组件示例

```typescript
// app/ozon/page.tsx

'use client';

import { useState } from 'react';
import { useOzonDownload } from '@/hooks/useOzonDownload';
import { useSession } from 'next-auth/react';

export default function OzonDownloadPage() {
  const { data: session } = useSession();
  const { download, isLoading, error } = useOzonDownload();

  const [clientId, setClientId] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [articles, setArticles] = useState('');

  const handleSubmit = async () => {
    const result = await download({
      credential: {
        client_id: clientId,
        api_key: apiKey,
      },
      articles: articles.split('\n').filter(Boolean),
      field: 'offer_id',
      user_id: session?.user?.id || 'unknown',
    });

    if (result) {
      console.log('Download complete:', result);
      // 显示结果
    }
  };

  return (
    <div>
      <h1>Ozon 图片下载</h1>

      {/* 凭证输入 */}
      <input
        placeholder="Client-Id"
        value={clientId}
        onChange={(e) => setClientId(e.target.value)}
      />
      <input
        placeholder="Api-Key"
        type="password"
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
      />

      {/* 货号输入 */}
      <textarea
        placeholder="货号列表（每行一个）"
        value={articles}
        onChange={(e) => setArticles(e.target.value)}
      />

      <button onClick={handleSubmit} disabled={isLoading}>
        {isLoading ? '下载中...' : '开始下载'}
      </button>

      {error && <p className="text-red-500">{error}</p>}
    </div>
  );
}
```

---

## 5. 安全设计

### 5.1 凭证传输安全

| 措施 | 实现方式 |
|------|----------|
| **HTTPS** | 生产环境强制使用 TLS |
| **API Key 验证** | 后端验证 X-API-Key |
| **前端加密存储** | 凭证在前端数据库加密存储 |
| **不存储日志** | 后端不记录凭证信息 |

### 5.2 前端凭证存储

```typescript
// 前端加密存储凭证（示例）

// 使用加密库（如 crypto-js）
import CryptoJS from 'crypto-js';

const ENCRYPTION_KEY = process.env.NEXT_PUBLIC_ENCRYPTION_KEY;

export function encryptCredential(credential: { client_id: string; api_key: string }) {
  const plaintext = JSON.stringify(credential);
  return CryptoJS.AES.encrypt(plaintext, ENCRYPTION_KEY).toString();
}

export function decryptCredential(ciphertext: string) {
  const bytes = CryptoJS.AES.decrypt(ciphertext, ENCRYPTION_KEY);
  return JSON.parse(bytes.toString(CryptoJS.enc.Utf8));
}

// 存储到数据库
await db.ozonCredentials.create({
  data: {
    userId: session.user.id,
    name: "My Ozon Account",
    encryptedData: encryptCredential({ client_id, api_key }),
  },
});
```

### 5.3 R2 路径隔离

```
{bucket}/
└── users/
    └── {user_id}/           # 用户隔离
        └── ozon/
            └── {article}/    # 按货号分组
                ├── {article}_1.jpg
                └── {article}_2.jpg
```

---

## 附录

### A. 错误代码

| 代码 | 说明 |
|------|------|
| `INVALID_CREDENTIALS` | Ozon API 凭证无效 |
| `PRODUCT_NOT_FOUND` | 未找到对应产品 |
| `NO_IMAGES` | 产品没有图片 |
| `DOWNLOAD_FAILED` | 图片下载失败 |
| `R2_UPLOAD_FAILED` | R2 上传失败 |
| `TIMEOUT` | 请求超时 |

### B. 前端数据模型建议

```prisma
// prisma/schema.prisma

model OzonCredential {
  id          String   @id @default(cuid())
  userId      String
  name        String
  encryptedData String  // 加密后的凭证
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt

  @@unique([userId, name])
}

model OzonTask {
  id          String   @id @default(cuid())
  userId      String
  credentialId String
  articles    Json      // 货号列表
  status      String   // pending/completed/failed
  result      Json?    // 结果数据
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt
}
```

### C. 最佳实践

1. **凭证管理**
   - ✅ 前端加密存储
   - ✅ 使用环境变量加密密钥
   - ❌ 不要在前端日志中输出凭证

2. **用户体验**
   - ✅ 显示下载进度（后端支持流式响应可扩展）
   - ✅ 失败重试机制
   - ✅ 批量操作支持

3. **性能优化**
   - ✅ 前端缓存任务结果
   - ✅ 后端并发控制（max_workers）
   - ✅ R2 CDN 加速

---

**文档版本**: 2.0.0
**架构**: 无状态 - 后端只干重活
**最后更新**: 2026-01-19
