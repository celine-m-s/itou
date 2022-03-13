from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse

from itou.cities.models import City
from itou.common_apps.address.departments import department_from_postcode
from itou.common_apps.organizations.views import deactivate_org_member, update_org_admin_role
from itou.jobs.models import Appellation
from itou.siaes.models import Siae, SiaeFinancialAnnex, SiaeJobDescription
from itou.users.models import User
from itou.utils.pagination import pager
from itou.utils.perms.siae import get_current_siae_or_404
from itou.utils.urls import get_safe_url
from itou.www.siaes_views.forms import (
    BlockJobApplicationsForm,
    CreateSiaeForm,
    EditJobDescriptionDetailsForm,
    EditJobDescriptionForm,
    EditSiaeDescriptionForm,
    EditSiaeForm,
    FinancialAnnexSelectForm,
)


NB_ITEMS_PER_PAGE = 10


### Job description views


def job_description_card(request, job_description_id, template_name="siaes/job_description_card.html"):
    job_description = get_object_or_404(SiaeJobDescription, pk=job_description_id)
    back_url = get_safe_url(request, "back_url")
    siae = job_description.siae
    others_active_jobs = (
        SiaeJobDescription.objects.select_related("appellation")
        .filter(is_active=True, siae=siae)
        .exclude(id=job_description_id)
        .order_by("-updated_at", "-created_at")
    )
    breadcrumbs = {
        "Métiers et recrutements": reverse("siaes_views:job_description_list"),
        "Détail du poste": reverse(
            "siaes_views:job_description_card",
            kwargs={
                "job_description_id": job_description_id,
            },
        ),
    }
    context = {
        "job": job_description,
        "siae": siae,
        "others_active_jobs": others_active_jobs,
        "back_url": back_url,
        "breadcrumbs": breadcrumbs,
    }
    return render(request, template_name, context)


@login_required
def card_search_preview(request, template_name="siaes/includes/_card_siae.html"):
    siae = get_current_siae_or_404(request, with_job_app_score=True, with_job_descriptions=True)
    job_descriptions = (
        SiaeJobDescription.objects.for_siae(siae)
        .prefetch_related("appellation", "appellation__rome", "siae")
        .order_by("-updated_at", "-created_at")
    )
    context = {
        "siae": siae,
        "jobs_descriptions": job_descriptions,
    }
    return HttpResponse(render_to_string(template_name, context))


@login_required
@transaction.atomic
def job_description_list(request, template_name="siaes/job_description_list.html"):
    siae = get_current_siae_or_404(request, with_job_app_score=True, with_job_descriptions=True)
    job_descriptions = (
        SiaeJobDescription.objects.for_siae(siae)
        .prefetch_related("appellation", "appellation__rome", "siae")
        .order_by("-updated_at", "-created_at")
    )
    page = int(request.GET.get("page") or request.session.get(settings.ITOU_SESSION_CURRENT_PAGE_KEY) or 1)
    request.session[settings.ITOU_SESSION_CURRENT_PAGE_KEY] = page

    # Remove possible obsolete session data when coming from breakcrumbs links and back buttons
    if request.session.get(settings.ITOU_SESSION_JOB_DESCRIPTION_KEY):
        del request.session[settings.ITOU_SESSION_JOB_DESCRIPTION_KEY]

    form = BlockJobApplicationsForm(instance=siae, data=request.POST or None)

    if request.method == "POST":
        action = request.GET.get("action")

        if action == "delete":
            job_description_id = request.POST.get("job_description_id")
            SiaeJobDescription.objects.get(pk=job_description_id).delete()
            messages.success(request, "La fiche de poste a été supprimée.")
        elif action == "toggle_active":
            job_description_id = request.POST.get("job_description_id")
            is_active = bool(request.POST.get("job_description_is_active", False))
            job_description = SiaeJobDescription.objects.get(pk=job_description_id)
            job_description.is_active = is_active
            job_description.save(update_fields=["is_active"])
            messages.success(request, f"Le recrutement est maintenant {'ouvert' if is_active else 'fermé'}")
        elif form.is_valid():
            siae = form.save()
            messages.success(
                request,
                "La réception de candidature est temporairement bloquée."
                if siae.block_job_applications
                else "La structure peut recevoir des candidatures.",
            )

        return HttpResponseRedirect(reverse("siaes_views:job_description_list"))

    job_pager = pager(job_descriptions, page, items_per_page=NB_ITEMS_PER_PAGE)
    breadcrumbs = {
        "Métiers et recrutements": reverse("siaes_views:job_description_list"),
    }

    context = {
        "siae": siae,
        "form": form,
        "job_pager": job_pager,
        "page": page,
        "breadcrumbs": breadcrumbs,
    }
    return render(request, template_name, context)


