import pytest
from dateutil.relativedelta import relativedelta
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.http import urlencode

from itou.approvals.enums import ProlongationReason
from itou.approvals.models import Prolongation
from itou.job_applications.factories import JobApplicationFactory
from itou.prescribers.factories import PrescriberOrganizationWithMembershipFactory
from itou.utils.storage.s3 import S3Upload
from itou.utils.widgets import DuetDatePickerWidget
from itou.www.approvals_views.forms import DeclareProlongationForm
from tests.utils.storage.test import S3AccessingTestCase
from tests.utils.test import parse_response_to_soup


@pytest.mark.usefixtures("unittest_compatibility")
class ApprovalProlongationTest(S3AccessingTestCase):
    def setUp(self):
        """
        Create test objects.
        """

        self.prescriber_organization = PrescriberOrganizationWithMembershipFactory(authorized=True)
        self.prescriber = self.prescriber_organization.members.first()

        today = timezone.localdate()
        self.job_application = JobApplicationFactory(
            with_approval=True,
            # Ensure that the job_application cannot be canceled.
            hiring_start_at=today - relativedelta(days=1),
            approval__start_at=today - relativedelta(months=12),
            approval__end_at=today + relativedelta(months=2),
        )
        self.siae = self.job_application.to_siae
        self.siae_user = self.job_application.to_siae.members.first()
        self.approval = self.job_application.approval
        assert 0 == self.approval.prolongation_set.count()

    def test_form_without_pre_existing_instance(self):
        """
        Test the default state of `DeclareProlongationForm`.
        """
        form = DeclareProlongationForm(approval=self.approval, siae=self.siae, data={})

        assert form.fields["reason"].initial is None

        # Ensure that `form.instance` is populated so that `Prolongation.clean()`
        # is triggered from within the form validation step with the right data.
        assert form.instance.declared_by_siae == self.siae
        assert form.instance.approval == self.approval
        assert form.instance.start_at == Prolongation.get_start_at(self.approval)

    def test_prolong_approval_view(self):
        """
        Test the creation of a prolongation.
        """

        self.client.force_login(self.siae_user)

        back_url = "/"
        params = urlencode({"back_url": back_url})
        url = reverse("approvals:declare_prolongation", kwargs={"approval_id": self.approval.pk})
        url = f"{url}?{params}"

        response = self.client.get(url)
        assert response.status_code == 200
        assert response.context["preview"] is False

        # Since December 1, 2021, health context reason can no longer be used
        reason = ProlongationReason.HEALTH_CONTEXT
        end_at = Prolongation.get_max_end_at(self.approval.end_at, reason=reason)
        post_data = {
            "end_at": end_at.strftime(DuetDatePickerWidget.INPUT_DATE_FORMAT),
            "reason": reason,
            "email": self.prescriber.email,
            # Preview.
            "preview": "1",
        }
        response = self.client.post(url, data=post_data)
        self.assertContains(response, escape("Sélectionnez un choix valide."))

        # With valid reason
        reason = ProlongationReason.SENIOR
        end_at = Prolongation.get_max_end_at(self.approval.end_at, reason=reason)

        post_data = {
            "end_at": end_at.strftime(DuetDatePickerWidget.INPUT_DATE_FORMAT),
            "reason": reason,
            "email": self.prescriber.email,
            "contact_email": self.faker.email(),
            "contact_phone": self.faker.phone_number(),
            "report_file_path": "prolongation_report/memento-mori.xslx",
            "uploaded_file_name": "report_file.xlsx",
            "prescriber_organization": self.prescriber_organization.pk,
            # Preview.
            "preview": "1",
        }

        # Go to preview.
        response = self.client.post(url, data=post_data)
        assert response.status_code == 200
        assert response.context["preview"] is True

        # Save to DB.
        del post_data["preview"]
        post_data["save"] = 1

        response = self.client.post(url, data=post_data)
        assert response.status_code == 302
        self.assertRedirects(response, back_url)

        assert 1 == self.approval.prolongation_set.count()

        prolongation = self.approval.prolongation_set.first()
        assert prolongation.created_by == self.siae_user
        assert prolongation.declared_by == self.siae_user
        assert prolongation.declared_by_siae == self.job_application.to_siae
        assert prolongation.validated_by == self.prescriber
        assert prolongation.reason == post_data["reason"]

        # An email should have been sent to the chosen authorized prescriber.
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert len(email.to) == 1
        assert email.to[0] == post_data["email"]

    def test_prolong_approval_view_without_prescriber(self):
        """
        Test the creation of a prolongation without prescriber.
        """

        self.client.force_login(self.siae_user)

        back_url = "/"
        params = urlencode({"back_url": back_url})
        url = reverse("approvals:declare_prolongation", kwargs={"approval_id": self.approval.pk})
        url = f"{url}?{params}"

        response = self.client.get(url)
        assert response.status_code == 200
        assert response.context["preview"] is False

        reason = ProlongationReason.COMPLETE_TRAINING
        end_at = Prolongation.get_max_end_at(self.approval.end_at, reason=reason)

        post_data = {
            "end_at": end_at.strftime(DuetDatePickerWidget.INPUT_DATE_FORMAT),
            "reason": reason,
            # Preview.
            "preview": "1",
        }

        # Go to preview.
        response = self.client.post(url, data=post_data)
        assert response.status_code == 200
        assert response.context["preview"] is True

        # Save to DB.
        del post_data["preview"]
        post_data["save"] = 1

        response = self.client.post(url, data=post_data)
        assert response.status_code == 302
        self.assertRedirects(response, back_url)

        assert 1 == self.approval.prolongation_set.count()

        prolongation = self.approval.prolongation_set.first()
        assert prolongation.created_by == self.siae_user
        assert prolongation.declared_by == self.siae_user
        assert prolongation.declared_by_siae == self.job_application.to_siae
        assert prolongation.validated_by is None
        assert prolongation.reason == post_data["reason"]

        # No email should have been sent.
        assert len(mail.outbox) == 0

    def test_prolongation_report_file_fields(self):
        # Check S3 parameters / hidden fields mandatory for report file upload

        self.client.force_login(self.siae_user)
        url = reverse("approvals:declare_prolongation", kwargs={"approval_id": self.approval.pk})
        response = self.client.get(url)

        assert response.status_code == 200

        s3_upload = S3Upload(kind="prolongation_report")

        # Check target S3 bucket URL
        self.assertContains(response, s3_upload.form_values["url"])

        # Config variables: same tests as for apply/resume
        s3_upload.config.pop("upload_expiration")
        for value in s3_upload.config.values():
            self.assertContains(response, value)

        assert s3_upload.config["key_path"] == "prolongation_report"
        assert (
            s3_upload.config["allowed_mime_types"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    def test_prolongation_report_file_saved(self):
        # Check that report file object is saved and linked to prolongation
        # Bad reason types are checked by UI (JS) and ultimately by DB constraints

        self.client.force_login(self.siae_user)
        url = reverse("approvals:declare_prolongation", kwargs={"approval_id": self.approval.pk})
        response = self.client.get(url)

        reason = ProlongationReason.RQTH
        end_at = Prolongation.get_max_end_at(self.approval.end_at, reason=reason)

        post_data = {
            "end_at": end_at.strftime(DuetDatePickerWidget.INPUT_DATE_FORMAT),
            "reason": reason,
            "email": self.prescriber.email,
            "contact_email": self.faker.email(),
            "contact_phone": self.faker.phone_number(),
            "report_file_path": "prolongation_report/memento-mori.xslx",
            "uploaded_file_name": "report_file.xlsx",
            "prescriber_organization": self.prescriber_organization.pk,
            "save": "1",
        }

        response = self.client.post(url, data=post_data)
        assert response.status_code == 302

        prolongation = self.approval.prolongation_set.first()

        assert prolongation.report_file
        assert prolongation.report_file.key == "prolongation_report/memento-mori.xslx"

    def test_prolongation_notification_contains_report_link(self):
        # Check that report file object is saved and linked to prolongation
        # Bad reason types are checked by UI (JS) and ultimately by DB constraints

        self.client.force_login(self.siae_user)
        url = reverse("approvals:declare_prolongation", kwargs={"approval_id": self.approval.pk})
        response = self.client.get(url)

        reason = ProlongationReason.SENIOR
        end_at = Prolongation.get_max_end_at(self.approval.end_at, reason=reason)

        post_data = {
            "end_at": end_at.strftime(DuetDatePickerWidget.INPUT_DATE_FORMAT),
            "reason": reason,
            "email": self.prescriber.email,
            "contact_email": self.faker.email(),
            "contact_phone": self.faker.phone_number(),
            "report_file_path": "prolongation_report/memento-mori.xslx",
            "uploaded_file_name": "report_file.xlsx",
            "prescriber_organization": self.prescriber_organization.pk,
            "save": "1",
        }

        response = self.client.post(url, data=post_data)

        assert response.status_code == 302
        assert len(mail.outbox) == 1

        email = mail.outbox[0]

        assert len(email.to) == 1
        assert email.to[0] == post_data["email"]
        assert email.subject == f"Demande de prolongation du PASS IAE de {self.approval.user.get_full_name()}"

        prolongation = self.approval.prolongation_set.first()

        assert prolongation.report_file.link in email.body

    def test_check_single_prescriber_organization(self):
        self.client.force_login(self.siae_user)
        url = reverse("approvals:declare_prolongation", kwargs={"approval_id": self.approval.pk})
        self.client.get(url)

        reason = ProlongationReason.SENIOR
        end_at = Prolongation.get_max_end_at(self.approval.end_at, reason=reason)

        post_data = {
            "end_at": end_at.strftime(DuetDatePickerWidget.INPUT_DATE_FORMAT),
            "reason": reason,
            "email": self.prescriber.email,
            "contact_email": self.faker.email(),
            "contact_phone": self.faker.phone_number(),
            "report_file_path": "prolongation_report/memento-mori.xslx",
            "uploaded_file_name": "report_file.xlsx",
            "edit": "1",
        }
        response = self.client.post(url, data=post_data)

        self.assertContains(response, self.prescriber_organization)
        self.assertNotContains(response, "Sélectionnez l'organisation du prescripteur habilité")

    def test_check_multiple_prescriber_organization(self):
        # Link prescriber to another prescriber organization
        other_prescriber_organization = PrescriberOrganizationWithMembershipFactory(authorized=True)
        other_prescriber_organization.members.add(self.prescriber)

        self.client.force_login(self.siae_user)
        url = reverse("approvals:declare_prolongation", kwargs={"approval_id": self.approval.pk})
        self.client.get(url)

        reason = ProlongationReason.SENIOR
        end_at = Prolongation.get_max_end_at(self.approval.end_at, reason=reason)

        post_data = {
            "end_at": end_at.strftime(DuetDatePickerWidget.INPUT_DATE_FORMAT),
            "reason": reason,
            "email": self.prescriber.email,
            "contact_email": self.faker.email(),
            "contact_phone": self.faker.phone_number(),
            "report_file_path": "prolongation_report/memento-mori.xslx",
            "uploaded_file_name": "report_file.xlsx",
            "edit": "1",
        }
        response = self.client.post(url, data=post_data)

        self.assertContains(response, self.prescriber_organization)
        self.assertContains(response, other_prescriber_organization)

        error_msg = parse_response_to_soup(response, selector="div#check_prescriber_email .invalid-feedback")
        assert str(error_msg) == self.snapshot(name="prescriber is member of many organizations")

    def test_check_invalid_prescriber(self):
        unauthorized_prescriber_organization = PrescriberOrganizationWithMembershipFactory(authorized=False)
        prescriber = unauthorized_prescriber_organization.members.first()

        self.client.force_login(self.siae_user)
        url = reverse("approvals:declare_prolongation", kwargs={"approval_id": self.approval.pk})
        self.client.get(url)

        reason = ProlongationReason.SENIOR
        end_at = Prolongation.get_max_end_at(self.approval.end_at, reason=reason)

        post_data = {
            "end_at": end_at.strftime(DuetDatePickerWidget.INPUT_DATE_FORMAT),
            "reason": reason,
            "email": prescriber.email,
            "contact_email": self.faker.email(),
            "contact_phone": self.faker.phone_number(),
            "report_file_path": "prolongation_report/memento-mori.xslx",
            "uploaded_file_name": "report_file.xlsx",
            "edit": "1",
        }
        response = self.client.post(url, data=post_data)

        error_msg = parse_response_to_soup(response, selector="div#check_prescriber_email .invalid-feedback")
        assert str(error_msg) == self.snapshot(name="unknown authorized prescriber")