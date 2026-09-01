from app.core.rbac import Permission, Role, has_permission


def test_owner_has_full_powers():
    assert has_permission(Role.OWNER.value, Permission.MANAGE_USERS)
    assert has_permission(Role.OWNER.value, Permission.VIEW_MARGIN)
    assert has_permission(Role.OWNER.value, Permission.EXPORT_REPORT)


def test_client_cannot_see_margin():
    assert not has_permission(Role.CLIENT.value, Permission.VIEW_MARGIN)
    assert not has_permission(Role.CLIENT.value, Permission.VIEW_ALL_PROJECTS)
    assert has_permission(Role.CLIENT.value, Permission.VIEW_OWN_PROJECTS)


def test_qs_can_only_review_takeoff():
    assert has_permission(Role.QS.value, Permission.REVIEW_TAKEOFF)
    assert not has_permission(Role.QS.value, Permission.MANAGE_PRICE_BOOK)
    assert not has_permission(Role.QS.value, Permission.VIEW_MARGIN)


def test_unknown_role_has_nothing():
    assert not has_permission("intruder", Permission.MANAGE_USERS)
