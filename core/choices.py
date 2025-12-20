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