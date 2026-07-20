import logging
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.config import settings
from app.db import User, get_session

router = APIRouter(prefix="/api/billing", tags=["billing"])
logger = logging.getLogger(__name__)

PLAN_LIMITS = {"free": 3, "pro": 50, "business": -1}


class CheckoutRequest(BaseModel):
    plan: str


@router.get("/usage")
def get_usage(current_user: User = Depends(get_current_user)):
    """Get user's current billing plan and analysis usage details."""
    plan = current_user.plan or "free"
    limit = PLAN_LIMITS.get(plan.lower(), 3)
    analyses = current_user.analyses_this_month or 0

    if limit == -1:
        remaining = -1
    else:
        remaining = max(0, limit - analyses)

    return {
        "plan": plan,
        "analyses_this_month": analyses,
        "limit": limit,
        "remaining": remaining,
    }


@router.post("/checkout")
def create_checkout(data: CheckoutRequest, current_user: User = Depends(get_current_user)):
    """Create a Stripe Checkout session for upgrading subscription."""
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY

    plan = data.plan.lower()
    if plan not in ["pro", "business"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan. Must be 'pro' or 'business'.",
        )

    price_id = (
        settings.STRIPE_PRICE_PRO_MONTHLY
        if plan == "pro"
        else settings.STRIPE_PRICE_BUSINESS_MONTHLY
    )

    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe price ID is not configured on the server.",
        )

    try:
        checkout_kwargs = {
            "payment_method_types": ["card"],
            "line_items": [{"price": price_id, "quantity": 1}],
            "mode": "subscription",
            "success_url": f"{settings.APP_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{settings.APP_URL}/cancel",
            "metadata": {
                "user_id": str(current_user.id),
                "plan": plan,
            },
        }

        if current_user.stripe_customer_id:
            checkout_kwargs["customer"] = current_user.stripe_customer_id
        else:
            checkout_kwargs["customer_email"] = current_user.email

        checkout_session = stripe.checkout.Session.create(**checkout_kwargs)
        return {"url": checkout_session.url}

    except Exception as e:
        logger.error("Error creating Stripe checkout session: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create checkout session: {str(e)}",
        )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
    db_session: Session = Depends(get_session),
):
    """Handle incoming Stripe webhook events."""
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY

    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.warning("Invalid webhook payload: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.warning("Invalid webhook signature: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")
    except Exception as e:
        logger.error("Error verifying Stripe webhook: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification error")

    event_type = event["type"]
    event_data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id_str = event_data.get("metadata", {}).get("user_id")
        plan = event_data.get("metadata", {}).get("plan")
        customer_id = event_data.get("customer")

        if user_id_str:
            user_id = int(user_id_str)
            user = db_session.get(User, user_id)
            if user:
                user.plan = plan
                user.analyses_this_month = 0
                if customer_id:
                    user.stripe_customer_id = customer_id
                db_session.add(user)
                db_session.commit()
                logger.info("Successfully upgraded user %d to plan %s", user_id, plan)

    elif event_type == "invoice.paid":
        customer_id = event_data.get("customer")
        if customer_id:
            statement = select(User).where(User.stripe_customer_id == customer_id)
            user = db_session.exec(statement).first()
            if user:
                user.analyses_this_month = 0
                db_session.add(user)
                db_session.commit()
                logger.info("Reset monthly usage for customer %s", customer_id)

    return {"status": "success"}


@router.post("/portal")
def create_portal(current_user: User = Depends(get_current_user)):
    """Create a Stripe Customer Portal session for managing subscription."""
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY

    if not current_user.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription or customer profile found.",
        )

    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=settings.APP_URL,
        )
        return {"url": portal_session.url}
    except Exception as e:
        logger.error("Error creating Stripe portal session: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create portal session: {str(e)}",
        )
