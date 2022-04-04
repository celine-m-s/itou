from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode

from itou.approvals.factories import SuspensionFactory
from itou.eligibility.factories import EligibilityDiagnosisFactory
from itou.eligibility.models import AdministrativeCriteria
from itou.job_applications.factories import (
    JobApplicationSentByJobSeekerFactory,
    JobApplicationSentByPrescriberFactory,
    JobApplicationWithApprovalFactory,
)
from itou.job_applications.models import JobApplicationWorkflow
from itou.jobs.models import Appellation
from itou.prescribers.factories import (
    AuthorizedPrescriberOrganizationWithMembershipFactory,
    PrescriberMembershipFactory,
    PrescriberOrganizationWithMembershipFactory,
)
from itou.siaes.factories import SiaeWithMembershipAndJobsFactory
from itou.users.factories import DEFAULT_PASSWORD
from itou.utils.widgets import DuetDatePickerWidget


class ProcessListTest(TestCase):
    def setUp(self):
        """
        Create three organizations with two members each:
        - pole_emploi: job seekers agency.
        - l_envol: an emergency center for homeless people.
        - hit_pit: a boxing gym looking for boxers.

        Pole Emploi prescribers:
        - Thibault
        - laurie

        L'envol prescribers:
        - Audrey
        - Manu

        Hit Pit staff:
        - Eddie
        """

        # Pole Emploi
        pole_emploi = AuthorizedPrescriberOrganizationWithMembershipFactory(
            name="Pôle emploi", membership__user__first_name="Thibault"
        )
        PrescriberMembershipFactory(organization=pole_emploi, user__first_name="Laurie")
        thibault_pe = pole_emploi.members.get(first_name="Thibault")
        laurie_pe = pole_emploi.members.get(first_name="Laurie")

        # L'Envol
        l_envol = PrescriberOrganizationWithMembershipFactory(name="L'Envol", membership__user__first_name="Manu")
        PrescriberMembershipFactory(organization=l_envol, user__first_name="Audrey")
        audrey_envol = l_envol.members.get(first_name="Audrey")

        # Hit Pit
        hit_pit = SiaeWithMembershipAndJobsFactory(name="Hit Pit", membership__user__first_name="Eddie")
        eddie_hit_pit = hit_pit.members.get(first_name="Eddie")

        # Now send applications
        for i, state in enumerate(JobApplicationWorkflow.states):
            creation_date = timezone.now() - timezone.timedelta(days=i)
            job_application = JobApplicationSentByPrescriberFactory(
                to_siae=hit_pit,
                state=state,
                created_at=creation_date,
                sender=thibault_pe,
                sender_prescriber_organization=pole_emploi,
            )

        maggie = job_application.job_seeker
        maggie.save(update_fields={"first_name": "Maggie"})
        JobApplicationSentByPrescriberFactory(
            to_siae=hit_pit, sender=laurie_pe, sender_prescriber_organization=pole_emploi, job_seeker=maggie
        )

        self.prescriber_base_url = reverse("apply:list_for_prescriber")
        self.job_seeker_base_url = reverse("apply:list_for_job_seeker")
        self.siae_base_url = reverse("apply:list_for_siae")
        self.prescriber_exports_url = reverse("apply:list_for_prescriber_exports")
        self.siae_exports_url = reverse("apply:list_for_siae_exports")

        # Variables available for unit tests
        self.pole_emploi = pole_emploi
        self.hit_pit = hit_pit
        self.l_envol = l_envol
        self.thibault_pe = thibault_pe
        self.laurie_pe = laurie_pe
        self.eddie_hit_pit = eddie_hit_pit
        self.audrey_envol = audrey_envol
        self.maggie = maggie


####################################################
################### Job Seeker #####################  # noqa E266
####################################################


