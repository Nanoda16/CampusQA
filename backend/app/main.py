"""FastAPI 应用入口"""

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import init_db
from app.routers import admin_router, ai_router, document_router, qa_router, user_router
from app.redis_client import redis_client as _  # Redis pre-init

logger = logging.getLogger(__name__)

app = FastAPI(title="CampusQA", version="1.0.0", docs_url="/docs", redoc_url="/redoc")

app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """把未预期的异常翻译成普通用户看得懂的中文提示。

    FastAPI 默认只返回 "Internal Server Error"，前端弹出来就是
    "Request failed with status code 500"，使用者完全不知道问题在哪。
    真正的堆栈仍然写进后端日志，响应里只给一句能照着做的说明。
    """
    logger.exception("未处理的异常: %s %s", request.method, request.url.path)

    if isinstance(exc, SQLAlchemyError):
        message = (
            "数据库操作失败。请确认 MySQL 已启动、campus_qa 库存在，"
            "并且在 backend 目录执行过 alembic upgrade head（版本升级后表结构需要迁移）。"
        )
    else:
        message = "服务端处理这个请求时出错，详细信息已记录到后端日志（backend 控制台）。"

    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": message,
            "detail": message,
            "timestamp": int(time.time()),
        },
    )

app.include_router(ai_router)
app.include_router(user_router)
app.include_router(document_router)
app.include_router(qa_router)
app.include_router(admin_router)


@app.get("/api/health")
def health_check():
    """健康检查

    必须在前端 catch-all 路由之前注册，否则 ``/{full_path:path}`` 会先
    匹配并对所有 ``api/`` 前缀返回 404，导致健康检查永远不可达。
    """
    return {
        "code": 200,
        "message": "success",
        "data": {
            "service": "CampusQA",
            "version": "1.0.0",
            "status": "running",
        },
        "timestamp": int(time.time()),
    }


# ---- Frontend static files (build first: cd frontend && npm run build) ----
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="frontend_assets")
    # SPA fallback: serve index.html for all non-API routes
    # index.html must never be cached, otherwise browsers keep loading stale
    # bundle references after a rebuild. Hashed assets under /assets are
    # immutable and safe to cache aggressively.
    _NO_CACHE = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str, request: Request):
        # Skip API routes (they should have matched above routers)
        if full_path.startswith("api/") or full_path.startswith("admin/cache") or full_path.startswith("docs") or full_path.startswith("redoc"):
            return HTMLResponse(status_code=404)
        fp = FRONTEND_DIR / full_path
        if fp.exists() and fp.is_file():
            # Serve real files as-is; only index.html gets no-cache below
            if fp.name == "index.html":
                return FileResponse(fp, headers=_NO_CACHE)
            return FileResponse(fp)
        return FileResponse(FRONTEND_DIR / "index.html", headers=_NO_CACHE)


_admin_html = Path(__file__).resolve().parent / "static" / "admin.html"


@app.get("/admin/cache", response_class=HTMLResponse, include_in_schema=False)
def admin_cache_page():
    """管理后台缓存面板"""
    if _admin_html.exists():
        return HTMLResponse(content=_admin_html.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Dashboard not found</h1>", status_code=404)


@app.on_event("startup")
def on_startup():
    """应用启动时创建数据库表"""
    try:
        init_db()
        print("✓ 数据库表初始化完成")
    except Exception as e:
        print(f"✗ 数据库表初始化失败: {e}")
        print("  请确保 MySQL 服务已启动且连接信息正确")
