"""Order-service settings, on top of the shared ones from farm_common."""

from decimal import Decimal
from functools import lru_cache

from farm_common.settings import ServiceSettings


class OrderSettings(ServiceSettings):
    # Base URL of the catalog service, used for the internal stock reserve/release calls.
    catalog_url: str = "http://catalog:8000"
    # Flat delivery fee added to every per-farm order.
    # TODO(M1): assumed flat fee; replace when a pricing rule exists.
    delivery_fee_per_order: Decimal = Decimal("20.00")
    # Mock payments always succeed, except when the payment intent amount equals this value.
    # Use it in demos and tests to show the payment-failed path.
    mock_payment_fail_amount: Decimal | None = None
    # Harvest orders (V2, #24). TODO(M1): both numbers are assumptions, see docs/m1-assumptions.md.
    # The deposit is this share of the crop price; used only when land does not send the price.
    harvest_deposit_share: Decimal = Decimal("0.20")
    # BUYBACK credits the customer this share of the harvest value.
    buyback_rate: Decimal = Decimal("0.90")
    # A DEPOSIT intent is paid the moment it is created. Turn off to settle it with the webhook.
    mock_auto_settle: bool = True
    # Shared secret of POST /orders/payments/webhook (header X-Webhook-Secret).
    payment_webhook_secret: str = "dev-webhook-secret"  # noqa: S105 (a mock gateway, no real secret)
    # Turn off the RabbitMQ consumers and the outbox relay (e.g. for local runs without a broker).
    events_enabled: bool = True


@lru_cache
def get_order_settings() -> OrderSettings:
    return OrderSettings()
