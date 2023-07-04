import respx
from allauth.account.adapter import get_adapter
from allauth.account.models import EmailConfirmationHMAC
from django.core import mail
from django.urls import reverse

from itou.siaes.factories import SiaeFactory
from itou.users.enums import KIND_PRESCRIBER, KIND_SIAE_STAFF
from itou.users.factories import DEFAULT_PASSWORD, JobSeekerFactory
from itou.users.models import User
from itou.utils import constants as global_constants
from tests.openid_connect.inclusion_connect.test import InclusionConnectBaseTestCase
from tests.openid_connect.inclusion_connect.tests import mock_oauth_dance
from tests.utils.test import TestCase


def get_confirm_email_url(request, email):
    user = User.objects.get(email=email)
    user_email = user.emailaddress_set.first()
    return get_adapter().get_email_confirmation_url(request, EmailConfirmationHMAC(user_email))


class WelcomingTourTest(InclusionConnectBaseTestCase):
    def setUp(self):
        self.email = None
        super().setUp()

    def verify_email(self, request, email):
        # User verifies its email clicking on the email he received
        confirm_email_url = get_confirm_email_url(request, email)
        response = self.client.post(confirm_email_url, follow=True)
        assert response.status_code == 200
        return response

    def test_new_job_seeker_sees_welcoming_tour_test(self):
        job_seeker = JobSeekerFactory.build()

        # First signup step: job seeker NIR.
        url = reverse("signup:job_seeker_nir")
        self.client.post(url, {"nir": job_seeker.nir, "confirm": 1})

        # Second signup step: job seeker credentials.
        url = reverse("signup:job_seeker")
        post_data = {
            "title": job_seeker.title,
            "first_name": job_seeker.first_name,
            "last_name": job_seeker.last_name,
            "email": job_seeker.email,
            "password1": DEFAULT_PASSWORD,
            "password2": DEFAULT_PASSWORD,
        }
        response = self.client.post(url, data=post_data)
        assert response.status_code == 302
        response = self.verify_email(response.wsgi_request, email=job_seeker.email)

        # User should be redirected to the welcoming tour as he just signed up
        assert response.wsgi_request.path == reverse("welcoming_tour:index")
        self.assertTemplateUsed(response, "welcoming_tour/job_seeker.html")

        self.client.logout()
        response = self.client.post(
            reverse("login:job_seeker"), follow=True, data={"login": job_seeker.email, "password": DEFAULT_PASSWORD}
        )
        assert response.wsgi_request.path != reverse("welcoming_tour:index")
        self.assertContains(response, "Revoir le message")

    @respx.mock
    def test_new_prescriber_sees_welcoming_tour_test(self):
        session = self.client.session
        session[global_constants.ITOU_SESSION_PRESCRIBER_SIGNUP_KEY] = {"url_history": []}
        session.save()
        response = mock_oauth_dance(self.client, KIND_PRESCRIBER)
        response = self.client.get(response.url, follow=True)

        # User should be redirected to the welcoming tour as he just signed up
        assert response.wsgi_request.path == reverse("welcoming_tour:index")
        self.assertTemplateUsed(response, "welcoming_tour/prescriber.html")

        self.client.logout()
        response = mock_oauth_dance(self.client, KIND_PRESCRIBER, expected_redirect_url=reverse("dashboard:index"))
        response = self.client.get(response.url, follow=True)
        self.assertContains(response, "Revoir le message")

    @respx.mock
    def test_new_employer_sees_welcoming_tour(self):
        siae = SiaeFactory(with_membership=True)
        token = siae.get_token()
        previous_url = reverse("signup:siae_user", args=(siae.pk, token))
        next_url = reverse("signup:siae_join", args=(siae.pk, token))
        response = mock_oauth_dance(
            self.client,
            KIND_SIAE_STAFF,
            previous_url=previous_url,
            next_url=next_url,
        )
        response = self.client.get(response.url, follow=True)

        # User should be redirected to the welcoming tour as he just signed up
        assert response.wsgi_request.path == reverse("welcoming_tour:index")
        self.assertTemplateUsed(response, "welcoming_tour/siae_staff.html")

        self.client.logout()
        response = mock_oauth_dance(self.client, KIND_SIAE_STAFF, expected_redirect_url=reverse("dashboard:index"))
        response = self.client.get(response.url, follow=True)
        self.assertContains(response, "Revoir le message")


class WelcomingTourExceptions(TestCase):
    def verify_email(self, email, request):
        # User verifies its email clicking on the email he received
        confirm_email_url = get_confirm_email_url(request, email)
        response = self.client.post(confirm_email_url, follow=True)
        assert response.status_code == 200
        return response

    def test_new_job_seeker_is_redirected_after_welcoming_tour_test(self):
        siae = SiaeFactory(with_membership=True)
        job_seeker = JobSeekerFactory.build()

        # First signup step: job seeker NIR.
        next_to = reverse("apply:start", kwargs={"siae_pk": siae.pk})
        url = f"{reverse('signup:job_seeker_nir')}?next={next_to}"
        self.client.post(url, {"nir": job_seeker.nir, "confirm": 1})

        # Second signup step: job seeker credentials.
        url = f"{reverse('signup:job_seeker')}?next={next_to}"
        post_data = {
            "title": job_seeker.title,
            "first_name": job_seeker.first_name,
            "last_name": job_seeker.last_name,
            "email": job_seeker.email,
            "password1": DEFAULT_PASSWORD,
            "password2": DEFAULT_PASSWORD,
        }
        response = self.client.post(url, data=post_data)
        assert response.status_code == 302
        response = self.verify_email(job_seeker.email, response.wsgi_request)

        # The user should not be redirected to the welcoming path if he wanted to perform
        # another action before signing up.
        assert response.wsgi_request.path not in reverse("welcoming_tour:index")

        # The user is redirected to "apply:step_check_job_seeker_info"
        # as birthdate and pole_emploi_id are missing from the signup form.
        # This is a valid behavior that may change in the future so
        # let's avoid too specific tests.
        assert response.wsgi_request.path.startswith("/apply")

        content = mail.outbox[0].body
        assert next_to in content