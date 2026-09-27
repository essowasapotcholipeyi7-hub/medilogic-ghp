"""
Sépare la ligne unique "SRV (Assurance privée locale)" de Clinique Valeo
(structure_id=13) en deux actes distincts, correspondant à deux méthodes
de sérologie rétrovirale bien différentes dans le barème officiel CHU
(fichier ACTES LABO -IMAGERIE- SI-CONSULT 3003 2024.xlsx, feuille "LABO
CHU et INH") :
    R412 - Sérologie VIH (tests rapides validés)          PBR AMU = 2 200
    R413 - Sérologie VIH (Elisa et autres méthodes...)     PBR AMU = 6 050

Confirmé par le patron : la ligne existante (prix assureur privé 13 800 F,
un prix élevé) correspond à l'Elisa. Le test rapide est ajouté comme
nouvel acte, provisoirement au même prix (13 800 F) — à ajuster depuis la
page Actes si besoin.

Actions :
1. Renomme la ligne existante en "SRV Elisa (Assurance privée locale)",
   met pbr=6050, met à jour sa description.
2. Ajoute une nouvelle ligne "SRV test rapide (Assurance privée locale)"
   (même structure de colonnes), prix=13800, pbr=2200.
3. Met à jour la ligne PbrComplementaire existante (nom_acte suit le
   renommage) et crée la nouvelle pour le test rapide — même pbr_1
   (13 800, prix assureur privé) que l'ancienne ligne unique.

Usage :
    python scripts/separer_srv_valeo.py            # aperçu (dry-run)
    python scripts/separer_srv_valeo.py --appliquer  # applique réellement
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

NOM_ANCIEN = "SRV (Assurance privée locale)"
NOM_ELISA = "SRV Elisa (Assurance privée locale)"
NOM_RAPIDE = "SRV test rapide (Assurance privée locale)"
PRIX_ASSUREUR_PRIVE = 13800
PBR_ELISA = 6050
PBR_RAPIDE = 2200


def main():
    appliquer = '--appliquer' in sys.argv

    sheets_helper.set_structure(STRUCTURE_ID, 'CLINIQUE VALEO')
    sheet_name = sheets_helper.get_sheet_name('actes')
    worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
    entetes = worksheet.row_values(1)
    idx_nom = entetes.index('nom')
    idx_prix = entetes.index('prix')
    idx_pbr = entetes.index('pbr')
    idx_desc = entetes.index('description')

    valeurs = worksheet.get_all_values()
    ligne_srv = None
    for i, row in enumerate(valeurs[1:], start=2):
        if len(row) > idx_nom and row[idx_nom] == NOM_ANCIEN:
            ligne_srv = i
            row_srv = row
            break

    if not ligne_srv:
        print(f"❌ Ligne '{NOM_ANCIEN}' introuvable — rien à faire (déjà séparée ?).")
        return

    ids = [int(a['ID']) for a in sheets_helper.get_all_records('actes', use_prefix=True) if str(a.get('ID', '')).isdigit()]
    nouvel_id = max(ids) + 1

    print(f"1) Renommer ligne {ligne_srv} : '{NOM_ANCIEN}' -> '{NOM_ELISA}', pbr {row_srv[idx_pbr]} -> {PBR_ELISA}")
    print(f"2) Ajouter une nouvelle ligne (ID={nouvel_id}) : '{NOM_RAPIDE}', prix={PRIX_ASSUREUR_PRIVE}, pbr={PBR_RAPIDE}")
    print(f"3) PbrComplementaire : renommer l'entrée existante + créer la nouvelle (pbr_1={PRIX_ASSUREUR_PRIVE} pour les deux)")

    if not appliquer:
        print("\nℹ️  Aperçu seulement (dry-run) — relancer avec --appliquer pour exécuter réellement.")
        return

    # 1) Renommer + corriger pbr de la ligne existante (Elisa)
    from gspread.utils import rowcol_to_a1
    worksheet.batch_update([
        {'range': rowcol_to_a1(ligne_srv, idx_nom + 1), 'values': [[NOM_ELISA]]},
        {'range': rowcol_to_a1(ligne_srv, idx_pbr + 1), 'values': [[PBR_ELISA]]},
        {'range': rowcol_to_a1(ligne_srv, idx_desc + 1), 'values': [['Biologie R413 - Sérologie VIH (Elisa)']]},
    ], value_input_option='USER_ENTERED')
    print(f"✅ Ligne {ligne_srv} renommée en '{NOM_ELISA}', pbr={PBR_ELISA}.")

    # 2) Nouvelle ligne pour le test rapide — même structure de colonnes
    nouvelle_ligne = [''] * len(entetes)
    nouvelle_ligne[entetes.index('ID')] = str(nouvel_id)
    nouvelle_ligne[idx_nom] = NOM_RAPIDE
    nouvelle_ligne[idx_prix] = str(PRIX_ASSUREUR_PRIVE)
    nouvelle_ligne[idx_pbr] = str(PBR_RAPIDE)
    nouvelle_ligne[idx_desc] = 'Biologie R412 - Sérologie VIH (test rapide)'
    nouvelle_ligne[entetes.index('structure_id')] = str(STRUCTURE_ID)
    nouvelle_ligne[entetes.index('prise_en_charge_amu')] = row_srv[entetes.index('prise_en_charge_amu')]
    nouvelle_ligne[entetes.index('prise_en_charge_cac')] = row_srv[entetes.index('prise_en_charge_cac')]
    nouvelle_ligne[entetes.index('statut')] = row_srv[entetes.index('statut')]
    nouvelle_ligne[entetes.index('AMU-TNS')] = row_srv[entetes.index('AMU-TNS')]
    worksheet.append_row(nouvelle_ligne, value_input_option='USER_ENTERED')
    print(f"✅ Nouvelle ligne ajoutée : '{NOM_RAPIDE}' (ID={nouvel_id}).")

    sheets_helper.clear_cache(sheet_name)

    # 3) PbrComplementaire
    with app.app_context():
        ancienne = PbrComplementaire.query.filter_by(
            structure_id=STRUCTURE_ID, type='acte', nom_acte=NOM_ANCIEN, compagnie=COMPAGNIE
        ).first()
        if ancienne:
            ancienne.nom_acte = NOM_ELISA
            print(f"✅ PbrComplementaire existante renommée -> '{NOM_ELISA}' (pbr_1={ancienne.pbr_1}).")
        else:
            print(f"⚠️ Aucune PbrComplementaire trouvée pour '{NOM_ANCIEN}' — rien à renommer.")

        nouvelle = PbrComplementaire.query.filter_by(
            structure_id=STRUCTURE_ID, type='acte', nom_acte=NOM_RAPIDE, compagnie=COMPAGNIE
        ).first()
        if not nouvelle:
            db.session.add(PbrComplementaire(
                structure_id=STRUCTURE_ID, type='acte', nom_acte=NOM_RAPIDE,
                compagnie=COMPAGNIE, pbr_1=PRIX_ASSUREUR_PRIVE, created_by='script:separer_srv_valeo'
            ))
            print(f"✅ PbrComplementaire créée pour '{NOM_RAPIDE}' (pbr_1={PRIX_ASSUREUR_PRIVE}).")
        db.session.commit()

    print("\n✅ Terminé.")


if __name__ == "__main__":
    main()
