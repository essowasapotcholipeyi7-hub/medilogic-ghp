"""
Ajoute au catalogue de Clinique Valeo (structure_id=13) les actes
"(Assurance privée locale)" du document remis par le patron aujourd'hui
(Downloads\\CLINIQUE VALEO\\0_ACTES MEDICAUX CV ASSURANCE PRIVEE.docx),
absents jusqu'ici : consultations/visites généralistes et spécialistes,
et 4 actes de spécialité (ophtalmologie/rhumatologie) sans négociation
"barème assureur" séparée.

Décisions confirmées par le patron avant ce script :
- Consultation/Visite (jour+nuit) : UNE ligne par type d'acte, utilisant
  le mécanisme prix/prix_nuit déjà existant (au lieu de 8 lignes
  séparées C/CN/V/VN/CS/CSN/VS/VSN) — cohérent avec le reste du
  catalogue Valeo (tarif nuit/férié/dimanche).
- Visites à domicile (V/VN, VS/VSN) : aucun code AMU officiel dans le
  référentiel CHU (labo/imagerie/soins infirmiers/consultations
  seulement) -> PBR AMU = 0.
- Ophtalmologie (Périmètre, Biomicroscopie, Tonographie) et Rhumatologie
  (Infiltration) : aucun code AMU officiel non plus -> PBR AMU = 0.
  Le document ne donne pas de "barème assureur" séparé pour ces 4
  actes (une seule colonne de prix) -> aucune entrée PbrComplementaire
  créée pour eux (rien à y mettre).

Consultation généraliste = S100 (PBR AMU 3 500) ; Consultation
spécialiste = S101 (PBR AMU 5 250) — seuls codes trouvés dans le
référentiel CHU (feuille CONSULT CHU).

⭐ Chirurgie (lettre clé K / K bloc) volontairement PAS incluse ici :
1 400-1 700 F dans le document est une VALEUR PAR POINT (système à
lettre clé), pas un prix fixe d'acte — l'ajouter tel quel au catalogue
(prix fixe par acte) facturerait n'importe quelle chirurgie 1 400 F,
ce qui serait faux. À traiter séparément si la clinique confirme
vouloir un catalogue d'actes chirurgicaux avec leurs coefficients.

PbrComplementaire.pbr_1 = "barème assureur" jour (colonne du document).
Le barème "nuit" du document n'est pas stocké séparément : PbrComplementaire
n'a qu'une valeur "habituelle" par (acte, compagnie) — voir modèle. À
revoir plus tard si la clinique a besoin d'un calcul CAC différent la
nuit pour ces actes précis.

Usage :
    python scripts/ajouter_consultations_valeo.py            # aperçu (dry-run)
    python scripts/ajouter_consultations_valeo.py --appliquer  # applique réellement
"""
import io
import os
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sheets_helper import sheets_helper
from models import db, PbrComplementaire
from app import app

STRUCTURE_ID = 13
COMPAGNIE = "Assurance privée locale"

# nom -> (prix jour, prix nuit ou None, pbr AMU, bareme assureur jour ou None, description)
NOUVEAUX_ACTES = [
    ("Consultation generaliste", 8000, 10500, 3500, 7000, "S100 - Consultation medecine generale"),
    ("Visite generaliste (deplacement)", 15000, 17500, 0, 12500, "Visite a domicile - pas de code AMU officiel"),
    ("Consultation specialiste", 10000, 12500, 5250, 8500, "S101 - Consultation specialisee"),
    ("Visite specialiste (deplacement)", 20000, 22500, 0, 17000, "Visite a domicile - pas de code AMU officiel"),
    ("Perimetre (Ophtalmologie)", 20000, None, 0, None, "Pas de code AMU officiel"),
    ("Biomicroscopie - Fond d'oeil (Ophtalmologie)", 10000, None, 0, None, "Pas de code AMU officiel"),
    ("Tonographie (Ophtalmologie)", 9000, None, 0, None, "Pas de code AMU officiel"),
    ("Infiltration (Rhumatologie)", 10000, None, 0, None, "Pas de code AMU officiel"),
]


def main():
    appliquer = '--appliquer' in sys.argv

    sheets_helper.set_structure(STRUCTURE_ID, 'CLINIQUE VALEO')
    sheet_name = sheets_helper.get_sheet_name('actes')
    worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
    entetes = worksheet.row_values(1)

    actes_existants = sheets_helper.get_all_records('actes', use_prefix=True)
    ids = [int(a['ID']) for a in actes_existants if str(a.get('ID', '')).isdigit()]
    noms_existants = {a.get('nom') for a in actes_existants}
    prochain_id = max(ids) + 1

    print(f"📖 {len(NOUVEAUX_ACTES)} nouvel(le) acte(s) à ajouter :\n")
    lignes_a_ajouter = []
    for (nom, prix, prix_nuit, pbr, bareme, desc) in NOUVEAUX_ACTES:
        nom_complet = f"{nom} ({COMPAGNIE})"
        if nom_complet in noms_existants:
            print(f"⏭️  '{nom_complet}' existe déjà — ignoré.")
            continue
        print(f"   {nom_complet:55} prix={prix}" + (f"/nuit={prix_nuit}" if prix_nuit else "") +
              f" pbr={pbr}" + (f" bareme_assureur={bareme}" if bareme else ""))
        lignes_a_ajouter.append((nom_complet, prix, prix_nuit, pbr, bareme, desc))

    if not appliquer:
        print("\nℹ️  Aperçu seulement (dry-run) — relancer avec --appliquer pour exécuter réellement.")
        return

    for (nom_complet, prix, prix_nuit, pbr, bareme, desc) in lignes_a_ajouter:
        ligne = [''] * len(entetes)
        ligne[entetes.index('ID')] = str(prochain_id)
        ligne[entetes.index('nom')] = nom_complet
        ligne[entetes.index('prix')] = str(prix)
        ligne[entetes.index('pbr')] = str(pbr)
        ligne[entetes.index('description')] = desc
        ligne[entetes.index('structure_id')] = str(STRUCTURE_ID)
        ligne[entetes.index('prise_en_charge_amu')] = 'TRUE'
        ligne[entetes.index('prise_en_charge_cac')] = 'TRUE'
        ligne[entetes.index('statut')] = 'EP'
        ligne[entetes.index('AMU-TNS')] = 'TRUE'
        if prix_nuit:
            ligne[entetes.index('prix_nuit')] = str(prix_nuit)
        worksheet.append_row(ligne, value_input_option='USER_ENTERED')
        print(f"✅ Ajouté : '{nom_complet}' (ID={prochain_id}).")
        prochain_id += 1

    sheets_helper.clear_cache(sheet_name)

    with app.app_context():
        crees = 0
        for (nom_complet, prix, prix_nuit, pbr, bareme, desc) in lignes_a_ajouter:
            if not bareme:
                continue
            existant = PbrComplementaire.query.filter_by(
                structure_id=STRUCTURE_ID, type='acte', nom_acte=nom_complet, compagnie=COMPAGNIE
            ).first()
            if not existant:
                db.session.add(PbrComplementaire(
                    structure_id=STRUCTURE_ID, type='acte', nom_acte=nom_complet,
                    compagnie=COMPAGNIE, pbr_1=bareme, created_by='script:ajouter_consultations_valeo'
                ))
                crees += 1
        db.session.commit()
        print(f"✅ PbrComplementaire : {crees} créée(s).")

    print("\n✅ Terminé.")


if __name__ == "__main__":
    main()
