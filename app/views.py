from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import CodeLoginForm, EmailStartForm, OTPVerifyForm, SubmitBallotHelper
from .models import Election, Position, Candidate, VotingSession, Vote


def home(request):
    elections = Election.objects.order_by("-created_at")
    open_elections = [e for e in elections if e.is_open_now()]
    return render(request, "app/home.html", {"open_elections": open_elections, "all_elections": elections[:10]})


def login(request, election_id: int):
    election = get_object_or_404(Election, id=election_id)

    if election.access_mode == Election.AccessMode.CODE_ONLY:
        if request.method == "POST":
            form = CodeLoginForm(request.POST, election=election)
            if form.is_valid():
                session = VotingSession.create_for_code_voter(voter=form.voter, election=election, minutes=15)
                return redirect("ballot", token=session.token)
        else:
            form = CodeLoginForm(election=election)

        return render(request, "app/login_code.html", {"election": election, "form": form})

    # Email-based flow
    if request.method == "POST":
        form = EmailStartForm(request.POST, election=election)
        if form.is_valid():
            if election.require_email_otp:
                form.send_otp()
                messages.success(request, "OTP sent. Check your email inbox (and spam).")
                return redirect("verify_otp", election_id=election.id, email=form.cleaned_data["email"])
            session = VotingSession.create_for_email(email=form.cleaned_data["email"], election=election, minutes=15)
            return redirect("ballot", token=session.token)
    else:
        form = EmailStartForm(election=election)

    return render(request, "app/login_email.html", {"election": election, "form": form})


def verify_otp(request, election_id: int, email: str):
    election = get_object_or_404(Election, id=election_id)

    if request.method == "POST":
        form = OTPVerifyForm(request.POST, election=election)
        if form.is_valid():
            form.mark_used()
            session = VotingSession.create_for_email(email=form.cleaned_data["email"], election=election, minutes=15)
            return redirect("ballot", token=session.token)
    else:
        form = OTPVerifyForm(initial={"email": email}, election=election)

    return render(request, "app/verify_otp.html", {"election": election, "form": form})


def ballot(request, token: str):
    session = get_object_or_404(VotingSession.objects.select_related("election", "voter"), token=token)

    if session.expires_at <= timezone.now():
        messages.error(request, "Session expired. Please login again.")
        return redirect("login", election_id=session.election_id)

    election = session.election
    if not election.is_open_now():
        messages.error(request, "Voting is not open for this election.")
        return redirect("login", election_id=election.id)

    positions = Position.objects.filter(election=election).order_by("sort_order", "name")

    blocks = []
    for pos in positions:
        candidates = Candidate.objects.filter(election=election, position=pos, is_active=True).order_by("full_name")

        if session.voter_id:
            existing_vote = Vote.objects.filter(election=election, position=pos, voter=session.voter).select_related("candidate").first()
        else:
            existing_vote = Vote.objects.filter(election=election, position=pos, voter_email=session.email).select_related("candidate").first()

        blocks.append({"position": pos, "candidates": candidates, "existing_vote": existing_vote})

    return render(request, "app/ballot.html", {"session": session, "election": election, "position_blocks": blocks})


def submit_ballot(request, token: str):
    session = get_object_or_404(VotingSession.objects.select_related("election", "voter"), token=token)

    if request.method != "POST":
        return redirect("ballot", token=token)

    if session.expires_at <= timezone.now():
        messages.error(request, "Session expired. Please login again.")
        return redirect("login", election_id=session.election_id)

    election = session.election
    if not election.is_open_now():
        messages.error(request, "Voting is not open for this election.")
        return redirect("login", election_id=election.id)

    helper = SubmitBallotHelper(session=session)
    created, already, errors = helper.save_votes(request.POST)

    if errors:
        messages.error(request, "Some selections were invalid. Please review your ballot.")
        return redirect("ballot", token=token)

    if created == 0 and already > 0:
        messages.info(request, "You already voted for the selected positions.")
        return redirect("ballot", token=token)

    return redirect("success")


def success(request):
    return render(request, "app/success.html")