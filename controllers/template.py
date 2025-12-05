from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from core import TemplateServiceDependency, CurrentUserDependency, AdminUserDependency
from schemas.template import TemplateCreate, TemplateDto, TemplateParams

template_router = APIRouter(prefix="/templates", tags=["Templates"])


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    params: Optional[TemplateParams] = None
    is_active: Optional[bool] = None


@template_router.get("", response_model=list[TemplateDto])
async def get_all_templates(
    current_user: CurrentUserDependency,
    template_service: TemplateServiceDependency,
    include_inactive: bool = False,
):
    """
    Get all templates.
    Regular users only see active templates.
    Admins can see inactive templates with include_inactive=True.
    """
    from models.user import UserRole
    
    # Only admins can see inactive templates
    if include_inactive and current_user.role != UserRole.ADMIN:
        include_inactive = False
    
    return template_service.get_all_templates(include_inactive=include_inactive)


@template_router.get("/{template_id}", response_model=TemplateDto)
async def get_template(
    template_id: int,
    current_user: CurrentUserDependency,
    template_service: TemplateServiceDependency,
):
    """
    Get a specific template by ID.
    """
    template = template_service.get_template(template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    return template


@template_router.post("", response_model=TemplateDto, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: TemplateCreate,
    admin_user: AdminUserDependency,
    template_service: TemplateServiceDependency,
):
    """
    Create a new template (admin only).
    """
    return template_service.create_template(data)


@template_router.put("/{template_id}", response_model=TemplateDto)
async def update_template(
    template_id: int,
    data: TemplateUpdate,
    admin_user: AdminUserDependency,
    template_service: TemplateServiceDependency,
):
    """
    Update template (admin only).
    """
    params_dict = data.params.model_dump() if data.params else None
    return template_service.update_template(
        template_id,
        name=data.name,
        description=data.description,
        params=params_dict,
        is_active=data.is_active,
    )


@template_router.delete("/{template_id}", response_model=TemplateDto)
async def delete_template(
    template_id: int,
    admin_user: AdminUserDependency,
    template_service: TemplateServiceDependency,
):
    """
    Delete a template (admin only).
    """
    return template_service.delete_template(template_id)
