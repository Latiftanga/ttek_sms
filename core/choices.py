from django.db import models
from django.utils.translation import gettext_lazy as _

class Gender(models.TextChoices):
    MALE = 'M', _('Male')
    FEMALE = 'F', _('Female')

class PersonTitle(models.TextChoices):
    MR = 'MR', _('Mr.')
    MRS = 'MRS', _('Mrs.')
    MS = 'MS', _('Ms.')
    DR = 'DR', _('Dr.')
    REV = 'REV', _('Rev.')
    PROF = 'PROF', _('Prof.')
    PASTOR = 'PST', _('Pastor')

class GhanaRegion(models.TextChoices):
    AHAFO = 'AH', _('Ahafo')
    ASHANTI = 'AS', _('Ashanti')
    BONO = 'BO', _('Bono')
    BONO_EAST = 'BE', _('Bono East')
    CENTRAL = 'CP', _('Central')
    EASTERN = 'ER', _('Eastern')
    GREATER_ACCRA = 'GA', _('Greater Accra')
    NORTH_EAST = 'NE', _('North East')
    NORTHERN = 'NP', _('Northern')
    OTI = 'OT', _('Oti')
    SAVANNAH = 'SV', _('Savannah')
    UPPER_EAST = 'UE', _('Upper East')
    UPPER_WEST = 'UW', _('Upper West')
    VOLTA = 'TV', _('Volta')
    WESTERN = 'WP', _('Western')
    WESTERN_NORTH = 'WN', _('Western North')

class RelationshipType(models.TextChoices):
    FATHER = 'FATHER', _('Father')
    MOTHER = 'MOTHER', _('Mother')
    UNCLE = 'UNCLE', _('Uncle')
    AUNT = 'AUNT', _('Aunt')
    BROTHER = 'BROTHER', _('Brother')
    SISTER = 'SISTER', _('Sister')
    GRANDPARENT = 'GRANDPARENT', _('Grandparent')
    GUARDIAN = 'GUARDIAN', _('Legal Guardian')


class EmploymentStatus(models.TextChoices):
    EMPLOYED = 'EMPLOYED', _('Employed')
    UNEMPLOYED = 'UNEMPLOYED', _('Unemployed')
    SELF_EMPLOYED = 'SELF_EMPLOYED', _('Self-employed')
    STUDENT = 'STUDENT', _('Student')
    RETIRED = 'RETIRED', _('Retired')

class EducationLevel(models.TextChoices):
    NONE = 'NONE', _('No formal education')
    BASIC = 'BASIC', _('Basic education')
    SHS = 'SHS', _('Senior High education')


class MaritalStatus(models.TextChoices):
    SINGLE = 'SINGLE', _('Single')
    MARRIED = 'MARRIED', _('Married')
    DIVORCED = 'DIVORCED', _('Divorced')
    WIDOWED = 'WIDOWED', _('Widowed')

class FeeCategoryChoices(models.TextChoices):
    TUITION = 'TUITION', _('Tuition/School Fees')
    ADMISSION = 'ADMISSION', _('Admission Fees')
    EXAM = 'EXAM', _('Examination Fees')
    PTA = 'PTA', _('PTA Dues')
    SPORTS = 'SPORTS', _('Sports & Extra-curricular')
    ICT = 'ICT', _('ICT/Computer Lab')
    LIBRARY = 'LIBRARY', _('Library Fees')
    BOARDING = 'BOARDING', _('Boarding Fees')
    FEEDING = 'FEEDING', _('Feeding Fees')
    TRANSPORT = 'TRANSPORT', _('Transport/Bus Fees')
    UNIFORM = 'UNIFORM', _('Uniform & Materials')
    CAUTION = 'CAUTION', _('Caution Deposit')
    OTHER = 'OTHER', _('Other Fees')


class PaymentMethods(models.TextChoices):
    CASH = 'CASH', _('Cash')
    CREDIT_CARD = 'CREDIT_CARD', _('Credit Card')
    DEBIT_CARD = 'DEBIT_CARD', _('Debit Card')
    MOBILE_MONEY = 'MOBILE_MONEY', _('Mobile Money')
    BANK_TRANSFER = 'BANK_TRANSFER', _('Bank Transfer')

class PaymentStatus(models.TextChoices):
    PENDING = 'PENDING', _('Pending')
    PROCESSING = 'PROCESSING', _('Processing')
    COMPLETED = 'COMPLETED', _('Completed')
    FAILED = 'FAILED', _('Failed')
    REFUNDED = 'REFUNDED', _('Refunded')
    CANCELLED = 'CANCELLED', _('Cancelled')

class AttendanceStatus(models.TextChoices):
    PRESENT = 'PRESENT', _('Present')
    ABSENT = 'ABSENT', _('Absent')
    EXCUSED = 'EXCUSED', _('Excused')
    LATE = 'LATE', _('Late')


class PaymentGatways(models.TextChoices):
    PAYSTACK = 'PAYSTACK', _('Paystack')
    HUBTEL = 'HUBTEL', _('Hubtel')
    FLUTTERWAVE = 'FLUTTERWAVE', _('Flutterwave')