def _get_job_description(session_data):
    if pk := session_data.get("pk"):
        job_description = get_object_or_404(
            SiaeJobDescription.objects.select_related(
                "appellation",
                "location",
            ),
            pk=pk,
        )
        return job_description
    return None


@login_required
def edit_job_description(request, template_name="siaes/edit_job_description.html"):
    siae = get_current_siae_or_404(request)
    session_data = request.session.get(settings.ITOU_SESSION_JOB_DESCRIPTION_KEY) or {}
    job_description = _get_job_description(session_data)

    form = EditJobDescriptionForm(siae, instance=job_description, data=request.POST or None, initial=session_data)

    if request.method == "POST" and form.is_valid():
        request.session[settings.ITOU_SESSION_JOB_DESCRIPTION_KEY] = {**session_data, **form.cleaned_data}
        return HttpResponseRedirect(reverse("siaes_views:edit_job_description_details"))

    breadcrumbs = {
        "Métiers et recrutements": reverse("siaes_views:job_description_list"),
    }
    if job_description and job_description.pk:
        kwargs = {"job_description_id": job_description.pk}
        breadcrumbs.update(
            {
                "Détails du poste": reverse("siaes_views:job_description_card", kwargs=kwargs),
                "Modifier une fiche de poste": reverse("siaes_views:update_job_description", kwargs=kwargs),
            }
        )
    else:
        breadcrumbs["Créer une fiche de poste"] = reverse("siaes_views:edit_job_description")

    context = {
        "form": form,
        "breadcrumbs": breadcrumbs,
    }

    return render(request, template_name, context)


@login_required
def edit_job_description_details(request, template_name="siaes/edit_job_description_details.html"):
    siae = get_current_siae_or_404(request)
    session_data = request.session.get(settings.ITOU_SESSION_JOB_DESCRIPTION_KEY)
    job_description = _get_job_description(session_data)

    rome = get_object_or_404(
        Appellation.objects.select_related("rome"), code=session_data.get("job_appellation_code")
    ).rome.code

    form = EditJobDescriptionDetailsForm(
        siae, instance=job_description, data=request.POST or None, initial=session_data
    )

    if request.method == "POST" and form.is_valid():
        request.session[settings.ITOU_SESSION_JOB_DESCRIPTION_KEY] = {**session_data, **form.cleaned_data}
        return HttpResponseRedirect(reverse("siaes_views:edit_job_description_preview"))

    breadcrumbs = {
        "Métiers et recrutements": reverse("siaes_views:job_description_list"),
    }

    if job_description and job_description.pk:
        kwargs = {"job_description_id": job_description.pk}
        breadcrumbs.update(
            {
                "Détails du poste": reverse("siaes_views:job_description_card", kwargs=kwargs),
                "Modifier une fiche de poste": reverse("siaes_views:update_job_description", kwargs=kwargs),
            }
        )
    else:
        breadcrumbs["Créer une fiche de poste"] = reverse("siaes_views:edit_job_description")

    context = {
        "form": form,
        "rome": rome,
        "breadcrumbs": breadcrumbs,
    }

    return render(request, template_name, context)


