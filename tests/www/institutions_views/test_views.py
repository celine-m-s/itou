from django.urls import reverse

from tests.institutions.factories import (
    InstitutionFactory,
    InstitutionMembershipFactory,
    InstitutionWith2MembershipFactory,
    InstitutionWithMembershipFactory,
)
from tests.utils.test import TestCase


class MembersTest(TestCase):
    MORE_ADMIN_MSG = "Nous vous recommandons de nommer plusieurs administrateurs"

    def test_members(self):
        institution = InstitutionWithMembershipFactory()
        user = institution.members.first()
        self.client.force_login(user)
        url = reverse("institutions_views:members")
        response = self.client.get(url)
        assert response.status_code == 200

    def test_active_members(self):
        institution = InstitutionFactory()
        active_member_active_user = InstitutionMembershipFactory(institution=institution)
        active_member_inactive_user = InstitutionMembershipFactory(institution=institution, user__is_active=False)
        inactive_member_active_user = InstitutionMembershipFactory(institution=institution, is_active=False)
        inactive_member_inactive_user = InstitutionMembershipFactory(
            institution=institution, is_active=False, user__is_active=False
        )

        self.client.force_login(active_member_active_user.user)
        url = reverse("institutions_views:members")
        response = self.client.get(url)
        assert response.status_code == 200
        assert len(response.context["members"]) == 1
        assert active_member_active_user in response.context["members"]
        assert active_member_inactive_user not in response.context["members"]
        assert inactive_member_active_user not in response.context["members"]
        assert inactive_member_inactive_user not in response.context["members"]

    def test_members_admin_warning_one_user(self):
        institution = InstitutionWithMembershipFactory()
        user = institution.members.first()
        self.client.force_login(user)
        url = reverse("institutions_views:members")
        response = self.client.get(url)
        self.assertNotContains(response, self.MORE_ADMIN_MSG)

    def test_members_admin_warning_two_users(self):
        institution = InstitutionWith2MembershipFactory()
        user = institution.members.first()
        self.client.force_login(user)
        url = reverse("institutions_views:members")
        response = self.client.get(url)
        self.assertContains(response, self.MORE_ADMIN_MSG)

        # Set all users admins
        institution.memberships.update(is_admin=True)
        response = self.client.get(url)
        self.assertNotContains(response, self.MORE_ADMIN_MSG)

    def test_members_admin_warning_many_users(self):
        institution = InstitutionWith2MembershipFactory()
        InstitutionMembershipFactory(institution=institution, user__is_active=False)
        InstitutionMembershipFactory(institution=institution, is_admin=False, user__is_active=False)
        user = institution.members.first()
        self.client.force_login(user)
        url = reverse("institutions_views:members")
        response = self.client.get(url)
        self.assertContains(response, self.MORE_ADMIN_MSG)