class ProcessListJobSeekerTest(ProcessListTest):
    def test_list_for_job_seeker_view(self):
        """
        Maggie wants to see job applications sent for her.
        """
        self.client.login(username=self.maggie.email, password=DEFAULT_PASSWORD)
        response = self.client.get(self.job_seeker_base_url)

        # Count job applications used by the template
        total_applications = len(response.context["job_applications_page"].object_list)

        # Result page should contain all SIAE's job applications.
        self.assertEqual(total_applications, self.maggie.job_applications.count())

    def test_list_for_job_seeker_view_filtered_by_state(self):
        """
        Provide a list of job applications sent by a job seeker
        and filtered by a state.
        """
        self.client.login(username=self.maggie.email, password=DEFAULT_PASSWORD)
        expected_state = self.maggie.job_applications.last().state
        params = urlencode({"states": [expected_state]}, True)
        url = f"{self.job_seeker_base_url}?{params}"
        response = self.client.get(url)

        # Count job applications used by the template
        applications = response.context["job_applications_page"].object_list

        # Result page should only contain job applications which status
        # matches the one selected by the user.
        self.assertEqual(len(applications), 1)
        self.assertEqual(applications[0].state, expected_state)

    def test_list_for_job_seeker_view_filtered_by_dates(self):
        """
        Provide a list of job applications sent by a job seeker
        and filtered by dates
        """
        now = timezone.now()

        for diff_day in [7, 5, 3, 0]:
            JobApplicationSentByJobSeekerFactory(
                created_at=now - timezone.timedelta(days=diff_day), job_seeker=self.maggie
            )

        self.client.login(username=self.maggie.email, password=DEFAULT_PASSWORD)

        date_format = DuetDatePickerWidget.INPUT_DATE_FORMAT

        start_date = now - timezone.timedelta(days=5)
        end_date = now - timezone.timedelta(days=1)
        query = urlencode(
            {
                "start_date": timezone.localdate(start_date).strftime(date_format),
                "end_date": timezone.localdate(end_date).strftime(date_format),
            }
        )
        url = f"{self.job_seeker_base_url}?{query}"
        response = self.client.get(url)
        applications = response.context["job_applications_page"].object_list

        self.assertEqual(len(applications), 2)
        self.assertGreaterEqual(applications[0].created_at, start_date)
        self.assertLessEqual(applications[0].created_at, end_date)


###################################################
#################### SIAE #########################  # noqa E266
###################################################


