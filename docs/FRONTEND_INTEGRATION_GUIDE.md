# 前端集成指南 - Ozon 图片下载系统

**版本**: 2.0.0
**最后更新**: 2026-01-19
**架构原则**: 后端专注计算/IO密集型任务，前端负责数据管理和业务逻辑

---

## 📋 架构概述

### 核心设计理念

这是一个**前后端分离的微服务架构**，职责明确划分：

#### 前端（Next.js + Drizzle/Prisma）
**职责**: 全栈应用，管理所有业务数据和逻辑
- ✅ 用户认证与授权（ShipAny Auth）
- ✅ Ozon API 凭证管理（加密存储）
- ✅ 下载任务记录与状态跟踪
- ✅ 业务逻辑与配额管理
- ✅ 用户界面与交互体验

#### 后端（Python FastAPI）
**职责**: 无状态服务，专注"重活"处理
- ✅ Ozon API 集成调用
- ✅ 并发图片下载
- ✅ 流式上传到 Cloudflare R2
- ✅ 计算密集型操作

### 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    Next.js 前端 (数据层)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ ShipAny Auth │  │ Drizzle ORM  │  │ 任务记录 & 业务逻辑   │  │
│  │ (用户认证)    │  │ (数据库管理)  │  │ (PostgreSQL)         │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                   │
│  数据存储:                                                         │
│  • users (用户表)                                                 │
│  • ozon_credentials (Ozon 凭证 - 加密)                            │
│  • ozon_tasks (下载任务记录)                                      │
└─────────────────────────────┬───────────────────────────────────┘
                              │ HTTP API
                              │ X-API-Key: shared_secret
                              │ 凭证: client_id + api_key
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Python 后端 (计算层 - 完全无状态)                     │
│                                                                  │
│  POST /api/v1/ozon/download                                      │
│   ┌────────────────────────────────────────────────────────┐    │
│   │ 1. 接收前端传递的凭证和货号列表                           │    │
│   │ 2. 调用 Ozon Seller API 查找产品                        │    │
│   │ 3. 获取所有产品图片 URL                                  │    │
│   │ 4. 并发下载图片到内存 (max_workers: 5)                  │    │
│   │ 5. 流式上传到 Cloudflare R2 (不写磁盘)                  │    │
│   │ 6. 返回完整结果 + R2 公共访问 URL                        │    │
│   │                                                            │    │
│   ❌ 不存储任何业务数据                                         │    │
│   ❌ 不维护用户会话                                             │    │
│   ❌ 不访问数据库                                               │    │
│   └────────────────────────────────────────────────────────┘    │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ Cloudflare R2    │
                    │   对象存储        │
                    │  (图片文件)       │
                    └──────────────────┘
```

### 数据流图

```
1️⃣ 用户配置 Ozon 凭证
   前端: 用户输入 client_id + api_key
   前端: AES 加密凭证
   前端数据库: 存储到 ozon_credentials 表

2️⃣ 用户创建下载任务
   前端: 选择凭证 + 输入货号列表
   前端: 从数据库读取加密凭证
   前端: 解密凭证

3️⃣ 调用后端 API
   前端 → POST /api/v1/ozon/download
   {
     "credential": { "client_id": "xxx", "api_key": "xxx" },
     "articles": ["123456", "789012"],
     "field": "offer_id",
     "user_id": "user_abc123"
   }

4️⃣ 后端处理（重活）
   后端: Ozon API 查询 → 获取图片列表
   后端: 并发下载 → 内存缓冲
   后端: 流式上传 R2 → 不写磁盘
   后端: 返回结果

5️⃣ 前端保存结果
   后端 ← 返回: { success, data, error }
   前端: 保存任务记录到 ozon_tasks 表
   前端: 显示下载结果和 R2 URL
