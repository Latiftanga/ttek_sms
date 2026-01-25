"""
Flutterwave Payment Gateway Adapter

Flutterwave supports payments across Africa including Ghana.
Documentation: https://developer.flutterwave.com/docs
"""

import hmac
import requests
from decimal import Decimal
from typing import Dict, Tuple
import logging

from .base import BaseGatewayAdapter, PaymentResponse

logger = logging.getLogger(__name__)


class FlutterwaveAdapter(BaseGatewayAdapter):
    """
    Flutterwave payment gateway implementation.

    Supports:
    - Card payments
    - Mobile Money (MTN, Vodafone, AirtelTigo)
    - Bank transfers
    - USSD
    """

    @property
    def name(self) -> str:
        return "Flutterwave"

    @property
    def base_url(self) -> str:
        return "https://api.flutterwave.com/v3"

    def _get_headers(self) -> Dict:
        """Get authorization headers."""
        return {
            "Authorization": f"Bearer {self.credentials['secret_key']}",
            "Content-Type": "application/json",
        }

    def verify_credentials(self) -> Tuple[bool, str]:
        """
        Verify Flutterwave credentials by making a test API call.
        """
        try:
            response = requests.get(
                f"{self.base_url}/balances/GHS",
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
            logger.exception("Flutterwave credential verification failed")
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
        Initialize a Flutterwave transaction using Standard Payment.
        """
        endpoint = f"{self.base_url}/payments"

        # Calculate charges
        charge_info = self.calculate_charges(amount)

        payload = {
            "tx_ref": reference,
            "amount": str(charge_info['amount_to_charge']),
            "currency": "GHS",
            "redirect_url": callback_url,
            "payment_options": "card,mobilemoneyghana,ussd",
            "customer": {
                "email": email,
            },
            "customizations": {
                "title": "School Fee Payment",
                "description": "Payment for school fees",
            }
        }

        if metadata:
            payload["meta"] = metadata

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

            if data.get('status') == 'success':
                return PaymentResponse(
                    success=True,
                    message="Payment initialized successfully",
                    reference=reference,
                    authorization_url=data['data']['link'],
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
            logger.exception("Flutterwave payment initialization failed")
            return PaymentResponse(
                success=False,
                message=f"Connection error: {str(e)}",
                reference=reference
            )

    def verify_payment(self, reference: str) -> PaymentResponse:
        """
        Verify a Flutterwave transaction by tx_ref.
        """
        endpoint = f"{self.base_url}/transactions/verify_by_reference"

        self.log_request(endpoint, "GET", {"tx_ref": reference})

        try:
            response = requests.get(
                endpoint,
                headers=self._get_headers(),
                params={"tx_ref": reference},
                timeout=30
            )

            data = response.json()
            self.log_response(endpoint, response.status_code, data)

            if data.get('status') == 'success' and data['data']['status'] == 'successful':
                tx_data = data['data']
                return PaymentResponse(
                    success=True,
                    message="Payment verified successfully",
                    reference=reference,
                    transaction_id=str(tx_data.get('id', '')),
                    amount=Decimal(str(tx_data.get('amount', 0))),
                    gateway_fee=Decimal(str(tx_data.get('app_fee', 0))),
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
            logger.exception("Flutterwave payment verification failed")
            return PaymentResponse(
                success=False,
                message=f"Connection error: {str(e)}",
                reference=reference
            )

    def handle_webhook(self, payload: Dict, signature: str) -> PaymentResponse:
        """
        Handle Flutterwave webhook notification.

        Flutterwave uses verif-hash for webhook verification.
        """
        # Verify signature
        if not self._verify_webhook_signature(signature):
            return PaymentResponse(
                success=False,
                message="Invalid webhook signature"
            )

        event = payload.get('event')
        data = payload.get('data', {})

        if event == 'charge.completed' and data.get('status') == 'successful':
            reference = data.get('tx_ref', '')
            return PaymentResponse(
                success=True,
                message="Payment successful",
                reference=reference,
                transaction_id=str(data.get('id', '')),
                amount=Decimal(str(data.get('amount', 0))),
                gateway_fee=Decimal(str(data.get('app_fee', 0))),
                raw_response=payload
            )
        elif event == 'charge.completed':
            return PaymentResponse(
                success=False,
                message=f"Payment {data.get('status', 'failed')}",
                reference=data.get('tx_ref', ''),
                raw_response=payload
            )
        else:
            return PaymentResponse(
                success=False,
                message=f"Unhandled event: {event}",
                raw_response=payload
            )

    def _verify_webhook_signature(self, signature: str) -> bool:
        """Verify Flutterwave webhook signature."""
        webhook_secret = self.credentials.get('webhook_secret', '')
        if not webhook_secret:
            logger.warning("No webhook secret configured")
            return False

        # Flutterwave sends the secret hash in verif-hash header
        return hmac.compare_digest(webhook_secret, signature)

    def get_supported_channels(self) -> list:
        """Get list of supported payment channels."""
        return [
            {"id": "card", "name": "Card Payment"},
            {"id": "mobilemoneyghana", "name": "Mobile Money (Ghana)"},
            {"id": "ussd", "name": "USSD"},
            {"id": "bank_transfer", "name": "Bank Transfer"},
        ]

    def charge_mobile_money(
        self,
        amount: Decimal,
        phone: str,
        network: str,
        email: str,
        reference: str,
        metadata: Dict = None
    ) -> PaymentResponse:
        """
        Charge mobile money directly.

        Args:
            amount: Amount in GHS
            phone: Phone number (e.g., 0244123456)
            network: Network code (MTN, VODAFONE, TIGO)
            email: Customer email
            reference: Transaction reference
            metadata: Additional data
        """
        endpoint = f"{self.base_url}/charges?type=mobile_money_ghana"

        charge_info = self.calculate_charges(amount)

        payload = {
            "tx_ref": reference,
            "amount": str(charge_info['amount_to_charge']),
            "currency": "GHS",
            "phone_number": phone,
            "network": network.upper(),
            "email": email,
        }

        if metadata:
            payload["meta"] = metadata

        try:
            response = requests.post(
                endpoint,
                headers=self._get_headers(),
                json=payload,
                timeout=60  # Mobile money can take longer
            )

            data = response.json()

            if data.get('status') == 'success':
                return PaymentResponse(
                    success=True,
                    message=data.get('meta', {}).get('authorization', {}).get('instruction', 'Approve the payment on your phone'),
                    reference=reference,
                    transaction_id=str(data['data'].get('id', '')),
                    amount=charge_info['amount_to_charge'],
                    raw_response=data
                )
            else:
                return PaymentResponse(
                    success=False,
                    message=data.get('message', 'Failed to charge mobile money'),
                    reference=reference,
                    raw_response=data
                )

        except requests.exceptions.RequestException as e:
            logger.exception("Flutterwave mobile money charge failed")
            return PaymentResponse(
                success=False,
                message=f"Connection error: {str(e)}",
                reference=reference
            )
