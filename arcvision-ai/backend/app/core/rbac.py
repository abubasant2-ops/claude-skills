"""Role-Based Access Control matrix (PRD §10.2)."""

from enum import Enum


class Role(str, Enum):
    OWNER = "owner"
    EXECUTIVE = "executive"
    PM = "pm"
    ESTIMATOR = "estimator"
    QS = "qs"
    CLIENT = "client"


class Permission(str, Enum):
    MANAGE_USERS = "manage_users"
    CREATE_PROJECT = "create_project"
    VIEW_ALL_PROJECTS = "view_all_projects"
    VIEW_OWN_PROJECTS = "view_own_projects"
    MANAGE_PRICE_BOOK = "manage_price_book"
    REVIEW_TAKEOFF = "review_takeoff"
    APPROVE_TAKEOFF = "approve_takeoff"
    VIEW_MARGIN = "view_margin"
    EXPORT_REPORT = "export_report"


PERMISSIONS: dict[Role, set[Permission]] = {
    Role.OWNER: {
        Permission.MANAGE_USERS,
        Permission.CREATE_PROJECT,
        Permission.VIEW_ALL_PROJECTS,
        Permission.MANAGE_PRICE_BOOK,
        Permission.REVIEW_TAKEOFF,
        Permission.APPROVE_TAKEOFF,
        Permission.VIEW_MARGIN,
        Permission.EXPORT_REPORT,
    },
    Role.EXECUTIVE: {
        Permission.VIEW_ALL_PROJECTS,
        Permission.VIEW_MARGIN,
        Permission.EXPORT_REPORT,
    },
    Role.PM: {
        Permission.CREATE_PROJECT,
        Permission.REVIEW_TAKEOFF,
        Permission.APPROVE_TAKEOFF,
        Permission.VIEW_MARGIN,
        Permission.EXPORT_REPORT,
    },
    Role.ESTIMATOR: {
        Permission.MANAGE_PRICE_BOOK,
        Permission.REVIEW_TAKEOFF,
        Permission.APPROVE_TAKEOFF,
        Permission.VIEW_MARGIN,
        Permission.EXPORT_REPORT,
    },
    Role.QS: {
        Permission.REVIEW_TAKEOFF,
    },
    Role.CLIENT: {
        Permission.VIEW_OWN_PROJECTS,
    },
}


def has_permission(role: str, permission: Permission) -> bool:
    try:
        return permission in PERMISSIONS[Role(role)]
    except (KeyError, ValueError):
        return False