```

---

## 目录

1. [技术栈](#1-技术栈)
2. [环境配置](#2-环境配置)
3. [数据库设计](#3-数据库设计)
4. [后端 API 说明](#4-后端-api-说明)
5. [前端集成步骤](#5-前端集成步骤)
6. [核心代码实现](#6-核心代码实现)
7. [安全最佳实践](#7-安全最佳实践)
8. [常见问题](#8-常见问题)

---

## 1. 技术栈

### 前端技术栈

| 组件 | 技术 | 版本要求 | 说明 |
|------|------|---------|------|
| 框架 | Next.js | 14+ | App Router |
| 语言 | TypeScript | 5+ | 类型安全 |
| 数据库 | PostgreSQL | 14+ | 生产环境 |
| ORM | Drizzle ORM | 最新 | 类型安全的数据库客户端 |
| 认证 | ShipAny Auth | - | 基于 NextAuth |
| 样式 | Tailwind CSS | 3+ | 实用优先的 CSS 框架 |
| 组件库 | shadcn/ui | 最新 | 高质量 React 组件 |
| 状态管理 | Zustand | 5+ | 轻量级状态管理 |
| 表单验证 | React Hook Form + Zod | 最新 | 表单处理 |
| 加密 | crypto-js | 4+ | 凭证加密存储 |

### 后端技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 框架 | FastAPI | 0.100+ |
| 异步运行时 | asyncio + aiohttp | 并发处理 |
| 对象存储 | Cloudflare R2 | 图片存储 |
| 认证 | X-API-Key Header | 服务间认证 |
| 部署 | Docker | 容器化部署 |

---

## 2. 环境配置

### 2.1 前端环境变量

在项目根目录创建 `.env` 文件：

```env
# ========================================
# 应用基础配置
# ========================================
NEXT_PUBLIC_APP_URL=http://localhost:3000
NEXT_PUBLIC_APP_NAME=Ozon Image Downloader

# ========================================
# 数据库配置 (前端管理)
# ========================================
DATABASE_PROVIDER=postgresql
DATABASE_URL=postgresql://user:password@localhost:5432/ozon_app
DB_SCHEMA=public
DB_MIGRATIONS_TABLE=__drizzle_migrations
DB_SINGLETON_ENABLED=true
DB_MAX_CONNECTIONS=10

# ========================================
# 认证配置
# ========================================
AUTH_SECRET=your-auth-secret-here-generate-with-openssl-rand-base64-32
AUTH_URL=http://localhost:3000

# ========================================
# Python 后端 API 配置
# ========================================
# 后端服务地址
PYTHON_API_URL=http://localhost:8000
# API 密钥 (与后端 .env 中的 PYTHON_SERVICE_API_KEY 一致)
PYTHON_API_KEY=your-shared-secret-key-change-in-production

# ========================================
# 凭证加密配置
# ========================================
# 32 字符加密密钥 (用于加密存储 Ozon 凭证)
CREDENTIAL_ENCRYPTION_KEY=your-32-char-encryption-key-here

# ========================================
# 可选: Cloudflare R2 配置 (如需直传)
# ========================================
# R2_ACCOUNT_ID=your_account_id
# R2_ACCESS_KEY_ID=your_access_key
# R2_SECRET_ACCESS_KEY=your_secret_key
# R2_BUCKET_NAME=ozon-images
# R2_PUBLIC_URL=https://your-r2-domain.com
```

### 2.2 后端环境变量

在 `dev/ozon-backen/.env` 配置：

```env
# ========================================
# Cloudflare R2 配置
# ========================================
R2_ACCOUNT_ID=your_r2_account_id
R2_ACCESS_KEY_ID=your_r2_access_key
R2_SECRET_ACCESS_KEY=your_r2_secret_key
R2_BUCKET_NAME=ozon-images-uploads
R2_PUBLIC_URL=https://your-r2-domain.com

# ========================================
# API 认证 (与前端共享)
# ========================================
PYTHON_SERVICE_API_KEY=your-shared-secret-key-change-in-production

# ========================================
# 插件配置 (可选)
# ========================================
OZON_MAX_WORKERS=5
OZON_TIMEOUT_SEC=20
OZON_DEFAULT_FIELD=offer_id
```

**⚠️ 重要**: `PYTHON_SERVICE_API_KEY` 必须在前端和后端保持一致！

### 2.3 安装依赖

```bash
# 前端依赖
cd /path/to/ozon-front
npm install

# 如果使用 crypto-js 加密
npm install crypto-js
npm install -D @types/crypto-js

