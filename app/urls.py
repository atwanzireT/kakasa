from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),

    path("login/<int:election_id>/", views.login, name="login"),
    path("verify-phone/<int:election_id>/<str:phone>/", views.verify_phone_otp, name="verify_phone_otp"),

    path("ballot/<str:token>/", views.ballot, name="ballot"),
    path("ballot/<str:token>/submit/", views.submit_ballot, name="submit_ballot"),

    path("success/", views.success, name="success"),
    path("elections/<int:election_id>/leaderboard/", views.election_leaderboard, name="election_leaderboard"),
]