"""
Corrige la colonne `pbr` des 123 lignes "(Assurance privée locale)"
(radiologie/échographie/biologie) importées par importer_tarifs_valeo.py.

Erreur corrigée (signalée par le patron) : le PBR de ces lignes avait été
rempli avec le "Prix de base de remboursement" du DOCUMENT DE L'ASSUREUR
PRIVÉ — alors que la colonne `pbr` du catalogue représente TOUJOURS le PBR
AMU officiel (national, fixe, indépendant de l'assureur du patient et de
l'heure). Ce script :

1. Corrige `pbr` avec la vraie valeur AMU officielle (catégorie CHU),
   retrouvée manuellement (pas de matching automatique flou — un premier
   essai avec difflib a produit des correspondances fausses sur des noms
   courts/ambigus comme "DOIGT"->"un doigt" (chirurgical) ou "GE"->"Genou").
   Le mapping ci-dessous a été vérifié ligne par ligne contre les feuilles
   IMAGERIE CHU et LABO CHU et INH (fichier ACTES LABO -IMAGERIE-
   SI-CONSULT 3003 2024.xlsx).
2. Crée une entrée PbrComplementaire (compagnie "Assurance privée locale")
   par acte, avec le PBR du document de l'assureur privé (celui qui était
   mal placé dans `pbr`) — c'est LÀ qu'il doit vivre, utilisé par le calcul
   CAC (voir _repartition_ligne_vente_attente/calculerTotal). Le patron a
   confirmé que le mécanisme PbrComplementaire gère déjà plusieurs
   compagnies séparément si besoin (page /pbr-complementaires).

Certains actes n'ont pas de correspondance AMU fiable trouvée (pas de code
officiel équivalent, ou trop ambigu pour deviner sans risque : ex. ECG/
HOLTER qui ne sont pas dans le référentiel imagerie, ou "INCIDENCE
COMPLÉMENTAIRE" qui n'a pas de code propre) — leur `pbr` reste inchangé et
ils sont listés en avertissement à la fin, à trancher avec la clinique.

Usage :
    python scripts/corriger_pbr_valeo.py            # aperçu (dry-run)
    python scripts/corriger_pbr_valeo.py --appliquer  # applique réellement
"""
import io
import os
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gspread.utils import rowcol_to_a1
from sheets_helper import sheets_helper
from models import db, CompagnieComplementaire, PbrComplementaire
from app import app

STRUCTURE_ID = 13
COMPAGNIE = "Assurance privée locale"

