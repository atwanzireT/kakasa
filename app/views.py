# app/views.py
from __future__ import annotations

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CodeLoginForm, OTPVerifyForm, PhoneStartForm, SubmitBallotHelper
from .models import Candidate, Election, Position, Vote, VotingSession
from .sms import send_sms


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _normalize_phone(phone: str) -> str:
    """
    Normalize phone to a consistent comparable string.
    Must align with how Vote.voter_phone is stored.
    """
    phone = (phone or "").strip().replace(" ", "")
    if phone.startswith("+"):
        phone = phone[1:]
    return phone


def _phone_already_voted(election: Election, phone: str) -> bool:
    """
    Phone is considered "used" if it has any Vote in this election.
    """
    phone = _normalize_phone(phone)
    if not phone:
        return False
    return Vote.objects.filter(election=election, voter_phone=phone).exists()


def _unique_voters_count(election: Election) -> int:
    """
    Accurate unique voter count:
    - CODE_ONLY elections: unique voters by voter_id
    - PHONE_OTP elections: unique voters by voter_phone
    """
    if election.access_mode == Election.AccessMode.CODE_ONLY:
        return (
            Vote.objects.filter(election=election, voter__isnull=False)
            .values("voter_id")
            .distinct()
            .count()
        )

    # PHONE_OTP
    return (
        Vote.objects.filter(election=election, voter_phone__isnull=False)
        .exclude(voter_phone="")
        .values("voter_phone")
        .distinct()
        .count()
    )


# -----------------------------------------------------------------------------
# Views
# -----------------------------------------------------------------------------
def home(request):
    all_elections = Election.objects.all().order_by("-created_at")
    open_elections = [e for e in all_elections if e.is_open_now()]  # uses Election.is_open_now() :contentReference[oaicite:4]{index=4}

    # add stats
    for e in all_elections:
        e.total_votes = Vote.objects.filter(election=e).count()
        e.unique_voters = _unique_voters_count(e)

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

    # -------------------------------------------------------------------------
    # CODE ONLY LOGIN
    # -------------------------------------------------------------------------
    if election.access_mode == Election.AccessMode.CODE_ONLY:  # :contentReference[oaicite:5]{index=5}
        if request.method == "POST":
            form = CodeLoginForm(request.POST, election=election)
            if form.is_valid():
                session = VotingSession.create_for_code_voter(voter=form.voter, election=election, minutes=15)
                return redirect("ballot", token=session.token)
        else:
            form = CodeLoginForm(election=election)

        return render(request, "app/login_code.html", {"election": election, "form": form})

    # -------------------------------------------------------------------------
    # PHONE OTP LOGIN
    # -------------------------------------------------------------------------
    if request.method == "POST":
        form = PhoneStartForm(request.POST, election=election)
        if form.is_valid():
            # Prefer the form's normalized phone if present
            phone = _normalize_phone(getattr(form, "cleaned_phone", "") or form.cleaned_data.get("phone", ""))

            # ✅ if phone already voted, don't send OTP
            if _phone_already_voted(election, phone):
                messages.error(request, "This phone number has already voted in this election. OTP not sent.")
                return render(request, "app/login_phone.html", {"election": election, "form": form})

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

    # ✅ if already voted, block verification too
    if _phone_already_voted(election, phone):
        messages.error(request, "This phone number has already voted in this election.")
        return redirect("login", election_id=election.id)

    if request.method == "POST":
        form = OTPVerifyForm(request.POST, election=election)
        if form.is_valid():
            posted_phone = _normalize_phone(form.cleaned_data.get("phone", ""))

            # double safety
            if _phone_already_voted(election, posted_phone):
                messages.error(request, "This phone number has already voted in this election.")
                return redirect("login", election_id=election.id)

            otp = form.otp_obj
            otp.is_used = True
            otp.save(update_fields=["is_used"])

            session = VotingSession.create_for_phone(phone=posted_phone, election=election, minutes=30)  # :contentReference[oaicite:6]{index=6}
            return redirect("ballot", token=session.token)
    else:
        form = OTPVerifyForm(election=election, initial={"phone": phone})

    return render(request, "app/verify_phone.html", {"election": election, "form": form, "phone": phone})


def ballot(request, token: str):
    session = get_object_or_404(
        VotingSession.objects.select_related("election", "voter"),
        token=token,
    )

    if not session.is_valid():
        messages.error(request, "Session expired. Please login again.")
        return redirect("login", election_id=session.election_id)

    election = session.election
    positions = Position.objects.filter(election=election).order_by("sort_order", "name")

    # Candidates: one query
    all_candidates = (
        Candidate.objects.filter(election=election, is_active=True)
        .select_related("position")
        .order_by("full_name")
    )

    candidates_by_position: dict[int, list[Candidate]] = {}
    for c in all_candidates:
        candidates_by_position.setdefault(c.position_id, []).append(c)

    # Vote counts: one query
    vote_counts = (
        Vote.objects.filter(election=election)
        .values("position_id", "candidate_id")
        .annotate(cnt=Count("id"))
    )
    vote_count_map = {(row["position_id"], row["candidate_id"]): row["cnt"] for row in vote_counts}

    # Existing votes for this voter/phone: prefetch once for speed
    existing_votes_map: dict[int, Vote] = {}
    if session.voter_id:
        qs = Vote.objects.filter(election=election, voter=session.voter)
    else:
        qs = Vote.objects.filter(election=election, voter_phone=_normalize_phone(session.phone or ""))

    for v in qs.select_related("candidate", "position"):
        existing_votes_map[v.position_id] = v

    position_blocks = []
    for pos in positions:
        candidates = candidates_by_position.get(pos.id, [])
        for c in candidates:
            c.vote_count = vote_count_map.get((pos.id, c.id), 0)

        existing_vote = existing_votes_map.get(pos.id)
        position_blocks.append({"position": pos, "candidates": candidates, "existing_vote": existing_vote})

    return render(
        request,
        "app/ballot.html",
        {"election": election, "session": session, "position_blocks": position_blocks},
    )


def submit_ballot(request, token: str):
    session = get_object_or_404(VotingSession.objects.select_related("election", "voter"), token=token)

    if request.method != "POST":
        return redirect("ballot", token=token)

    if not session.is_valid():
        messages.error(request, "Session expired. Please login again.")
        return redirect("login", election_id=session.election_id)

    # ✅ Safety: block phone session if already voted (prevents session reuse edge cases)
    if not session.voter_id and session.phone:
        if _phone_already_voted(session.election, session.phone):
            messages.error(request, "This phone number has already voted in this election.")
            return redirect("success")

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