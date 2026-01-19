# 前端集成指南 - Ozon 图片下载系统

**版本**: 2.0.0
**最后更新**: 2026-01-19
**架构原则**: 后端专注计算/IO密集型任务，前端负责数据管理和业务逻辑

---

## 📋 架构概述

### 设计理念
- **后端（Python FastAPI）**: 无状态服务，只处理重活（API调用、图片下载、文件上传）
- **前端（Next.js）**: 全栈应用，管理所有数据（用户、凭证、任务记录）和业务逻辑

### 系统架构图
```
┌──────────────────────────────────────────────────────┐
│              Next.js 前端 (数据层)                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ 用户认证  │  │ 凭证管理  │  │ 任务记录 & 结果   │   │
│  │ (Supabase)│  │ (加密存储) │  │ (数据库存储)      │   │
│  └──────────┘  └──────────┘  └──────────────────┘   │
└─────────────────────┬────────────────────────────────┘
                      │ HTTP API (X-API-Key)
                      ▼
┌──────────────────────────────────────────────────────┐
│         Python 后端 (计算层 - 无状态)                  │
│  POST /api/v1/ozon/download                          │
│   • 调用 Ozon API 查找产品                            │
│   • 并发下载图片                                       │
│   • 流式上传到 R2                                      │
│   • 返回结果（不存储）                                 │
└─────────────────────┬────────────────────────────────┘
                      │
                      ▼
              Cloudflare R2 存储
```

---

## 目录

