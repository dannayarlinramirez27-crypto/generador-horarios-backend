import psycopg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import (
    asignaciones,
    configs,
    cursos,
    docentes,
    health,
    horarios,
    materias,
    salones,
)
from app.routers._common import db_error_to_response

settings = get_settings()

# ============================================================================
# FastAPI app — Sistema Generador de Horarios
# ============================================================================
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API RESTo del generador de horarios escolares (CSP).",
)

# ----------------------------------------------------------------------------
# CORS: permitimos el origen del frontend Next.js (localhost) y, en producción,
# el dominio de Vercel. Los orígenes explícitos se ajustan vía CORS_ORIGINS;
# el patrón opcional CORS_ORIGIN_REGEX habilita los previews dinámicos de
# Vercel (*.vercel.app) sin necesidad de listarlos uno a uno.
# ----------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex_value,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    """Bienvenida: apunta a la documentación interactiva (Swagger)."""
    return {"app": settings.app_name, "docs": "/docs", "health": "/api/v1/health"}


# Exception handler global: convierte errores de psycopg/Postgres en
# respuestas HTTP claras (400/409/500/503) — ver app/routers/_common.py.
@app.exception_handler(psycopg.Error)
async def psycopg_exception_handler(
    request: Request, exc: psycopg.Error
) -> JSONResponse:
    status_code, detail = db_error_to_response(exc)
    return JSONResponse(status_code=status_code, content={"detail": detail})


# Routers bajo el prefijo /api/v1
app.include_router(health.router, prefix="/api/v1")
app.include_router(configs.router, prefix="/api/v1")
app.include_router(docentes.router, prefix="/api/v1")
app.include_router(cursos.router, prefix="/api/v1")
app.include_router(materias.router, prefix="/api/v1")
app.include_router(salones.router, prefix="/api/v1")
app.include_router(asignaciones.router, prefix="/api/v1")
app.include_router(horarios.router, prefix="/api/v1")