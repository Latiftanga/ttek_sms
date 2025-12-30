"""
Payment Gateway Adapters for Ghana-focused payment processing.

Supported gateways:
- Paystack (recommended for Ghana)
- Flutterwave
- Hubtel (Ghana-only)
"""

from .base import BaseGatewayAdapter
from .paystack import PaystackAdapter
from .flutterwave import FlutterwaveAdapter
from .hubtel import HubtelAdapter


def get_gateway_adapter(config):
    """
    Factory function to get the appropriate gateway adapter.

    Args:
        config: PaymentGatewayConfig instance

    Returns:
        BaseGatewayAdapter subclass instance
    """
    gateway_name = config.gateway.name

    adapters = {
        'PAYSTACK': PaystackAdapter,
        'FLUTTERWAVE': FlutterwaveAdapter,
        'HUBTEL': HubtelAdapter,
    }

    adapter_class = adapters.get(gateway_name)
    if not adapter_class:
        raise ValueError(f"Unsupported gateway: {gateway_name}")

    return adapter_class(config)


__all__ = [
    'BaseGatewayAdapter',
    'PaystackAdapter',
    'FlutterwaveAdapter',
    'HubtelAdapter',
    'get_gateway_adapter',
]
