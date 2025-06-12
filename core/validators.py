from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError

# Phone number validator for Ghana format
PHONE_VALIDATOR = RegexValidator(
    regex=r'^(\+233|0)[0-9]{9}$',
    message="Phone number must be in format: +233XXXXXXXXX or 0XXXXXXXXX"
)

# Ghana Card ID validator
GHANA_CARD_VALIDATOR = RegexValidator(
    regex=r'^GHA-[0-9]{9}-[0-9]$',
    message="Ghana Card number must be in format: GHA-XXXXXXXXX-X"
)