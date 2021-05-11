from django.test import TestCase
from django.urls import reverse

from itou.employee_record.models import EmployeeRecord
from itou.job_applications.factories import JobApplicationWithApprovalFactory
from itou.siaes.factories import SiaeWithMembershipAndJobsFactory
from itou.users.factories import DEFAULT_PASSWORD


class ListEmployeeRecordsTest(TestCase):
    def setUp(self):
        self.siae = SiaeWithMembershipAndJobsFactory(name="Evil Corp.", membership__user__first_name="Elliot")
        self.siae_without_perms = SiaeWithMembershipAndJobsFactory(
            kind="EITI", name="A-Team", membership__user__first_name="Hannibal"
        )
        self.user = self.siae.members.get(first_name="Elliot")
        self.user_without_perms = self.siae_without_perms.members.get(first_name="Hannibal")
        self.job_application = JobApplicationWithApprovalFactory(
            to_siae=self.siae,
        )
        self.url = reverse("employee_record_views:list")

    def test_permissions(self):
        """
        Non-eligible SIAE should not be able to access this list
        """
        self.client.login(username=self.user_without_perms.username, password=DEFAULT_PASSWORD)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_new_employee_records(self):
        """
        Check if new employee records / job applications are displayed in the list
        """
        self.client.login(username=self.user.username, password=DEFAULT_PASSWORD)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.get_full_name())

    def test_status_filter(self):
        """
        Check status filter
        """
        # No status defined
        self.client.login(username=self.user.username, password=DEFAULT_PASSWORD)
        response = self.client.get(self.url)

        self.assertContains(response, self.user.get_full_name())

        # Or NEW
        response = self.client.get(self.url + "?status=NEW")
        self.assertContains(response, self.user.get_full_name())

        # More complete tests to come with fixtures files
        for status in [EmployeeRecord.Status.SENT, EmployeeRecord.Status.REJECTED, EmployeeRecord.Status.PROCESSED]:
            response = self.client.get(self.url + f"?status={status.value}", {"status": status.value})
            self.assertNotContains(response, self.user.get_full_name())

    # To be completed with other status during UI part 2
    # when connected to employee record backend with sample employee records...