class ProcessListSiaeTest(ProcessListTest):
    def test_list_for_siae_view(self):
        """
        Eddie wants to see a list of job applications sent to his SIAE.
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)
        response = self.client.get(self.siae_base_url)

        total_applications = len(response.context["job_applications_page"].object_list)

        # Result page should contain all SIAE's job applications.
        self.assertEqual(total_applications, self.hit_pit.job_applications_received.not_archived().count())

    def test_list_for_siae_view__filtered_by_one_state(self):
        """
        Eddie wants to see only accepted job applications.
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)
        state_accepted = JobApplicationWorkflow.STATE_ACCEPTED
        params = urlencode({"states": [state_accepted]}, True)
        url = f"{self.siae_base_url}?{params}"
        response = self.client.get(url)

        applications = response.context["job_applications_page"].object_list

        self.assertEqual(len(applications), 1)
        self.assertEqual(applications[0].state, state_accepted)

    def test_list_for_siae_view__filtered_by_many_states(self):
        """
        Eddie wants to see NEW and PROCESSING job applications.
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)
        job_applications_states = [JobApplicationWorkflow.STATE_NEW, JobApplicationWorkflow.STATE_PROCESSING]
        params = urlencode({"states": job_applications_states}, True)
        url = f"{self.siae_base_url}?{params}"
        response = self.client.get(url)

        applications = response.context["job_applications_page"].object_list

        self.assertEqual(len(applications), 3)
        self.assertIn(applications[0].state.name, job_applications_states)

    def test_list_for_siae_view__filtered_by_dates(self):
        """
        Eddie wants to see job applications sent at a specific date.
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)
        date_format = DuetDatePickerWidget.INPUT_DATE_FORMAT
        job_applications = self.hit_pit.job_applications_received.not_archived().order_by("created_at")
        jobs_in_range = job_applications[3:]
        start_date = jobs_in_range[0].created_at

        # Negative indexing is not allowed in querysets
        end_date = jobs_in_range[len(jobs_in_range) - 1].created_at
        query = urlencode(
            {
                "start_date": timezone.localdate(start_date).strftime(date_format),
                "end_date": timezone.localdate(end_date).strftime(date_format),
            }
        )
        url = f"{self.siae_base_url}?{query}"
        response = self.client.get(url)
        applications = response.context["job_applications_page"].object_list

        self.assertEqual(len(applications), 5)
        self.assertGreaterEqual(applications[0].created_at, start_date)
        self.assertLessEqual(applications[0].created_at, end_date)

    def test_list_for_siae_view__empty_dates_in_params(self):
        """
        Our form uses a Datepicker that adds empty start and end dates
        in the HTTP query if they are not filled in by the user.
        Make sure the template loads all available job applications if fields are empty.
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)
        url = f"{self.siae_base_url}?start_date=&end_date="
        response = self.client.get(url)
        total_applications = len(response.context["job_applications_page"].object_list)

        self.assertEqual(total_applications, self.hit_pit.job_applications_received.not_archived().count())

    def test_view__filtered_by_sender_organization_name(self):
        """
        Eddie wants to see applications sent by Pôle emploi.
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)
        sender_organization = self.pole_emploi
        params = urlencode({"sender_organizations": [sender_organization.id]}, True)
        url = f"{self.siae_base_url}?{params}"
        response = self.client.get(url)

        applications = response.context["job_applications_page"].object_list

        self.assertEqual(len(applications), 8)
        self.assertEqual(applications[0].sender_prescriber_organization.id, sender_organization.id)

    def test_view__filtered_by_sender_name(self):
        """
        Eddie wants to see applications sent by a member of Pôle emploi.
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)
        sender = self.thibault_pe
        params = urlencode({"senders": [sender.id]}, True)
        url = f"{self.siae_base_url}?{params}"
        response = self.client.get(url)

        applications = response.context["job_applications_page"].object_list

        self.assertEqual(len(applications), 7)
        self.assertEqual(applications[0].sender.id, sender.id)

    def test_view__filtered_by_job_seeker_name(self):
        """
        Eddie wants to see Maggie's job applications.
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)
        job_seekers_ids = [self.maggie.id]
        params = urlencode({"job_seekers": job_seekers_ids}, True)
        url = f"{self.siae_base_url}?{params}"
        response = self.client.get(url)

        applications = response.context["job_applications_page"].object_list

        self.assertEqual(len(applications), 2)
        self.assertIn(applications[0].job_seeker.id, job_seekers_ids)

    def test_view__filtered_by_many_organization_names(self):
        """
        Eddie wants to see applications sent by Pôle emploi and L'Envol.
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)
        senders_ids = [self.pole_emploi.id, self.l_envol.id]
        params = urlencode({"sender_organizations": [self.thibault_pe.id, self.audrey_envol.id]}, True)
        url = f"{self.siae_base_url}?{params}"
        response = self.client.get(url)

        applications = response.context["job_applications_page"].object_list

        self.assertEqual(len(applications), 8)
        self.assertIn(applications[0].sender_prescriber_organization.id, senders_ids)

    def test_view__filtered_by_pass_state(self):
        """
        Eddie wants to see applications with a suspended or in progress IAE PASS.
        """
        now = timezone.now()
        yesterday = (now - timezone.timedelta(days=1)).date()
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)

        params = urlencode(
            {
                "states": [JobApplicationWorkflow.STATE_ACCEPTED, JobApplicationWorkflow.STATE_NEW],
                "pass_iae_active": True,
            },
            True,
        )
        response = self.client.get(f"{self.siae_base_url}?{params}")
        self.assertEqual(len(response.context["job_applications_page"].object_list), 0)

        job_application = JobApplicationWithApprovalFactory(
            state=JobApplicationWorkflow.STATE_ACCEPTED,
            hiring_start_at=yesterday,
            approval__start_at=yesterday,
            to_siae=self.hit_pit,
        )
        response = self.client.get(f"{self.siae_base_url}?{params}")
        applications = response.context["job_applications_page"].object_list
        self.assertEqual(len(applications), 1)
        self.assertIn(job_application, applications)

        params = urlencode(
            {
                "states": [JobApplicationWorkflow.STATE_ACCEPTED, JobApplicationWorkflow.STATE_NEW],
                "pass_iae_suspended": True,
            },
            True,
        )
        response = self.client.get(f"{self.siae_base_url}?{params}")
        self.assertEqual(len(response.context["job_applications_page"].object_list), 0)

        SuspensionFactory(
            approval=job_application.approval,
            start_at=yesterday,
            end_at=now + timezone.timedelta(days=2),
        )
        response = self.client.get(f"{self.siae_base_url}?{params}")

        applications = response.context["job_applications_page"].object_list
        self.assertEqual(len(applications), 1)
        self.assertIn(job_application, applications)

    def test_view__filtered_by_eligibility_validated(self):
        """
        Eddie wants to see applications of job seeker for whom
        the diagnosis of eligibility has been validated.
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)

        params = urlencode({"eligibility_validated": True})
        url = f"{self.siae_base_url}?{params}"

        response = self.client.get(url)
        self.assertEqual(len(response.context["job_applications_page"].object_list), 0)

        EligibilityDiagnosisFactory(job_seeker=self.maggie)

        response = self.client.get(url)
        # Maggie has two applications, one created in the state loop and the other created by SentByPrescriberFactory
        self.assertEqual(len(response.context["job_applications_page"].object_list), 2)

    def test_view__filtered_by_administrative_criteria(self):
        """
        Eddie wants to see applications of job seeker for whom
        the diagnosis of eligibility has been validated with specific criteria.
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)

        diagnosis = EligibilityDiagnosisFactory(job_seeker=self.maggie)

        level1_criterion = AdministrativeCriteria.objects.filter(level=AdministrativeCriteria.Level.LEVEL_1).first()
        level2_criterion = AdministrativeCriteria.objects.filter(level=AdministrativeCriteria.Level.LEVEL_2).first()
        level1_other_criterion = AdministrativeCriteria.objects.filter(
            level=AdministrativeCriteria.Level.LEVEL_1
        ).last()

        diagnosis.administrative_criteria.add(level1_criterion)
        diagnosis.administrative_criteria.add(level2_criterion)
        diagnosis.save()

        # Filter by level1 criterion
        params = urlencode({"criteria": [level1_criterion.pk]}, True)
        url = f"{self.siae_base_url}?{params}"
        response = self.client.get(url)
        applications = response.context["job_applications_page"].object_list
        self.assertEqual(len(applications), 2)

        # Filter by level2 criterion
        params = urlencode({"criteria": [level2_criterion.pk]}, True)
        url = f"{self.siae_base_url}?{params}"
        response = self.client.get(url)
        applications = response.context["job_applications_page"].object_list
        self.assertEqual(len(applications), 2)

        # Filter by two criteria
        params = urlencode({"criteria": [level1_criterion.pk, level2_criterion.pk]}, True)
        url = f"{self.siae_base_url}?{params}"
        response = self.client.get(url)
        applications = response.context["job_applications_page"].object_list
        self.assertEqual(len(applications), 2)

        # Filter by other criteria
        params = urlencode({"criteria": [level1_other_criterion.pk]}, True)
        url = f"{self.siae_base_url}?{params}"
        response = self.client.get(url)
        applications = response.context["job_applications_page"].object_list
        self.assertEqual(len(applications), 0)

    def test_view__filtered_by_jobseeker_department(self):
        """
        Eddie wants to see applications of job seeker who live in given department.
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)

        # Maggie moves to Department 37
        self.maggie.post_code = "37000"
        self.maggie.save()

        params = urlencode({"departments": ["37"]}, True)
        url = f"{self.siae_base_url}?{params}"
        response = self.client.get(url)
        applications = response.context["job_applications_page"].object_list

        # Maggie has two applications and is the only one living in department 37.
        self.assertEqual(len(applications), 2)

    def test_view__filtered_by_selected_job(self):
        """
        Eddie wants to see applications with a given job appellation.
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)

        (appellation1, appellation2) = Appellation.objects.all().order_by("?")[0:2]
        JobApplicationSentByJobSeekerFactory(to_siae=self.hit_pit, selected_jobs=[appellation1])
        JobApplicationSentByJobSeekerFactory(to_siae=self.hit_pit, selected_jobs=[appellation2])

        params = urlencode({"selected_jobs": [appellation1.pk]}, True)
        url = f"{self.siae_base_url}?{params}"
        response = self.client.get(url)
        applications = response.context["job_applications_page"].object_list

        self.assertEqual(len(applications), 1)
        self.assertIn(appellation1, [job_desc.appellation for job_desc in applications[0].selected_jobs.all()])


####################################################
################### Prescriber #####################  # noqa E266
####################################################


class ProcessListPrescriberTest(ProcessListTest):
    def test_list_for_prescriber_view(self):
        """
        Connect as Thibault to see a list of job applications
        sent by his organization (Pôle emploi).
        """
        self.client.login(username=self.thibault_pe.email, password=DEFAULT_PASSWORD)
        response = self.client.get(self.prescriber_base_url)

        # Count job applications used by the template
        total_applications = len(response.context["job_applications_page"].object_list)

        self.assertEqual(total_applications, self.pole_emploi.jobapplication_set.count())

    def test_list_for_prescriber_exports_view(self):
        """
        Connect as Thibault to see a list of available job applications exports
        """
        self.client.login(username=self.thibault_pe.email, password=DEFAULT_PASSWORD)
        response = self.client.get(self.prescriber_exports_url)

        self.assertEqual(200, response.status_code)

    def test_list_for_prescriber_exports_download_view(self):
        """
        Connect as Thibault to see a list of available job applications exports
        """
        self.client.login(username=self.thibault_pe.email, password=DEFAULT_PASSWORD)

        response = self.client.get(self.prescriber_exports_url)
        sample_date = response.context["job_applications_by_month"][0]["month"]
        month_identifier = sample_date.strftime("%Y-%d")
        download_url = reverse(
            "apply:list_for_prescriber_exports_download", kwargs={"month_identifier": month_identifier}
        )

        response = self.client.get(download_url)

        self.assertEqual(200, response.status_code)
        self.assertIn("text/csv", response.get("Content-Type"))

    def test_view__filtered_by_state(self):
        """
        Thibault wants to filter a list of job applications
        by the default initial state.
        """
        self.client.login(username=self.thibault_pe.email, password=DEFAULT_PASSWORD)
        expected_state = JobApplicationWorkflow.initial_state
        params = urlencode({"states": [expected_state]}, True)
        url = f"{self.prescriber_base_url}?{params}"
        response = self.client.get(url)

        applications = response.context["job_applications_page"].object_list
        self.assertEqual(len(applications), 2)
        self.assertEqual(applications[0].state, expected_state)

    def test_view__filtered_by_sender_name(self):
        """
        Thibault wants to see job applications sent by his colleague Laurie.
        He filters results using her full name.
        """
        self.client.login(username=self.thibault_pe.email, password=DEFAULT_PASSWORD)
        sender_id = self.laurie_pe.id
        params = urlencode({"senders": sender_id})
        url = f"{self.prescriber_base_url}?{params}"
        response = self.client.get(url)

        applications = response.context["job_applications_page"].object_list
        self.assertEqual(len(applications), 1)
        self.assertEqual(applications[0].sender.id, sender_id)

    def test_view__filtered_by_job_seeker_name(self):
        """
        Thibault wants to see Maggie's job applications.
        """
        self.client.login(username=self.thibault_pe.email, password=DEFAULT_PASSWORD)
        job_seekers_ids = [self.maggie.id]
        params = urlencode({"job_seekers": job_seekers_ids}, True)
        url = f"{self.prescriber_base_url}?{params}"
        response = self.client.get(url)

        applications = response.context["job_applications_page"].object_list
        self.assertEqual(len(applications), 2)
        self.assertIn(applications[0].job_seeker.id, job_seekers_ids)

    def test_view__filtered_by_siae_name(self):
        """
        Thibault wants to see applications sent to Hit Pit.
        """
        self.client.login(username=self.thibault_pe.email, password=DEFAULT_PASSWORD)
        to_siaes_ids = [self.hit_pit.pk]
        params = urlencode({"to_siaes": to_siaes_ids}, True)
        url = f"{self.prescriber_base_url}?{params}"
        response = self.client.get(url)

        applications = response.context["job_applications_page"].object_list
        self.assertEqual(len(applications), 8)
        self.assertIn(applications[0].to_siae.pk, to_siaes_ids)


####################################################
################### Prescriber export list #########
####################################################


class ProcessListExportsPrescriberTest(ProcessListTest):
    def test_list_for_prescriber_exports_view(self):
        """
        Connect as Thibault to see a list of available job applications exports
        """
        self.client.login(username=self.thibault_pe.email, password=DEFAULT_PASSWORD)
        response = self.client.get(self.prescriber_exports_url)

        self.assertEqual(200, response.status_code)

    def test_list_for_prescriber_exports_as_siae_view(self):
        """
        Connect as a SIAE and try to see the prescriber export -> redirected
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)
        response = self.client.get(self.prescriber_exports_url)

        self.assertEqual(302, response.status_code)


