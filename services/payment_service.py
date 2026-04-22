"""
Payment service — Razorpay order creation and signature verification.

SETUP:
  1. Create account at razorpay.com (free)
  2. Dashboard → Settings → API Keys → Generate Test Key
  3. Add to .env:
       RAZORPAY_KEY_ID=rzp_test_XXXXXXXXXXXXXXXX
       RAZORPAY_KEY_SECRET=XXXXXXXXXXXXXXXXXXXXXXXX
  4. For production, generate Live Key and swap the values.
"""
import hmac
import hashlib
import logging

from config import settings

logger = logging.getLogger(__name__)

PLAN_AMOUNTS = {
    "solo":  39900,   # ₹399 in paise — Tier 1 Solo plan
    "basic": 29900,   # ₹299 in paise — legacy (existing subscribers)
    "pro":   49900,   # ₹499 in paise — legacy (existing subscribers)
}


def _razorpay_client():
    """Return a Razorpay client, or None if credentials are missing."""
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        return None
    try:
        import razorpay
        return razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
    except Exception as exc:
        logger.error(f"Razorpay client init failed: {exc}")
        return None


def create_order(plan: str) -> dict:
    """Create a Razorpay order for the given plan.

    Returns dict with keys: order_id, amount, currency, key_id.
    Returns {"error": "..."} on failure.
    """
    if plan not in PLAN_AMOUNTS:
        return {"error": f"Unknown plan: {plan}"}

    client = _razorpay_client()
    if not client:
        return {"error": "Payment gateway not configured. Add Razorpay keys to .env"}

    try:
        order = client.order.create({
            "amount":   PLAN_AMOUNTS[plan],
            "currency": "INR",
            "notes":    {"plan": plan, "product": "ClinicOS"},
        })
        return {
            "order_id": order["id"],
            "amount":   order["amount"],
            "currency": order["currency"],
            "key_id":   settings.RAZORPAY_KEY_ID,
            "plan":     plan,
        }
    except Exception as exc:
        logger.error(f"Razorpay order creation failed: {exc}")
        return {"error": str(exc)}


def verify_signature(payment_id: str, order_id: str, signature: str) -> bool:
    """Verify Razorpay payment signature using HMAC-SHA256.

    Razorpay signs: "{order_id}|{payment_id}" with the key secret.
    Returns True only if signature matches — NEVER activate plan without this check.
    """
    if not settings.RAZORPAY_KEY_SECRET:
        return False
    try:
        msg      = f"{order_id}|{payment_id}".encode()
        expected = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            msg,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception as exc:
        logger.error(f"Signature verification error: {exc}")
        return False
