# DocQA —— 基于 RAG 的知识库问答系统

> 上传文档、构建知识库、用 AI 提问。适用于任何领域的私有知识问答。

基于 **RAG（检索增强生成）** 构建的通用文档问答系统。知识库内容完全由你自己注入：既可以上传文档，也可以把一批文件放进知识目录，系统只认那个目录。

---

## 功能介绍

### 🤖 智能问答

- **RAG 模式**：检索知识库后由 AI 生成回答，每条回答可核查事实并标注引用来源
- **来源卡片**：展示相关度评分、原文片段、来源链接、发布日期
- **低置信拒答**：知识库外的问题自动回复「未找到相关信息」，避免幻觉
- **闲聊识别**：问候/寒暄自动跳过检索，直接返回引导信息
- **流式输出**：SSE 逐字打字机效果，支持「停止生成」
- **多轮对话**：自动携带最近 6 轮历史上下文
- **会话持久化**：问答记录自动保存，切换页面不丢失

### 📄 知识库文档管理

- 上传 `.txt` / `.pdf` / `.doc` / `.docx`，填写标题、分类、来源链接
- 文档列表支持分类筛选、关键词搜索
- **重建索引**：一键清空向量库 → 全部文档重新向量化 → 即时生效
- 删除文档时同步清理对应向量

### 👤 用户系统

- 注册 / 登录（JWT + BCrypt）
- 修改密码、个人中心
- 管理员：用户管理（角色切换、启禁用）、硬删除

### ⚡ 缓存系统

- Redis 问答缓存 + 会话缓存 + 热门问题排行
- Redis 不可用时自动降级到内存模式
- 管理员可视化缓存面板

### 📊 评测框架

- 50 条评测数据集（单轮知识题 + 多轮对话 + 知识库外问题）
- 多检索配置对比：dense-only / hybrid / hybrid+reranker
- 指标：Hit@5、MRR@5、Precision、Recall、OOD 拒答率、P95 延迟

---

## 知识库：一个目录就是全部真相

系统的可检索内容只来自一个目录，默认是仓库根目录下的 `knowledge_docs/`：

```
knowledge_docs/                 ← 唯一真相：所有可检索内容都以纯文本躺在这里
├── 院系介绍/                   ← 子目录名就是文档分类
│   └── 计算机学院_1f57a249.md
└── uploads/                   ← 界面上的上传也会落到这里
    └── 校历说明_8b3c1d02.md
```

规则很简单：

- 只认 `.md` 和 `.txt`。上传的 PDF/Word 会先被解析成纯文本写成 `.md` 再入库，所以这个目录永远是人类可读、可 diff 的。
- 子目录名 = 文档分类，可以自己建任意分类。
- `# 标题` 是文档标题，`> 来源:` 是来源链接。
- 重建索引 = 重新扫这个目录，所以「往目录里放文件」和「界面上传」两条路的结果完全等价。

想换成你自己的资料，两种做法：

```bash
# 方式一：直接把文件放进目录
cp -r 我的资料/* knowledge_docs/

# 方式二：让它指向别的目录（绝对路径，或相对仓库根目录）
export KNOWLEDGE_DIR=D:/我的资料
```

然后点界面上的「重建索引」（或在 ai_service 上调 `GET /reindex`）。

### 示例语料（可选）

仓库本身不带语料，开箱是空知识库。如果需要一套现成的中文校园语料用来试跑，下载 Releases 里的 **`knowledge_docs-seed.zip`**，解压到 `knowledge_docs/` 再重建索引即可：

```
knowledge_docs-seed.zip
├── news/            学校新闻、学术动态、通知公告
├── academic/        教务处通知、研究生院、课程安排
├── university_info/ 学校概况、院系设置、校园文化
├── academic_files/  课程清单、校历、使用指南
├── departments/     各学院简介、师资队伍
├── admin/           职能部门信息
├── alumni/          校友会、教育发展基金会
├── third_party/     百度百科、维基百科、教育部等
├── research/        科研平台信息
└── campus_life/     校园生活
```

