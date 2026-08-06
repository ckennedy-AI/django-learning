from rest_framework.permissions import BasePermission


class IsStaff(BasePermission):
    """Caller-level check only. There is no object to scope against here,
    DepartmentActivityReportApi's read is unscoped once the caller is staff.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)


class IsAssigneeManager(BasePermission):
    """Object-level check for TaskApprovalApi.

    Row scoping already lives in the selector
    (task_assignment_get_for_manager), which 404s a task assignment that
    does not belong to the requesting manager's report before this class
    ever runs. This class exists so the endpoint declares its access rule
    the same way every other endpoint in the permissions table does, and so
    a future change to the selector's scoping does not silently drop
    enforcement. has_object_permission only runs where a view calls
    check_object_permissions explicitly, since it is not automatic on a
    plain APIView.
    """

    def has_object_permission(self, request, view, obj):
        return obj.assignee.manager_id == request.user.id
