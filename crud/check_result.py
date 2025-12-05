from typing import Annotated, Optional

from fastapi import Depends
from sqlalchemy import select

from db import SessionDep
from models import CheckResult


class CheckResultRepository:
    def __init__(self, session: SessionDep):
        self.session = session

    def get_check_result_by_id(self, check_result_id: int) -> Optional[CheckResult]:
        return self.session.get(CheckResult, check_result_id)

    def get_check_results_by_document_id(self, document_id: int) -> list[CheckResult]:
        query = select(CheckResult).where(CheckResult.document_id == document_id)
        return list(self.session.scalars(query).all())

    def create_check_result(self, check_result: CheckResult) -> CheckResult:
        self.session.add(check_result)
        self.session.commit()
        self.session.refresh(check_result)
        return check_result

    def delete_check_result(self, check_result: CheckResult) -> CheckResult:
        self.session.delete(check_result)
        self.session.commit()
        return check_result


CheckResultRepositoryDependency = Annotated[CheckResultRepository, Depends(CheckResultRepository)]
