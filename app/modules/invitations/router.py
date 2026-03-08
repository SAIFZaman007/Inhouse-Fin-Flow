"""
app/modules/invitations/router.py
====================================
Invitation-based user onboarding — replaces the old temp-password user creation.

Endpoints:
  POST   /api/v1/users/invitations              → Send invitation email     [CEO only]
  GET    /api/v1/users/invitations              → List invitations          [CEO only]
  POST   /api/v1/users/invitations/{id}/resend → Resend invitation email   [CEO only]
  DELETE /api/v1/users/invitations/{id}         → Cancel invitation         [CEO only]
  GET    /api/v1/users/invitations/accept-form  → HTML acceptance page      [PUBLIC]
  POST   /api/v1/users/invitations/accept       → Create account from token [PUBLIC]

Mounted under the /users router so all invitation management lives at /api/v1/users/...
"""
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from prisma import Prisma
from prisma.models import User

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import CEO_ONLY

from .schema import AcceptInvitation, InviteCreate
from .service import (
    accept_invitation,
    cancel_invitation,
    create_invitation,
    list_invitations,
    resend_invitation,
)

router = APIRouter(prefix="/invitations")
settings = get_settings()


# ── CEO-protected invitation management ───────────────────────────────────────

@router.post(
    "",
    status_code=201,
    summary="Invite a team member — sends email with secure link",
)
async def invite_user(
    body: InviteCreate,
    request: Request,
    db: Prisma = Depends(get_db),
    _: User = Depends(CEO_ONLY),
):
    """
    CEO sends an email invitation to a new team member.
    The invitee receives a secure link and sets their own password.
    No temp password is ever created or emailed.
    """
    base_url = str(request.base_url)
    return await create_invitation(db, body, _.id, base_url)


@router.get("", summary="List all invitations (paginated)")
async def get_invitations(
    page:      int         = Query(1, ge=1),
    page_size: int         = Query(20, ge=1, le=100),
    status:    str | None  = Query(None, description="Filter: PENDING | ACCEPTED | EXPIRED | CANCELLED"),
    db:        Prisma      = Depends(get_db),
    _:         User        = Depends(CEO_ONLY),
):
    return await list_invitations(db, page, page_size, status)


@router.post(
    "/{invitation_id}/resend",
    summary="Resend invitation email (same token, fresh email)",
)
async def resend(
    invitation_id: str,
    request:       Request,
    db:            Prisma = Depends(get_db),
    current_user:  User   = Depends(CEO_ONLY),
):
    base_url = str(request.base_url)
    return await resend_invitation(db, invitation_id, current_user.id, base_url)


@router.delete(
    "/{invitation_id}",
    status_code=200,
    summary="Cancel a pending invitation",
)
async def cancel(
    invitation_id: str,
    db: Prisma = Depends(get_db),
    _: User    = Depends(CEO_ONLY),
):
    return await cancel_invitation(db, invitation_id)


# ── Public endpoints — no auth ────────────────────────────────────────────────

