"""
Calcule les métriques de présence (mairie/réception/after) affichées sur la
page analytics : invités attendus mais pas encore scannés, scans non prévus
(retardataires non confirmés), et taux de no-show.
"""
from app.models import Invite, Logement, OuiNon, OuiNonPasConcerne, RestrictionAlimentaire, TransportMode

PHASES = ["mairie", "reception", "after"]
PHASE_LABELS = {"mairie": "Mairie", "reception": "Réception", "after": "After"}

RESTRICTION_LABELS = {
    "aucune": "Non",
    "halal": "Halal",
    "vegetarien": "Végétarien",
    "vegetalien": "Végétalien (vegan)",
    "sans_gluten": "Sans gluten",
    "sans_sel": "Sans sel",
    "sans_sucre": "Sans sucre",
    "sans_alcool": "Sans alcool",
    "autre": "Autre",
}

TRANSPORT_LABELS = {
    "pas_concerne": "Pas concerné",
    "voiture": "Voiture",
    "train": "Train",
    "covoiturage": "Covoiturage",
    "en_recherche": "En recherche",
    "autre": "Autre",
}

LOGEMENT_LABELS = {
    "trouve": "Logement trouvé",
    "besoin_aide": "Besoin d'aide",
    "pas_concerne": "Pas concerné",
}


def compute_presence_analytics(invites: list[Invite]) -> dict:
    labels = [PHASE_LABELS[p] for p in PHASES]
    arrives = []
    attendus_non_arrives = []
    scans_non_prevus = []

    for phase in PHASES:
        presence_attr = f"presence_{phase}"
        checked_attr = f"checked_in_{phase}"

        attendus = [i for i in invites if getattr(i, presence_attr) == OuiNon.oui]
        non_arrives = sum(1 for i in attendus if not getattr(i, checked_attr))

        non_prevus = sum(
            1
            for i in invites
            if getattr(i, checked_attr) and getattr(i, presence_attr) != OuiNon.oui
        )

        arrives.append(len(attendus) - non_arrives)
        attendus_non_arrives.append(non_arrives)
        scans_non_prevus.append(non_prevus)

    non_rempli = [i for i in invites if not i.questionnaire_rempli]
    taux_questionnaire_non_rempli = round(len(non_rempli) / len(invites) * 100, 1) if invites else 0.0

    return {
        "phases": labels,
        "arrives": arrives,
        "attendus_non_arrives": attendus_non_arrives,
        "scans_non_prevus": scans_non_prevus,
        "taux_questionnaire_non_rempli": taux_questionnaire_non_rempli,
        "noms_questionnaire_non_rempli": [{"nom": f"{i.prenom} {i.nom}"} for i in non_rempli],
    }


def _restriction_key(invite: Invite) -> str:
    return invite.restriction_alimentaire.value if invite.restriction_alimentaire else "aucune"


def compute_alimentaire_analytics(invites: list[Invite]) -> dict:
    counts = {r.value: 0 for r in RestrictionAlimentaire}
    for invite in invites:
        key = _restriction_key(invite)
        counts[key] = counts.get(key, 0) + 1

    histogram = [
        {"label": RESTRICTION_LABELS.get(key, key), "count": count}
        for key, count in counts.items()
        if count > 0
    ]

    autres = [
        {"nom": f"{invite.prenom} {invite.nom}", "detail": invite.restriction_alimentaire_autre}
        for invite in invites
        if invite.restriction_alimentaire == RestrictionAlimentaire.autre and invite.restriction_alimentaire_autre
    ]

    crosstab = []
    for key, count in counts.items():
        if count == 0:
            continue
        subset = [i for i in invites if _restriction_key(i) == key]
        oui = sum(1 for i in subset if i.presence_reception == OuiNon.oui)
        non = sum(1 for i in subset if i.presence_reception == OuiNon.non)
        en_attente = len(subset) - oui - non
        crosstab.append(
            {"label": RESTRICTION_LABELS.get(key, key), "oui": oui, "non": non, "en_attente": en_attente}
        )

    return {"histogram": histogram, "autres": autres, "crosstab": crosstab}


def _guest_row(invite: Invite) -> dict:
    return {"nom": f"{invite.prenom} {invite.nom}", "contact": invite.contact or invite.mail or "—"}


def compute_transport_logement_analytics(invites: list[Invite]) -> dict:
    transport_counts = {t.value: 0 for t in TransportMode}
    for invite in invites:
        key = invite.mode_transport.value if invite.mode_transport else "pas_concerne"
        transport_counts[key] = transport_counts.get(key, 0) + 1
    transport_histogram = [
        {"label": TRANSPORT_LABELS.get(key, key), "count": count}
        for key, count in transport_counts.items()
        if count > 0
    ]

    navette = [_guest_row(i) for i in invites if i.navette_souhaitee == OuiNonPasConcerne.oui]
    covoiturage = [_guest_row(i) for i in invites if i.covoiturage_possible == OuiNonPasConcerne.oui]
    sans_solution = [_guest_row(i) for i in invites if i.mode_transport == TransportMode.en_recherche]

    logement_counts = {"trouve": 0, "besoin_aide": 0, "pas_concerne": 0}
    for invite in invites:
        if invite.logement == Logement.oui:
            logement_counts["trouve"] += 1
        elif invite.logement in (Logement.toujours_en_recherche, Logement.ne_sait_pas):
            logement_counts["besoin_aide"] += 1
        else:
            logement_counts["pas_concerne"] += 1
    logement_histogram = [
        {"label": LOGEMENT_LABELS[key], "count": count}
        for key, count in logement_counts.items()
        if count > 0
    ]

    return {
        "transport_histogram": transport_histogram,
        "navette": navette,
        "covoiturage": covoiturage,
        "sans_solution": sans_solution,
        "logement_histogram": logement_histogram,
    }