# nom Valeo (sans le suffixe) -> (code AMU, PBR AMU officiel) ou None si
# pas de correspondance fiable trouvée.
MAPPING_PBR_AMU = {
    # --- Radiologie (IMAGERIE CHU) ---
    "DOIGT": ("Q100", 6630),
    "MAIN": ("Q101", 6630),
    "POIGNET": ("Q103", 6630),
    "AVANT BRAS": ("Q107", 6630),
    "BRAS": ("Q108", 6630),
    "COUDE": ("Q112", 6630),
    "EPAULE": ("Q160", 6630),
    "CLAVICULE": ("Q160", 6630),
    "ARTICULATION STERNO-CLAVICULAIRE": ("Q308", 6630),
    "ARTICULATION ACROMIO-CLAVICULAIRE": None,  # pas de code officiel distinct trouvé
    "DEUX SEGMENTS CONTIGUS": ("Q117", 9945),  # ambiguïté membre sup/inf, même PBR (Q117/Q134)
    "DEUX SEGMENTS NON CONTIGUS": None,  # pas de code "non contigus" distinct
    "INCIDENCE COMPLÉMENTAIRE": None,  # pas de code propre (supplément, pas un acte séparé)
    "PIED": ("Q129", 6630),
    "CHEVILLE": ("Q130", 6630),
    "JAMBE": ("Q131", 6630),
    "GENOU": ("Q132", 6630),
    "CUISSE": ("Q133", 6630),
    "BASSIN / COCCYX/ DE SEZE": ("Q139", 6630),
    "PANGONOGRAMME": ("Q146", 13260),
    "CRÂNE, MASSIF FACIAL": ("Q147", 6630),
    "BLONDEAU": ("Q148", 6630),
    "CAVUM": ("Q200", 6630),
    "OS PROPRES DU NEZ": ("Q149", 6630),
    "ARTICULATIONS TEMPORO-MANDIBULAIRES": ("Q154", 8840),
    "THORAX / POUMONS": ("Q157", 6630),
    "GRILL COSTAL": ("Q164", 6630),
    "STERNUM": ("Q163", 6630),
    "RACHIS CERVICAL BOUCHE OUVERTE": ("Q104", 6630),
    "RACHIS CERVICAL": ("Q105", 6630),
    "RACHIS CERVICO-DORSAL": ("Q106", 7956),
    "RACHIS DORSAL": ("Q111", 6630),
    "RACHIS DORSO-LOMBAIRE": ("Q114", 7956),
    "RACHIS LOMBAIRE": ("Q116", 6630),
    "CHARNIERE RACHIDIENNE C7-T1, T12-L1, L5-S1": ("Q119", 5304),
    "SACRUM": ("Q121", 6630),
    "DEUX REGIONS CONTIGUES": ("Q109", 13260),  # incertain
    "DEUX REGIONS NON CONTIGUES": None,
    "RADIO ASP ADULTE": ("Q202", 6630),
    "TRANSIT OESOPHAGIEN": ("Q203", 17680),
    "TOGD": ("Q204", 26520),
    "TRANSIT DU GRELE": ("Q220", 22100),
    "LAVEMENT BARYTE": ("Q205", 22100),
    "UIV": ("Q207", 26520),
    "HSG": ("Q212", 26520),
    "UCR": ("Q211", 19890),
    "MAMMOGRAPHIE": ("Q208", 13260),  # bilatérale supposée
    "RADIOPELVIMETRIE": ("Q213", 13260),

    # --- Échographie (IMAGERIE CHU, section Echographie) ---
    "ECG": None,  # pas dans ce référentiel imagerie (cardiologie/consultation)
    "ECHO DOPPLER DU CŒUR": ("Q435", 17680),
    "HOLTER TENSIONNEL": None,
    "HOLTER ECG": None,
    "ECHO TRANSFONTANELLAIRE": ("Q411", 8840),
    "ECHO OCULAIRE": ("Q416", 6630),
    "ECHO CERVICALE / THYROIDE / PAROTIDE / SOUS MAXILLAIRE / THORACIQUE": ("Q423", 13260),  # incertain
    "ECHO PROSTATIQUE": ("Q419", 6630),
    "ECHO MAMMAIRE": ("Q414", 6630),
    "ECHO TESTICULAIRE": ("Q421", 6630),
    "ECHO PARTIE MOLLES / ARTICULAIRE": ("Q425", 6630),
    "ECHO ABDOMINALE / HEPATIQUE / RENALE / VESICALE": ("Q410", 13260),
    "ECHO ABDOMINALE-PELVIENNE": ("Q429", 17680),
    "ECHO OBSTERICALE (1er, 2ème, 3ème trimestre)": ("Q415", 6630),
    "ECHO MORPHOLOGIQUE (3D)": ("Q415", 6630),  # incertain, repli sur obstétricale
    "ECHO PELVIENNE": ("Q417", 8840),
    "ECHO TUMORALE": ("Q425", 6630),
    "DOPPLER VEINEUX MEMBRES INF": ("Q436", 17680),
    "DOPPLER ARTERIEL MEMBRES INF": ("Q436", 17680),
    "DOPPLER (TRANSCRANIEN/TRONC SUPRAAORTIQUE/RENAL OBSTETRIQUE": ("Q436", 17680),

    # --- Biologie (LABO CHU et INH) ---
    "CREATININE": ("R831", 1100),
    "CRP": ("R828", 1320),  # pas de code qualitatif distinct, repli sur quantitative
    "CRP (quantitatif)": ("R828", 1320),
    "GE": ("R101", 880),
    "GLYCEMIE": ("R823", 1100),  # veineuse supposée
    "GROUPAGE/Rhésus": ("R300", 2750),
    "NFS": ("R607", 3850),
    "UREE SANGUINE": ("R830", 1100),
    "VS": ("R611", 1100),
    "Electrophorèse de l’hémoglobine": ("R610", 3850),
    "AgHbs": ("R416", 6050),
    "DYE TEST (TOXO)": ("R400", 6050),
    "RUBEOLE": ("R411", 7700),
    "SRV": None,  # abréviation non identifiée avec certitude
    "TPHA": ("R406", 3850),
    "VDRL/RPR": ("R406", 3850),
    "TRANSAMINASES": ("R876", 1650),
    "AgHbe": ("R417", 6050),
    "Bilan hépatique complet (transa, GGT, PAL, bilirubine TD)": ("R877", 3850),
    "BILIRUBINE TD": ("R821", 1650),
    "Gamma GT": ("R804", 1100),
    "PHOSPHATASE ALCALINES (PAL)": ("R809", 1100),
    "TRIGLYCERIDES": ("R826", 2200),
    "CHOLESTEROL TOTAL": ("R825", 1100),
    "CHOLESTEROL LDL": ("R866", 2750),
    "CHOLESTEROL HDL": ("R827", 2750),
    "Bilan lipidique complet": ("R878", 7700),
    "ACIDE URIQUE / URICEMIE": ("R820", 1100),
    "CALCIUM": ("R835", 1650),
    "IONOGRAMME SANGUIN": ("R838", 7700),
    "MAGNESIUM": ("R836", 1650),
    "POTASSIUM": ("R839", 2750),
    "SODIUM": ("R839", 2750),
    "COPROCULTURE": ("R903", 3850),
    "CULOT URINAIRE": ("R918", 1100),
    "ECBU": ("R904", 3850),
    "HEMOCULTURE": ("R901", 4950),
    "PRELEVEMENT DE GORGE": None,  # pas de code "gorge" trouvé
    "PU": ("R907", 3850),
    "PUS": ("R905", 3850),
    "PV": ("R906", 3850),
    "SELLES KOP": ("R100", 880),
    "TCK": ("R703", 1100),
    "TP/INR": ("R702", 1100),
    "TS": ("R700", 1100),
    "Acétonurie": ("R853", 550),  # incertain (repli sur recherche qualitative)
    "Albuminémie": ("R834", 1210),
    "CPK": ("R805", 1100),
    "Electrophorèse des protides": ("R829", 5500),
    "Glycosurie": ("R853", 550),  # incertain
    "Hémoglobine glycosylée (ou glyquée)": ("R824", 9350),
    "PSA": ("R847", 5500),
    "T3": ("R810", 7150),
    "T4": ("R811", 7150),
    "TSH": ("R812", 7150),
}