@login_required
@transaction.atomic
def edit_job_description_preview(request, template_name="siaes/edit_job_description_preview.html"):
    siae = get_current_siae_or_404(request)
    session_data = request.session.get(settings.ITOU_SESSION_JOB_DESCRIPTION_KEY)
    job_description = _get_job_description(session_data) or SiaeJobDescription()

    job_description.__dict__.update(**session_data)

    if location_code := session_data.get("location_code"):
        job_description.location = City.objects.get(slug=location_code)
    job_description.appellation = Appellation.objects.get(code=session_data.get("job_appellation_code"))
    job_description.siae = siae

    if request.method == "POST":
        try:
            job_description.save()
            messages.success(request, "Enregistrement de la fiche de poste effectué.")
        except Exception as ex:
            messages.error(request, f"Une erreur est survenue lors de l'enregistrement de la fiche de poste. ({ ex })")
        finally:
            request.session.pop(settings.ITOU_SESSION_JOB_DESCRIPTION_KEY)
            return HttpResponseRedirect(reverse("siaes_views:job_description_list"))

    breadcrumbs = {
        "Métiers et recrutements": reverse("siaes_views:job_description_list"),
    }

    if job_description and job_description.pk:
        kwargs = {"job_description_id": job_description.pk}
        breadcrumbs.update(
            {
                "Détails du poste": reverse("siaes_views:job_description_card", kwargs=kwargs),
                "Modifier une fiche de poste": reverse("siaes_views:update_job_description", kwargs=kwargs),
            }
        )
    else:
        breadcrumbs["Créer une fiche de poste"] = reverse("siaes_views:edit_job_description")

    context = {
        "siae": siae,
        "job": job_description,
        "breadcrumbs": breadcrumbs,
    }

    return render(request, template_name, context)


@login_required
def update_job_description(request, job_description_id):
    request.session[settings.ITOU_SESSION_JOB_DESCRIPTION_KEY] = {"pk": job_description_id}
    return HttpResponseRedirect(reverse("siaes_views:edit_job_description"))


### Financial annexes views


@login_required
def show_financial_annexes(request, template_name="siaes/show_financial_annexes.html"):
    """
    Show a summary of the financial annexes of the convention to the siae admin user. Financial annexes are grouped
    by suffix and only the most relevant one (active if any, or most recent if not) is shown for each suffix.
    """
    current_siae = get_current_siae_or_404(request)
    if not current_siae.convention_can_be_accessed_by(request.user):
        raise PermissionDenied

    financial_annexes = []
    if current_siae.convention:
        financial_annexes = current_siae.convention.financial_annexes.all()

    # For each group of AFs sharing the same number prefix, show only the most relevant AF
    # (active if any, or most recent if not). We do this to avoid showing too many AFs and confusing the user.
    prefix_to_af = {}
    for af in financial_annexes:
        prefix = af.number_prefix
        if prefix not in prefix_to_af or af.is_active:
            # Always show an active AF when there is one.
            prefix_to_af[prefix] = af
            continue
        old_suffix = prefix_to_af[prefix].number_suffix
        new_suffix = af.number_suffix
        if not prefix_to_af[prefix].is_active and new_suffix > old_suffix:
            # Show the AF with the latest suffix when there is no active one.
            prefix_to_af[prefix] = af
            continue

    financial_annexes = list(prefix_to_af.values())
    financial_annexes.sort(key=lambda af: af.number, reverse=True)

    context = {
        "siae": current_siae,
        "convention": current_siae.convention,
        "financial_annexes": financial_annexes,
        "can_select_af": current_siae.convention_can_be_changed_by(request.user),
        "current_siae_is_asp": current_siae.source == Siae.SOURCE_ASP,
        "current_siae_is_user_created": current_siae.source == Siae.SOURCE_USER_CREATED,
    }
    return render(request, template_name, context)


