import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler

# ── In-memory rate limiting ───────────────────────────────────────────
# Simple IP-based rate limiter: max 5 submissions per IP per hour.
# Not persistent across deployments — intentionally lightweight.
_rate_store: dict[str, list[float]] = {}
RATE_LIMIT = 5
RATE_WINDOW = 3600  # 1 hour in seconds


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    timestamps = _rate_store.get(ip, [])
    # Prune old entries
    timestamps = [t for t in timestamps if now - t < RATE_WINDOW]
    _rate_store[ip] = timestamps
    if len(timestamps) >= RATE_LIMIT:
        return True
    timestamps.append(now)
    return False


# ── Validation ────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
MAX_EMAIL_LEN = 254
MAX_MESSAGE_LEN = 5000

VALID_SUBJECTS = {
    "Site Feedback or Suggestion",
    "Report a Problem",
    "Contribute or Collaborate",
    "Share Your ChattyHound Story",
    "Something Else",
}


def _validate(body: dict) -> str | None:
    """Return an error message string, or None if valid."""
    subject = (body.get("subject") or "").strip()
    email = (body.get("email") or "").strip()
    message = (body.get("message") or "").strip()

    if subject not in VALID_SUBJECTS:
        return "Please select a valid subject."

    if email:
        if len(email) > MAX_EMAIL_LEN:
            return "Email address is too long."
        if not EMAIL_RE.match(email):
            return "Please enter a valid email address."

    if not message:
        return "Please enter a message."

    if len(message) > MAX_MESSAGE_LEN:
        return f"Message is too long (max {MAX_MESSAGE_LEN:,} characters)."

    return None


# ── Resend email delivery ─────────────────────────────────────────────
def _send_email(subject: str, email: str, message: str, ip: str) -> dict:
    """Send the contact form email via Resend API. Returns the API response dict."""
    import urllib.request
    import urllib.error

    api_key = os.environ.get("RESEND_API_KEY", "")
    from_email = os.environ.get("CONTACT_FROM_EMAIL", "")
    to_email = os.environ.get("CONTACT_TO_EMAIL", "")

    if not api_key or not from_email or not to_email:
        raise RuntimeError("Missing email configuration.")

    full_subject = f"ChattyHound Contact: {subject}"

    # Build plain-text body
    lines = [
        f"Subject: {subject}",
        f"From: {email or '(anonymous)'}",
        f"IP: {ip}",
        "",
        "Message:",
        "─" * 40,
        message,
        "─" * 40,
    ]
    text_body = "\n".join(lines)

    payload = {
        "from": f"ChattyHound Contact <{from_email}>",
        "to": [to_email],
        "subject": full_subject,
        "text": text_body,
    }

    if email:
        payload["reply_to"] = email

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ChattyHound/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend API error {e.code}: {error_body}")


# ── Handler ───────────────────────────────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type")
        self.end_headers()

    def do_POST(self):
        try:
            # Get client IP
            ip = self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            if not ip:
                ip = self.client_address[0] if self.client_address else "unknown"

            # Rate limit check
            if _is_rate_limited(ip):
                self._send_response(429, {
                    "error": "You've sent too many messages recently. Please try again later."
                })
                return

            # Parse body
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0 or content_length > 50000:
                self._send_response(400, {"error": "Invalid request."})
                return

            raw = self.rfile.read(content_length)
            try:
                body = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_response(400, {"error": "Invalid request format."})
                return

            # Validate
            error = _validate(body)
            if error:
                self._send_response(400, {"error": error})
                return

            subject = body["subject"].strip()
            email = (body.get("email") or "").strip()
            message = body["message"].strip()

            # Send email
            _send_email(subject, email, message, ip)

            self._send_response(200, {"ok": True, "message": "Message sent! Thank you. 🐾"})

        except RuntimeError as e:
            print(f"Contact form error: {e}")
            self._send_response(500, {"error": "Something went wrong sending your message. Please try again."})
        except Exception as e:
            print(f"Contact form unexpected error: {e}")
            self._send_response(500, {"error": "Something went wrong. Please try again."})

    def _send_response(self, status: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress default stderr logging
        pass
