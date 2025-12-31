import base64
import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def generate_qr_code_base64(data, box_size=10, border=2):
    """
    Generate a QR code and return it as a base64 data URI.

    Args:
        data: The data to encode in the QR code (usually a URL)
        box_size: Size of each box in pixels (default 10)
        border: Border size in boxes (default 2)

    Returns:
        str: Base64 data URI string for embedding in HTML/PDF, or None if failed
    """
    try:
        import qrcode

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)

        # Create image using default PIL/Pillow backend
        img = qr.make_image(fill_color="black", back_color="white")

        # Save to buffer as PNG
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        # Encode as base64
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/png;base64,{img_base64}"

    except ImportError as e:
        logger.warning(f"qrcode or PIL package not installed: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        return None


def generate_verification_qr(verification_code, request=None, domain=None):
    """
    Generate a QR code for document verification.

    Args:
        verification_code: The verification code to encode
        request: Django request object (optional, used to build absolute URL)
        domain: Domain string like "school.example.com" (optional, used when request not available)

    Returns:
        str: Base64 data URI string, or None if failed
    """
    from django.conf import settings

    # Build the verification URL
    verify_path = f"/verify/{verification_code}/"

    if request:
        # Build absolute URL from request
        verification_url = request.build_absolute_uri(verify_path)
    elif domain:
        # Build URL from provided domain
        scheme = 'https'  # Default to https for security
        verification_url = f"{scheme}://{domain}{verify_path}"
    else:
        # Try to get base URL from settings
        base_url = getattr(settings, 'VERIFICATION_BASE_URL', None)
        if base_url:
            verification_url = f"{base_url.rstrip('/')}{verify_path}"
        else:
            # Fall back to relative path (won't be recognized as link by phone cameras)
            verification_url = verify_path

    return generate_qr_code_base64(verification_url, box_size=6, border=1)
