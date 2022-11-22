import datetime
import io
import json
from unittest.mock import patch

import httpx
import respx
from django.core import management
from django.test import override_settings
from django.utils import timezone

from itou.approvals.factories import ApprovalFactory, PoleEmploiApprovalFactory
from itou.approvals.models import Approval
from itou.job_applications.factories import JobApplicationFactory
from itou.job_applications.models import JobApplicationWorkflow
from itou.siaes.enums import SiaeKind, siae_kind_to_pe_type_siae
from itou.siaes.factories import SiaeFactory
from itou.users.factories import JobSeekerFactory
from itou.utils.mocks.pole_emploi import (
    API_MAJPASS_RESULT_ERROR,
    API_MAJPASS_RESULT_OK,
    API_RECHERCHE_MANY_RESULTS,
    API_RECHERCHE_RESULT_KNOWN,
)
from itou.utils.test import TestCase


@override_settings(
    API_ESD={
        "BASE_URL": "https://pe.fake",
        "AUTH_BASE_URL": "https://auth.fr",
        "KEY": "foobar",
        "SECRET": "pe-secret",
    }
)
class ApprovalNotifyPoleEmploiIntegrationTest(TestCase):
    def setUp(self):
        respx.post("https://auth.fr/connexion/oauth2/access_token?realm=%2Fpartenaire").respond(
            200, json={"token_type": "foo", "access_token": "batman", "expires_in": 3600}
        )

    def test_invalid_job_seeker_for_pole_emploi(self):
        """
        Error case: our job seeker is not valid (from PoleEmploi’s point of view: here, the NIR is missing)
         - We do not even call the APIs
         - no entry should be added to the notification log database
        """
        now = timezone.now()
        approval = ApprovalFactory(user__nir="", with_jobapplication=True)
        approval.notify_pole_emploi(at=now)
        approval.refresh_from_db()
        self.assertEqual(approval.pe_notification_status, "notification_pending")
        self.assertEqual(approval.pe_notification_time, now)
        self.assertEqual(approval.pe_notification_endpoint, None)
        self.assertEqual(approval.pe_notification_exit_code, "MISSING_USER_DATA")

    def test_invalid_job_application(self):
        now = timezone.now()
        approval = ApprovalFactory(
            with_jobapplication=True,
            with_jobapplication__state=JobApplicationWorkflow.STATE_CANCELLED,
        )
        approval.notify_pole_emploi(at=now)
        approval.refresh_from_db()
        self.assertEqual(approval.pe_notification_status, "notification_pending")
        self.assertEqual(approval.pe_notification_time, now)
        self.assertEqual(approval.pe_notification_endpoint, None)
        self.assertEqual(approval.pe_notification_exit_code, "NO_JOB_APPLICATION")

    @respx.mock
    def test_notification_accepted_nominal(self):
        now = timezone.now()
        respx.post("https://pe.fake/rechercheindividucertifie/v1/rechercheIndividuCertifie").respond(
            200, json=API_RECHERCHE_RESULT_KNOWN
        )
        respx.post("https://pe.fake/maj-pass-iae/v1/passIAE/miseAjour").respond(200, json=API_MAJPASS_RESULT_OK)
        approval = ApprovalFactory(
            with_jobapplication=True,
            with_jobapplication__to_siae__kind=SiaeKind.ACI,
        )
        approval.notify_pole_emploi(at=now)
        approval.refresh_from_db()
        payload = json.loads(respx.calls.last.request.content)
        self.assertEqual(
            payload,
            {
                "dateDebutPassIAE": approval.start_at.isoformat(),
                "dateFinPassIAE": approval.end_at.isoformat(),
                "idNational": "ruLuawDxNzERAFwxw6Na4V8A8UCXg6vXM_WKkx5j8UQ",
                "numPassIAE": approval.number,
                "numSIRETsiae": approval.jobapplication_set.first().to_siae.siret,
                "origineCandidature": "PRES",
                "statutReponsePassIAE": "A",
                "typeSIAE": 836,
            },
        )
        self.assertEqual(approval.pe_notification_status, "notification_success")
        self.assertEqual(approval.pe_notification_time, now)
        self.assertEqual(approval.pe_notification_endpoint, None)
        self.assertEqual(approval.pe_notification_exit_code, None)

    @respx.mock
    def test_notification_stays_pending_if_approval_starts_after_today(self):
        now = timezone.now()
        respx.post("https://pe.fake/rechercheindividucertifie/v1/rechercheIndividuCertifie").respond(
            200, json=API_RECHERCHE_RESULT_KNOWN
        )
        respx.post("https://pe.fake/maj-pass-iae/v1/passIAE/miseAjour").respond(200, json=API_MAJPASS_RESULT_OK)
        tomorrow = (now + datetime.timedelta(days=1)).date()
        approval = ApprovalFactory(start_at=tomorrow)
        with self.assertLogs("itou.approvals.models") as logs:
            approval.notify_pole_emploi(at=now)
        self.assertIn(
            f"notify_pole_emploi approval={approval} "
            f"start_at={approval.start_at} "
            f"starts after today={now.date()}",
            logs.output[0],
        )
        approval.refresh_from_db()
        self.assertEqual(approval.pe_notification_status, "notification_pending")
        self.assertEqual(approval.pe_notification_time, now)
        self.assertEqual(approval.pe_notification_endpoint, None)
        self.assertEqual(approval.pe_notification_exit_code, "STARTS_IN_FUTURE")

    @respx.mock
    def test_notification_goes_to_retry_if_there_is_a_timeout(self):
        now = timezone.now()
        respx.post("https://auth.fr/connexion/oauth2/access_token?realm=%2Fpartenaire").mock(
            side_effect=httpx.ConnectTimeout
        )
        job_seeker = JobSeekerFactory()
        approval = ApprovalFactory(user=job_seeker, with_jobapplication=True)
        approval.notify_pole_emploi(at=now)
        approval.refresh_from_db()
        self.assertEqual(approval.pe_notification_status, "notification_should_retry")
        self.assertEqual(approval.pe_notification_time, now)
        self.assertEqual(approval.pe_notification_endpoint, None)
        self.assertEqual(approval.pe_notification_exit_code, None)

    @respx.mock
    def test_notification_goes_to_error_if_something_goes_wrong_with_rech_individu(self):
        now = timezone.now()
        respx.post("https://pe.fake/rechercheindividucertifie/v1/rechercheIndividuCertifie").respond(
            200, json=API_RECHERCHE_MANY_RESULTS
        )
        job_seeker = JobSeekerFactory()
        approval = ApprovalFactory(user=job_seeker, with_jobapplication=True)
        approval.notify_pole_emploi(at=now)
        approval.refresh_from_db()
        self.assertEqual(approval.pe_notification_status, "notification_error")
        self.assertEqual(approval.pe_notification_time, now)
        self.assertEqual(approval.pe_notification_endpoint, "rech_individu")
        self.assertEqual(approval.pe_notification_exit_code, "S002")

    @respx.mock
    def test_notification_goes_to_error_if_something_goes_wrong_with_maj_pass(self):
        now = timezone.now()
        respx.post("https://pe.fake/rechercheindividucertifie/v1/rechercheIndividuCertifie").respond(
            200, json=API_RECHERCHE_RESULT_KNOWN
        )
        respx.post("https://pe.fake/maj-pass-iae/v1/passIAE/miseAjour").respond(200, json=API_MAJPASS_RESULT_ERROR)
        job_seeker = JobSeekerFactory()
        approval = ApprovalFactory(user=job_seeker, with_jobapplication=True)
        approval.notify_pole_emploi(at=now)
        approval.refresh_from_db()
        self.assertEqual(approval.pe_notification_status, "notification_error")
        self.assertEqual(approval.pe_notification_time, now)
        self.assertEqual(approval.pe_notification_endpoint, "maj_pass")
        self.assertEqual(approval.pe_notification_exit_code, "S022")

    @respx.mock
    def test_notification_goes_to_error_if_missing_siae_kind(self):
        now = timezone.now()
        respx.post("https://pe.fake/rechercheindividucertifie/v1/rechercheIndividuCertifie").respond(
            200, json=API_RECHERCHE_RESULT_KNOWN
        )
        respx.post("https://pe.fake/maj-pass-iae/v1/passIAE/miseAjour").respond(200, json=API_MAJPASS_RESULT_ERROR)
        job_seeker = JobSeekerFactory()
        siae = SiaeFactory(kind="FOOBAR")  # unknown kind
        approval = ApprovalFactory(user=job_seeker)
        JobApplicationFactory(to_siae=siae, approval=approval, state=JobApplicationWorkflow.STATE_ACCEPTED)
        approval.notify_pole_emploi(at=now)
        approval.refresh_from_db()
        self.assertEqual(approval.pe_notification_status, "notification_error")
        self.assertEqual(approval.pe_notification_time, now)
        self.assertEqual(approval.pe_notification_endpoint, None)
        self.assertEqual(approval.pe_notification_exit_code, "INVALID_SIAE_KIND")

    @respx.mock
    def test_notification_goes_to_pending_if_job_application_is_not_accepted(self):
        now = timezone.now()
        respx.post("https://pe.fake/rechercheindividucertifie/v1/rechercheIndividuCertifie").respond(
            200, json=API_RECHERCHE_RESULT_KNOWN
        )
        respx.post("https://pe.fake/maj-pass-iae/v1/passIAE/miseAjour").respond(200, json=API_MAJPASS_RESULT_ERROR)
        job_seeker = JobSeekerFactory()
        siae = SiaeFactory(kind="FOOBAR")  # unknown kind
        approval = ApprovalFactory(user=job_seeker)
        JobApplicationFactory(to_siae=siae, approval=approval, state=JobApplicationWorkflow.STATE_POSTPONED)
        approval.notify_pole_emploi(at=now)
        approval.refresh_from_db()
        self.assertEqual(approval.pe_notification_status, "notification_pending")
        self.assertEqual(approval.pe_notification_time, now)
        self.assertEqual(approval.pe_notification_endpoint, None)
        self.assertEqual(approval.pe_notification_exit_code, "NO_JOB_APPLICATION")


