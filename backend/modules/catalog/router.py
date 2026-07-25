from fastapi import APIRouter, Depends, HTTPException, status

from core.config import settings
from core.dependencies import CurrentUser, require_admin, require_teacher_reviewer_or_admin
from modules.catalog.schemas import (
    AiModelPayload,
    ChapterPayload,
    EvaluationPolicyPayload,
    LearningOutcomePayload,
    PromptTemplatePayload,
    SubjectPayload,
    SubjectResponse,
)
from modules.catalog.service import CatalogService, get_catalog_service

router = APIRouter(prefix=f"{settings.api_prefix}/catalog", tags=["Catalog"])


def _translate(exc: Exception):
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/overview")
def catalog_overview(
    _user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    return service.overview()


@router.get("/subjects", response_model=list[SubjectResponse])
def list_subjects(
    _user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    return service.list_subjects()


@router.post("/subjects", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
def upsert_subject(
    payload: SubjectPayload,
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    try:
        return service.upsert_subject(payload)
    except Exception as exc:
        _translate(exc)


@router.post("/subjects/{subject_id}/chapters", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
def add_chapter(
    subject_id: str,
    payload: ChapterPayload,
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    try:
        return service.add_chapter(subject_id, payload)
    except Exception as exc:
        _translate(exc)


@router.post("/subjects/{subject_id}/learning-outcomes", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
def add_learning_outcome(
    subject_id: str,
    payload: LearningOutcomePayload,
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    try:
        return service.add_learning_outcome(subject_id, payload)
    except Exception as exc:
        _translate(exc)


@router.get("/ai-models")
def list_ai_models(
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    return {"items": service.list_ai_models()}


@router.post("/ai-models", status_code=status.HTTP_201_CREATED)
def upsert_ai_model(
    payload: AiModelPayload,
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    return service.upsert_ai_model(payload)


@router.get("/prompt-templates")
def list_prompt_templates(
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    return {"items": service.list_prompt_templates()}


@router.post("/prompt-templates", status_code=status.HTTP_201_CREATED)
def save_prompt_template(
    payload: PromptTemplatePayload,
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    return service.save_prompt_template(payload)


@router.get("/evaluation-policies")
def list_evaluation_policies(
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    return {"items": service.list_evaluation_policies()}


@router.post("/evaluation-policies", status_code=status.HTTP_201_CREATED)
def save_evaluation_policy(
    payload: EvaluationPolicyPayload,
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    return service.save_evaluation_policy(payload)