# shadcn/ui 组件 (如果需要)
npx shadcn-ui@latest add button card input label textarea
npx shadcn-ui@latest add table dialog form select alert
```

---

## 3. 数据库设计

> **重要原则**: 后端完全不接触数据库，所有业务数据由前端数据库管理。

### 3.1 Drizzle Schema 定义

在 `src/config/db/schema.postgres.ts` 中添加：

```typescript
import { boolean, index, integer, pgTable, text, timestamp, json } from 'drizzle-orm/pg-core';

// ========================================
// Ozon 凭证表 (加密存储)
// ========================================
export const ozonCredential = pgTable('ozon_credential',
  {
    id: text('id').primaryKey(), // 使用 cuid() 生成
    userId: text('user_id')
      .notNull()
      .references(() => user.id, { onDelete: 'cascade' }),

    // 用户自定义的凭证名称 (如 "主店铺", "备用账号")
    name: text('name').notNull(),

    // AES 加密后的凭证数据: {"client_id": "xxx", "api_key": "xxx"}
    encryptedData: text('encrypted_data').notNull(),

    createdAt: timestamp('created_at').defaultNow().notNull(),
    updatedAt: timestamp('updated_at')
      .defaultNow()
      .$onUpdate(() => new Date())
      .notNull(),
  },
  (table) => [
    index('idx_ozon_credential_user').on(table.userId),
  ]
);

