"""
Hubtel Payment Gateway Adapter

Hubtel is a Ghana-focused payment gateway.
Documentation: https://developers.hubtel.com/
"""

import base64
import requests
from decimal import Decimal
from typing import Dict, Tuple
import logging

from .base import BaseGatewayAdapter, PaymentResponse

logger = logging.getLogger(__name__)


class HubtelAdapter(BaseGatewayAdapter):
    """
    Hubtel payment gateway implementation.

    Hubtel is a Ghana-only payment gateway that supports:
    - Mobile Money (MTN, Vodafone, AirtelTigo)
    - Card payments
    - Hubtel wallet
    """

    @property
    def name(self) -> str:
        return "Hubtel"

    @property
    def base_url(self) -> str:
        if self.is_test_mode:
            return "https://api-txnstatus.hubtel.com/checkout"
        return "https://api-txnstatus.hubtel.com/checkout"

    @property
    def _pos_base_url(self) -> str:
        """Base URL for POS/Direct charge API."""
        return "https://devp-reqsendmoney-230622-api.hubtel.com"

    def _get_headers(self) -> Dict:
        """Get authorization headers using Basic Auth."""
        client_id = self.credentials.get('merchant_id', '')
        client_secret = self.credentials.get('secret_key', '')

        # Hubtel uses Basic Auth with client_id:client_secret
        credentials = f"{client_id}:{client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()

        return {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
        }

    def verify_credentials(self) -> Tuple[bool, str]:
        """
        Verify Hubtel credentials by making a test API call.
        """
        try:
            # There's no direct balance endpoint, so we make a minimal request
            # to check if credentials work
            response = requests.get(
                f"{self.base_url}/status/test",
                headers=self._get_headers(),
                timeout=30
            )

            # Hubtel returns 401 for invalid credentials
            if response.status_code in [200, 404]:  # 404 is OK - endpoint doesn't exist but auth passed
                return True, "Credentials verified successfully"
            elif response.status_code == 401:
                return False, "Invalid client ID or client secret"
            else:
                return False, f"Verification failed: HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            return False, "Connection timeout"
        except requests.exceptions.RequestException as e:
            return False, f"Connection error: {str(e)}"
        except Exception as e:
            logger.exception("Hubtel credential verification failed")
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
        Initialize a Hubtel checkout transaction.
        """
        endpoint = f"{self.base_url}/initiate"

        # Calculate charges
        charge_info = self.calculate_charges(amount)

        payload = {
            "totalAmount": float(charge_info['amount_to_charge']),
            "description": "School Fee Payment",
            "callbackUrl": callback_url,
            "returnUrl": callback_url,
            "cancellationUrl": callback_url,
            "merchantBusinessLogoUrl": "",
            "merchantAccountNumber": self.credentials.get('merchant_account', ''),
            "clientReference": reference,
        }

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

            if data.get('responseCode') == '0000':
                return PaymentResponse(
                    success=True,
                    message="Payment initialized successfully",
                    reference=reference,
                    authorization_url=data.get('data', {}).get('checkoutUrl', ''),
                    transaction_id=data.get('data', {}).get('checkoutId', ''),
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
            logger.exception("Hubtel payment initialization failed")
            return PaymentResponse(
                success=False,
                message=f"Connection error: {str(e)}",
                reference=reference
            )

    def verify_payment(self, reference: str) -> PaymentResponse:
        """
        Verify a Hubtel transaction using client reference.
        """
        endpoint = f"{self.base_url}/status/{reference}"

        self.log_request(endpoint, "GET")

        try:
            response = requests.get(
                endpoint,
                headers=self._get_headers(),
                timeout=30
            )

            data = response.json()
            self.log_response(endpoint, response.status_code, data)

            if data.get('responseCode') == '0000':
                tx_data = data.get('data', {})
                status = tx_data.get('status', '').lower()

                if status == 'paid':
                    return PaymentResponse(
                        success=True,
                        message="Payment verified successfully",
                        reference=reference,
                        transaction_id=tx_data.get('transactionId', ''),
                        amount=Decimal(str(tx_data.get('amount', 0))),
                        raw_response=data
                    )
                else:
                    return PaymentResponse(
                        success=False,
                        message=f"Payment {status}",
                        reference=reference,
                        raw_response=data
                    )
            else:
                return PaymentResponse(
                    success=False,
                    message=data.get('message', 'Verification failed'),
                    reference=reference,
                    raw_response=data
                )

        except requests.exceptions.RequestException as e:
            logger.exception("Hubtel payment verification failed")
            return PaymentResponse(
                success=False,
                message=f"Connection error: {str(e)}",
                reference=reference
            )

    def handle_webhook(self, payload: Dict, signature: str) -> PaymentResponse:
        """
        Handle Hubtel webhook notification.
        """
        # Hubtel webhooks contain the transaction status
        response_code = payload.get('ResponseCode')
        data = payload.get('Data', {})
        reference = data.get('ClientReference', '')

        if response_code == '0000':
            return PaymentResponse(
                success=True,
                message="Payment successful",
                reference=reference,
                transaction_id=data.get('TransactionId', ''),
                amount=Decimal(str(data.get('Amount', 0))),
                raw_response=payload
            )
        else:
            return PaymentResponse(
                success=False,
                message=payload.get('Message', 'Payment failed'),
                reference=reference,
                raw_response=payload
            )

    def get_supported_channels(self) -> list:
        """Get list of supported payment channels."""
        return [
            {"id": "mtn", "name": "MTN Mobile Money"},
            {"id": "vodafone", "name": "Vodafone Cash"},
            {"id": "airteltigo", "name": "AirtelTigo Money"},
            {"id": "card", "name": "Card Payment"},
            {"id": "hubtel", "name": "Hubtel Wallet"},
        ]

    def charge_mobile_money(
        self,
        amount: Decimal,
        phone: str,
        network: str,
        reference: str,
        metadata: Dict = None
    ) -> PaymentResponse:
        """
        Charge mobile money directly using Send Money API.

        Args:
            amount: Amount in GHS
            phone: Phone number (e.g., 0244123456)
            network: Network code (mtn-gh, vodafone-gh, tigo-gh)
            reference: Transaction reference
            metadata: Additional data
        """
        endpoint = f"{self._pos_base_url}/request-money"

        # Format phone number
        if phone.startswith('0'):
            phone = '233' + phone[1:]
        elif not phone.startswith('233'):
            phone = '233' + phone

        # Map network names
        network_map = {
            'MTN': 'mtn-gh',
            'VODAFONE': 'vodafone-gh',
            'TIGO': 'tigo-gh',
            'AIRTELTIGO': 'tigo-gh',
        }
        channel = network_map.get(network.upper(), 'mtn-gh')

        charge_info = self.calculate_charges(amount)

        payload = {
            "amount": float(charge_info['amount_to_charge']),
            "title": "School Fee Payment",
            "description": metadata.get('description', 'Fee payment') if metadata else 'Fee payment',
            "clientReference": reference,
            "callbackUrl": metadata.get('callback_url', '') if metadata else '',
            "primaryMomoNumber": phone,
            "channels": [channel],
        }

        try:
            response = requests.post(
                endpoint,
                headers=self._get_headers(),
                json=payload,
                timeout=60
            )

            data = response.json()

            if data.get('responseCode') == '0001':  # Pending approval
                return PaymentResponse(
                    success=True,
                    message="Please approve the payment on your phone",
                    reference=reference,
                    transaction_id=data.get('data', {}).get('transactionId', ''),
                    amount=charge_info['amount_to_charge'],
                    raw_response=data
                )
            elif data.get('responseCode') == '0000':  # Success
                return PaymentResponse(
                    success=True,
                    message="Payment successful",
                    reference=reference,
                    transaction_id=data.get('data', {}).get('transactionId', ''),
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
            logger.exception("Hubtel mobile money charge failed")
            return PaymentResponse(
                success=False,
                message=f"Connection error: {str(e)}",
                reference=reference
            )
