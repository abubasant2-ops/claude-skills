from fastapi import APIRouter

from app.api.assessments import router as assessments_router
from app.api.children import router as children_router
from app.api.sessions import router as sessions_router
from app.api.treatment_plans import router as treatment_plans_router
from app.api.users import router as users_router

api_router = APIRouter()
api_router.include_router(users_router)
api_router.include_router(children_router)
api_router.include_router(assessments_router)
api_router.include_router(treatment_plans_router)
api_router.include_router(sessions_router)
