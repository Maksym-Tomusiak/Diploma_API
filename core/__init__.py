from core.auth import (
    AuthService,
    AuthServiceDependency,
    CurrentUserDependency,
    AdminUserDependency,
    get_current_user,
    require_admin,
)
from core.user import UserService, UserServiceDependency
from core.document import DocumentService, DocumentServiceDependency
from core.template import TemplateService, TemplateServiceDependency
from core.check_result import CheckResultService, CheckResultServiceDependency
from core.user_action_log import UserActionLogService, UserActionLogServiceDependency
from core.google_docs import GoogleDocsService, GoogleDocsServiceDependency
from core.format_checker import FormatCheckerService, FormatCheckerServiceDependency

__all__ = [
    # Auth
    "AuthService",
    "AuthServiceDependency",
    "CurrentUserDependency",
    "AdminUserDependency",
    "get_current_user",
    "require_admin",
    # Services
    "UserService",
    "UserServiceDependency",
    "DocumentService",
    "DocumentServiceDependency",
    "TemplateService",
    "TemplateServiceDependency",
    "CheckResultService",
    "CheckResultServiceDependency",
    "UserActionLogService",
    "UserActionLogServiceDependency",
    "GoogleDocsService",
    "GoogleDocsServiceDependency",
    "FormatCheckerService",
    "FormatCheckerServiceDependency",
]