@login_required
def select_financial_annex(request, template_name="siaes/select_financial_annex.html"):
    """
    Let siae admin user select a new convention via a financial annex number.
    """
    current_siae = get_current_siae_or_404(request)
    if not current_siae.convention_can_be_changed_by(request.user):
        raise PermissionDenied

    # We only allow the user to select an AF under the same SIREN as the current siae.
    financial_annexes = (
        SiaeFinancialAnnex.objects.select_related("convention")
        .filter(convention__kind=current_siae.kind, convention__siret_signature__startswith=current_siae.siren)
        .order_by("-number")
    )

    # Show only one AF for each AF number prefix to significantly reduce the length of the dropdown when there are
    # many AFs in the same SIREN.
    prefix_to_af = {af.number_prefix: af for af in financial_annexes.all()}
    # The form expects a queryset and not a list.
    financial_annexes = financial_annexes.filter(pk__in=[af.pk for af in prefix_to_af.values()])

    select_form = FinancialAnnexSelectForm(data=request.POST or None, financial_annexes=financial_annexes)

    if request.method == "POST" and select_form.is_valid():
        financial_annex = select_form.cleaned_data["financial_annexes"]
        current_siae.convention = financial_annex.convention
        current_siae.save()
        message = (
            f"Nous avons bien attaché votre structure à l'annexe financière"
            f" {financial_annex.number_prefix_with_spaces}."
        )
        messages.success(request, message)
        return HttpResponseRedirect(reverse("siaes_views:show_financial_annexes"))

    context = {"select_form": select_form}
    return render(request, template_name, context)


### SIAE CRUD views


def card(request, siae_id, template_name="siaes/card.html"):
    queryset = Siae.objects.prefetch_job_description_through().with_job_app_score()

    siae = get_object_or_404(queryset, pk=siae_id)
    jobs_descriptions = siae.job_description_through.all()
    back_url = get_safe_url(request, "back_url")
    context = {"siae": siae, "back_url": back_url, "jobs_descriptions": jobs_descriptions}
    return render(request, template_name, context)


@login_required
@transaction.atomic
def create_siae(request, template_name="siaes/create_siae.html"):
    current_siae = get_current_siae_or_404(request)
    if not request.user.can_create_siae_antenna(parent_siae=current_siae):
        raise PermissionDenied

    form = CreateSiaeForm(
        current_siae=current_siae,
        current_user=request.user,
        data=request.POST or None,
        initial={"siret": current_siae.siret, "kind": current_siae.kind, "department": current_siae.department},
    )

    if request.method == "POST" and form.is_valid():
        siae = form.save()
        request.session[settings.ITOU_SESSION_CURRENT_SIAE_KEY] = siae.pk
        return HttpResponseRedirect(reverse("dashboard:index"))

    context = {"form": form}
    return render(request, template_name, context)


@login_required
def edit_siae_step_contact_infos(request, template_name="siaes/edit_siae.html"):
    if settings.ITOU_SESSION_EDIT_SIAE_KEY not in request.session:
        request.session[settings.ITOU_SESSION_EDIT_SIAE_KEY] = {}

    siae = get_current_siae_or_404(request)
    if not siae.has_admin(request.user):
        raise PermissionDenied

    # Force the "brand" initial data to match either brand, or a capitalized version of the base name.
    # This ensures the filed will be filled with a correct value as default.
    siae.brand = siae.display_name

    form = EditSiaeForm(
        instance=siae, data=request.POST or None, initial=request.session[settings.ITOU_SESSION_EDIT_SIAE_KEY]
    )
    if request.method == "POST" and form.is_valid():
        request.session[settings.ITOU_SESSION_EDIT_SIAE_KEY].update(form.cleaned_data)
        request.session.modified = True
        return HttpResponseRedirect(reverse("siaes_views:edit_siae_step_description"))

    context = {"form": form, "siae": siae}
    return render(request, template_name, context)