def main():
    appliquer = '--appliquer' in sys.argv

    sheets_helper.set_structure(STRUCTURE_ID, 'CLINIQUE VALEO')
    sheet_name = sheets_helper.get_sheet_name('actes')
    worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
    entetes = worksheet.row_values(1)
    idx_pbr = entetes.index('pbr') + 1
    idx_nom_col = entetes.index('nom')

    valeurs = worksheet.get_all_values()

    corrections_pbr = []   # (ligne_sheet, nom, ancien_pbr_faux, nouveau_pbr_amu, code_amu)
    entrees_pbr_comp = []  # (nom_complet, pbr_assureur_prive)
    non_trouves = []

    for i, row in enumerate(valeurs[1:], start=2):
        if len(row) <= idx_nom_col:
            continue
        nom_complet = row[idx_nom_col]
        if 'Assurance privée locale' not in nom_complet:
            continue
        if nom_complet.startswith('B20') or 'Chambre' in nom_complet or 'personnes' in nom_complet:
            continue  # hors périmètre (majoration forfaitaire / chambres, pas de PBR AMU)

        nom_court = nom_complet.replace(' (Assurance privée locale)', '')
        pbr_actuel = row[idx_pbr - 1] if len(row) >= idx_pbr else ''

        if nom_court not in MAPPING_PBR_AMU:
            non_trouves.append((i, nom_complet, "nom absent du mapping (vérifier orthographe)"))
            continue

        entree = MAPPING_PBR_AMU[nom_court]

        # Le PBR actuellement stocké est celui de l'assureur privé (erreur
        # initiale) -> va dans PbrComplementaire quoi qu'il arrive.
        try:
            pbr_assureur_prive = float(str(pbr_actuel).replace(',', '.'))
        except (TypeError, ValueError):
            pbr_assureur_prive = None
        if pbr_assureur_prive:
            entrees_pbr_comp.append((nom_complet, pbr_assureur_prive))

        if entree is None:
            non_trouves.append((i, nom_complet, "pas de correspondance AMU fiable trouvée"))
            continue

        code_amu, pbr_amu = entree
        if str(pbr_actuel) != str(pbr_amu):
            corrections_pbr.append((i, nom_complet, pbr_actuel, pbr_amu, code_amu))

    print(f"📝 {len(corrections_pbr)} correction(s) de PBR (colonne `pbr` -> vrai PBR AMU) :")
    for c in corrections_pbr:
        print(f"   ligne {c[0]:4} {c[1][:55]:55} | pbr actuel (faux, = assureur privé): {c[2]:>7} -> PBR AMU réel ({c[4]}): {c[3]}")

    print(f"\n📋 {len(entrees_pbr_comp)} entrée(s) PbrComplementaire à créer (compagnie \"{COMPAGNIE}\") :")
    for (nom, pbr) in entrees_pbr_comp[:10]:
        print(f"   {nom[:55]:55} pbr_1={pbr}")
    if len(entrees_pbr_comp) > 10:
        print(f"   ... et {len(entrees_pbr_comp) - 10} autre(s)")

    print(f"\n⚠️  {len(non_trouves)} ligne(s) SANS correspondance AMU fiable (pbr laissé tel quel, à trancher avec la clinique) :")
    for (ligne, nom, raison) in non_trouves:
        print(f"   ligne {ligne:4} {nom[:55]:55} | {raison}")

    if not appliquer:
        print("\nℹ️  Aperçu seulement (dry-run) — relancer avec --appliquer pour exécuter réellement.")
        return

    if corrections_pbr:
        batch = [{'range': rowcol_to_a1(c[0], idx_pbr), 'values': [[c[3]]]} for c in corrections_pbr]
        worksheet.batch_update(batch, value_input_option='USER_ENTERED')
        print(f"\n✅ {len(corrections_pbr)} colonne(s) pbr corrigée(s) dans le Sheet.")

    if entrees_pbr_comp:
        with app.app_context():
            existant = CompagnieComplementaire.query.filter_by(structure_id=STRUCTURE_ID, nom=COMPAGNIE).first()
            if not existant:
                db.session.add(CompagnieComplementaire(structure_id=STRUCTURE_ID, nom=COMPAGNIE))
                db.session.commit()
                print(f"✅ Compagnie complémentaire \"{COMPAGNIE}\" créée pour la structure {STRUCTURE_ID}.")

            crees, maj = 0, 0
            for (nom, pbr) in entrees_pbr_comp:
                ligne = PbrComplementaire.query.filter_by(
                    structure_id=STRUCTURE_ID, type='acte', nom_acte=nom, compagnie=COMPAGNIE
                ).first()
                if ligne:
                    ligne.pbr_1 = pbr
                    maj += 1
                else:
                    db.session.add(PbrComplementaire(
                        structure_id=STRUCTURE_ID, type='acte', nom_acte=nom,
                        compagnie=COMPAGNIE, pbr_1=pbr, created_by='script:corriger_pbr_valeo'
                    ))
                    crees += 1
            db.session.commit()
            print(f"✅ PbrComplementaire : {crees} créée(s), {maj} mise(s) à jour.")

    sheets_helper.clear_cache(sheet_name)
    print("\n✅ Terminé.")


if __name__ == "__main__":
    main()