### 派生数据放哪

向量和索引都是可再生的派生物，不进 git：

```
ai_service/data/faiss.index     向量（每个切片 512 维）
ai_service/data/metadata.json   切片原文 + 标题/分类/来源（检索时靠它还原文本）
ai_service/data/bm25/           关键词索引
```

这两样必须成对存在：FAISS 只返回「第几条最像」，正文是从 `metadata.json` 同下标取出来的。删掉了重新「重建索引」即可。也可以用 `AI_DATA_DIR` 把它们放到别的盘。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI |
| 数据库 | MySQL 8.0 + SQLAlchemy |
| 缓存 | Redis 5.0（自动降级 fakeredis） |
| 认证 | JWT (HS256) + BCrypt |
| 嵌入模型 | BAAI/bge-small-zh-v1.5 (512 维) |
| 向量库 | FAISS (IndexFlatIP) |
| 关键词检索 | BM25Okapi (jieba 分词) |
| 融合算法 | RRF (Reciprocal Rank Fusion, k=60) |
| 重排序 | BGE-reranker-base（可选开关） |
| 生成模型 | DeepSeek API（可替换为 OpenAI / 千问 等） |
| 前端 | React 18 + TypeScript + Vite + Ant Design + Tailwind CSS |

---

## 项目结构

```
├── knowledge_docs/           # 知识库唯一真相：放 .md/.txt，子目录名即分类
│
├── ai_service/               # AI 微服务 (port 8003)
│   ├── main.py               # FastAPI 入口
│   ├── config.py             # 配置中心
│   ├── engine/
│   │   ├── pipeline.py       # RAG 管线编排 + 索引构建
│   │   ├── loader.py         # 知识目录扫描 / 文件解析 / 上传落盘
│   │   ├── retriever.py      # FAISS 稠密检索 + 低置信检测
│   │   ├── embedding.py      # BGE 嵌入模型
│   │   ├── chunker.py        # 文档切片
│   │   ├── vector_store.py   # FAISS 索引管理
│   │   ├── bm25_retriever.py # BM25 关键词检索（稠密 + 稀疏混合）
│   │   ├── fusion.py         # RRF 倒数排名融合
│   │   ├── reranker.py       # Cross-Encoder 重排（默认关闭）
│   │   ├── citation.py       # 引用后校验
│   │   ├── generator.py      # LLM API 客户端
│   │   └── prompts.py        # Prompt 模板
│   ├── data/                 # 派生的索引产物（不进 git，可再生）
│   └── cli.py                # 命令行工具
│
├── backend/                  # 业务后端 (port 8002)
│   ├── app/
│   │   ├── main.py           # FastAPI 入口
│   │   ├── config.py         # 配置中心
│   │   ├── database.py       # SQLAlchemy 引擎
│   │   ├── redis_client.py   # Redis（降级 fakeredis）
│   │   ├── models/           # ORM 模型
│   │   ├── schemas/          # Pydantic 模型
│   │   ├── services/         # 业务逻辑（入库 / 重建对齐）
│   │   ├── routers/          # API 路由
│   │   └── cache/            # Redis 缓存层
│   ├── alembic/              # 数据库迁移
│   ├── uploads/              # 上传暂存（转成文本后即清理，不进 git）
│   ├── tests/                # pytest 测试
│   └── init_db.sql           # 建库脚本
│
├── frontend/                 # React 前端 (port 5173)
│   └── src/pages/            # Chat, Documents, Profile, Login, Admin, UserManagement
│
├── evals/                    # 评测框架 + 数据集 + 报告
├── start.ps1                 # 一键启动脚本
└── start.bat                 # Windows 快捷启动
```

---

## 快速开始

### 前提

- Python 3.11+、Node.js 18+、MySQL 8.0
- Redis 可选（无 Redis 时自动降级为内存缓存）

