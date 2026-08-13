"""
Calcule les métriques affichées sur la page analytics, à partir de la liste
des invités (déjà synchronisée et verrouillée par store.list_guests())
convertie en DataFrame pandas pour les agrégations (comptages, groupby).
"""
import pandas as pd

from app.config import (
    _BOOL_COLUMNS,
    _COLUMNS,
    LOGEMENT_BUCKET_LABELS,
    PHASE_LABELS,
    PHASES,
    RESTRICTION_LABELS,
    TRANSPORT_LABELS,
)
from app.models import Invite, Logement, OuiNonPasConcerne


def _to_dataframe(invites: list[Invite]) -> pd.DataFrame:
    """Aplati la liste d'Invite en DataFrame : enums résolus en str (avec le
    même repli que l'ancien code — ex. mode_transport manquant = 'pas_concerne'),
    prêt pour value_counts()/groupby()."""
    if not invites:
        # Un DataFrame vide créé juste avec `columns=` met tout en dtype
        # object, y compris les colonnes booléennes — `~df["x"]` ne se
        # comporte alors plus comme un masque booléen. On force les dtypes.
        return pd.DataFrame(
            {col: pd.Series(dtype="bool" if col in _BOOL_COLUMNS else "object") for col in _COLUMNS}
        )

    rows = [
        {
            "nom_complet": f"{i.prenom} {i.nom}",
            "contact": i.contact or i.mail or "—",
            "presence_mairie": i.presence_mairie.value if i.presence_mairie else None,
            "presence_reception": i.presence_reception.value if i.presence_reception else None,
            "presence_after": i.presence_after.value if i.presence_after else None,
            "checked_in_mairie": i.checked_in_mairie,
            "checked_in_reception": i.checked_in_reception,
            "checked_in_after": i.checked_in_after,
            "questionnaire_rempli": i.questionnaire_rempli,
            "mode_transport": i.mode_transport.value if i.mode_transport else "pas_concerne",
            "covoiturage_possible": i.covoiturage_possible.value if i.covoiturage_possible else None,
            "navette_souhaitee": i.navette_souhaitee.value if i.navette_souhaitee else None,
            "logement": i.logement.value if i.logement else "pas_concerne",
            "restriction_alimentaire": i.restriction_alimentaire.value if i.restriction_alimentaire else "aucune",
            "restriction_alimentaire_autre": i.restriction_alimentaire_autre,
        }
        for i in invites
    ]
    return pd.DataFrame(rows, columns=_COLUMNS)


def _name_records(df: pd.DataFrame, extra_col: str | None = None, extra_key: str = "detail") -> list[dict]:
    """DataFrame filtré -> liste de {"nom": ...} (+ un champ optionnel nommé extra_key)."""
    if extra_col is None:
        return [{"nom": n} for n in df["nom_complet"]]
    return [{"nom": n, extra_key: d} for n, d in zip(df["nom_complet"], df[extra_col])]


def compute_presence_analytics(invites: list[Invite]) -> dict:
    df = _to_dataframe(invites)

    labels = [PHASE_LABELS[p] for p in PHASES]
    arrives, attendus_non_arrives, scans_non_prevus = [], [], []

    for phase in PHASES:
        presence_col = f"presence_{phase}"
        checked_col = f"checked_in_{phase}"

        attendus = df[df[presence_col] == "oui"]
        non_arrives = int((~attendus[checked_col]).sum())
        non_prevus = int((df[checked_col] & (df[presence_col] != "oui")).sum())

        arrives.append(len(attendus) - non_arrives)
        attendus_non_arrives.append(non_arrives)
        scans_non_prevus.append(non_prevus)

    non_rempli = df[~df["questionnaire_rempli"]]
    taux_questionnaire_non_rempli = round(len(non_rempli) / len(df) * 100, 1) if len(df) else 0.0

    return {
        "phases": labels,
        "arrives": arrives,
        "attendus_non_arrives": attendus_non_arrives,
        "scans_non_prevus": scans_non_prevus,
        "taux_questionnaire_non_rempli": taux_questionnaire_non_rempli,
        "noms_questionnaire_non_rempli": _name_records(non_rempli),
    }


def compute_alimentaire_analytics(invites: list[Invite]) -> dict:
    df = _to_dataframe(invites)

    counts = df["restriction_alimentaire"].value_counts()
    histogram = [
        {"label": RESTRICTION_LABELS.get(key, key), "count": int(count)} for key, count in counts.items()
    ]

    autres_df = df[(df["restriction_alimentaire"] == "autre") & df["restriction_alimentaire_autre"].fillna("").ne("")]
    autres = _name_records(autres_df, "restriction_alimentaire_autre", "detail")

    crosstab = []
    for key, group in df.groupby("restriction_alimentaire"):
        oui = int((group["presence_reception"] == "oui").sum())
        non = int((group["presence_reception"] == "non").sum())
        en_attente = len(group) - oui - non
        crosstab.append({"label": RESTRICTION_LABELS.get(key, key), "oui": oui, "non": non, "en_attente": en_attente})

    return {"histogram": histogram, "autres": autres, "crosstab": crosstab}


def compute_transport_analytics(invites: list[Invite]) -> dict:
    df = _to_dataframe(invites)

    counts = df["mode_transport"].value_counts()
    transport_histogram = [
        {"label": TRANSPORT_LABELS.get(key, key), "count": int(count)} for key, count in counts.items()
    ]

    navette = _name_records(df[df["navette_souhaitee"] == OuiNonPasConcerne.oui.value], "contact", "contact")
    covoiturage = _name_records(df[df["covoiturage_possible"] == OuiNonPasConcerne.oui.value], "contact", "contact")
    sans_solution = _name_records(df[df["mode_transport"] == "en_recherche"], "contact", "contact")

    return {
        "transport_histogram": transport_histogram,
        "navette": navette,
        "covoiturage": covoiturage,
        "sans_solution": sans_solution,
    }


def compute_logement_analytics(invites: list[Invite]) -> dict:
    df = _to_dataframe(invites)

    besoin_aide_values = {Logement.toujours_en_recherche.value, Logement.ne_sait_pas.value}
    bucket = df["logement"].apply(
        lambda v: "trouve" if v == Logement.oui.value else ("besoin_aide" if v in besoin_aide_values else "pas_concerne")
    )
    counts = bucket.value_counts()
    logement_histogram = [{"label": LOGEMENT_BUCKET_LABELS[key], "count": int(count)} for key, count in counts.items()]

    ne_sait_pas = _name_records(df[df["logement"] == Logement.ne_sait_pas.value], "contact", "contact")
    en_recherche = _name_records(df[df["logement"] == Logement.toujours_en_recherche.value], "contact", "contact")

    return {
        "logement_histogram": logement_histogram,
        "ne_sait_pas": ne_sait_pas,
        "en_recherche": en_recherche,
    }
