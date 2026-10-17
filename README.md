# CampusQA

校园知识库问答系统：React 前端 + FastAPI 业务后端 + FastAPI AI 微服务。提问时先从知识库检索相关片段，再调用 DeepSeek 生成回答。

## 功能

- 知识库问答：FAISS 向量和 BM25 关键词混合检索，回答附引用来源，库里没有的内容直接回答未找到
- SSE 流式输出，支持多轮对话
- 文档管理：上传 pdf / doc / docx / txt，解析成纯文本入库，按分类管理，可一键重建索引
- 用户系统：注册登录（JWT），管理员可管理用户
- Redis 缓存问答结果，没装 Redis 时自动降级为本地 SQLite 缓存

## 快速开始

环境：Python 3.11+、Node.js 20.19+、MySQL 8；Redis 可选。

### 1. 配置 AI 服务

新建 `ai_service/.env`：

```env
DEEPSEEK_API_KEY=你的key
# 下面两项可选，写出的是默认值
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

### 2. 准备数据库

建一个 MySQL 库：

```sql
CREATE DATABASE IF NOT EXISTS campus_qa DEFAULT CHARSET utf8mb4;
```

连接参数放在 `backend/.env`：

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=你的密码
DB_NAME=campus_qa
```

空库第一次启动后端时会自动建表。如果手上是旧版本的表结构，先在 `backend/` 目录做迁移（alembic 不在 requirements.txt 里，需要单独安装）：

```bash
pip install alembic
alembic upgrade head
```

### 3. 启动服务

三个进程，各占一个终端：

```bash
# AI 微服务，端口 8003
cd ai_service
pip install -r requirements.txt
python -m uvicorn main:app --port 8003

# 业务后端，端口 8002
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8002

# 前端开发服务器，端口 5173，/api 由 vite 代理到 8002
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173 ，接口文档在 http://localhost:8002/docs 。

不想开三个窗口的话：先在 `frontend/` 执行 `npm run build`，再运行根目录的 `start.bat` 或 `start.ps1`。后端启动时发现 `frontend/dist` 存在就会直接托管它，这样只要 8002 和 8003 两个进程，浏览器打开 http://localhost:8002 即可。

### 4. 装入知识库

仓库不带语料，克隆下来知识库是空的。把自己的 `.md` / `.txt` 文件放进 `knowledge_docs/`，或者从 Release v1.0.0 下载 `knowledge_docs-seed.zip` 解压到 `knowledge_docs/`，然后在页面上点「重建索引」，之后就能提问了。

## 知识目录

`knowledge_docs/` 是知识库唯一的来源：

- 只认 `.md` 和 `.txt`，子目录名就是分类
- 重建索引就是重扫这个目录
- 界面上传的文件会先解析成纯文本写进这个目录，和手动放文件等价
- 环境变量 `KNOWLEDGE_DIR` 可以指向别的目录；`AI_DATA_DIR` 可以改索引产物（向量、元数据）的位置，默认在 `ai_service/data/`

## 目录结构

```
├── ai_service/        # AI 微服务（8003）：检索、索引、调用 DeepSeek
│   ├── main.py        # FastAPI 入口
│   ├── engine/        # 切片、向量库、混合检索、生成等
│   └── requirements.txt
├── backend/           # 业务后端（8002）：用户、文档、问答记录
│   ├── app/
│   ├── alembic/       # 数据库迁移
│   └── requirements.txt
├── frontend/          # React + Vite 前端（开发端口 5173）
├── knowledge_docs/    # 知识库目录
├── start.bat          # 一键启动（先 npm run build）
└── start.ps1
```

## 许可证

MIT
