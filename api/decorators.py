from functools import wraps

from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required


def admin_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.role_code != 'admin':
            return HttpResponseForbidden("Bạn không có quyền truy cập")
        return view_func(request, *args, **kwargs)
    return wrapper


def permission_required(codes):
    """
    Decorator kiểm tra quyền theo Permission.code.
    - Admin luôn được phép.
    - Nếu user có ít nhất một permission trong danh sách thì được vào.
    """
    if isinstance(codes, str):
        codes_list = [codes]
    else:
        codes_list = list(codes)

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user

            # Admin có mọi quyền
            if getattr(user, "role_code", None) == "admin":
                return view_func(request, *args, **kwargs)

            # Kiểm tra từng permission code
            for code in codes_list:
                if getattr(user, "has_perm_code", None) and user.has_perm_code(code):
                    return view_func(request, *args, **kwargs)

            return HttpResponseForbidden("Bạn không có quyền truy cập")

        return _wrapped

    return decorator
