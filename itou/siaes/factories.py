import functools
import string

import factory.fuzzy
from django.utils import timezone

from itou.cities.models import City
from itou.common_apps.address.departments import department_from_postcode
from itou.jobs.factories import create_test_romes_and_appellations
from itou.jobs.models import Appellation
from itou.siaes import models
from itou.siaes.enums import SIAE_WITH_CONVENTION_KINDS, ContractType, SiaeKind
from itou.users.factories import SiaeStaffFactory


NAF_CODES = ["9522Z", "7820Z", "6312Z", "8130Z", "1071A", "5510Z"]

GRACE_PERIOD = timezone.timedelta(days=models.SiaeConvention.DEACTIVATION_GRACE_PERIOD_IN_DAYS)
ONE_DAY = timezone.timedelta(days=1)
ONE_MONTH = timezone.timedelta(days=30)


class SiaeFinancialAnnexFactory(factory.django.DjangoModelFactory):
    """Generate an SiaeFinancialAnnex() object for unit tests."""

    class Meta:
        model = models.SiaeFinancialAnnex

    # e.g. EI59V182019A1M1
    number = factory.Sequence(lambda n: f"EI59V{n:06d}A1M1")
    state = models.SiaeFinancialAnnex.STATE_VALID
    start_at = factory.LazyFunction(lambda: timezone.now() - ONE_MONTH)
    end_at = factory.LazyFunction(lambda: timezone.now() + ONE_MONTH)


class SiaeConventionFactory(factory.django.DjangoModelFactory):
    """Generate an SiaeConvention() object for unit tests."""

    class Meta:
        model = models.SiaeConvention
        django_get_or_create = ("asp_id", "kind")

    # Don't start a SIRET with 0.
    siret_signature = factory.fuzzy.FuzzyText(length=13, chars=string.digits, prefix="1")
    # FIXME(vperron): this should be made random
    kind = SiaeKind.EI
    # factory.Sequence() start with 0 and an ASP ID should be greater than 0
    asp_id = factory.Sequence(lambda n: n + 1)
    is_active = True
    financial_annex = factory.RelatedFactory(SiaeFinancialAnnexFactory, "convention")


def _create_job_from_rome_code(self, create, extracted, **kwargs):
    if not create:
        # Simple build, do nothing.
        return

    romes = extracted or ("N1101", "N1105", "N1103", "N4105")
    create_test_romes_and_appellations(romes)
    # Pick random results.
    appellations = Appellation.objects.order_by("?")[: len(romes)]
    self.jobs.add(*appellations)


class SiaeFactory(factory.django.DjangoModelFactory):
    """Generate a Siae() object for unit tests.

    Usage:
        SiaeFactory(subject_to_eligibility=True, ...)
        SiaeFactory(not_subject_to_eligibility=True, ...)
        SiaeFactory(with_membership=True, ...)
        SiaeFactory(with_jobs=True, romes=("N1101", "N1105", "N1103", "N4105"), ...)
    """

    class Meta:
        model = models.Siae

    class Params:
        subject_to_eligibility = factory.Trait(
            kind=factory.fuzzy.FuzzyChoice(SIAE_WITH_CONVENTION_KINDS),
        )
        not_subject_to_eligibility = factory.Trait(
            kind=factory.fuzzy.FuzzyChoice([kind for kind in SiaeKind if kind not in SIAE_WITH_CONVENTION_KINDS]),
        )
        use_employee_record = factory.Trait(kind=factory.fuzzy.FuzzyChoice(models.Siae.ASP_EMPLOYEE_RECORD_KINDS))
        with_membership = factory.Trait(
            membership=factory.RelatedFactory("itou.siaes.factories.SiaeMembershipFactory", "siae"),
        )
        with_jobs = factory.Trait(romes=factory.PostGeneration(_create_job_from_rome_code))

    # Don't start a SIRET with 0.
    siret = factory.fuzzy.FuzzyText(length=13, chars=string.digits, prefix="1")
    naf = factory.fuzzy.FuzzyChoice(NAF_CODES)
    # FIXME(vperron): this should be made random
    kind = SiaeKind.EI
    name = factory.Faker("company", locale="fr_FR")
    phone = factory.fuzzy.FuzzyText(length=10, chars=string.digits)
    email = factory.Faker("email", locale="fr_FR")
    auth_email = factory.Faker("email", locale="fr_FR")
    address_line_1 = factory.Faker("street_address", locale="fr_FR")
    post_code = factory.Faker("postalcode")
    city = factory.Faker("city", locale="fr_FR")
    source = models.Siae.SOURCE_ASP
    convention = factory.SubFactory(SiaeConventionFactory)
    department = factory.LazyAttribute(lambda o: department_from_postcode(o.post_code))