@login_required
def edit_siae_step_description(request, template_name="siaes/edit_siae_description.html"):
    if settings.ITOU_SESSION_EDIT_SIAE_KEY not in request.session:
        return HttpResponseRedirect(reverse("siaes_views:edit_siae_step_contact_infos"))

    siae = get_current_siae_or_404(request)
    if not siae.has_admin(request.user):
        raise PermissionDenied

    form = EditSiaeDescriptionForm(
        instance=siae, data=request.POST or None, initial=request.session[settings.ITOU_SESSION_EDIT_SIAE_KEY]
    )

    if request.method == "POST" and form.is_valid():
        request.session[settings.ITOU_SESSION_EDIT_SIAE_KEY].update(form.cleaned_data)
        request.session.modified = True
        return HttpResponseRedirect(reverse("siaes_views:edit_siae_step_preview"))

    context = {"form": form, "siae": siae, "prev_url": reverse("siaes_views:edit_siae_step_contact_infos")}
    return render(request, template_name, context)


@login_required
@transaction.atomic
def edit_siae_step_preview(request, template_name="siaes/edit_siae_preview.html"):
    if settings.ITOU_SESSION_EDIT_SIAE_KEY not in request.session:
        return HttpResponseRedirect(reverse("siaes_views:edit_siae_step_contact_infos"))

    siae = get_current_siae_or_404(request)
    if not siae.has_admin(request.user):
        raise PermissionDenied

    form_data = request.session[settings.ITOU_SESSION_EDIT_SIAE_KEY]

    # Update the object's data with the recorded changes, for the preview.
    # NOTE(vperron): This may seem "ugly" but it's probably acceptable here since it:
    # - only takes in pre-validated and cleand data (the ModelForms do call full_clean()
    #   on the underlying models)
    # - enables us to perform a single save() in the whole block instead of at least 2 (custom
    #   form) or 3 (existing forms)
    siae.__dict__.update(**form_data)

    if request.method == "POST":
        siae.department = department_from_postcode(siae.post_code)
        siae.set_coords(siae.geocoding_address, post_code=siae.post_code)
        siae.save()
        # Clear the session now, so that we start fresh if we edit again.
        del request.session[settings.ITOU_SESSION_EDIT_SIAE_KEY]
        request.session.modified = True
        messages.success(request, "Mise à jour effectuée !")
        return HttpResponseRedirect(reverse("dashboard:index"))

    context = {"siae": siae, "form_data": form_data, "prev_url": reverse("siaes_views:edit_siae_step_description")}
    return render(request, template_name, context)


### SIAE memberships views


@login_required
def members(request, template_name="siaes/members.html"):
    siae = get_current_siae_or_404(request)
    if not siae.is_active:
        raise PermissionDenied

    active_siae_members = siae.siaemembership_set.active().select_related("user").all().order_by("joined_at")
    pending_invitations = siae.invitations.pending()

    context = {
        "siae": siae,
        "members": active_siae_members,
        "pending_invitations": pending_invitations,
    }
    return render(request, template_name, context)


@login_required
def deactivate_member(request, user_id, template_name="siaes/deactivate_member.html"):
    siae = get_current_siae_or_404(request)
    target_member = User.objects.get(pk=user_id)

    if deactivate_org_member(request=request, target_member=target_member, organization=siae):
        return HttpResponseRedirect(reverse("siaes_views:members"))

    context = {
        "structure": siae,
        "target_member": target_member,
    }

    return render(request, template_name, context)


@login_required
def update_admin_role(request, action, user_id, template_name="siaes/update_admins.html"):
    siae = get_current_siae_or_404(request)
    target_member = User.objects.get(pk=user_id)

    if update_org_admin_role(request=request, organization=siae, target_member=target_member, action=action):
        return HttpResponseRedirect(reverse("siaes_views:members"))

    context = {
        "action": action,
        "structure": siae,
        "target_member": target_member,
    }

    return render(request, template_name, context)
