import psycopg
from fastapi import FastAPI, HTTPException, Request
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
# CORS: aceptamos cualquier origen (los previews de Vercel cambian de
# subdominio en cada deploy). La seguridad la aporta el JWT + RLS, no CORS.
# Starlette con allow_origins=["*"] + allow_credentials=True hace echo del
# Origin del cliente (no envía "*" literal), cumpliendo la spec CORS.
# ----------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    """Bienvenida: apunta a la documentación interactiva (Swagger)."""
    return {"app": settings.app_name, "docs": "/docs", "health": "/api/v1/health"}


# CORS headers para respuestas de error (los handlers manuales bypassan el
# middleware CORS de Starlette, así que los inyectamos explícitamente).
_ORIGIN_ANY = "*"
_CORS_HEADERS = {
    "Access-Control-Allow-Origin": _ORIGIN_ANY,
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Methods": "*",
    "Access-Control-Allow-Headers": "*",
}


def _cors_json_response(status_code: int, content: dict) -> JSONResponse:
    """Devuelve JSONResponse con headers CORS para que el frontend en Vercel
    pueda leer los mensajes de error en cualquier status (400, 409, 500...)."""
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=_CORS_HEADERS,
    )


# Exception handler global: convierte errores de psycopg/Postgres en
# respuestas HTTP claras (400/409/500/503) — ver app/routers/_common.py.
@app.exception_handler(psycopg.Error)
async def psycopg_exception_handler(
    request: Request, exc: psycopg.Error
) -> JSONResponse:
    status_code, detail = db_error_to_response(exc)
    return _cors_json_response(status_code, {"detail": detail})


# Handler para HTTPException (400, 403, 404, 409, 422…) con CORS headers.
# Sin esto Vercel no puede leer el mensaje de error en preflight/requests.
@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    return _cors_json_response(
        exc.status_code,
        exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail},
    )


# Handler de último recurso: captura cualquier excepción no manejada para
# que la respuesta sea JSON con CORS headers (el middleware los añade después).
# Sin esto, un 500 crudo hace que el navegador reporte un falso error de CORS.
@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    return _cors_json_response(
        500,
        {"detail": f"Error interno del servidor: {str(exc)}"},
    )


# Routers bajo el prefijo /api/v1
app.include_router(health.router, prefix="/api/v1")
app.include_router(configs.router, prefix="/api/v1")
app.include_router(docentes.router, prefix="/api/v1")
app.include_router(cursos.router, prefix="/api/v1")
app.include_router(materias.router, prefix="/api/v1")
app.include_router(salones.router, prefix="/api/v1")
app.include_router(asignaciones.router, prefix="/api/v1")
app.include_router(horarios.router, prefix="/api/v1")