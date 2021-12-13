# flake8: noqa
# pylint: disable=logging-fstring-interpolation, singleton-comparison, invalid-name

import csv
import datetime
import logging
import uuid
from pathlib import Path

import pandas as pd
import pytz
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.utils import IntegrityError
from tqdm import tqdm

from itou.approvals.models import Approval
from itou.asp.models import Commune
from itou.common_apps.address.departments import department_from_postcode
from itou.job_applications.models import JobApplication, JobApplicationWorkflow
from itou.siaes.models import Siae
from itou.users.models import User
from itou.utils.validators import validate_nir


# Columns
APPROVAL_COL = "agr_numero_agrement"
BIRTHDATE_COL = "pph_date_naissance"
BIRTHCITY_INSEE_COL = "code_insee_naissance"
CITY_INSEE_COL = "codeinseecom"
CONTRACT_STARTDATE_COL = "ctr_date_embauche"
CONTRACT_ENDDATE_COL = "ctr_date_fin_reelle"
COUNTRY_COL = "adr_code_insee_pays"
EMAIL_COL = "adr_mail"
FIRST_NAME_COL = "pph_prenom"
GENDER_COL = "pph_sexe"
LAST_NAME_COL = "pph_nom_usage"
NIR_COL = "ppn_numero_inscription"
PHONE_COL = "adr_telephone"
POST_CODE_COL = "codepostalcedex"
SIAE_NAME_COL = "pmo_denom_soc"
SIRET_COL = "pmo_siret"
PASS_IAE_NUMBER_COL = "Numéro de PASS IAE"
USER_PK_COL = "ID salarié"
COMMENTS_COL = "Commentaire"

DATE_FORMAT = "%Y-%m-%d"


