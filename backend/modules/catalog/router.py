from fastapi import APIRouter, Depends, HTTPException, status

from core.config import settings
from core.dependencies import CurrentUser, require_admin, require_teacher_reviewer_or_admin
from modules.catalog.schemas import (
    AiModelActivationPayload,
    AiModelHealthCheckPayload,
    AiModelPayload,
    ChapterPayload,
    ChapterUpdatePayload,
    EvaluationPolicyActivationPayload,
    EvaluationPolicyPayload,
    LearningOutcomePayload,
    LearningOutcomeUpdatePayload,
    PromptTemplateActivationPayload,
    PromptTemplatePayload,
    PromptTemplateTestPayload,
    SubjectPayload,
    SubjectResponse,
    SubjectUpdatePayload,
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


@router.get("/runtime-config")
def runtime_config(
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    return service.runtime_config()


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


@router.patch("/subjects/{subject_id}", response_model=SubjectResponse)
def update_subject(
    subject_id: str,
    payload: SubjectUpdatePayload,
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    try:
        return service.update_subject(subject_id, payload)
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


@router.patch("/subjects/{subject_id}/chapters/{chapter_id}", response_model=SubjectResponse)
def update_chapter(
    subject_id: str,
    chapter_id: str,
    payload: ChapterUpdatePayload,
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    try:
        return service.update_chapter(subject_id, chapter_id, payload)
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


@router.patch("/subjects/{subject_id}/learning-outcomes/{clo_id}", response_model=SubjectResponse)
def update_learning_outcome(
    subject_id: str,
    clo_id: str,
    payload: LearningOutcomeUpdatePayload,
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    try:
        return service.update_learning_outcome(subject_id, clo_id, payload)
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


@router.post("/ai-models/active")
def set_ai_model_active(
    payload: AiModelActivationPayload,
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    try:
        return service.set_ai_model_active(payload)
    except Exception as exc:
        _translate(exc)


@router.post("/ai-models/health-check")
async def check_ai_model_health(
    payload: AiModelHealthCheckPayload,
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    return await service.check_ai_model_health(payload)


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


@router.post("/prompt-templates/active")
def activate_prompt_template(
    payload: PromptTemplateActivationPayload,
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    try:
        return service.activate_prompt_template(payload)
    except Exception as exc:
        _translate(exc)


@router.post("/prompt-templates/test-build")
def test_prompt_template(
    payload: PromptTemplateTestPayload,
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    try:
        return service.test_prompt_template(payload)
    except Exception as exc:
        _translate(exc)


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


@router.post("/evaluation-policies/active")
def activate_evaluation_policy(
    payload: EvaluationPolicyActivationPayload,
    _admin: CurrentUser = Depends(require_admin),
    service: CatalogService = Depends(get_catalog_service),
):
    try:
        return service.activate_evaluation_policy(payload)
    except Exception as exc:
        _translate(exc)
