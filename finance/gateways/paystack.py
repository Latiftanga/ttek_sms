"""
Paystack Payment Gateway Adapter

Paystack is the leading payment gateway in Ghana and Nigeria.
Documentation: https://paystack.com/docs/api/
"""

import hashlib
import hmac
import json
import requests
from decimal import Decimal
from typing import Dict, Tuple
import logging

from .base import BaseGatewayAdapter, PaymentResponse

logger = logging.getLogger(__name__)


class PaystackAdapter(BaseGatewayAdapter):
    """
    Paystack payment gateway implementation.

    Supports:
    - Card payments
    - Mobile Money (MTN, Vodafone, AirtelTigo)
    - Bank transfers
    - USSD
    """

    @property
    def name(self) -> str:
        return "Paystack"

    @property
    def base_url(self) -> str:
        # Paystack uses same URL for test and live
        return "https://api.paystack.co"

    def _get_headers(self) -> Dict:
        """Get authorization headers."""
        return {
            "Authorization": f"Bearer {self.credentials['secret_key']}",
            "Content-Type": "application/json",
        }

    def verify_credentials(self) -> Tuple[bool, str]:
        """
        Verify Paystack credentials by making a test API call.
        """
        try:
            response = requests.get(
                f"{self.base_url}/balance",
                headers=self._get_headers(),
                timeout=30
            )

            if response.status_code == 200:
                return True, "Credentials verified successfully"
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                data = response.json()
                return False, data.get('message', 'Verification failed')

        except requests.exceptions.Timeout:
            return False, "Connection timeout"
        except requests.exceptions.RequestException as e:
            return False, f"Connection error: {str(e)}"
        except Exception as e:
            logger.exception("Paystack credential verification failed")
            return False, f"Unexpected error: {str(e)}"

    def initialize_payment(
        self,
        amount: Decimal,
        email: str,
        reference: str,
        callback_url: str,
        metadata: Dict = None
    ) -> PaymentResponse:
        """
        Initialize a Paystack transaction.

        This creates a payment link that the user will be redirected to.
        """
        endpoint = f"{self.base_url}/transaction/initialize"

        # Calculate charges
        charge_info = self.calculate_charges(amount)

        payload = {
            "amount": self.format_amount(charge_info['amount_to_charge']),
            "email": email,
            "reference": reference,
            "callback_url": callback_url,
            "currency": "GHS",
            "channels": ["card", "mobile_money", "bank_transfer"],
        }

        if metadata:
            payload["metadata"] = metadata

        self.log_request(endpoint, "POST", payload)

        try:
            response = requests.post(
                endpoint,
                headers=self._get_headers(),
                json=payload,
                timeout=30
            )

            data = response.json()
            self.log_response(endpoint, response.status_code, data)

            if data.get('status'):
                return PaymentResponse(
                    success=True,
                    message="Payment initialized successfully",
                    reference=reference,
                    authorization_url=data['data']['authorization_url'],
                    amount=charge_info['amount_to_charge'],
                    raw_response=data
                )
            else:
                return PaymentResponse(
                    success=False,
                    message=data.get('message', 'Failed to initialize payment'),
                    reference=reference,
                    raw_response=data
                )

        except requests.exceptions.RequestException as e:
            logger.exception("Paystack payment initialization failed")
            return PaymentResponse(
                success=False,
                message=f"Connection error: {str(e)}",
                reference=reference
            )

    def verify_payment(self, reference: str) -> PaymentResponse:
        """
        Verify a Paystack transaction.

        Call this after the user returns from the payment page.
        """
        endpoint = f"{self.base_url}/transaction/verify/{reference}"

        self.log_request(endpoint, "GET")

        try:
            response = requests.get(
                endpoint,
                headers=self._get_headers(),
                timeout=30
            )

            data = response.json()
            self.log_response(endpoint, response.status_code, data)

            if data.get('status') and data['data']['status'] == 'success':
                tx_data = data['data']
                return PaymentResponse(
                    success=True,
                    message="Payment verified successfully",
                    reference=reference,
                    transaction_id=str(tx_data.get('id', '')),
                    amount=self.parse_amount(tx_data['amount']),
                    gateway_fee=self.parse_amount(tx_data.get('fees', 0)),
                    raw_response=data
                )
            else:
                status = data.get('data', {}).get('status', 'unknown')
                return PaymentResponse(
                    success=False,
                    message=f"Payment {status}",
                    reference=reference,
                    raw_response=data
                )

        except requests.exceptions.RequestException as e:
            logger.exception("Paystack payment verification failed")
            return PaymentResponse(
                success=False,
                message=f"Connection error: {str(e)}",
                reference=reference
            )

    def handle_webhook(self, payload: Dict, signature: str) -> PaymentResponse:
        """
        Handle Paystack webhook notification.

        Paystack signs webhooks with HMAC SHA512.
        """
        # Verify signature
        if not self._verify_webhook_signature(payload, signature):
            return PaymentResponse(
                success=False,
                message="Invalid webhook signature"
            )

        event = payload.get('event')
        data = payload.get('data', {})

        if event == 'charge.success':
            reference = data.get('reference', '')
            return PaymentResponse(
                success=True,
                message="Payment successful",
                reference=reference,
                transaction_id=str(data.get('id', '')),
                amount=self.parse_amount(data.get('amount', 0)),
                gateway_fee=self.parse_amount(data.get('fees', 0)),
                raw_response=payload
            )
        elif event == 'charge.failed':
            return PaymentResponse(
                success=False,
                message="Payment failed",
                reference=data.get('reference', ''),
                raw_response=payload
            )
        else:
            return PaymentResponse(
                success=False,
                message=f"Unhandled event: {event}",
                raw_response=payload
            )

    def _verify_webhook_signature(self, payload: Dict, signature: str) -> bool:
        """Verify Paystack webhook signature."""
        webhook_secret = self.credentials.get('webhook_secret', '')
        if not webhook_secret:
            logger.warning("No webhook secret configured")
            return False

        # Paystack sends signature in X-Paystack-Signature header
        payload_string = json.dumps(payload, separators=(',', ':'))
        expected_signature = hmac.new(
            webhook_secret.encode('utf-8'),
            payload_string.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)

    def get_supported_channels(self) -> list:
        """Get list of supported payment channels."""
        return [
            {"id": "card", "name": "Card Payment"},
            {"id": "mobile_money", "name": "Mobile Money"},
            {"id": "bank_transfer", "name": "Bank Transfer"},
            {"id": "ussd", "name": "USSD"},
            {"id": "qr", "name": "QR Code"},
        ]

    def list_banks(self) -> list:
        """Get list of supported banks."""
        try:
            response = requests.get(
                f"{self.base_url}/bank?country=ghana",
                headers=self._get_headers(),
                timeout=30
            )

            data = response.json()
            if data.get('status'):
                return data['data']
            return []

        except Exception as e:
            logger.exception("Failed to fetch banks")
            return []