class ApprovalsSendToPeManagementTestCase(TestCase):
    @patch.object(Approval, "notify_pole_emploi")
    @patch("itou.approvals.management.commands.send_approvals_to_pe.sleep")
    def test_invalid_job_seeker_for_pole_emploi(self, sleep_mock, notify_mock):
        stdout = io.StringIO()
        # create ignored Approvals, will not even be counted in the batch. the cron will wait for
        # the database to have the necessary job application, nir, or start date to fetch them.
        ApprovalFactory(with_jobapplication=False)
        ApprovalFactory(user__nir="")
        ApprovalFactory(user__nir=None)
        ApprovalFactory(user__birthdate=None)
        ApprovalFactory(start_at=datetime.datetime.today().date() + datetime.timedelta(days=1))

        # other approvals
        retry_approval = ApprovalFactory(
            start_at=datetime.datetime.today().date() - datetime.timedelta(days=1),
            with_jobapplication=True,
            pe_notification_status="notification_should_retry",
        )
        pending_approval = ApprovalFactory(with_jobapplication=True)
        management.call_command(
            "send_approvals_to_pe",
            wet_run=True,
            delay=3,
            stdout=stdout,
        )
        self.assertEqual(
            stdout.getvalue().split("\n"),
            [
                "approvals needing to be sent count=2, batch count=100",
                f"approvals={pending_approval} start_at={pending_approval.start_at.isoformat()} "
                "pe_state=notification_pending",
                f"approvals={retry_approval} start_at={retry_approval.start_at.isoformat()} "
                "pe_state=notification_should_retry",
                "",
            ],
        )
        sleep_mock.assert_called_with(3)
        self.assertEqual(sleep_mock.call_count, 2)
        self.assertEqual(notify_mock.call_count, 2)