class SiaeMembershipFactory(factory.django.DjangoModelFactory):
    """
    Generate an SiaeMembership() object (with its related Siae() and User() objects) for unit tests.
    https://factoryboy.readthedocs.io/en/latest/recipes.html#many-to-many-relation-with-a-through
    """

    class Meta:
        model = models.SiaeMembership

    user = factory.SubFactory(SiaeStaffFactory)
    siae = factory.SubFactory(SiaeFactory)
    is_admin = True


class SiaeWith2MembershipsFactory(SiaeFactory):
    """
    Generates an Siae() object with 2 members for unit tests.
    https://factoryboy.readthedocs.io/en/latest/recipes.html#many-to-many-relation-with-a-through
    """

    membership1 = factory.RelatedFactory(SiaeMembershipFactory, "siae")
    membership2 = factory.RelatedFactory(SiaeMembershipFactory, "siae", is_admin=False)


class SiaeWith4MembershipsFactory(SiaeFactory):
    """
    Generates an Siae() object with 4 members for unit tests.
    https://factoryboy.readthedocs.io/en/latest/recipes.html#many-to-many-relation-with-a-through
    """

    # active admin user
    membership1 = factory.RelatedFactory(SiaeMembershipFactory, "siae")
    # active normal user
    membership2 = factory.RelatedFactory(SiaeMembershipFactory, "siae", is_admin=False)
    # inactive admin user
    membership3 = factory.RelatedFactory(SiaeMembershipFactory, "siae", user__is_active=False)
    # inactive normal user
    membership4 = factory.RelatedFactory(SiaeMembershipFactory, "siae", is_admin=False, user__is_active=False)


SiaeWithMembershipAndJobsFactory = functools.partial(SiaeFactory, with_membership=True, with_jobs=True)


class SiaeConventionPendingGracePeriodFactory(SiaeConventionFactory):
    """
    Generates a SiaeConvention() object which is inactive but still experiencing its grace period.
    """

    is_active = False
    deactivated_at = factory.LazyFunction(lambda: timezone.now() - GRACE_PERIOD + ONE_DAY)


class SiaePendingGracePeriodFactory(SiaeFactory):
    convention = factory.SubFactory(SiaeConventionPendingGracePeriodFactory)


class SiaeConventionAfterGracePeriodFactory(SiaeConventionFactory):
    """
    Generates an SiaeConvention() object which is inactive and has passed its grace period.
    """

    is_active = False
    deactivated_at = factory.LazyFunction(lambda: timezone.now() - GRACE_PERIOD - ONE_DAY)


class SiaeAfterGracePeriodFactory(SiaeFactory):
    convention = factory.SubFactory(SiaeConventionAfterGracePeriodFactory)


class SiaeJobDescriptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.SiaeJobDescription

    appellation = factory.LazyAttribute(lambda obj: Appellation.objects.order_by("?").first())
    siae = factory.SubFactory(SiaeFactory)
    description = factory.Faker("sentence", locale="fr_FR")
    contract_type = factory.fuzzy.FuzzyChoice(ContractType.values)
    other_contract_type = factory.Faker("word", locale="fr_FR")
    location = factory.LazyAttribute(lambda obj: City.objects.order_by("?").first())
    profile_description = factory.Faker("sentence", locale="fr_FR")
    market_context_description = factory.Faker("sentence", locale="fr_FR")
