# app/views.py
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Election, VotingSession, Position, Candidate, Vote
from .forms import CodeLoginForm, PhoneStartForm, OTPVerifyForm, SubmitBallotHelper
from .sms import send_sms


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _normalize_phone(phone: str) -> str:
    """
    Keep it simple and consistent.
    If your forms already normalize (cleaned_phone), this is just extra safety.
    """
    return (phone or "").strip().replace(" ", "")


def _phone_already_voted(election: Election, phone: str) -> bool:
    """
    ✅ A phone is considered "used" if it has ANY vote in this election.
    So we block OTP sending/verification for that phone.
    """
    phone = _normalize_phone(phone)
    if not phone:
        return False
    return Vote.objects.filter(election=election, voter_phone=phone).exists()


# -----------------------------------------------------------------------------
# Views
# -----------------------------------------------------------------------------
def home(request):
    # Show open elections + all elections list
    all_elections = Election.objects.all().order_by("-created_at")
    open_elections = [e for e in all_elections if e.is_open_now()]

    # simple stats
    for e in all_elections:
        e.total_votes = Vote.objects.filter(election=e).count()
        e.unique_voters = (
            Vote.objects.filter(election=e, voter_phone__isnull=False).values("voter_phone").distinct().count()
            + Vote.objects.filter(election=e, voter__isnull=False).values("voter").distinct().count()
        )

    return render(
        request,
        "app/home.html",
        {"open_elections": open_elections, "all_elections": all_elections},
    )


def login(request, election_id: int):
    election = get_object_or_404(Election, id=election_id)

    if not election.is_open_now():
        messages.error(request, "Voting is not open for this election.")
        return redirect("home")

    # -----------------------------
    # CODE ONLY LOGIN
    # -----------------------------
    if election.access_mode == Election.AccessMode.CODE_ONLY:
        if request.method == "POST":
            form = CodeLoginForm(request.POST, election=election)
            if form.is_valid():
                session = VotingSession.create_for_code_voter(voter=form.voter, election=election, minutes=15)
                return redirect("ballot", token=session.token)
        else:
            form = CodeLoginForm(election=election)

        return render(request, "app/login_code.html", {"election": election, "form": form})

    # -----------------------------
    # PHONE OTP LOGIN
    # -----------------------------
    if request.method == "POST":
        form = PhoneStartForm(request.POST, election=election)
        if form.is_valid():
            # IMPORTANT: use cleaned_phone (your form already prepares it)
            phone = _normalize_phone(getattr(form, "cleaned_phone", "") or form.cleaned_data.get("phone", ""))

            # ✅ NEW RULE: If phone already voted, DO NOT send OTP
            if _phone_already_voted(election, phone):
                messages.error(request, "This phone number has already voted in this election. OTP not sent.")
                return render(request, "app/login_phone.html", {"election": election, "form": form})

            # create otp and send
            otp = form.create_otp()
            message = f"Kakasa Voting OTP: {otp.code}. Expires in 5 minutes."
            ok, resp = send_sms(phone, message)

            if not ok:
                messages.error(request, f"Failed to send OTP. {resp}")
                return render(request, "app/login_phone.html", {"election": election, "form": form})

            messages.success(request, "OTP sent. Enter the code to continue.")
            return redirect("verify_phone_otp", election_id=election.id, phone=phone)
    else:
        form = PhoneStartForm(election=election)

    return render(request, "app/login_phone.html", {"election": election, "form": form})


def verify_phone_otp(request, election_id: int, phone: str):
    election = get_object_or_404(Election, id=election_id)

    if not election.is_open_now():
        messages.error(request, "Voting is not open for this election.")
        return redirect("home")

    phone = _normalize_phone(phone)

    # ✅ Extra protection: if phone already voted, block verification too
    if _phone_already_voted(election, phone):
        messages.error(request, "This phone number has already voted in this election.")
        return redirect("login", election_id=election.id)

    if request.method == "POST":
        form = OTPVerifyForm(request.POST, election=election)
        if form.is_valid():
            # Ensure the phone in the form is same normalized phone
            posted_phone = _normalize_phone(form.cleaned_data.get("phone", ""))

            # ✅ Block if posted phone already voted (double safety)
            if _phone_already_voted(election, posted_phone):
                messages.error(request, "This phone number has already voted in this election.")
                return redirect("login", election_id=election.id)

            otp = form.otp_obj
            otp.is_used = True
            otp.save(update_fields=["is_used"])

            session = VotingSession.create_for_phone(phone=posted_phone, election=election, minutes=30)
            return redirect("ballot", token=session.token)
    else:
        form = OTPVerifyForm(election=election, initial={"phone": phone})

    return render(request, "app/verify_phone.html", {"election": election, "form": form, "phone": phone})


def ballot(request, token: str):
    session = get_object_or_404(VotingSession.objects.select_related("election", "voter"), token=token)

    if not session.is_valid():
        messages.error(request, "Session expired. Please login again.")
        return redirect("login", election_id=session.election_id)

    election = session.election
    positions = Position.objects.filter(election=election).order_by("sort_order", "name")

    position_blocks = []
    for pos in positions:
        candidates = list(
            Candidate.objects.filter(election=election, position=pos, is_active=True).order_by("full_name")
        )

        # attach vote counts
        for c in candidates:
            c.vote_count = Vote.objects.filter(election=election, position=pos, candidate=c).count()

        # find existing vote for this position (so radio pre-check works)
        if session.voter_id:
            existing_vote = Vote.objects.filter(election=election, position=pos, voter=session.voter).first()
        else:
            existing_vote = Vote.objects.filter(election=election, position=pos, voter_phone=session.phone).first()

        position_blocks.append({"position": pos, "candidates": candidates, "existing_vote": existing_vote})

    return render(
        request,
        "app/ballot.html",
        {
            "election": election,
            "session": session,
            "position_blocks": position_blocks,
        },
    )


def submit_ballot(request, token: str):
    session = get_object_or_404(VotingSession.objects.select_related("election", "voter"), token=token)

    if request.method != "POST":
        return redirect("ballot", token=token)

    if not session.is_valid():
        messages.error(request, "Session expired. Please login again.")
        return redirect("login", election_id=session.election_id)

    helper = SubmitBallotHelper(session=session)
    created, already, errors = helper.save_votes(request.POST)

    if errors:
        messages.error(request, "Some selections were invalid. Please review your ballot.")
        return redirect("ballot", token=token)

    if created == 0 and already > 0:
        messages.info(request, "You already voted for those positions.")
        return redirect("ballot", token=token)

    messages.success(request, "Your vote has been recorded!")
    return redirect("success")


def success(request):
    return render(request, "app/success.html")