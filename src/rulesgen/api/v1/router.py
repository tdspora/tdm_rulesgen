from __future__ import annotations

from fastapi import APIRouter

from rulesgen.api.v1.endpoints.datasets import router as datasets_router
from rulesgen.api.v1.endpoints.docs import router as docs_router
from rulesgen.api.v1.endpoints.health import router as health_router
from rulesgen.api.v1.endpoints.jobs import router as jobs_router
from rulesgen.api.v1.endpoints.rules import router as rules_router

router = APIRouter()
router.include_router(health_router)
router.include_router(rules_router)
router.include_router(jobs_router)
router.include_router(datasets_router)
router.include_router(docs_router)
