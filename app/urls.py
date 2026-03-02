from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/<int:election_id>/", views.login, name="login"),
    path("verify/<int:election_id>/<str:email>/", views.verify_otp, name="verify_otp"),
    path("ballot/<str:token>/", views.ballot, name="ballot"),
    path("vote/<str:token>/", views.submit_ballot, name="submit_ballot"),
    path("success/", views.success, name="success"),
]