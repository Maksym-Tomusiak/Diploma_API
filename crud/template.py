from typing import Annotated, Optional

from fastapi import Depends
from sqlalchemy import select

from db import SessionDep
from models import Template


class TemplateRepository:
    def __init__(self, session: SessionDep):
        self.session = session

    def get_template_by_id(self, template_id: int) -> Optional[Template]:
        return self.session.get(Template, template_id)

    def get_all_templates(self, active_only: bool = True) -> list[Template]:
        query = select(Template)
        if active_only:
            query = query.where(Template.is_active == True)
        return list(self.session.scalars(query).all())

    def get_template_by_name(self, name: str) -> Optional[Template]:
        query = select(Template).where(Template.name == name)
        return self.session.scalars(query).first()

    def create_template(self, template: Template) -> Template:
        self.session.add(template)
        self.session.commit()
        self.session.refresh(template)
        return template

    def update_template(self, template: Template) -> Template:
        self.session.commit()
        self.session.refresh(template)
        return template

    def delete_template(self, template: Template) -> Template:
        self.session.delete(template)
        self.session.commit()
        return template


TemplateRepositoryDependency = Annotated[TemplateRepository, Depends(TemplateRepository)]