class Command(BaseCommand):
    """
    On December 1st, 2021, every AI were asked to present a PASS IAE for each of their employees.
    Before that date, they were able to hire without one. To catch up with the ongoing stock,
    the platform has to create missing users and deliver brand new PASS IAE.
    AI employees list was provided by the ASP in a CSV file.

    This is what this script does:
    1/ Parse a file provided by the ASP.
    2/ Clean data.
    3/ Create job seekers, approvals and job applications when needed.

    Mandatory arguments
    -------------------
    File path: path to the CSV file.
    django-admin import_ai_employees --file-path=/imports/file.csv

    Developer email: email of the person running this script. It must belong to
    a user account registered in the database.
    Job applications, users and approvals will be marked as created by this person.
    django-admin import_ai_employees --email=funky@developer.com

    Optional arguments
    ------------------
    Run without writing to the database:
    django-admin import_ai_employees --dry-run

    Run with a small amount of data (sample):
    django-admin import_ai_employees --sample-size=100

    """

    help = "Import AI employees and deliver a PASS IAE."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", dest="dry_run", action="store_true", help="Don't change anything in the database."
        )
        parser.add_argument(
            "--sample-size",
            dest="sample_size",
            help="Sample size to run this script with (instead of the whole file).",
        )

        parser.add_argument(
            "--invalid-nirs-only",
            dest="invalid_nirs_only",
            action="store_true",
            help="Only save users whose NIR is invalid.",
        )

        parser.add_argument(
            "--file-path",
            dest="file_path",
            required=True,
            action="store",
            help="Absolute path of the CSV file to import",
        )
        parser.add_argument(
            "--email",
            dest="developer_email",
            required=True,
            action="store",
            help="Developer email account (in the Itou database).",
        )

    def set_logger(self, verbosity):
        """
        Set logger level based on the verbosity option.
        """
        handler = logging.StreamHandler(self.stdout)

        self.logger = logging.getLogger(__name__)
        self.logger.propagate = False
        self.logger.addHandler(handler)

        self.logger.setLevel(logging.INFO)
        if verbosity >= 1:
            self.logger.setLevel(logging.DEBUG)

    def get_ratio(self, first_value, second_value):
        return round((first_value / second_value) * 100, 2)

    def fix_dates(self, date):
        # This is quick and ugly!
        if date.startswith("16"):
            return date[0] + "9" + date[2:]
        return date

    def log_to_csv(self, csv_name, logs):
        csv_file = Path(settings.EXPORT_DIR) / f"{csv_name}.csv"
        with open(csv_file, "w", newline="") as file:
            if isinstance(logs, list):
                fieldnames = list(logs[0].keys())
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(logs)
            else:
                file.write(logs.to_csv())

    def clean_nir(self, row):
        nir = row[NIR_COL]
        try:
            validate_nir(nir)
        except ValidationError:
            return None
        return nir

    def siret_validated_by_asp(self, row):
        # ASP-validated list.
        excluded_sirets = [
            "88763724700016",
            "34536738700031",
            "82369160500013",
            "49185002000026",
            "33491197100029",
            "43196860100887",
            "47759309900054",
            "34229040000031",
            "89020637800014",
            "40136283500035",
            "88309441900024",
            "34526210900043",
            "35050254800034",
            "48856661300045",
            "81054375100012",
            "39359706700023",
            "38870926300023",
            "38403628100010",
            "37980819900010",
            "42385382900129",
            "43272738600018",
            "34280044800033",
            "51439409700018",
            "50088443200054",
            "26300199200019",
            "38420642100040",
            "33246830500021",
            "75231474000016",
            "34112012900034",
        ]
        return row[SIRET_COL] not in excluded_sirets

    def fake_email(self):
        return f"{uuid.uuid4().hex}@email-temp.com"

    def get_inexistent_structures(self, df):
        unique_ai = set(df[SIRET_COL])  # Between 600 and 700.
        existing_structures = Siae.objects.filter(siret__in=unique_ai, kind=Siae.KIND_AI).values_list(
            "siret", flat=True
        )
        not_existing_structures = unique_ai.difference(existing_structures)
        self.logger.debug(f"{len(not_existing_structures)} not existing structures:")
        self.logger.debug(not_existing_structures)
        return not_existing_structures

    def commune_from_insee_col(self, insee_code):
        try:
            commune = Commune.objects.current().get(code=insee_code)
        except Commune.DoesNotExist:
            # Communes stores the history of city names and INSEE codes.
            # Sometimes, a commune is found twice but with the same name.
            # As we just need a human name, we can take the first one.
            commune = Commune.objects.filter(code=insee_code).first()
        except Commune.MultipleObjectsReturned:
            commune = Commune.objects.current().filter(code=insee_code).first()
        else:
            commune = Commune.objects.current().get(code=insee_code)

        if insee_code == "01440":
            # Veyziat has been merged with Oyonnax.
            commune = Commune(name="Veyziat", code="01283")
        return commune

    def find_or_create_job_seeker(self, row, created_by):
        # Data has been formatted previously.
        created = False
        # Get city by its INSEE code to fill in the `User.city` attribute with a valid name.
        commune = self.commune_from_insee_col(row[CITY_INSEE_COL])

        user_data = {
            "first_name": row[FIRST_NAME_COL].title(),
            "last_name": row[LAST_NAME_COL].title(),
            "birthdate": row[BIRTHDATE_COL],
            # If no email: create a fake one.
            "email": row[EMAIL_COL] or self.fake_email(),
            "address_line_1": f"{row['adr_numero_voie']} {row['codeextensionvoie']} {row['codetypevoie']} {row['adr_libelle_voie']}",
            "address_line_2": f"{row['adr_cplt_distribution']} {row['adr_point_remise']}",
            "post_code": row[POST_CODE_COL],
            "city": commune.name.title(),
            "department": department_from_postcode(row[POST_CODE_COL]),
            "phone": row[PHONE_COL],
            "nir": row[NIR_COL],
            "date_joined": settings.AI_EMPLOYEES_STOCK_IMPORT_DATE,
        }

        # If NIR is not valid, row[NIR_COL] is empty.
        # See `self.clean_nir`.
        if not row.nir_is_valid:
            # ignored_nirs += 1
            user_data["nir"] = None

        job_seeker = User.objects.filter(nir=user_data["nir"]).exclude(nir__isnull=True).first()

        if not job_seeker:
            job_seeker = User.objects.filter(email=user_data["email"]).first()

        # Some e-mail addresses belong to prescribers!
        if job_seeker and not job_seeker.is_job_seeker:
            # If job seeker is not a job seeker, create a new one.
            user_data["email"] = self.fake_email()
            job_seeker = None

        if not job_seeker:
            # Find users created previously by this script,
            # either because a bug forced us to interrupt it
            # or because we had to run it twice to import new users.
            job_seeker = User.objects.filter(
                first_name=user_data["first_name"],
                last_name=user_data["last_name"],
                birthdate=user_data["birthdate"].date(),
                created_by=created_by,
                date_joined__date=settings.AI_EMPLOYEES_STOCK_IMPORT_DATE.date(),
            ).first()

        if not job_seeker:
            if self.dry_run:
                job_seeker = User(**user_data)
            else:
                job_seeker = User.create_job_seeker_by_proxy(created_by, **user_data)
            created = True

        return created, job_seeker

    def import_data_into_itou(self, df):
        df = df.copy()

        created_users = 0
        already_existing_users = 0
        ignored_nirs = 0
        already_existing_approvals = 0
        created_approvals = 0
        already_existing_job_apps = 0
        created_job_applications = 0

        # A fixed creation date allows us to retrieve objects
        # created by this script.
        # See Approval.is_from_ai_stock for example.
        objects_created_at = settings.AI_EMPLOYEES_STOCK_IMPORT_DATE

        # Get developer account by email.
        # Used to store who created the following users, approvals and job applications.
        developer = User.objects.get(email=self.developer_email)

        pbar = tqdm(total=len(df))
        for i, row in df.iterrows():
            pbar.update(1)

            with transaction.atomic():

                created, job_seeker = self.find_or_create_job_seeker(row=row, created_by=developer)

                if created:
                    created_users += 1
                else:
                    already_existing_users += 1

                # If job seeker has already a valid approval: don't redeliver it.
                if job_seeker.approvals.valid().exists():
                    already_existing_approvals += 1
                    approval = job_seeker.approvals_wrapper.latest_approval
                else:
                    approval = Approval(
                        start_at=datetime.date(2021, 12, 1),
                        end_at=datetime.date(2023, 11, 30),
                        user_id=job_seeker.pk,
                        created_by=developer,
                        created_at=objects_created_at,
                    )
                    if not self.dry_run:
                        # In production, it can raise an IntegrityError if another PASS has just been delivered a few seconds ago.
                        # Try to save with another number until it succeeds.
                        succeeded = None
                        while succeeded is None:
                            try:
                                # `Approval.save()` delivers an automatic number.
                                approval.save()
                                succeeded = True
                            except IntegrityError:
                                pass
                    created_approvals += 1

                # Create a new job application.
                siae = Siae.objects.prefetch_related("memberships").get(kind=Siae.KIND_AI, siret=row[SIRET_COL])

                # Find job applications created previously by this script,
                # either because a bug forced us to interrupt it
                # or because we had to run it twice to import new users.
                job_application_exists = JobApplication.objects.filter(
                    to_siae=siae,
                    approval_manually_delivered_by=developer,
                    created_at__date=objects_created_at.date(),
                    job_seeker=job_seeker,
                ).exists()
                if job_application_exists:
                    already_existing_job_apps += 1
                else:
                    job_app_dict = {
                        "sender": siae.active_admin_members.first(),
                        "sender_kind": JobApplication.SENDER_KIND_SIAE_STAFF,
                        "sender_siae": siae,
                        "to_siae": siae,
                        "job_seeker": job_seeker,
                        "state": JobApplicationWorkflow.STATE_ACCEPTED,
                        "hiring_start_at": row[CONTRACT_STARTDATE_COL],
                        "approval_delivery_mode": JobApplication.APPROVAL_DELIVERY_MODE_MANUAL,
                        "approval_id": approval.pk,
                        "approval_manually_delivered_by": developer,
                        "create_employee_record": False,
                        "created_at": objects_created_at,
                    }
                    job_application = JobApplication(**job_app_dict)
                    if not self.dry_run:
                        job_application.save()
                    created_job_applications += 1

            # Update dataframe values.
            # https://stackoverflow.com/questions/25478528/updating-value-in-iterrow-for-pandas
            df.loc[i, USER_PK_COL] = job_seeker.jobseeker_hash_id
            df.loc[i, PASS_IAE_NUMBER_COL] = approval.number

        self.logger.info("Import is over!")
        self.logger.info(f"Already existing users: {already_existing_users}.")
        self.logger.info(f"Created users: {created_users}.")
        self.logger.info(f"Ignored NIRs: {ignored_nirs}.")
        self.logger.info(f"Already existing approvals: {already_existing_approvals}.")
        self.logger.info(f"Created approvals: {created_approvals}.")
        self.logger.info(f"Already existing job applications: {already_existing_job_apps}.")
        self.logger.info(f"Created job applications: {created_job_applications}.")

        return df

    def clean_df(self, df):
        df[BIRTHDATE_COL] = df[BIRTHDATE_COL].apply(self.fix_dates)
        df[BIRTHDATE_COL] = pd.to_datetime(df[BIRTHDATE_COL], format=DATE_FORMAT)
        df[CONTRACT_STARTDATE_COL] = pd.to_datetime(df[CONTRACT_STARTDATE_COL], format=DATE_FORMAT)
        df[NIR_COL] = df.apply(self.clean_nir, axis=1)
        df["nir_is_valid"] = ~df[NIR_COL].isnull()
        df["siret_validated_by_asp"] = df.apply(self.siret_validated_by_asp, axis=1)

        # Replace empty values by "" instead of NaN.
        df = df.fillna("")
        return df

    def add_columns_for_asp(self, df):
        df[COMMENTS_COL] = ""
        df[PASS_IAE_NUMBER_COL] = ""
        df[USER_PK_COL] = ""
        return df

    def assert_asp_columns(self, df):
        expected_columns = [
            COMMENTS_COL,
            PASS_IAE_NUMBER_COL,
            USER_PK_COL,
        ]
        assert all(item in df.columns for item in expected_columns)

    def filter_invalid_nirs(self, df):
        total_df = df.copy()
        invalid_nirs_df = total_df[~total_df.nir_is_valid].copy()
        comment = "NIR invalide. Utilisateur potentiellement créé sans NIR."
        total_df.loc[invalid_nirs_df.index, COMMENTS_COL] = comment
        invalid_nirs_df.loc[invalid_nirs_df.index, COMMENTS_COL] = comment
        return total_df, invalid_nirs_df

    def remove_ignored_rows(self, total_df):
        # Exclude ended contracts.
        total_df = total_df.copy()
        filtered_df = total_df.copy()
        ended_contracts = total_df[total_df[CONTRACT_ENDDATE_COL] != ""]
        filtered_df = filtered_df.drop(ended_contracts.index)
        self.logger.info(f"Ended contract: excluding {len(ended_contracts)} rows.")
        total_df.loc[ended_contracts.index, COMMENTS_COL] = "Ligne ignorée : contrat terminé."

        # List provided by the ASP.
        excluded_structures_df = filtered_df[~filtered_df.siret_validated_by_asp]
        self.logger.info(f"Inexistent structures: excluding {len(excluded_structures_df)} rows.")
        filtered_df = filtered_df.drop(excluded_structures_df.index)
        total_df.loc[
            excluded_structures_df.index, COMMENTS_COL
        ] = "Ligne ignorée : entreprise inexistante communiquée par l'ASP."

        # Inexistent SIRETS.
        inexisting_sirets = self.get_inexistent_structures(filtered_df)
        inexistent_structures_df = filtered_df[filtered_df[SIRET_COL].isin(inexisting_sirets)]
        self.logger.info(f"Inexistent structures: excluding {len(inexistent_structures_df)} rows.")
        filtered_df = filtered_df.drop(inexistent_structures_df.index)
        total_df.loc[inexistent_structures_df.index, COMMENTS_COL] = "Ligne ignorée : entreprise inexistante."

        # Exclude rows with an approval.
        rows_with_approval_df = filtered_df[filtered_df[APPROVAL_COL] != ""]
        filtered_df = filtered_df.drop(rows_with_approval_df.index)
        self.logger.info(f"Existing approval: excluding {len(rows_with_approval_df)} rows.")
        total_df.loc[rows_with_approval_df.index, COMMENTS_COL] = "Ligne ignorée : agrément ou PASS IAE renseigné."
        return total_df, filtered_df

    def handle(self, file_path, developer_email, dry_run=False, invalid_nirs_only=False, **options):
        """
        Each line represents a contract.
        1/ Read the file and clean data.
        2/ Exclude ignored rows.
        3/ Create job seekers, approvals and job applications.
        """
        self.dry_run = dry_run
        self.developer_email = developer_email
        sample_size = options.get("sample_size")
        self.set_logger(options.get("verbosity"))

        self.logger.info("Starting. Good luck…")
        self.logger.info("-" * 80)

        if sample_size:
            df = pd.read_csv(file_path, dtype=str, encoding="latin_1").sample(int(sample_size))
        else:
            df = pd.read_csv(file_path, dtype=str, encoding="latin_1")

        # Add columns to share data with the ASP.
        df = self.add_columns_for_asp(df)

        # Step 1: clean data
        self.logger.info("✨ STEP 1: clean data!")
        df = self.clean_df(df)

        # Users with invalid NIRS are stored but without a NIR.
        df, invalid_nirs_df = self.filter_invalid_nirs(df)
        self.logger.info(f"Invalid nirs: {len(invalid_nirs_df)}.")

        self.logger.info("🚮 STEP 2: remove rows!")
        if invalid_nirs_only:
            df = invalid_nirs_df

        df = self.remove_ignored_rows(df)
        self.logger.info(f"Continuing with {len(df)} rows left ({self.get_ratio(len(df), len(df))} %).")

        # Step 3: import data.
        self.logger.info("🔥 STEP 3: create job seekers, approvals and job applications.")
        df = self.import_data_into_itou(df=df)

        # Step 4: create a CSV file including comments to be shared with the ASP.
        df = df.drop(["nir_is_valid", "siret_validated_by_asp"], axis=1)  # Remove useless columns.

        # Make sure expected columns are present.
        self.assert_asp_columns(df)
        self.log_to_csv("fichier_final", df)
        self.logger.info("📖 STEP 4: log final results.")
        self.logger.info("You can transfer this file to the ASP: /exports/import_ai_bilan.csv")

        self.logger.info("-" * 80)
        self.logger.info("👏 Good job!")
