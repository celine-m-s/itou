select
    c.id,
    cd.id as id_candidature,
    c.hash_nir,
    c.age,
    c.département,
    c.nom_département,
    c.région,
    c.adresse_en_qpv,
    c.total_candidatures,
    c.total_embauches,
    c.date_diagnostic,
    c.id_auteur_diagnostic_employeur,
    c.type_auteur_diagnostic,
    c.sous_type_auteur_diagnostic,
    c.nom_auteur_diagnostic,
    cd.état,
    cd.origine,
    cd.origine_détaillée,
    cd.id_structure,
    cd.type_structure,
    cd.nom_structure,
    cd.département_structure,
    cd.nom_département_structure,
    cd.région_structure,
    cd.injection_ai as injection_ai_candidatures,
    c.injection_ai as injection_ai_candidats
from candidats c
    left join candidatures cd
        on c.id = cd.id_candidat 
/* on considère que l'on a de l'auto prescription lorsque l'employeur est l'auteur du diagnostic et effectue l'embauche */
where c.type_auteur_diagnostic = 'Employeur' and cd.origine = 'Employeur' and c.id_auteur_diagnostic_employeur = cd.id_structure 