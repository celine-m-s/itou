import csv
import os
import os.path
from io import StringIO

import respx
from django.conf import settings
from django.core import management
from django.test import TestCase, override_settings
from httpx import Response

from itou.users.factories import JobSeekerWithAddressFactory


def mock_ban_api(user_id):
    resp = Response(
        200,
        text=f"""id;adresse_line_1;post_code;city;result_label;result_score;latitude;longitude\n"""
        f"""{user_id};École Claude Déruet;6 Rue Albert 1er;54600,Villers-lès-Nancy;"""
        f"""Avenue de la République 54580 Moineville;0.94;49.205293;5.944871\n""",
    )
    respx.post(settings.API_BAN_BASE_URL + "/search/csv").mock(return_value=resp)


@override_settings(API_BAN_BASE_URL="https://foobar.com")
class GeolocateJobseekerManagementCommandTest(TestCase):
    """
    Bulk update - import - export of user location via BAN API.
    Was in the `geo` app, but is likely to be "one-shot", hence moved to `scripts`.
    """

    def run_command(self, *args, **kwargs):
        out = StringIO()
        err = StringIO()

        management.call_command("geolocate_jobseeker_addresses", *args, stdout=out, stderr=err, **kwargs)

        return out.getvalue(), err.getvalue()

    def test_update_dry_run(self):
        JobSeekerWithAddressFactory(is_active=True)

        out, _ = self.run_command("update")

        self.assertIn("Geolocation of active job seekers addresses (updating DB)", out)
        self.assertIn("+ NOT storing data", out)
        self.assertIn("+ NOT calling geo API", out)

    @respx.mock
    def test_update_wet_run(self):
        user = JobSeekerWithAddressFactory(is_active=True)

        mock_ban_api(user.pk)

        out, _ = self.run_command("update", wet_run=True)

        self.assertIn("Geolocation of active job seekers addresses (updating DB)", out)
        self.assertNotIn("+ NOT storing data", out)
        self.assertNotIn("+ NOT calling geo API", out)

        user.refresh_from_db()

        self.assertEqual("SRID=4326;POINT (5.944871 49.205293)", user.coords)
        self.assertEqual(0.94, user.geocoding_score)
        self.assertIn("+ updated: 1, errors: 0, total: 1", out)

    def test_export_dry_run(self):
        out, _ = self.run_command("export")

        self.assertIn("Export job seeker geocoding data to file:", out)
        self.assertIn("+ implicit 'dry-run': NOT creating file", out)

    def test_export_wet_run(self):
        coords = "SRID=4326;POINT (5.944871 49.205293)"
        score = 0.95
        JobSeekerWithAddressFactory(
            is_active=True,
            coords=coords,
            geocoding_score=score,
        )
        path = os.path.join(settings.EXPORT_DIR, "export.csv")

        out, _ = self.run_command("export", filename=path, wet_run=True)

        self.assertIn("+ found 1 geocoding entries with score > 0.0", out)

        # Could not find an elegant way to mock file creation
        # `mock_open()` does not seem to be the right thing to use for write ops
        # Works well for reading ops though
        with open(path, "r") as f:
            [_, row] = csv.reader(f, delimiter=";")
            self.assertIn(coords, row)
            self.assertIn(str(score), row)

    def test_import_dry_run(self):
        out, _ = self.run_command("import", filename="foo")

        self.assertIn("Import job seeker geocoding data from file:", out)
        self.assertIn("+ implicit `dry-run`: reading file but NOT writing into DB", out)

    def test_import_wet_run(self):
        user = JobSeekerWithAddressFactory(is_active=True)
        path = os.path.join(settings.IMPORT_DIR, "sample_user_geoloc.csv")

        with open(path, "w") as f:
            f.write("id;coords;geocoding_score\n")
            f.write(f"""{user.pk};"SRID=4326;POINT (5.944871 49.205293)";0.95""")

        out, _ = self.run_command("import", filename=path, wet_run=True)

        self.assertIn("Import job seeker geocoding data from file:", out)

        user.refresh_from_db()

        self.assertEqual(0.95, user.geocoding_score)
        self.assertEqual("SRID=4326;POINT (5.944871 49.205293)", user.coords)
        self.assertIn("+ updated 1 'user.User' objects", out)