@override_settings(
    API_ESD={
        "BASE_URL": "https://pe.fake",
        "AUTH_BASE_URL": "https://auth.fr",
        "KEY": "foobar",
        "SECRET": "pe-secret",
    }
)
class PoleEmploiApprovalNotifyPoleEmploiIntegrationTest(TestCase):
    @respx.mock
    def test_notification_accepted_nominal(self):
        now = timezone.now()
        respx.post("https://auth.fr/connexion/oauth2/access_token?realm=%2Fpartenaire").respond(
            200, json={"token_type": "foo", "access_token": "batman", "expires_in": 3600}
        )
        respx.post("https://pe.fake/rechercheindividucertifie/v1/rechercheIndividuCertifie").respond(
            200, json=API_RECHERCHE_RESULT_KNOWN
        )
        respx.post("https://pe.fake/maj-pass-iae/v1/passIAE/miseAjour").respond(200, json=API_MAJPASS_RESULT_OK)
        pe_approval = PoleEmploiApprovalFactory(
            nir="FOOBAR2000", siae_kind=SiaeKind.ACI.value
        )  # avoid the OPCS, not mapped yet
        pe_approval.notify_pole_emploi(at=now)
        pe_approval.refresh_from_db()
        payload = json.loads(respx.calls.last.request.content)
        self.assertEqual(
            payload,
            {
                "dateDebutPassIAE": pe_approval.start_at.isoformat(),
                "dateFinPassIAE": pe_approval.end_at.isoformat(),
                "idNational": "ruLuawDxNzERAFwxw6Na4V8A8UCXg6vXM_WKkx5j8UQ",
                "numPassIAE": pe_approval.number,
                "numSIRETsiae": pe_approval.siae_siret,
                "origineCandidature": "PRES",
                "statutReponsePassIAE": "A",
                "typeSIAE": siae_kind_to_pe_type_siae(pe_approval.siae_kind),
            },
        )
        self.assertEqual(pe_approval.pe_notification_status, "notification_success")
        self.assertEqual(pe_approval.pe_notification_time, now)
        self.assertEqual(pe_approval.pe_notification_endpoint, None)
        self.assertEqual(pe_approval.pe_notification_exit_code, None)
