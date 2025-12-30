"""
Base Gateway Adapter providing a common interface for all payment gateways.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class PaymentResponse:
    """Standardized payment response object."""

    def __init__(
        self,
        success: bool,
        message: str,
        reference: str = '',
        transaction_id: str = '',
        authorization_url: str = '',
        amount: Decimal = Decimal('0.00'),
        gateway_fee: Decimal = Decimal('0.00'),
        raw_response: Dict = None
    ):
        self.success = success
        self.message = message
        self.reference = reference
        self.transaction_id = transaction_id
        self.authorization_url = authorization_url
        self.amount = amount
        self.gateway_fee = gateway_fee
        self.raw_response = raw_response or {}

    def to_dict(self) -> Dict:
        return {
            'success': self.success,
            'message': self.message,
            'reference': self.reference,
            'transaction_id': self.transaction_id,
            'authorization_url': self.authorization_url,
            'amount': float(self.amount),
            'gateway_fee': float(self.gateway_fee),
        }


class BaseGatewayAdapter(ABC):
    """
    Abstract base class for payment gateway adapters.

    All gateway implementations should inherit from this class
    and implement the required abstract methods.
    """

    def __init__(self, config):
        """
        Initialize the adapter with gateway configuration.

        Args:
            config: PaymentGatewayConfig instance containing credentials
        """
        self.config = config
        self.credentials = config.get_credentials()
        self.is_test_mode = config.is_test_mode
        self._setup()

    def _setup(self):
        """Optional setup hook for subclasses."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the gateway name."""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Return the API base URL (test or live)."""
        pass

    @abstractmethod
    def verify_credentials(self) -> Tuple[bool, str]:
        """
        Verify that the configured credentials are valid.

        Returns:
            Tuple of (is_valid, message)
        """
        pass

    @abstractmethod
    def initialize_payment(
        self,
        amount: Decimal,
        email: str,
        reference: str,
        callback_url: str,
        metadata: Dict = None
    ) -> PaymentResponse:
        """
        Initialize a payment transaction.

        Args:
            amount: Amount in GHS
            email: Customer email
            reference: Unique transaction reference
            callback_url: URL to redirect after payment
            metadata: Additional transaction data

        Returns:
            PaymentResponse with authorization URL
        """
        pass

    @abstractmethod
    def verify_payment(self, reference: str) -> PaymentResponse:
        """
        Verify a payment transaction.

        Args:
            reference: Transaction reference

        Returns:
            PaymentResponse with transaction details
        """
        pass

    @abstractmethod
    def handle_webhook(self, payload: Dict, signature: str) -> PaymentResponse:
        """
        Handle webhook notification from gateway.

        Args:
            payload: Webhook payload
            signature: Request signature for verification

        Returns:
            PaymentResponse with transaction details
        """
        pass

    def calculate_charges(self, amount: Decimal) -> Dict:
        """
        Calculate gateway charges for an amount.

        Args:
            amount: Payment amount in GHS

        Returns:
            Dict with charge breakdown
        """
        percentage_charge = amount * (self.config.transaction_charge_percentage / 100)
        fixed_charge = self.config.transaction_charge_fixed
        total_charge = percentage_charge + fixed_charge

        if self.config.who_bears_charge == 'PARENT':
            amount_to_charge = amount + total_charge
        else:
            amount_to_charge = amount

        return {
            'original_amount': amount,
            'percentage_charge': percentage_charge,
            'fixed_charge': fixed_charge,
            'total_charge': total_charge,
            'amount_to_charge': amount_to_charge,
            'who_bears': self.config.who_bears_charge,
        }

    def log_request(self, endpoint: str, method: str, data: Dict = None):
        """Log API request for debugging."""
        logger.info(f"{self.name} API Request: {method} {endpoint}")
        if data and not self.is_test_mode:
            # Don't log sensitive data in production
            logger.debug(f"Request data: {data}")

    def log_response(self, endpoint: str, status_code: int, response: Dict):
        """Log API response for debugging."""
        logger.info(f"{self.name} API Response: {status_code} from {endpoint}")
        if not self.is_test_mode:
            logger.debug(f"Response data: {response}")

    def format_amount(self, amount: Decimal) -> int:
        """
        Format amount for API (most APIs expect amount in kobo/pesewas).

        Args:
            amount: Amount in GHS

        Returns:
            Amount in pesewas (smallest currency unit)
        """
        return int(amount * 100)

    def parse_amount(self, pesewas: int) -> Decimal:
        """
        Parse amount from API response (pesewas to GHS).

        Args:
            pesewas: Amount in pesewas

        Returns:
            Amount in GHS
        """
        return Decimal(pesewas) / 100