1. [技术栈](#1-技术栈)
2. [环境配置](#2-环境配置)
3. [数据库设计](#3-数据库设计)
4. [用户认证](#4-用户认证)
5. [API 客户端](#5-api-客户端)
6. [凭证管理](#6-凭证管理)
7. [下载功能](#7-下载功能)
8. [状态管理](#8-状态管理)
9. [页面实现](#9-页面实现)
10. [集成步骤](#10-集成步骤)

---

## 1. 技术栈

### 前端技术栈
| 组件 | 技术 | 说明 |
|------|------|------|
| 框架 | Next.js 14+ (App Router) | React 全栈框架 |
| 语言 | TypeScript | 类型安全 |
| 数据库 | Supabase (PostgreSQL) | 用户数据、凭证、任务记录 |
| 认证 | Supabase Auth | 基于JWT的用户认证 |
| ORM | Prisma / Drizzle | 类型安全的数据库客户端 |
| 样式 | Tailwind CSS | 实用优先的CSS框架 |
| 组件 | shadcn/ui | 高质量React组件库 |
| 状态 | Zustand | 轻量级状态管理 |
| 表单 | React Hook Form + Zod | 表单验证 |
| 加密 | crypto-js | 凭证加密存储 |

### 后端技术栈
| 组件 | 技术 | 说明 |
|------|------|------|
| 框架 | FastAPI | 高性能异步Python框架 |
| 存储 | Cloudflare R2 | 对象存储（图片） |
| 认证 | API Key (X-API-Key) | 服务间认证 |

---

## 2. 环境配置

### 2.1 环境变量

创建 `.env.local` 文件：

```env
# Supabase 配置
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Python 后端 API（无状态服务）
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_API_KEY=your-shared-secret

# 凭证加密密钥（32字符）
NEXT_PUBLIC_ENCRYPTION_KEY=your-32-char-encryption-key-here

# 应用配置
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

### 2.2 安装依赖

```bash
# 创建 Next.js 项目
npx create-next-app@latest frontend --typescript --tailwind --app

cd frontend

# 安装核心依赖
npm install @supabase/supabase-js @supabase/auth-helpers-nextjs
npm install zustand react-hook-form @hookform/resolvers zod
npm install crypto-js

# 安装 Prisma（如果使用 Prisma）
npm install prisma @prisma/client

# 安装 shadcn/ui 组件
npx shadcn-ui@latest init
npx shadcn-ui@latest add button card input label textarea
npx shadcn-ui@latest add table dialog form select
npx shadcn-ui@latest add alert badge progress toast

# 安装开发依赖
npm install -D @types/crypto-js
```

---

## 3. 数据库设计

> **注意**: 所有业务数据存储在前端数据库，后端完全不存储任何业务数据。

### 3.1 Prisma Schema

```prisma
// prisma/schema.prisma

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

// 用户表（Supabase auth.users 的镜像）
model User {
  id            String    @id @default(cuid())
  supabaseId    String    @unique
  email         String    @unique
  name          String?
  createdAt     DateTime  @default(now())
  updatedAt     DateTime  @updatedAt

  // 关联
  ozonCredentials OzonCredential[]
  ozonTasks       OzonTask[]
}

// Ozon 凭证表（加密存储）
model OzonCredential {
  id          String   @id @default(cuid())
  userId      String
  name        String   // 用户自定义名称，如 "我的主店铺"
  encryptedData String // AES 加密的 {client_id, api_key}

  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt

  // 关联
  user        User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  tasks       OzonTask[]

  @@index([userId])
}

// Ozon 下载任务表
model OzonTask {
  id          String   @id @default(cuid())
  userId      String
  credentialId String

  // 请求参数
  articles    Json     // 货号列表
  field       String   @default("offer_id") // offer_id | sku | vendor_code

  // 状态
  status      String   // pending | processing | completed | failed
  progress    Float    @default(0) // 0-100

  // 结果
  result      Json?    // 完整的 API 响应结果
  errorMessage String?  // 错误信息

  // 统计
  totalArticles   Int?
  processedArticles Int?
  totalImages     Int?
  successImages   Int?
  failedImages    Int?

  startedAt   DateTime?
  completedAt DateTime?
  createdAt   DateTime  @default(now())
  updatedAt   DateTime  @updatedAt

  // 关联
  user        User            @relation(fields: [userId], references: [id], onDelete: Cascade)
  credential  OzonCredential  @relation(fields: [credentialId], references: [id], onDelete: Cascade)

  @@index([userId])
  @@index([status])
}

// 系统配置表（可选，用于存储全局配置）
model SystemConfig {
  id          String   @id @default(cuid())
  key         String   @unique
  value       Json
  description String?
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt
}
```

### 4.2 数据库迁移

```bash
# 初始化 Prisma
npx prisma init

# 生成迁移
npx prisma migrate dev --name init

# 生成 Prisma Client
npx prisma generate

# 打开 Prisma Studio 查看
npx prisma studio
```

### 4.3 Supabase 表创建

```sql
-- 在 Supabase SQL Editor 中执行

-- 启用 Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE ozon_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE ozon_tasks ENABLE ROW LEVEL SECURITY;

-- 用户只能访问自己的数据
CREATE POLICY "Users can view own data" ON users
  FOR SELECT USING (auth.uid()::text = supabase_id);

CREATE POLICY "Users can view own credentials" ON ozon_credentials
  FOR SELECT USING (auth.uid()::text = (SELECT supabaseId FROM users WHERE id = userId));

CREATE POLICY "Users can insert own credentials" ON ozon_credentials
  FOR INSERT WITH CHECK (auth.uid()::text = (SELECT supabaseId FROM users WHERE id = userId));

CREATE POLICY "Users can update own credentials" ON ozon_credentials
  FOR UPDATE USING (auth.uid()::text = (SELECT supabaseId FROM users WHERE id = userId));

CREATE POLICY "Users can delete own credentials" ON ozon_credentials
  FOR DELETE USING (auth.uid()::text = (SELECT supabaseId FROM users WHERE id = userId));

CREATE POLICY "Users can view own tasks" ON ozon_tasks
  FOR SELECT USING (auth.uid()::text = (SELECT supabaseId FROM users WHERE id = userId));

CREATE POLICY "Users can insert own tasks" ON ozon_tasks
  FOR INSERT WITH CHECK (auth.uid()::text = (SELECT supabaseId FROM users WHERE id = userId));

CREATE POLICY "Users can update own tasks" ON ozon_tasks
  FOR UPDATE USING (auth.uid()::text = (SELECT supabaseId FROM users WHERE id = userId));

CREATE POLICY "Users can delete own tasks" ON ozon_tasks
  FOR DELETE USING (auth.uid()::text = (SELECT supabaseId FROM users WHERE id = userId));
```

---

## 5. 用户认证

### 5.1 Supabase 客户端配置

```typescript
// lib/supabase/client.ts
// 浏览器端客户端

import { createClientComponentClient } from '@supabase/auth-helpers-nextjs';
import type { Database } from '@/types/database';

export const createClient = () => {
  return createClientComponentClient<Database>();
};

// 使用示例
// const supabase = createClient();
// const { data: { user } } = await supabase.auth.getUser();
```

```typescript
// lib/supabase/server.ts
// 服务端客户端

import { createServerComponentClient } from '@supabase/auth-helpers-nextjs';
import { cookies } from 'next/headers';
import type { Database } from '@/types/database';

export const createServerClient = () => {
  const cookieStore = cookies();
  return createServerComponentClient<Database>({ cookies: cookieStore });
};
```

```typescript
// lib/supabase/middleware.ts
// 路由保护中间件

import { createMiddlewareClient } from '@supabase/auth-helpers-nextjs';
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export async function middleware(req: NextRequest) {
  const res = NextResponse.next();
  const supabase = createMiddlewareClient({ req, res });

  const {
    data: { session },
  } = await supabase.auth.getSession();

  // 未登录用户重定向到登录页
  if (!session && req.nextUrl.pathname.startsWith('/dashboard')) {
    return NextResponse.redirect(new URL('/login', req.url));
  }

  // 已登录用户访问登录页重定向到 dashboard
  if (session && req.nextUrl.pathname === '/login') {
    return NextResponse.redirect(new URL('/dashboard', req.url));
  }

  return res;
}

export const config = {
  matcher: ['/dashboard/:path*', '/login'],
};
```

### 5.2 认证 Hook

```typescript
// hooks/use-auth.ts

import { useEffect, useState } from 'react';
import { User } from '@supabase/supabase-js';
import { createClient } from '@/lib/supabase/client';
import { useRouter } from 'next/navigation';

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const supabase = createClient();

  useEffect(() => {
    // 获取当前用户
    const getUser = async () => {
      const { data: { user } } = await supabase.auth.getUser();
      setUser(user);
      setLoading(false);
    };

    getUser();

    // 监听认证状态变化
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event, session) => {
        if (session?.user) {
          setUser(session.user);
        } else {
          setUser(null);
        }
        setLoading(false);
      }
    );

    return () => subscription.unsubscribe();
  }, [supabase.auth]);

  const signOut = async () => {
    await supabase.auth.signOut();
    router.push('/login');
  };

  return { user, loading, signOut };
}
```

### 5.3 登录页面

```typescript
// app/(auth)/login/page.tsx

'use client';

import { useState } from 'react';
import { createClient } from '@/lib/supabase/client';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2 } from 'lucide-react';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const supabase = createClient();

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error) throw error;

      // 登录成功，确保用户在本地数据库中存在
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        // 调用 API 同步用户到本地数据库
        await fetch('/api/auth/sync-user', {
          method: 'POST',
        });
      }

      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSignUp = async () => {
    setLoading(true);
    setError(null);

    try {
      const { error } = await supabase.auth.signUp({
        email,
        password,
      });

      if (error) throw error;

      setError('请检查邮箱以确认注册');
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>登录</CardTitle>
          <CardDescription>输入您的邮箱和密码登录</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSignIn} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">邮箱</Label>
              <Input
                id="email"
                type="email"
                placeholder="your@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">密码</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="flex gap-2">
              <Button type="submit" disabled={loading} className="flex-1">
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                登录
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={loading}
                onClick={handleSignUp}
              >
                注册
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
```

### 5.4 用户同步 API

```typescript
// app/api/auth/sync-user/route.ts

import { createRouteHandlerClient } from '@supabase/auth-helpers-nextjs';
import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export async function POST() {
  const supabase = createRouteHandlerClient({ cookies });

  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  // 同步用户到本地数据库
  const dbUser = await prisma.user.upsert({
    where: { supabaseId: user.id },
    update: {
      email: user.email!,
      name: user.user_metadata.name,
    },
    create: {
      supabaseId: user.id,
      email: user.email!,
      name: user.user_metadata.name,
    },
  });

  return NextResponse.json({ user: dbUser });
}
```

---

## 6. API 客户端

### 6.1 类型定义

```typescript
// types/ozon.ts

export interface OzonCredential {
  client_id: string;
  api_key: string;
}

export interface OzonDownloadRequest {
  credential: OzonCredential;
  articles: string[];
  field?: 'offer_id' | 'sku' | 'vendor_code';
  user_id: string;
}

export interface OzonDownloadResponse {
  success: boolean;
  data?: OzonDownloadResult;
  error?: string;
}

export interface OzonDownloadResult {
  total_articles: number;
  processed: number;
  total_images: number;
  success_images: number;
  failed_images: number;
  items: OzonDownloadItem[];
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

// Prisma 模型类型
export interface DbOzonCredential {
  id: string;
  userId: string;
  name: string;
  encryptedData: string;
  createdAt: Date;
  updatedAt: Date;
}

export interface DbOzonTask {
  id: string;
  userId: string;
  credentialId: string;
  articles: unknown;
  field: string;
  status: string;
  progress: number;
  result: unknown | null;
  errorMessage: string | null;
  totalArticles: number | null;
  processedArticles: number | null;
  totalImages: number | null;
  successImages: number | null;
  failedImages: number | null;
  startedAt: Date | null;
  completedAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
}
```

### 6.2 加密工具

```typescript
// lib/crypto.ts

import CryptoJS from 'crypto-js';

const ENCRYPTION_KEY = process.env.NEXT_PUBLIC_ENCRYPTION_KEY;

if (!ENCRYPTION_KEY) {
  throw new Error('NEXT_PUBLIC_ENCRYPTION_KEY is not set');
}

export interface OzonCredential {
  client_id: string;
  api_key: string;
}

export function encryptCredential(credential: OzonCredential): string {
  const plaintext = JSON.stringify(credential);
  return CryptoJS.AES.encrypt(plaintext, ENCRYPTION_KEY).toString();
}

export function decryptCredential(ciphertext: string): OzonCredential {
  const bytes = CryptoJS.AES.decrypt(ciphertext, ENCRYPTION_KEY);
  const plaintext = bytes.toString(CryptoJS.enc.Utf8);
  return JSON.parse(plaintext);
}
```

### 6.3 Ozon API 客户端

```typescript
// lib/api/ozon.ts

import type {
  OzonDownloadRequest,
  OzonDownloadResponse,
} from '@/types/ozon';

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

if (!API_URL || !API_KEY) {
  throw new Error('API_URL or API_KEY is not configured');
}

export async function downloadOzonImages(
  request: OzonDownloadRequest
): Promise<OzonDownloadResponse> {
  try {
    const response = await fetch(`${API_URL}/api/v1/ozon/download`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY,
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`API Error ${response.status}: ${error}`);
    }

    return response.json();
  } catch (error) {
    console.error('Ozon download error:', error);
    throw error;
  }
}

export async function checkApiHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/api/v1/health`, {
      headers: {
        'X-API-Key': API_KEY,
      },
    });
    return response.ok;
  } catch {
    return false;
  }
}
```

---

## 7. 状态管理

### 7.1 Zustand Store

```typescript
// stores/ozon-store.ts

import { create } from 'zustand';
import type { DbOzonCredential, DbOzonTask } from '@/types/ozon';

interface OzonState {
  // 凭证
  credentials: DbOzonCredential[];
  selectedCredentialId: string | null;
  setCredentials: (credentials: DbOzonCredential[]) => void;
  setSelectedCredentialId: (id: string | null) => void;

  // 任务
  tasks: DbOzonTask[];
  activeTaskId: string | null;
  setTasks: (tasks: DbOzonTask[]) => void;
  setActiveTaskId: (id: string | null) => void;
  updateTask: (id: string, updates: Partial<DbOzonTask>) => void;

  // UI 状态
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
  error: string | null;
  setError: (error: string | null) => void;
}

export const useOzonStore = create<OzonState>((set) => ({
  // 初始状态
  credentials: [],
  selectedCredentialId: null,
  tasks: [],
  activeTaskId: null,
  isLoading: false,
  error: null,

  // 凭证操作
  setCredentials: (credentials) => set({ credentials }),
  setSelectedCredentialId: (id) => set({ selectedCredentialId: id }),

  // 任务操作
  setTasks: (tasks) => set({ tasks }),
  setActiveTaskId: (id) => set({ activeTaskId: id }),
  updateTask: (id, updates) =>
    set((state) => ({
      tasks: state.tasks.map((t) =>
        t.id === id ? { ...t, ...updates } : t
      ),
    })),

  // UI 状态
  setIsLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
}));
```

---

## 8. 页面实现

### 8.1 Dashboard 布局

```typescript
// app/(dashboard)/layout.tsx

import { createServerClient } from '@/lib/supabase/server';
import { redirect } from 'next/navigation';
import { Sidebar } from '@/components/dashboard/sidebar';
import { Header } from '@/components/dashboard/header';

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = createServerClient();

  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    redirect('/login');
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header user={session.user} />
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
```

### 8.2 Dashboard 首页

```typescript
// app/(dashboard)/dashboard/page.tsx

import { createServerClient } from '@/lib/supabase/server';
import { prisma } from '@/lib/prisma';
import { StatsCard } from '@/components/dashboard/stats-card';
import { Package, Key, CheckCircle, AlertCircle } from 'lucide-react';

export default async function DashboardPage() {
  const supabase = createServerClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return null;
  }

  // 获取本地用户 ID
  const dbUser = await prisma.user.findUnique({
    where: { supabaseId: user.id },
  });

  if (!dbUser) {
    return null;
  }

  // 获取统计数据
  const [credentialCount, taskCount, completedTasks, failedTasks] =
    await Promise.all([
      prisma.ozonCredential.count({ where: { userId: dbUser.id } }),
      prisma.ozonTask.count({ where: { userId: dbUser.id } }),
      prisma.ozonTask.count({
        where: { userId: dbUser.id, status: 'completed' },
      }),
      prisma.ozonTask.count({
        where: { userId: dbUser.id, status: 'failed' },
      }),
    ]);

  // 最近任务
  const recentTasks = await prisma.ozonTask.findMany({
    where: { userId: dbUser.id },
    include: { credential: true },
    orderBy: { createdAt: 'desc' },
    take: 5,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <p className="text-gray-500 mt-1">欢迎使用 Ozon 图片下载工具</p>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatsCard
          title="已配置店铺"
          value={credentialCount}
          icon={<Key className="h-6 w-6" />}
          href="/dashboard/ozon/credentials"
        />
        <StatsCard
          title="总任务数"
          value={taskCount}
          icon={<Package className="h-6 w-6" />}
          href="/dashboard/ozon/tasks"
        />
        <StatsCard
          title="成功任务"
          value={completedTasks}
          icon={<CheckCircle className="h-6 w-6 text-green-600" />}
          href="/dashboard/ozon/tasks?status=completed"
        />
        <StatsCard
          title="失败任务"
          value={failedTasks}
          icon={<AlertCircle className="h-6 w-6 text-red-600" />}
          href="/dashboard/ozon/tasks?status=failed"
        />
      </div>

      {/* 最近任务 */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold mb-4">最近任务</h2>
        {recentTasks.length === 0 ? (
          <p className="text-gray-500 text-center py-8">
            还没有任务，开始创建第一个下载任务吧！
          </p>
        ) : (
          <div className="space-y-3">
            {recentTasks.map((task) => (
              <div
                key={task.id}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
              >
                <div>
                  <p className="font-medium">{task.credential.name}</p>
                  <p className="text-sm text-gray-500">
                    {task.totalArticles || 0} 个货号 · {task.createdAt.toLocaleString()}
                  </p>
                </div>
                <span
                  className={`px-3 py-1 rounded-full text-sm ${
                    task.status === 'completed'
                      ? 'bg-green-100 text-green-800'
                      : task.status === 'failed'
                      ? 'bg-red-100 text-red-800'
                      : 'bg-blue-100 text-blue-800'
                  }`}
                >
                  {task.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

### 8.3 凭证管理页面

```typescript
// app/(dashboard)/ozon/credentials/page.tsx

'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/hooks/use-auth';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Plus, Edit, Trash2, Key } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { CredentialForm } from '@/components/ozon/credential-form';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useOzonStore } from '@/stores/ozon-store';
import type { DbOzonCredential } from '@/types/ozon';
import { createClient } from '@/lib/supabase/client';
import { decryptCredential } from '@/lib/crypto';

export default function CredentialsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const supabase = createClient();
  const { credentials, setCredentials } = useOzonStore();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingCredential, setEditingCredential] =
    useState<DbOzonCredential | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    if (user) fetchCredentials();
  }, [user]);

  const fetchCredentials = async () => {
    const response = await fetch('/api/ozon/credentials');
    if (response.ok) {
      const data = await response.json();
      setCredentials(data);
    }
  };

  const handleEdit = (credential: DbOzonCredential) => {
    setEditingCredential(credential);
    setDialogOpen(true);
  };

  const handleDelete = async () => {
    if (!deletingId) return;

    const response = await fetch(`/api/ozon/credentials/${deletingId}`, {
      method: 'DELETE',
    });

    if (response.ok) {
      setCredentials(credentials.filter((c) => c.id !== deletingId));
      setDeleteDialogOpen(false);
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Ozon 店铺管理</h1>
          <p className="text-gray-500 mt-1">管理您的 Ozon API 凭证</p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button onClick={() => setEditingCredential(null)}>
              <Plus className="mr-2 h-4 w-4" />
              添加店铺
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>
                {editingCredential ? '编辑店铺' : '添加店铺'}
              </DialogTitle>
            </DialogHeader>
            <CredentialForm
              credential={editingCredential}
              onSuccess={() => {
                setDialogOpen(false);
                setEditingCredential(null);
                fetchCredentials();
              }}
            />
          </DialogContent>
        </Dialog>
      </div>

      {credentials.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Key className="h-12 w-12 text-gray-400 mb-4" />
            <p className="text-gray-500 mb-4">还没有配置任何店铺</p>
            <Button onClick={() => setDialogOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              添加第一个店铺
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {credentials.map((credential) => (
            <Card key={credential.id} className="hover:shadow-lg transition">
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="flex items-center">
                  <Key className="mr-2 h-5 w-5 text-blue-600" />
                  {credential.name}
                </CardTitle>
                <div className="flex gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleEdit(credential)}
                  >
                    <Edit className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setDeletingId(credential.id);
                      setDeleteDialogOpen(true);
                    }}
                  >
                    <Trash2 className="h-4 w-4 text-red-600" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-gray-500">
                  创建于 {new Date(credential.createdAt).toLocaleDateString()}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              删除后无法恢复，确定要删除这个店铺配置吗？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
```

### 8.4 下载任务页面

```typescript
// app/(dashboard)/ozon/download/page.tsx

'use client';

import { useState } from 'react';
import { useAuth } from '@/hooks/use-auth';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Download } from 'lucide-react';
import { DownloadForm } from '@/components/ozon/download-form';
import { useOzonStore } from '@/stores/ozon-store';
import { useOzonDownload } from '@/hooks/use-ozon-download';
import { Progress } from '@/components/ui/progress';
import { CheckCircle, XCircle, AlertCircle } from 'lucide-react';

export default function DownloadPage() {
  const { user } = useAuth();
  const router = useRouter();
  const { credentials, selectedCredentialId, setSelectedCredentialId } =
    useOzonStore();
  const { download, isLoading, error, result } = useOzonDownload();

  const handleDownload = async (data: {
    credentialId: string;
    articles: string[];
    field: 'offer_id' | 'sku' | 'vendor_code';
  }) => {
    await download(data);

    // 下载完成后跳转到任务列表
    if (result) {
      router.push('/dashboard/ozon/tasks');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">下载 Ozon 图片</h1>
        <p className="text-gray-500 mt-1">批量下载 Ozon 商品图片</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 下载表单 */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <Download className="mr-2 h-5 w-5" />
                创建下载任务
              </CardTitle>
            </CardHeader>
            <CardContent>
              {credentials.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-gray-500 mb-4">
                    请先添加 Ozon 店铺凭证
                  </p>
                  <Button onClick={() => router.push('/dashboard/ozon/credentials')}>
                    添加店铺
                  </Button>
                </div>
              ) : (
                <DownloadForm
                  credentials={credentials}
                  selectedCredentialId={selectedCredentialId}
                  onCredentialChange={setSelectedCredentialId}
                  onSubmit={handleDownload}
                  isLoading={isLoading}
                  error={error}
                />
              )}
            </CardContent>
          </Card>
        </div>

        {/* 结果预览 */}
        <div>
          <Card>
            <CardHeader>
              <CardTitle>下载结果</CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="space-y-4">
                  <p className="text-sm text-gray-500">正在处理...</p>
                  <Progress value={66} />
                </div>
              ) : result ? (
                <div className="space-y-4">
                  <div className="flex items-center text-green-600">
                    <CheckCircle className="mr-2 h-5 w-5" />
                    <span>下载完成</span>
                  </div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span>总货号数:</span>
                      <span className="font-medium">
                        {result.total_articles}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>总图片数:</span>
                      <span className="font-medium">
                        {result.total_images}
                      </span>
                    </div>
                    <div className="flex justify-between text-green-600">
                      <span>成功:</span>
                      <span className="font-medium">
                        {result.success_images}
                      </span>
                    </div>
                    {result.failed_images > 0 && (
                      <div className="flex justify-between text-red-600">
                        <span>失败:</span>
                        <span className="font-medium">
                          {result.failed_images}
                        </span>
                      </div>
                    )}
                  </div>
                  <Button
                    className="w-full"
                    onClick={() => router.push('/dashboard/ozon/tasks')}
                  >
                    查看详情
                  </Button>
                </div>
              ) : null}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
```

---

## 9. 组件实现

### 9.1 凭证表单组件

```typescript
// components/ozon/credential-form.tsx

'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Loader2, Eye, EyeOff } from 'lucide-react';
import { encryptCredential, decryptCredential } from '@/lib/crypto';
import type { DbOzonCredential } from '@/types/ozon';
import { createClient } from '@/lib/supabase/client';

const credentialSchema = z.object({
  name: z.string().min(1, '店铺名称不能为空'),
  client_id: z.string().min(1, 'Client ID 不能为空'),
  api_key: z.string().min(1, 'API Key 不能为空'),
});

type CredentialFormData = z.infer<typeof credentialSchema>;

interface CredentialFormProps {
  credential?: DbOzonCredential | null;
  onSuccess?: () => void;
}

export function CredentialForm({ credential, onSuccess }: CredentialFormProps) {
  const [loading, setLoading] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const supabase = createClient();

  const form = useForm<CredentialFormData>({
    resolver: zodResolver(credentialSchema),
    defaultValues: credential
      ? {
          name: credential.name,
          client_id: '',
          api_key: '',
        }
      : {
          name: '',
          client_id: '',
          api_key: '',
        },
  });

  const onSubmit = async (data: CredentialFormData) => {
    setLoading(true);
    setError(null);

    try {
      const {
        data: { user },
      } = await supabase.auth.getUser();

      if (!user) throw new Error('未登录');

      // 加密凭证
      const encryptedData = encryptCredential({
        client_id: data.client_id,
        api_key: data.api_key,
      });

      const body = {
        name: data.name,
        encryptedData,
      };

      const url = credential
        ? `/api/ozon/credentials/${credential.id}`
        : '/api/ozon/credentials';

      const response = await fetch(url, {
        method: credential ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || '操作失败');
      }

      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>店铺名称</FormLabel>
              <FormControl>
                <Input
                  placeholder="例如：我的主店铺"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="client_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Client ID</FormLabel>
              <FormControl>
                <Input placeholder="输入 Ozon Client ID" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="api_key"
          render={({ field }) => (
            <FormItem>
              <FormLabel>API Key</FormLabel>
              <FormControl>
                <div className="relative">
                  <Input
                    type={showApiKey ? 'text' : 'password'}
                    placeholder="输入 Ozon API Key"
                    {...field}
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-3 top-1/2 -translate-y-1/2"
                  >
                    {showApiKey ? (
                      <EyeOff className="h-4 w-4 text-gray-500" />
                    ) : (
                      <Eye className="h-4 w-4 text-gray-500" />
                    )}
                  </button>
                </div>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {error && (
          <div className="text-sm text-red-600 bg-red-50 p-3 rounded">
            {error}
          </div>
        )}

        <div className="flex gap-2">
          <Button type="submit" disabled={loading} className="flex-1">
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                保存中...
              </>
            ) : (
              <>
                {credential ? '更新' : '添加'}
              </>
            )}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => form.reset()}
          >
            重置
          </Button>
        </div>
      </form>
    </Form>
  );
}
```

### 9.2 下载表单组件

```typescript
// components/ozon/download-form.tsx

'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Loader2, Upload } from 'lucide-react';
import type { DbOzonCredential } from '@/types/ozon';

const downloadSchema = z.object({
  credentialId: z.string().min(1, '请选择店铺'),
  articles: z.string().min(1, '请输入货号'),
  field: z.enum(['offer_id', 'sku', 'vendor_code']),
});

type DownloadFormData = z.infer<typeof downloadSchema>;

interface DownloadFormProps {
  credentials: DbOzonCredential[];
  selectedCredentialId: string | null;
  onCredentialChange: (id: string) => void;
  onSubmit: (data: {
    credentialId: string;
    articles: string[];
    field: 'offer_id' | 'sku' | 'vendor_code';
  }) => void;
  isLoading: boolean;
  error?: string | null;
}

export function DownloadForm({
  credentials,
  selectedCredentialId,
  onCredentialChange,
  onSubmit,
  isLoading,
  error,
}: DownloadFormProps) {
  const form = useForm<DownloadFormData>({
    resolver: zodResolver(downloadSchema),
    defaultValues: {
      credentialId: selectedCredentialId || '',
      articles: '',
      field: 'offer_id',
    },
  });

  const handleSubmit = (data: DownloadFormData) => {
    const articles = data.articles
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);

    onSubmit({
      credentialId: data.credentialId,
      articles,
      field: data.field,
    });
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
        <FormField
          control={form.control}
          name="credentialId"
          render={({ field }) => (
            <FormItem>
              <FormLabel>选择店铺</FormLabel>
              <Select
                onValueChange={(value) => {
                  field.onChange(value);
                  onCredentialChange(value);
                }}
                defaultValue={field.value}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="选择一个店铺" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {credentials.map((cred) => (
                    <SelectItem key={cred.id} value={cred.id}>
                      {cred.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="field"
          render={({ field }) => (
            <FormItem>
              <FormLabel>查询字段</FormLabel>
              <Select
                onValueChange={field.onChange}
                defaultValue={field.value}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="offer_id">Offer ID (推荐)</SelectItem>
                  <SelectItem value="sku">SKU</SelectItem>
                  <SelectItem value="vendor_code">Vendor Code</SelectItem>
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="articles"
          render={({ field }) => (
            <FormItem>
              <FormLabel>货号列表</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="输入货号，每行一个&#10;例如：&#10;123456&#10;789012&#10;345678"
                  className="min-h-[200px] font-mono"
                  {...field}
                />
              </FormControl>
              <p className="text-sm text-gray-500">
                每行一个货号，支持批量下载
              </p>
              <FormMessage />
            </FormItem>
          )}
        />

        {error && (
          <div className="text-sm text-red-600 bg-red-50 p-3 rounded">
            {error}
          </div>
        )}

        <Button type="submit" disabled={isLoading} className="w-full">
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              下载中...
            </>
          ) : (
            <>
              <Upload className="mr-2 h-4 w-4" />
              开始下载
            </>
          )}
        </Button>
      </form>
    </Form>
  );
}
```

### 9.3 下载 Hook

```typescript
// hooks/use-ozon-download.ts

'use client';

import { useState } from 'react';
import { useAuth } from './use-auth';
import { downloadOzonImages } from '@/lib/api/ozon';
import { decryptCredential } from '@/lib/crypto';
import type { OzonDownloadResult } from '@/types/ozon';
import { createClient } from '@/lib/supabase/client';

export function useOzonDownload() {
  const { user } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OzonDownloadResult | null>(null);
  const supabase = createClient();

  const download = async (data: {
    credentialId: string;
    articles: string[];
    field: 'offer_id' | 'sku' | 'vendor_code';
  }) => {
    if (!user) {
      setError('请先登录');
      return;
    }

    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      // 1. 获取加密的凭证
      const credResponse = await fetch(
        `/api/ozon/credentials/${data.credentialId}`
      );

      if (!credResponse.ok) {
        throw new Error('获取凭证失败');
      }

      const credential = await credResponse.json();

      // 2. 解密凭证
      const decryptedCred = decryptCredential(credential.encryptedData);

      // 3. 调用后端 API
      const response = await downloadOzonImages({
        credential: decryptedCred,
        articles: data.articles,
        field: data.field,
        user_id: user.id,
      });

      if (!response.success || !response.data) {
        throw new Error(response.error || '下载失败');
      }

      // 4. 保存任务到数据库
      const taskResponse = await fetch('/api/ozon/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          credentialId: data.credentialId,
          articles: data.articles,
          field: data.field,
          status: 'completed',
          progress: 100,
          result: response.data,
          totalArticles: response.data.total_articles,
          processedArticles: response.data.processed,
          totalImages: response.data.total_images,
          successImages: response.data.success_images,
          failedImages: response.data.failed_images,
          startedAt: new Date().toISOString(),
          completedAt: new Date().toISOString(),
        }),
      });

      if (!taskResponse.ok) {
        console.error('保存任务失败:', await taskResponse.text());
      }

      setResult(response.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '下载失败');
    } finally {
      setIsLoading(false);
    }
  };

  return { download, isLoading, error, result };
}
```

---

## 10. 集成步骤

### 10.1 项目初始化

```bash
# 1. 创建 Next.js 项目
npx create-next-app@latest frontend --typescript --tailwind --app
cd frontend

# 2. 安装依赖
npm install @supabase/supabase-js @supabase/auth-helpers-nextjs
npm install zustand react-hook-form @hookform/resolvers zod
npm install crypto-js prisma @prisma/client
npm install -D @types/crypto-js

# 3. 配置 shadcn/ui
npx shadcn-ui@latest init
npx shadcn-ui@latest add button card input label textarea
npx shadcn-ui@latest add table dialog form select alert
npx shadcn-ui@latest add badge progress toast

# 4. 创建环境变量文件
cp .env.example .env.local
# 填写 Supabase 和后端 API 配置
```

### 10.2 数据库配置

```bash
# 1. 配置 Prisma
npx prisma init

# 2. 复制 schema 到 prisma/schema.prisma
# (使用上面的 Prisma Schema)

# 3. 设置 DATABASE_URL
# .env.local
DATABASE_URL="postgresql://user:password@host:5432/database"

# 4. 生成并运行迁移
npx prisma migrate dev --name init

# 5. 生成 Prisma Client
npx prisma generate
```

### 10.3 创建 API Routes

```typescript
// app/api/ozon/credentials/route.ts

import { createRouteHandlerClient } from '@supabase/auth-helpers-nextjs';
import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

// GET - 获取所有凭证
export async function GET() {
  const supabase = createRouteHandlerClient({ cookies });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const dbUser = await prisma.user.findUnique({
    where: { supabaseId: user.id },
  });

  if (!dbUser) {
    return NextResponse.json({ error: 'User not found' }, { status: 404 });
  }

  const credentials = await prisma.ozonCredential.findMany({
    where: { userId: dbUser.id },
    orderBy: { createdAt: 'desc' },
  });

  return NextResponse.json(credentials);
}

// POST - 创建凭证
export async function POST(request: Request) {
  const supabase = createRouteHandlerClient({ cookies });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const body = await request.json();
  const { name, encryptedData } = body;

  const dbUser = await prisma.user.findUnique({
    where: { supabaseId: user.id },
  });

  if (!dbUser) {
    return NextResponse.json({ error: 'User not found' }, { status: 404 });
  }

  const credential = await prisma.ozonCredential.create({
    data: {
      userId: dbUser.id,
      name,
      encryptedData,
    },
  });

  return NextResponse.json(credential);
}
```

```typescript
// app/api/ozon/credentials/[id]/route.ts

import { createRouteHandlerClient } from '@supabase/auth-helpers-nextjs';
import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

// GET - 获取单个凭证
export async function GET(
  request: Request,
  { params }: { params: { id: string } }
) {
  const supabase = createRouteHandlerClient({ cookies });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const credential = await prisma.ozonCredential.findFirst({
    where: {
      id: params.id,
      userId: user.id, // 确保用户只能获取自己的凭证
    },
  });

  if (!credential) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  }

  return NextResponse.json(credential);
}

// PATCH - 更新凭证
export async function PATCH(
  request: Request,
  { params }: { params: { id: string } }
) {
  const supabase = createRouteHandlerClient({ cookies });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const body = await request.json();
  const { name, encryptedData } = body;

  const credential = await prisma.ozonCredential.updateMany({
    where: {
      id: params.id,
      userId: user.id,
    },
    data: {
      ...(name && { name }),
      ...(encryptedData && { encryptedData }),
    },
  });

  if (credential.count === 0) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  }

  return NextResponse.json({ success: true });
}

// DELETE - 删除凭证
export async function DELETE(
  request: Request,
  { params }: { params: { id: string } }
) {
  const supabase = createRouteHandlerClient({ cookies });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const credential = await prisma.ozonCredential.deleteMany({
    where: {
      id: params.id,
      userId: user.id,
    },
  });

  if (credential.count === 0) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  }

  return NextResponse.json({ success: true });
}
```

```typescript
// app/api/ozon/tasks/route.ts

import { createRouteHandlerClient } from '@supabase/auth-helpers-nextjs';
import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export async function GET() {
  const supabase = createRouteHandlerClient({ cookies });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const dbUser = await prisma.user.findUnique({
    where: { supabaseId: user.id },
  });

  if (!dbUser) {
    return NextResponse.json({ error: 'User not found' }, { status: 404 });
  }

  const tasks = await prisma.ozonTask.findMany({
    where: { userId: dbUser.id },
    include: { credential: true },
    orderBy: { createdAt: 'desc' },
  });

  return NextResponse.json(tasks);
}

export async function POST(request: Request) {
  const supabase = createRouteHandlerClient({ cookies });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const body = await request.json();

  const dbUser = await prisma.user.findUnique({
    where: { supabaseId: user.id },
  });

  if (!dbUser) {
    return NextResponse.json({ error: 'User not found' }, { status: 404 });
  }

  const task = await prisma.ozonTask.create({
    data: {
      userId: dbUser.id,
      credentialId: body.credentialId,
      articles: body.articles,
      field: body.field,
      status: body.status || 'pending',
      progress: body.progress || 0,
      result: body.result,
      totalArticles: body.totalArticles,
      processedArticles: body.processedArticles,
      totalImages: body.totalImages,
      successImages: body.successImages,
      failedImages: body.failedImages,
      startedAt: body.startedAt ? new Date(body.startedAt) : null,
      completedAt: body.completedAt ? new Date(body.completedAt) : null,
    },
  });

  return NextResponse.json(task);
}
```

### 10.4 创建工具文件

```typescript
// lib/prisma.ts

import { PrismaClient } from '@prisma/client';

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = prisma;
```

### 10.5 测试流程

```bash
# 1. 启动开发服务器
npm run dev

# 2. 注册并登录
# 访问 http://localhost:3000/login

# 3. 添加 Ozon 凭证
# 访问 http://localhost:3000/dashboard/ozon/credentials

# 4. 创建下载任务
# 访问 http://localhost:3000/dashboard/ozon/download

# 5. 查看任务列表
# 访问 http://localhost:3000/dashboard/ozon/tasks
```

### 10.6 验证清单

- [ ] 用户可以注册和登录
- [ ] 登录后可以访问 Dashboard
- [ ] 可以添加 Ozon 凭证（加密存储）
- [ ] 可以编辑和删除凭证
- [ ] 可以创建下载任务
- [ ] 下载任务正常工作（调用后端 API）
- [ ] 任务结果正确保存到数据库
- [ ] 可以查看任务历史记录
- [ ] 用户只能访问自己的数据
- [ ] 未登录用户无法访问 Dashboard

---

## 总结

这个完整的集成指南涵盖了：

1. ✅ Next.js 14 + Supabase 技术栈
2. ✅ 完整的数据库设计（Prisma）
3. ✅ 用户认证流程（Supabase Auth）
4. ✅ Dashboard 页面布局
5. ✅ Ozon 凭证管理（CRUD）
6. ✅ 下载任务创建和管理
7. ✅ 加密存储敏感数据
8. ✅ 后端 API 集成
9. ✅ 完整的组件和 Hooks
10. ✅ 逐步集成指南

按照这个文档，前端开发者可以一次性完成整个功能的集成。