@router.get(
    "/accept-form",
    response_class=HTMLResponse,
    include_in_schema=False,   # Don't show in Swagger 
)
async def accept_form(
    request: Request,
    token: str = Query(..., description="Invitation token from email link"),
):
    """
    Serves a browser-ready HTML form when the invitee clicks the link in their email.
    On submit → calls POST /accept.
    On success → shows login link.
    PUBLIC — no auth required.
    """
    base_url  = str(request.base_url).rstrip("/")
    accept_api = f"{base_url}/api/v1/users/invitations/accept"
    login_url  = f"{base_url}/docs"   # swap to frontend login URL when available

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Accept Invitation — {settings.APP_NAME}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin:0; padding:0; }}
    body {{
      min-height: 100vh; display: flex; align-items: center; justify-content: center;
      background: linear-gradient(135deg, #e8eeff 0%, #f4f4f7 100%);
      font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; padding: 24px;
    }}
    .card {{ background:#fff; border-radius:12px; box-shadow:0 4px 24px rgba(0,0,0,.10);
             width:100%; max-width:440px; overflow:hidden; }}
    .card-header {{
      background: linear-gradient(135deg,#1F3864,#2d5be3);
      padding: 32px 40px 24px; text-align: center;
    }}
    .card-header h1 {{ color:#fff; font-size:20px; font-weight:700; letter-spacing:-.3px; }}
    .card-header p  {{ color:#aac4ff; font-size:13px; margin-top:6px; }}
    .card-body {{ padding:32px 40px 28px; }}
    .form-group {{ margin-bottom:18px; }}
    label {{ display:block; font-size:13px; font-weight:600; color:#444; margin-bottom:6px; }}
    input  {{
      width:100%; padding:11px 14px; border:1.5px solid #ddd; border-radius:6px;
      font-size:14px; color:#222; outline:none; transition:border-color .2s;
    }}
    input:focus {{ border-color:#2d5be3; }}
    .hint {{ font-size:11px; color:#999; margin-top:4px; }}
    button[type=submit] {{
      width:100%; padding:13px; border:none; border-radius:6px; cursor:pointer;
      background: linear-gradient(135deg,#1F3864,#2d5be3);
      color:#fff; font-size:15px; font-weight:600; margin-top:8px;
      letter-spacing:.3px; transition:opacity .2s;
    }}
    button:hover {{ opacity:.9; }}
    button:disabled {{ opacity:.6; cursor:not-allowed; }}
    .msg {{ margin-top:16px; padding:12px 16px; border-radius:6px; font-size:13px; display:none; }}
    .success {{ background:#f0fdf4; color:#166534; border:1px solid #bbf7d0; display:block; }}
    .error   {{ background:#fef2f2; color:#991b1b; border:1px solid #fecaca; display:block; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="card-header">
      <h1>{settings.APP_NAME}</h1>
      <p>Set up your account to get started</p>
    </div>
    <div class="card-body">
      <form id="acceptForm">
        <input type="hidden" id="token" value="{token}" />
        <div class="form-group">
          <label for="name">Full Name</label>
          <input type="text" id="name" placeholder="Your full name" required autocomplete="name"/>
        </div>
        <div class="form-group">
          <label for="password">Password</label>
          <input type="password" id="password" placeholder="Min 8 chars, include a number" required/>
          <p class="hint">Minimum 8 characters with at least one digit.</p>
        </div>
        <div class="form-group">
          <label for="confirm">Confirm Password</label>
          <input type="password" id="confirm" placeholder="Repeat your password" required/>
        </div>
        <button type="submit" id="submitBtn">Create My Account &rarr;</button>
        <div class="msg" id="msg"></div>
      </form>
    </div>
  </div>
  <script>
    const ACCEPT_URL = "{accept_api}";
    const LOGIN_URL  = "{login_url}";

    document.getElementById('acceptForm').addEventListener('submit', async (e) => {{
      e.preventDefault();
      const btn  = document.getElementById('submitBtn');
      const msg  = document.getElementById('msg');
      const name = document.getElementById('name').value.trim();
      const pw   = document.getElementById('password').value;
      const con  = document.getElementById('confirm').value;
      const tok  = document.getElementById('token').value;

      msg.className = 'msg'; msg.textContent = '';

      if (pw !== con) {{
        msg.textContent = 'Passwords do not match.';
        msg.className = 'msg error'; return;
      }}
      if (pw.length < 8 || !/\\d/.test(pw)) {{
        msg.textContent = 'Password must be ≥8 characters and include at least one digit.';
        msg.className = 'msg error'; return;
      }}

      btn.disabled = true; btn.textContent = 'Creating account…';

      try {{
        const res  = await fetch(ACCEPT_URL, {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{ invite_token: tok, name, password: pw }})
        }});
        const data = await res.json();
        if (res.ok) {{
          msg.innerHTML = '🎉 Account created! <a href="' + LOGIN_URL + '">Click here to log in →</a>';
          msg.className = 'msg success';
          btn.style.display = 'none';
          setTimeout(() => {{ window.location.href = LOGIN_URL; }}, 3000);
        }} else {{
          msg.textContent = data.detail || 'Something went wrong. Please try again.';
          msg.className = 'msg error';
          btn.disabled = false; btn.textContent = 'Create My Account →';
        }}
      }} catch (err) {{
        msg.textContent = 'Network error. Please check your connection.';
        msg.className = 'msg error';
        btn.disabled = false; btn.textContent = 'Create My Account →';
      }}
    }});
  </script>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)


@router.post("/accept", summary="Accept invitation and create account [PUBLIC]")
async def accept(
    body: AcceptInvitation,
    db: Prisma = Depends(get_db),
):
    """
    PUBLIC — no auth required. Secured by one-time invitation token.
    Creates the user account and marks the invitation as ACCEPTED.
    """
    return await accept_invitation(db, body)