####################################################
################### SIAE export list #########
####################################################


class ProcessListExportsSiaeTest(ProcessListTest):
    def test_list_for_siae_exports_view(self):
        """
        Connect as a SIAE to see a list of available job applications exports
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)
        response = self.client.get(self.siae_exports_url)

        self.assertEqual(200, response.status_code)

    def test_list_for_siae_exports_as_prescriber_view(self):
        """
        Connect as Thibault and try to see the siae export -> redirected
        """
        self.client.login(username=self.thibault_pe.email, password=DEFAULT_PASSWORD)
        response = self.client.get(self.siae_exports_url)

        self.assertEqual(404, response.status_code)


####################################################
################### Prescriber export download #########
####################################################


class ProcessListExportsDownloadPrescriberTest(ProcessListTest):
    def test_list_for_prescriber_exports_download_view(self):
        """
        Connect as Thibault to download a CSV export of available job applications
        """
        self.client.login(username=self.thibault_pe.email, password=DEFAULT_PASSWORD)

        response = self.client.get(self.prescriber_exports_url)
        sample_date = response.context["job_applications_by_month"][0]["month"]
        month_identifier = sample_date.strftime("%Y-%d")
        download_url = reverse(
            "apply:list_for_prescriber_exports_download", kwargs={"month_identifier": month_identifier}
        )

        response = self.client.get(download_url)

        self.assertEqual(200, response.status_code)
        self.assertIn("text/csv", response.get("Content-Type"))

    def test_list_for_siae_exports_download_view(self):
        """
        Connect as Thibault and attempt to download a CSV export of available job applications from SIAE
        """
        self.client.login(username=self.thibault_pe.email, password=DEFAULT_PASSWORD)

        response = self.client.get(self.prescriber_exports_url)
        sample_date = response.context["job_applications_by_month"][0]["month"]
        month_identifier = sample_date.strftime("%Y-%d")
        download_url = reverse("apply:list_for_siae_exports_download", kwargs={"month_identifier": month_identifier})

        response = self.client.get(download_url)

        self.assertEqual(404, response.status_code)


####################################################
################### Prescriber export download #########
####################################################


class ProcessListExportsDownloadSiaeTest(ProcessListTest):
    def test_list_for_siae_exports_download_view(self):
        """
        Connect as Thibault to download a CSV export of available job applications
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)

        response = self.client.get(self.siae_exports_url)
        sample_date = response.context["job_applications_by_month"][0]["month"]
        month_identifier = sample_date.strftime("%Y-%d")
        download_url = reverse("apply:list_for_siae_exports_download", kwargs={"month_identifier": month_identifier})

        response = self.client.get(download_url)

        self.assertEqual(200, response.status_code)
        self.assertIn("text/csv", response.get("Content-Type"))

    def test_list_for_prescriber_exports_download_view(self):
        """
        Connect as SIAE and attempt to download a CSV export of available job applications from prescribers
        """
        self.client.login(username=self.eddie_hit_pit.email, password=DEFAULT_PASSWORD)

        response = self.client.get(self.siae_exports_url)
        sample_date = response.context["job_applications_by_month"][0]["month"]
        month_identifier = sample_date.strftime("%Y-%d")
        download_url = reverse(
            "apply:list_for_prescriber_exports_download", kwargs={"month_identifier": month_identifier}
        )

        response = self.client.get(download_url)

        self.assertEqual(302, response.status_code)
