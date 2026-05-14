# decorators.py
from django.shortcuts import redirect
from functools import wraps


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        try:
            role = request.user.userprofile.role
            print(f"DEBUG admin_required: user={request.user.username}, role={role}")
            if role == 'admin':
                return view_func(request, *args, **kwargs)
        except Exception as e:
            print(f"DEBUG admin_required ERROR: {e}")
        return redirect('user_dashboard')
    return wrapper

def staff_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        try:
            role = request.user.userprofile.role
            print(f"DEBUG staff_required: user={request.user.username}, role={role}")
            if role in ('staff', 'admin'):
                return view_func(request, *args, **kwargs)
        except Exception as e:
            print(f"DEBUG staff_required ERROR: {e}")
        return redirect('user_dashboard')
    return wrapper