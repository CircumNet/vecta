from django.urls import path
from rest_framework.routers import SimpleRouter

from . import account_views as acct
from . import auth_views as auth
from . import oauth_views as oauth
from . import views

router = SimpleRouter()
router.register("users", views.UserViewSet, basename="user")
router.register("departments", views.DepartmentViewSet, basename="department")

urlpatterns = [
    path("auth/config/", auth.ConfigView.as_view()),
    path("auth/login/", auth.LoginView.as_view()),
    path("auth/logout/", views.LogoutView.as_view()),
    path("auth/me/", views.MeView.as_view()),
    path("auth/change-password/", views.ChangePasswordView.as_view()),
    path("auth/register/", auth.RegisterView.as_view()),
    path("auth/register/verify/", auth.RegisterVerifyView.as_view()),
    path("auth/register/resend/", auth.RegisterResendView.as_view()),
    path("auth/password/forgot/", auth.ForgotView.as_view()),
    path("auth/password/verify/", auth.VerifyResetCodeView.as_view()),
    path("auth/password/reset/", auth.ResetPasswordView.as_view()),
    path("auth/oauth/exchange/", oauth.OAuthExchangeView.as_view()),
    path("auth/oauth/<str:provider>/start/", oauth.OAuthStartView.as_view()),
    path("auth/oauth/<str:provider>/callback/", oauth.OAuthCallbackView.as_view()),
    path("account/profile/", acct.ProfileView.as_view()),
    path("account/email/request/", acct.EmailChangeRequestView.as_view()),
    path("account/email/confirm/", acct.EmailChangeConfirmView.as_view()),
    path("account/password/set/", acct.SetPasswordView.as_view()),
    path("account/sessions/revoke/", acct.RevokeSessionsView.as_view()),
    path("account/identities/", acct.IdentitiesView.as_view()),
    path("account/identities/<str:provider>/", acct.IdentityDetailView.as_view()),
    path("account/export/", acct.ExportView.as_view()),
    path("auth/hr/invite/", auth.HRInviteView.as_view()),
    path("auth/hr/register/", auth.HRRegisterView.as_view()),
] + router.urls