// ========================================
// Ozon 下载任务表
// ========================================
export const ozonTask = pgTable('ozon_task',
  {
    id: text('id').primaryKey(), // cuid()

    userId: text('user_id')
      .notNull()
      .references(() => user.id, { onDelete: 'cascade' }),

    credentialId: text('credential_id')
      .notNull()
      .references(() => ozonCredential.id, { onDelete: 'cascade' }),

    // 请求参数 (JSON 存储)
    articles: json('articles').notNull(), // ["123456", "789012"]
    field: text('field').notNull(), // "offer_id" | "sku" | "vendor_code"

    // 任务状态
    status: text('status').notNull(), // "pending" | "processing" | "completed" | "failed"
    progress: integer('progress').notNull().default(0), // 0-100

    // 任务结果 (JSON 存储)
    result: json('result'), // 后端返回的完整结果
    errorMessage: text('error_message'),

    // 统计数据 (从 result 中提取，便于查询)
    totalArticles: integer('total_articles'),
    processedArticles: integer('processed_articles'),
    totalImages: integer('total_images'),
    successImages: integer('success_images'),
    failedImages: integer('failed_images'),

    // 时间戳
    startedAt: timestamp('started_at'),
    completedAt: timestamp('completed_at'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
    updatedAt: timestamp('updated_at')
      .defaultNow()
      .$onUpdate(() => new Date())
      .notNull(),
  },
  (table) => [
    index('idx_ozon_task_user').on(table.userId),
    index('idx_ozon_task_status').on(table.status),
    index('idx_ozon_task_created').on(table.createdAt),
  ]
);
```

### 3.2 数据库迁移

```bash
# 生成迁移文件
npx drizzle-kit generate:pg

# 执行迁移
npm run db:migrate

# 或使用 Drizzle Kit
npx drizzle-kit push:pg
```

### 3.3 数据关系图

```
user (用户表)
  ↓ 1:N
ozon_credential (Ozon 凭证表)
  ├─ id (主键)
  ├─ userId (外键 → user.id)
  ├─ name (凭证名称)
  └─ encryptedData (加密的 client_id + api_key)
      ↓ 1:N
  ozon_task (下载任务表)
    ├─ id (主键)
    ├─ userId (外键 → user.id)
    ├─ credentialId (外键 → ozon_credential.id)
    ├─ articles (货号列表 JSON)
    ├─ status (状态)
    └─ result (结果 JSON)
```

---

## 4. 后端 API 说明

### 4.1 API 端点概览

| 端点 | 方法 | 功能 | 认证 |
|------|------|------|------|
| `/api/v1/health` | GET | 健康检查 | X-API-Key |
| `/api/v1/ozon/download` | POST | 批量下载图片 | X-API-Key |

### 4.2 健康检查 API

**端点**: `GET /api/v1/health`

**请求示例**:
```typescript
const response = await fetch(`${PYTHON_API_URL}/api/v1/health`, {
  method: 'GET',
  headers: {
    'X-API-Key': PYTHON_API_KEY,
  },
});
```

**响应示例**:
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "plugins": [
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

### 4.3 Ozon 下载 API (核心)

**端点**: `POST /api/v1/ozon/download`

**请求头**:
```http
X-API-Key: your-shared-secret
Content-Type: application/json
```

**请求体**:
```json
{
  "credential": {
    "client_id": "ozon_client_id_here",
    "api_key": "ozon_api_key_here"
  },
  "articles": ["123456", "789012", "345678"],
  "field": "offer_id",
  "user_id": "user_abc123"
}
```

**请求参数说明**:

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `credential.client_id` | string | ✅ | Ozon Seller API Client ID |
| `credential.api_key` | string | ✅ | Ozon Seller API Key |
| `articles` | string[] | ✅ | 货号列表 (1-100个) |
| `field` | string | ❌ | 查询字段，默认 `offer_id`，可选: `sku`、`vendor_code` |
| `user_id` | string | ✅ | 用户 ID (用于 R2 路径隔离) |

**成功响应** (200 OK):
```json
{
  "success": true,
  "data": {
    "total_articles": 3,
    "processed": 3,
    "total_images": 24,
    "success_images": 24,
    "failed_images": 0,
    "items": [
      {
        "article": "123456",
        "product_id": 123456789,
        "status": "success",
        "total_images": 8,
        "success_images": 8,
        "failed_images": 0,
        "urls": [
          "https://your-r2-domain.com/users/user_abc123/ozon/123456/123456_1.jpg",
          "https://your-r2-domain.com/users/user_abc123/ozon/123456/123456_2.jpg",
          "https://your-r2-domain.com/users/user_abc123/ozon/123456/123456_3.jpg"
        ]
      },
      {
        "article": "789012",
        "product_id": 987654321,
        "status": "success",
        "total_images": 8,
        "success_images": 8,
        "failed_images": 0,
        "urls": [
          "https://your-r2-domain.com/users/user_abc123/ozon/789012/789012_1.jpg"
        ]
      },
      {
        "article": "345678",
        "product_id": 345678901,
        "status": "failed",
        "total_images": 0,
        "success_images": 0,
        "failed_images": 0,
        "error": "Product not found"
      }
    ]
  },
  "execution_time_ms": 5234
}
```

**失败响应** (4xx/5xx):
```json
{
  "success": false,
  "data": null,
  "error": "Invalid Ozon credentials"
}
```

### 4.4 错误代码说明

| HTTP 状态 | 错误信息 | 说明 | 前端处理建议 |
|----------|---------|------|-------------|
| 401 | Unauthorized | API Key 无效 | 检查环境变量配置 |
| 400 | Invalid credentials | Ozon 凭证无效 | 提示用户检查凭证 |
| 404 | Product not found | 货号不存在 | 显示失败列表 |
| 500 | Download failed | 下载失败 | 提示重试或联系支持 |

---

## 5. 前端集成步骤

### 5.1 创建 API 客户端

**文件**: `src/lib/api/ozon.ts`

```typescript
/**
 * Ozon API 客户端
 * 与 Python 后端交互的封装
 */

interface OzonCredential {
  client_id: string;
  api_key: string;
}

interface OzonDownloadRequest {
  credential: OzonCredential;
  articles: string[];
  field?: 'offer_id' | 'sku' | 'vendor_code';
  user_id: string;
}

interface OzonDownloadItem {
  article: string;
  product_id?: number;
  status: 'success' | 'failed';
  total_images: number;
  success_images: number;
  failed_images: number;
  urls: string[];
  error?: string;
}

interface OzonDownloadResult {
  total_articles: number;
  processed: number;
  total_images: number;
  success_images: number;
  failed_images: number;
  items: OzonDownloadItem[];
}

interface OzonDownloadResponse {
  success: boolean;
  data?: OzonDownloadResult;
  error?: string;
  execution_time_ms?: number;
}

const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:8000';
const PYTHON_API_KEY = process.env.PYTHON_API_KEY || '';

export class OzonApiClient {
  /**
   * 调用后端下载 API
   */
  async downloadImages(request: OzonDownloadRequest): Promise<OzonDownloadResponse> {
    try {
      const response = await fetch(`${PYTHON_API_URL}/api/v1/ozon/download`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': PYTHON_API_KEY,
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API Error ${response.status}: ${errorText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Ozon download API error:', error);
      throw error;
    }
  }

  /**
   * 健康检查
   */
  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${PYTHON_API_URL}/api/v1/health`, {
        headers: {
          'X-API-Key': PYTHON_API_KEY,
        },
      });
      return response.ok;
    } catch {
      return false;
    }
  }
}

// 单例导出
export const ozonApi = new OzonApiClient();
```

### 5.2 凭证加密工具

**文件**: `src/lib/crypto.ts`

```typescript
/**
 * 凭证加密/解密工具
 * 使用 AES 加密存储 Ozon API 凭证
 */
import CryptoJS from 'crypto-js';

const ENCRYPTION_KEY = process.env.CREDENTIAL_ENCRYPTION_KEY || '';

if (!ENCRYPTION_KEY) {
  throw new Error('CREDENTIAL_ENCRYPTION_KEY is not set in environment variables');
}

export interface OzonCredentialPlain {
  client_id: string;
  api_key: string;
}

/**
 * 加密凭证
 */
export function encryptCredential(credential: OzonCredentialPlain): string {
  const plaintext = JSON.stringify(credential);
  const encrypted = CryptoJS.AES.encrypt(plaintext, ENCRYPTION_KEY);
  return encrypted.toString();
}

/**
 * 解密凭证
 */
export function decryptCredential(ciphertext: string): OzonCredentialPlain {
  const decrypted = CryptoJS.AES.decrypt(ciphertext, ENCRYPTION_KEY);
  const plaintext = decrypted.toString(CryptoJS.enc.Utf8);

  if (!plaintext) {
    throw new Error('Failed to decrypt credential');
  }

  return JSON.parse(plaintext);
}
```

### 5.3 数据库操作 (Drizzle ORM)

**文件**: `src/lib/db/ozon.ts`

```typescript
/**
 * Ozon 相关数据库操作
 */
import { db } from '@/core/db';
import { ozonCredential, ozonTask } from '@/config/db/schema';
import { eq, desc } from 'drizzle-orm';
import { cuid } from '@/shared/lib/utils';
import type { OzonCredentialPlain } from '@/lib/crypto';

export interface CreateOzonCredentialInput {
  userId: string;
  name: string;
  encryptedData: string;
}

export interface CreateOzonTaskInput {
  userId: string;
  credentialId: string;
  articles: string[];
  field: string;
}

export class OzonDb {
  /**
   * 创建 Ozon 凭证
   */
  async createCredential(input: CreateOzonCredentialInput) {
    const [credential] = await db
      .insert(ozonCredential)
      .values({
        id: cuid(),
        userId: input.userId,
        name: input.name,
        encryptedData: input.encryptedData,
      })
      .returning();

    return credential;
  }

  /**
   * 获取用户的所有凭证
   */
  async getUserCredentials(userId: string) {
    return await db
      .select()
      .from(ozonCredential)
      .where(eq(ozonCredential.userId, userId))
      .orderBy(desc(ozonCredential.createdAt));
  }

  /**
   * 获取单个凭证
   */
  async getCredential(id: string, userId: string) {
    const [credential] = await db
      .select()
      .from(ozonCredential)
      .where(eq(ozonCredential.id, id))
      .limit(1);

    // 验证所有权
    if (credential && credential.userId !== userId) {
      throw new Error('Credential not found or access denied');
    }

    return credential;
  }

  /**
   * 删除凭证
   */
  async deleteCredential(id: string, userId: string) {
    const credential = await this.getCredential(id, userId);
    if (!credential) {
      throw new Error('Credential not found');
    }

    await db.delete(ozonCredential).where(eq(ozonCredential.id, id));
  }

  /**
   * 创建下载任务
   */
  async createTask(input: CreateOzonTaskInput) {
    const [task] = await db
      .insert(ozonTask)
      .values({
        id: cuid(),
        userId: input.userId,
        credentialId: input.credentialId,
        articles: input.articles as any, // JSON 类型
        field: input.field,
        status: 'pending',
        progress: 0,
      })
      .returning();

    return task;
  }

  /**
   * 更新任务状态
   */
  async updateTask(
    taskId: string,
    userId: string,
    updates: {
      status?: string;
      progress?: number;
      result?: any;
      errorMessage?: string;
      totalArticles?: number;
      processedArticles?: number;
      totalImages?: number;
      successImages?: number;
      failedImages?: number;
      startedAt?: Date;
      completedAt?: Date;
    }
  ) {
    // 验证任务所有权
    const [task] = await db
      .select()
      .from(ozonTask)
      .where(eq(ozonTask.id, taskId))
      .limit(1);

    if (!task || task.userId !== userId) {
      throw new Error('Task not found or access denied');
    }

    await db
      .update(ozonTask)
      .set({
        ...updates,
        result: updates.result as any,
        updatedAt: new Date(),
      })
      .where(eq(ozonTask.id, taskId));
  }

  /**
   * 获取用户的任务列表
   */
  async getUserTasks(userId: string, limit = 20) {
    return await db
      .select()
      .from(ozonTask)
      .where(eq(ozonTask.userId, userId))
      .orderBy(desc(ozonTask.createdAt))
      .limit(limit);
  }

  /**
   * 获取单个任务
   */
  async getTask(taskId: string, userId: string) {
    const [task] = await db
      .select()
      .from(ozonTask)
      .where(eq(ozonTask.id, taskId))
      .limit(1);

    if (task && task.userId !== userId) {
      throw new Error('Task not found or access denied');
    }

    return task;
  }
}

export const ozonDb = new OzonDb();
```

### 5.4 React Hook 集成

**文件**: `src/app/hooks/use-ozon-download.ts`

```typescript
/**
 * Ozon 下载功能 Hook
 */
'use client';

import { useState } from 'react';
import { useSession } from 'next-auth/react';
import { ozonApi } from '@/lib/api/ozon';
import { ozonDb } from '@/lib/db/ozon';
import { decryptCredential } from '@/lib/crypto';

export function useOzonDownload() {
  const { data: session } = useSession();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  /**
   * 执行下载任务
   */
  const download = async (input: {
    credentialId: string;
    articles: string[];
    field: 'offer_id' | 'sku' | 'vendor_code';
  }) => {
    if (!session?.user?.id) {
      setError('请先登录');
      return null;
    }

    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      // 1. 从数据库获取加密的凭证
      const credentialRecord = await ozonDb.getCredential(
        input.credentialId,
        session.user.id
      );

      if (!credentialRecord) {
        throw new Error('凭证不存在');
      }

      // 2. 解密凭证
      const credential = decryptCredential(credentialRecord.encryptedData);

      // 3. 创建任务记录
      const task = await ozonDb.createTask({
        userId: session.user.id,
        credentialId: input.credentialId,
        articles: input.articles,
        field: input.field,
      });

      // 4. 更新任务状态为处理中
      await ozonDb.updateTask(task.id, session.user.id, {
        status: 'processing',
        progress: 0,
        startedAt: new Date(),
      });

      // 5. 调用后端 API
      const response = await ozonApi.downloadImages({
        credential: credential,
        articles: input.articles,
        field: input.field,
        user_id: session.user.id,
      });

      // 6. 保存结果
      if (response.success && response.data) {
        await ozonDb.updateTask(task.id, session.user.id, {
          status: 'completed',
          progress: 100,
          result: response.data,
          totalArticles: response.data.total_articles,
          processedArticles: response.data.processed,
          totalImages: response.data.total_images,
          successImages: response.data.success_images,
          failedImages: response.data.failed_images,
          completedAt: new Date(),
        });

        setResult(response.data);
        return { task, result: response.data };
      } else {
        throw new Error(response.error || '下载失败');
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '未知错误';
      setError(errorMessage);
      return null;
    } finally {
      setIsLoading(false);
    }
  };

  return {
    download,
    isLoading,
    error,
    result,
  };
}
```

---

## 6. 核心代码实现

### 6.1 API 路由示例

**文件**: `src/app/api/ozon/credentials/route.ts`

```typescript
import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/core/auth';
import { ozonDb } from '@/lib/db/ozon';
import { encryptCredential } from '@/lib/crypto';
import { z } from 'zod';

const createCredentialSchema = z.object({
  name: z.string().min(1, '凭证名称不能为空'),
  client_id: z.string().min(1, 'Client ID 不能为空'),
  api_key: z.string().min(1, 'API Key 不能为空'),
});

// GET - 获取当前用户的凭证列表
export async function GET(req: NextRequest) {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const credentials = await ozonDb.getUserCredentials(session.user.id);

    // 不返回加密数据给前端
    const safeCredentials = credentials.map(({ encryptedData, ...rest }) => rest);

    return NextResponse.json(safeCredentials);
  } catch (error) {
    console.error('Get credentials error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}

// POST - 创建新凭证
export async function POST(req: NextRequest) {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await req.json();
    const validatedData = createCredentialSchema.parse(body);

    // 加密凭证
    const encryptedData = encryptCredential({
      client_id: validatedData.client_id,
      api_key: validatedData.api_key,
    });

    // 保存到数据库
    const credential = await ozonDb.createCredential({
      userId: session.user.id,
      name: validatedData.name,
      encryptedData,
    });

    // 不返回加密数据
    const { encryptedData: _, ...safeCredential } = credential;

    return NextResponse.json(safeCredential, { status: 201 });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json({ error: error.errors }, { status: 400 });
    }

    console.error('Create credential error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
```

### 6.2 页面组件示例

**文件**: `src/app/[locale]/(landing)/ozon/download/page.tsx`

```typescript
'use client';

import { useState } from 'react';
import { useSession } from 'next-auth/react';
import { useOzonDownload } from '@/app/hooks/use-ozon-download';
import { Button } from '@/shared/components/ui/button';
import { Textarea } from '@/shared/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card';

export default function OzonDownloadPage() {
  const { data: session } = useSession();
  const { download, isLoading, error, result } = useOzonDownload();

  const [credentialId, setCredialId] = useState('');
  const [articles, setArticles] = useState('');
  const [field, setField] = useState<'offer_id' | 'sku' | 'vendor_code'>('offer_id');

  // 模拟凭证列表 (实际应从数据库获取)
  const credentials = [
    { id: '1', name: '主店铺' },
    { id: '2', name: '备用店铺' },
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const articleList = articles
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean);

    if (articleList.length === 0) {
      alert('请输入至少一个货号');
      return;
    }

    await download({
      credentialId,
      articles: articleList,
      field,
    });
  };

  if (!session) {
    return <div>请先登录</div>;
  }

  return (
    <div className="container mx-auto py-8">
      <Card>
        <CardHeader>
          <CardTitle>下载 Ozon 商品图片</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">选择店铺</label>
              <Select value={credentialId} onValueChange={setCredialId}>
                <SelectTrigger>
                  <SelectValue placeholder="选择一个店铺" />
                </SelectTrigger>
                <SelectContent>
                  {credentials.map(cred => (
                    <SelectItem key={cred.id} value={cred.id}>
                      {cred.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">查询字段</label>
              <Select value={field} onValueChange={(v: any) => setField(v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="offer_id">Offer ID (推荐)</SelectItem>
                  <SelectItem value="sku">SKU</SelectItem>
                  <SelectItem value="vendor_code">Vendor Code</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">货号列表</label>
              <Textarea
                placeholder="每行输入一个货号&#10;例如：&#10;123456&#10;789012&#10;345678"
                className="min-h-[200px] font-mono"
                value={articles}
                onChange={(e) => setArticles(e.target.value)}
              />
              <p className="text-sm text-gray-500 mt-1">
                支持批量下载，每行一个货号
              </p>
            </div>

            {error && (
              <div className="text-sm text-red-600 bg-red-50 p-3 rounded">
                {error}
              </div>
            )}

            <Button type="submit" disabled={isLoading || !credentialId}>
              {isLoading ? '下载中...' : '开始下载'}
            </Button>
          </form>

          {result && (
            <div className="mt-8 p-4 bg-green-50 rounded-lg">
              <h3 className="font-semibold text-green-900 mb-2">下载完成</h3>
              <div className="text-sm text-green-700 space-y-1">
                <p>总货号数: {result.total_articles}</p>
                <p>成功处理: {result.processed}</p>
                <p>总图片数: {result.total_images}</p>
                <p>成功下载: {result.success_images}</p>
                {result.failed_images > 0 && (
                  <p className="text-red-600">失败: {result.failed_images}</p>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

---

## 7. 安全最佳实践

### 7.1 凭证安全

| 措施 | 实现 | 重要性 |
|------|------|--------|
| **加密存储** | 使用 AES 加密 `client_id` 和 `api_key` | ⭐⭐⭐⭐⭐ |
| **环境变量隔离** | 加密密钥存储在服务器环境变量，不暴露给前端 | ⭐⭐⭐⭐⭐ |
| **HTTPS 强制** | 生产环境强制使用 HTTPS | ⭐⭐⭐⭐⭐ |
| **不记录日志** | 后端不记录敏感凭证信息 | ⭐⭐⭐⭐ |
| **API Key 保护** | 后端 X-API-Key 使用强随机密钥 | ⭐⭐⭐⭐ |

### 7.2 数据隔离

```
R2 存储路径隔离:
{bucket}/
└── users/
    └── {user_id}/           # 按用户隔离
        └── ozon/
            └── {article}/    # 按货号分组
                ├── {article}_1.jpg
                └── {article}_2.jpg
```

### 7.3 权限控制

- ✅ 用户只能访问自己的凭证 (数据库级别隔离)
- ✅ 用户只能查看自己的任务 (数据库级别隔离)
- ✅ 凭证删除时级联删除相关任务
- ✅ 前端 API 路由验证用户身份

### 7.4 错误处理

```typescript
// 不暴露敏感错误信息给用户
try {
  const result = await ozonApi.downloadImages(request);
} catch (error) {
  // 生产环境记录详细错误到日志
  console.error('Download failed:', error);

  // 用户只看到友好提示
  showToast('下载失败，请稍后重试');
}
```

---

## 8. 常见问题

### Q1: 后端 API 返回 401 Unauthorized

**原因**: API Key 不匹配

**解决方案**:
1. 检查前端 `.env` 中的 `PYTHON_API_KEY`
2. 检查后端 `.env` 中的 `PYTHON_SERVICE_API_KEY`
3. 确保两者完全一致

### Q2: 下载返回 "Invalid Ozon credentials"

**原因**: Ozon API 凭证无效或过期

**解决方案**:
1. 验证用户输入的 `client_id` 和 `api_key` 是否正确
2. 检查 Ozon Seller API 权限是否启用
3. 提示用户重新配置凭证

### Q3: 图片上传到 R2 失败

**原因**: R2 配置错误或网络问题

**解决方案**:
1. 检查后端 R2 环境变量配置
2. 验证 R2 Bucket 是否存在
3. 检查网络连接和超时设置

### Q4: 前端无法连接到后端

**原因**: 跨域问题或端口不正确

**解决方案**:
1. 确认后端服务正在运行 (`http://localhost:8000`)
2. 检查 CORS 配置 (后端 FastAPI 需要配置 CORS)
3. 使用健康检查 API 测试连接

### Q5: 凭证解密失败

**原因**: 加密密钥不一致

**解决方案**:
1. 确保前端和服务器使用相同的 `CREDENTIAL_ENCRYPTION_KEY`
2. 检查环境变量是否正确加载
3. 重新加密存储凭证

---

## 9. 部署清单

### 9.1 前端部署 (Vercel/Netlify)

- [ ] 设置环境变量 (`.env` 所有配置)
- [ ] 配置数据库连接 (PostgreSQL)
- [ ] 执行数据库迁移
- [ ] 验证认证系统工作正常

### 9.2 后端部署 (Docker)

- [ ] 构建 Docker 镜像
- [ ] 设置环境变量 (R2 配置、API Key)
- [ ] 配置 CORS 允许前端域名
- [ ] 健康检查测试

### 9.3 R2 配置

- [ ] 创建 Bucket
- [ ] 配置公共访问 (如果需要)
- [ ] 设置自定义域名 (可选)
- [ ] 配置 CORS 规则

---

## 10. 总结

这个架构的核心优势：

✅ **职责明确**: 前端管数据，后端干重活
✅ **无状态后端**: 易于扩展和部署
✅ **数据安全**: 凭证加密存储，R2 路径隔离
✅ **开发效率**: 前端使用成熟框架 (ShipAny)
✅ **性能优化**: 并发下载、流式上传、不写磁盘

按照本文档，前端开发者可以快速集成 Ozon 图片下载功能，无需深入了解 Python 后端实现细节。

---

**文档版本**: 2.0.0
**最后更新**: 2026-01-19
**适用架构**: Next.js (ShipAny) + Python FastAPI (无状态)
