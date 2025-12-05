from controllers.auth import auth_router
from controllers.user import user_router
from controllers.document import document_router
from controllers.template import template_router
from controllers.check_result import check_result_router

__all__ = [
    "auth_router",
    "user_router",
    "document_router",
    "template_router",
    "check_result_router",
]
