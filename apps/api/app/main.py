import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import settings
from app.database import Base, engine
from app.routers import ai, assets, auth, collections, projects, traits, workflows
from app.seed import maybe_seed
from app.services.generator import GenerationError
from app.services.imaging import ImageError
from app.services.jobs import start_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("nftstudio")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    maybe_seed()
    stopper = None
    if settings.embed_worker and not settings.force_sync:
        stopper = start_worker()
        logger.info("Embedded job worker started")
    yield
    if stopper is not None:
        stopper.set()


app = FastAPI(title="NFT Creative Studio", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, projects, assets, traits, collections, workflows, ai):
    app.include_router(module.router)


@app.exception_handler(GenerationError)
def generation_error(_request, exc: GenerationError):
    return JSONResponse(status_code=422, content={"detail": {"message": exc.message, "suggestions": exc.suggestions}})


@app.exception_handler(ImageError)
def image_error(_request, exc: ImageError):
    return JSONResponse(status_code=400, content={"detail": exc.message})


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__, "service": "nft-creative-studio"}
