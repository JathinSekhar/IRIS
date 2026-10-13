from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .auth_service import AuthError
from .config import settings
from .db import IS_SQLITE, Base, engine
from .routers import auth, checkin, doctor, messages, reviewer


@asynccontextmanager
async def lifespan(_: FastAPI):
    if IS_SQLITE:  # zero-setup fallback; Postgres schemas are managed by Alembic (`alembic upgrade head`)
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="IRIS API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

@app.exception_handler(AuthError)
async def auth_error_handler(_: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse({"detail": exc.message}, status_code=exc.status_code)


app.include_router(auth.router)
app.include_router(checkin.router)
app.include_router(messages.router)
app.include_router(reviewer.router)
app.include_router(doctor.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
