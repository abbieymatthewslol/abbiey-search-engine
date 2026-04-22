"""Auth blueprint — signup, email verification, login, logout, Supabase OAuth.

All view functions were lifted verbatim from `app.py` with the following changes:

- Decorators switched from `@app.route(...)` / `@limiter.limit(...)` to
  `@auth_bp.route(...)` (rate limits are re-applied in `app.py` through
  the module-level `RATE_LIMITS` map).
- Module-level helpers that still live in `app.py` are resolved lazily via
  `_app()` to avoid a circular import at package-load time.
- Endpoint names preserve the original function names — flask-limiter and
  `url_for` both pick up the blueprint-qualified form (`auth.signup`,
  `auth.login`, ...), so templates reference the dotted form.
"""
from __future__ import annotations

import hmac

from flask import (
    Blueprint,
    flash,
    get_flashed_messages,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

auth_bp = Blueprint("auth", __name__)


def _app():
    """Return the `app` module, imported lazily to avoid circular imports."""
    import app as _app_mod
    return _app_mod


# ---------------------------------------------------------------------------
# Sign up
# ---------------------------------------------------------------------------


@auth_bp.route("/signup", methods=["GET", "POST"], endpoint="signup")
def signup():
    a = _app()
    uid = session.get("user_id")
    if uid:
        u = a._get_user_by_id(uid)
        if u and a._user_is_email_verified(u):
            return redirect(url_for("profile"))
        session.pop("user_id", None)

    sb_ctx = {
        "supabase_url": a._SUPABASE_URL,
        "supabase_anon_key": a._SUPABASE_ANON_KEY,
        "supabase_auth": a._SUPABASE_AUTH_ENABLED,
    }

    if request.method == "GET":
        return render_template("signup.html", **sb_ctx)

    try:
        return a._signup_process_post()
    except Exception:
        a.logger.exception("signup_post_unhandled")
        return render_template(
            "signup.html",
            errors=[
                "Something went wrong while creating your account. Please try again. "
                "If you already registered, sign in instead."
            ],
            username=(request.form.get("username") or "").strip(),
            email=(request.form.get("email") or "").strip().lower(),
            phone=(request.form.get("phone") or "").strip(),
            **sb_ctx,
        )


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


@auth_bp.route("/verify-email", methods=["GET", "POST"], endpoint="verify_email")
def verify_email():
    a = _app()
    token = (request.args.get("token") or "").strip()
    if request.method == "GET" and token:
        rows = a._users_execute("SELECT * FROM users WHERE verify_token=? LIMIT 1", [token])
        if not rows:
            return render_template(
                "verify_email.html",
                errors=["That link is invalid or has already been used."],
            )
        u = rows[0]
        if a._user_is_email_verified(u):
            return render_template(
                "verify_email.html",
                errors=["That account is already verified. You can sign in."],
                verified_hint=True,
            )
        if not a._ts_still_valid(u.get("verify_token_expires")):
            em = (u.get("email") or "").strip().lower()
            return render_template(
                "verify_email.html",
                errors=["That link has expired. Enter your email below and request a new code."],
                email=em,
            )
        try:
            uid_ok = int(u["id"])
        except (TypeError, ValueError):
            return render_template("verify_email.html", errors=["Something went wrong. Try again."])
        a._mark_email_verified(uid_ok)
        session.permanent = True
        session["user_id"] = uid_ok
        flash("welcome", "welcome")
        r = redirect(url_for("index") + "?welcome=1")
        a._set_welcome_seen_cookie(r)
        return r

    if request.method == "POST":
        email_in = (request.form.get("email") or "").strip().lower()
        code = (request.form.get("code") or "").strip().replace(" ", "")
        errors = []
        if not email_in or "@" not in email_in:
            errors.append("Enter the email you used to sign up.")
        if not code or not code.isdigit() or len(code) != 6:
            errors.append("Enter the 6-digit code from your email.")
        if errors:
            return render_template("verify_email.html", errors=errors, email=email_in)
        rows = a._users_execute(
            "SELECT * FROM users WHERE LOWER(email)=LOWER(?) LIMIT 1", [email_in]
        )
        if not rows:
            return render_template(
                "verify_email.html",
                errors=["No account found for that email. Check the address or sign up again."],
                email=email_in,
            )
        u = rows[0]
        if a._user_is_email_verified(u):
            return render_template(
                "verify_email.html",
                errors=["That email is already verified. You can sign in."],
                email=email_in,
                verified_hint=True,
            )
        if not a._ts_still_valid(u.get("otp_expires")):
            return render_template(
                "verify_email.html",
                errors=["That code has expired. Request a new code below."],
                email=email_in,
            )
        try:
            uid_ok = int(u["id"])
        except (TypeError, ValueError):
            return render_template(
                "verify_email.html", errors=["Something went wrong. Try again."], email=email_in
            )
        expect = (u.get("otp_code_hash") or "").strip()
        if not expect or not hmac.compare_digest(expect, a._otp_digest(uid_ok, code)):
            return render_template(
                "verify_email.html",
                errors=["That code is not correct."],
                email=email_in,
            )
        a._mark_email_verified(uid_ok)
        session.permanent = True
        session["user_id"] = uid_ok
        flash("welcome", "welcome")
        r = redirect(url_for("index") + "?welcome=1")
        a._set_welcome_seen_cookie(r)
        return r

    email_q = (request.args.get("email") or "").strip().lower()
    return render_template(
        "verify_email.html",
        email=email_q,
        from_signup=(request.args.get("new") == "1"),
        resent=(request.args.get("resent") == "1"),
        email_failed=(request.args.get("email_failed") == "1"),
    )


@auth_bp.route("/verify-email/resend", methods=["POST"], endpoint="verify_email_resend")
def verify_email_resend():
    a = _app()
    email_in = (request.form.get("email") or "").strip().lower()
    if not email_in or "@" not in email_in:
        return render_template(
            "verify_email.html",
            errors=["Enter your email address."],
            email=email_in,
        )
    rows = a._users_execute(
        "SELECT * FROM users WHERE LOWER(email)=LOWER(?) LIMIT 1", [email_in]
    )
    if not rows or a._user_is_email_verified(rows[0]):
        return redirect(url_for("auth.verify_email", email=email_in, resent="1"))
    u = rows[0]
    try:
        uid_ok = int(u["id"])
    except (TypeError, ValueError):
        return redirect(url_for("auth.verify_email", email=email_in, resent="1"))
    try:
        otp, vtok = a._set_verification_challenge(uid_ok)
    except Exception:
        a.logger.exception("verify_resend_challenge_failed")
        return render_template(
            "verify_email.html",
            errors=["Could not send a new code right now. Try again in a few minutes."],
            email=email_in,
        )
    disp = u.get("display_name") or u.get("username") or "there"
    sent = a._send_signup_verification_email(email_in, disp, otp, vtok)
    rq = {"email": email_in, "resent": "1"}
    if not sent:
        rq["email_failed"] = "1"
    return redirect(url_for("auth.verify_email", **rq))


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------


@auth_bp.route("/login", methods=["GET", "POST"], endpoint="login")
def login():
    a = _app()
    uid = session.get("user_id")
    if uid:
        u = a._get_user_by_id(uid)
        if u and a._user_is_email_verified(u):
            return redirect(url_for("profile"))
        session.pop("user_id", None)

    sb_ctx = {
        "supabase_url": a._SUPABASE_URL,
        "supabase_anon_key": a._SUPABASE_ANON_KEY,
        "supabase_auth": a._SUPABASE_AUTH_ENABLED,
    }

    if request.method == "GET":
        oauth_device_msg = None
        msgs = get_flashed_messages(category_filter=["oauth_device"])
        if msgs:
            oauth_device_msg = msgs[0]
        return render_template(
            "login.html",
            next=request.args.get("next", ""),
            oauth_device_error=oauth_device_msg,
            **sb_ctx,
        )

    identifier = request.form.get("identifier", "").strip()
    password = request.form.get("password", "")
    next_url = request.form.get("next", "")

    try:
        user = a._get_user_by_login(identifier)
    except Exception:
        a.logger.exception("login_lookup_failed")
        return render_template(
            "login.html",
            error="Something went wrong. Please try again in a moment.",
            identifier=identifier,
            next=next_url,
            **sb_ctx,
        )
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template(
            "login.html",
            error="Invalid email/username or password.",
            identifier=identifier,
            next=next_url,
            **sb_ctx,
        )
    if not a._user_is_email_verified(user):
        return render_template(
            "login.html",
            error=(
                "Please verify your email before signing in. Check your inbox for a 6-digit "
                "code and link, or use the verification page to request a new email."
            ),
            identifier=identifier,
            next=next_url,
            verify_email_hint=True,
            **sb_ctx,
        )
    session.permanent = True
    try:
        session["user_id"] = int(user["id"])
    except (TypeError, ValueError):
        session["user_id"] = user["id"]
    return redirect(a._safe_redirect_url(next_url))


@auth_bp.route("/logout", methods=["GET", "POST"], endpoint="logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Supabase Auth callback (client-side PKCE flow completes here)
# ---------------------------------------------------------------------------


@auth_bp.route("/auth/callback", methods=["POST"], endpoint="auth_callback")
def auth_callback():
    """Client-side Supabase Auth sends us the session after sign-in/sign-up.

    Requires a valid Supabase ``access_token`` (server-validated via GoTrue
    ``/auth/v1/user``). Google OAuth accounts are bound to the first browser
    profile (httpOnly device cookie) and to the Google OIDC subject stored
    at signup; other devices or Google accounts are rejected.
    """
    import secrets
    a = _app()

    if not a._SUPABASE_AUTH_ENABLED:
        return jsonify({"error": "Supabase Auth not configured"}), 400
    data = request.get_json(silent=True) or {}
    access_token = (data.get("access_token") or "").strip()
    if not access_token:
        return jsonify({"error": "invalid_token", "message": "Missing access token."}), 401

    sb_user = a._supabase_fetch_user_from_access_token(access_token)
    if not sb_user:
        return (
            jsonify(
                {"error": "invalid_token", "message": "Could not validate session with Supabase."}
            ),
            401,
        )

    token_email = (sb_user.get("email") or "").strip().lower()
    if not token_email or "@" not in token_email:
        return jsonify({"error": "invalid_token", "message": "No email on Supabase account."}), 401

    client_email = (data.get("email") or "").strip().lower()
    if client_email and client_email != token_email:
        return jsonify({"error": "email_mismatch"}), 400

    display_name = (data.get("display_name") or "").strip() or (
        (sb_user.get("user_metadata") or {}).get("full_name") or ""
    ).strip()
    phone_raw = (data.get("phone") or "").strip()
    phone_e164 = None
    if phone_raw:
        phone_e164 = a._normalize_e164_phone(phone_raw)
        if not phone_e164:
            return (
                jsonify(
                    {
                        "error": "Invalid phone number. Use international format "
                        "(e.g. +1 555 123 4567)."
                    }
                ),
                400,
            )

    supabase_uid = (sb_user.get("id") or "").strip()
    google_sub = a._google_sub_from_supabase_user(sb_user)

    try:
        uid = a._sync_supabase_auth_user(token_email, display_name, phone_e164)
    except Exception:
        a.logger.exception("auth_callback_sync_failed")
        return jsonify({"error": "Could not sync account"}), 500
    if not uid:
        return jsonify({"error": "Could not create account"}), 500
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return jsonify({"error": "Could not create account"}), 500

    new_device_secret: str | None = None
    existing = a._oauth_binding_row_for_user(uid)

    if existing:
        if not google_sub:
            return (
                jsonify(
                    {
                        "error": "google_required",
                        "message": (
                            "This account was registered with Google on a specific device. "
                            "Sign in with Google on that device."
                        ),
                    }
                ),
                403,
            )
        if (existing.get("google_sub") or "").strip() != google_sub:
            return (
                jsonify(
                    {
                        "error": "wrong_google_account",
                        "message": (
                            "Use the same Google account you used when you first signed up "
                            "for this site."
                        ),
                    }
                ),
                403,
            )
        stored_sid = (existing.get("supabase_auth_uid") or "").strip()
        if stored_sid and supabase_uid and stored_sid != supabase_uid:
            return (
                jsonify(
                    {
                        "error": "identity_mismatch",
                        "message": "Supabase user does not match this profile.",
                    }
                ),
                403,
            )
        if not a._oauth_device_cookie_matches_binding(uid, existing):
            return (
                jsonify(
                    {
                        "error": "device_mismatch",
                        "message": (
                            "This profile is bound to another device or browser profile "
                            "(the first place you completed Google sign-in)."
                        ),
                    }
                ),
                403,
            )
    elif google_sub and supabase_uid:
        new_device_secret = secrets.token_urlsafe(32)
        try:
            a._users_execute(
                "INSERT INTO oauth_user_binding (user_id, supabase_auth_uid, google_sub, "
                "device_secret_hash) VALUES (?,?,?,?)",
                [
                    uid,
                    supabase_uid,
                    google_sub,
                    a._hash_auth_device_secret(new_device_secret),
                ],
            )
        except Exception:
            a.logger.exception("oauth_user_binding_insert_failed")
            return jsonify({"error": "Could not finalize device binding"}), 500

    session.permanent = True
    session["user_id"] = uid
    resp = jsonify({"ok": True, "user_id": uid})
    a._set_welcome_seen_cookie(resp)
    if new_device_secret:
        a._set_auth_device_cookie(resp, new_device_secret)
    return resp


@auth_bp.route("/auth/confirm", endpoint="auth_confirm")
def auth_confirm():
    """Landing page after Supabase OAuth redirect (e.g. Google). JS picks up the session."""
    a = _app()
    if not a._SUPABASE_AUTH_ENABLED:
        return redirect(url_for("auth.login"))
    return render_template("auth_confirm.html")


@auth_bp.route("/forgot-password", endpoint="forgot_password")
def forgot_password():
    """Password reset page — uses Supabase Auth resetPasswordForEmail."""
    return render_template("forgot_password.html")


# Rate limits applied by `app.py` once this blueprint is registered.
RATE_LIMITS = {
    signup: "100/hour",
    verify_email: "120/hour",
    verify_email_resend: "8/hour",
    login: "120/hour",
    auth_callback: "60/minute",
}