### 1. 配置 API Key

在 `ai_service/.env` 中配置你的大模型 API Key：

```env
DEEPSEEK_API_KEY=你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

> 支持任意 OpenAI 兼容接口，修改 `generator.py` 中的 `base_url` 即可切换模型。

### 2. 初始化数据库

```bash
# 创建 MySQL 数据库
mysql -u root -e "CREATE DATABASE IF NOT EXISTS campus_qa DEFAULT CHARSET utf8mb4;"

# 启动后端（自动建表）
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8002
```

### 3. 启动 AI 服务

```bash
cd ai_service
pip install -r requirements.txt
python -m uvicorn main:app --port 8003
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`。

### 5. 构建知识库

1. 注册账号 → 登录
2. 进入「知识库文档」→ 上传文档，或者把文件直接放进 `knowledge_docs/`
3. 点击「重建索引」（会把知识目录里的全部内容重新入库，并把文档列表对齐到磁盘）
4. 进入「智能问答」→ 开始提问

上传和放文件这两条路是等价的：上传的文件也会被写进 `knowledge_docs/`，所以下一次重建索引它们照样在。

---

## 运行测试

```bash
# 后端测试（跳过需 GPU 的重排序测试）
cd backend
python -m pytest tests/ --ignore=tests/test_reranker.py

# 前端测试
cd frontend
npx vitest run
```

---

## API 概览

### AI 服务 (port 8003)

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/query` | 同步 RAG 问答 |
| GET  | `/query/stream` | SSE 流式问答 |
| GET  | `/reindex` | 扫描知识目录全量重建（返回文档清单） |
| POST | `/process` | 处理单篇文档：`persist=true` 会先把文本写进知识目录再入库 |
| DELETE | `/document/{id}` | 删除文档：索引 + 知识目录里的文件（`?delete_file=false` 只删索引） |
| POST | `/rebuild` | 【已废弃】从数据库行重建，改用 `/reindex` |
| GET  | `/stats` | 知识库统计 |
| GET  | `/health` | 健康检查 |

### 业务后端 (port 8002)

| 模块 | 端点 | 说明 |
|------|------|------|
| 用户 | `/api/user/register` `/login` `/profile` `/change-password` | 注册/登录/个人信息/改密 |
| 用户管理 | `/api/user/list` `/user/{id}` `/user/{id}/status` | 管理员接口 |
| 文档 | `/api/document` `/document/list` `/document/{id}` `/document/rebuild-index` | CRUD + 重建索引 |
| 问答 | `/api/qa/ask` `/qa/history` `/qa/session/{id}` `/qa/hot` | 问答 + 会话 |
| AI | `/api/ai/query` `/api/ai/query/stream` | RAG 代理（SSE） |

---

## 安全说明

- API Key 存放在 `ai_service/.env`，已被 `.gitignore` 排除，**不会上传到 GitHub**
- 代码中无硬编码密钥
- 如果你 fork 本项目，请在 `ai_service/` 下创建自己的 `.env` 文件

---

## 实训课程对照

本项目作为「校园问答助手开发项目」实训成果，覆盖 6 天课程全部要求：

| Day | 主题 | 要求 | 完成 |
|-----|------|------|------|
| Day1 | 前置与环境搭建 | GitHub、环境、数据库设计 | ✅ |
| Day2 | 基础功能开发 | 注册/登录/JWT、CRUD、前端页面 | ✅ |
| Day3 | RAG 技术专题 | 文档切分、Embedding、FAISS 向量库 | ✅ |
| Day4 | 业务模块开发 | 文档上传、处理流转、状态管理 | ✅ |
| Day5 | AI 模块开发 | RAG 问答、SSE 流式、多轮对话 | ✅ |
| Day6 | 测试与发布 | 联调测试、打包、项目文档 | ✅ |

> 技术栈说明：课程要求 Java/Spring Boot，本项目使用 Python/FastAPI，功能完全等价。
>

---

## License

MIT
