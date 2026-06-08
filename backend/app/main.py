"""主应用入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import analytics, auth, dashboard, llm, materials, questions, student, training
from app.bootstrap import initialize_database, should_auto_create_schema
from app.config import settings
from app.database import Base, engine
from app.services.llm_service import LLMService
from app.utils.errors import http_exception_handler, unhandled_exception_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database(
        base=Base,
        engine=engine,
        should_create=should_auto_create_schema(
            debug=settings.DEBUG,
            db_auto_create=settings.DB_AUTO_CREATE,
        ),
    )
    app.state.llm_service = LLMService()
    yield

# 创建数据库表

# 创建 FastAPI 应用
app = FastAPI(
    title="Tutor 后端服务",
    description="智能数学教学系统后端 API",
    version="1.0.0",
    lifespan=lifespan,
)


# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept-Language"],
)
app.add_exception_handler(Exception, unhandled_exception_handler)


async def starlette_http_exception_adapter(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, StarletteHTTPException):
        return await http_exception_handler(request, exc)
    return await unhandled_exception_handler(request, exc)


app.add_exception_handler(StarletteHTTPException, starlette_http_exception_adapter)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' https:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'",
    )
    if not settings.DEBUG:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# 注册路由
app.include_router(auth.router)
app.include_router(questions.router)
app.include_router(training.router)
app.include_router(student.router)
app.include_router(llm.router)
app.include_router(analytics.router)
app.include_router(dashboard.router)
app.include_router(materials.router)


@app.get("/")
def root():
    """根路径"""
    return {
        "message": "Tutor 后端服务 API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    """健康检查"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
