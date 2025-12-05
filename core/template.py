from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status

from crud import TemplateRepositoryDependency
from models import Template
from schemas.template import TemplateCreate, TemplateDto


class TemplateService:
    def __init__(self, template_repository: TemplateRepositoryDependency):
        self.template_repository = template_repository

    def get_template(self, template_id: int) -> Optional[TemplateDto]:
        """Get template by ID."""
        template = self.template_repository.get_template_by_id(template_id)
        if not template:
            return None
        return TemplateDto.from_template(template)

    def get_all_templates(self, include_inactive: bool = False) -> list[TemplateDto]:
        """Get all templates, optionally including inactive ones."""
        templates = self.template_repository.get_all_templates(active_only=not include_inactive)
        return [TemplateDto.from_template(t) for t in templates]

    def create_template(self, data: TemplateCreate) -> TemplateDto:
        """Create a new template (admin only)."""
        # Check if template with same name exists
        existing = self.template_repository.get_template_by_name(data.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Template with this name already exists",
            )

        template = Template(
            name=data.name,
            description=data.description,
            params=data.params.model_dump(),
        )
        created_template = self.template_repository.create_template(template)
        return TemplateDto.from_template(created_template)

    def update_template(
        self,
        template_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        params: Optional[dict] = None,
        is_active: Optional[bool] = None,
    ) -> TemplateDto:
        """Update template fields."""
        template = self.template_repository.get_template_by_id(template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found",
            )

        if name is not None:
            # Check for duplicate name
            existing = self.template_repository.get_template_by_name(name)
            if existing and existing.id != template_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Template with this name already exists",
                )
            template.name = name

        if description is not None:
            template.description = description
        if params is not None:
            template.params = params
        if is_active is not None:
            template.is_active = is_active

        updated_template = self.template_repository.update_template(template)
        return TemplateDto.from_template(updated_template)

    def delete_template(self, template_id: int) -> TemplateDto:
        """Delete a template (admin only)."""
        template = self.template_repository.get_template_by_id(template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found",
            )

        deleted_template = self.template_repository.delete_template(template)
        return TemplateDto.from_template(deleted_template)


TemplateServiceDependency = Annotated[TemplateService, Depends(TemplateService)]
