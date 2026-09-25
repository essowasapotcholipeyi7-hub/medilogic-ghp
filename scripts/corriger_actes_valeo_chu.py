"""
Corrige le catalogue AMU de Clinique Valeo (structure_id=13) avec les
VRAIS tarifs officiels de la catégorie CHU, à partir des deux barèmes
nationaux remis par le patron :
    C:\\Users\\HP\\Downloads\\ACTES LABO -IMAGERIE- SI-CONSULT 3003 2024.xlsx
    C:\\Users\\HP\\Downloads\\ACTES_NON_IONISANTS 30 03 2024.xlsx

Contexte : les 418 lignes AMU déjà dans struct_13_actes n'étaient que des
exemples (confirmé par le patron), pas les vrais tarifs. Ce script :

1. Corrige prix/pbr des lignes dont le CODE (préfixe de `nom`, ex. "Q100")
   correspond à EXACTEMENT UNE ligne du catalogue ET à un code du barème
   CHU, quand la valeur diffère. Les codes présents sur PLUSIEURS lignes
   (ex. S101 x3 avec des libellés différents type "(PEDIATRIQUE)"/"(NEO
   NAT)") sont volontairement laissés intacts — probablement une
   différenciation voulue par la clinique, décision du patron.
2. Supprime les ~51 lignes qui sont en réalité des en-têtes de section
   recopiés par erreur depuis le document source (ex. "Membre superieur",
   "HEMATOLOGIE", des phrases de note) — liste figée ci-dessous, revue
   ligne par ligne avant ce script, PAS une heuristique automatique (pour
   ne jamais supprimer par erreur un vrai acte local sans code officiel,
   comme "MISE EN OBSERVATION (MEO)" ou "CARNET DE CONSULTATION").

Ne touche JAMAIS aux 128 lignes "(Assurance privée locale)" (import
séparé, voir importer_tarifs_valeo.py) ni aux codes P157/P158/P160 (pas de
référence disponible dans ces deux fichiers pour les corriger).

Usage :
    python scripts/corriger_actes_valeo_chu.py            # aperçu (dry-run)
    python scripts/corriger_actes_valeo_chu.py --appliquer  # applique réellement
"""
import io
import os
import re
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl
from sheets_helper import sheets_helper

STRUCTURE_ID = 13
FICHIER_1 = r"C:\Users\HP\Downloads\ACTES LABO -IMAGERIE- SI-CONSULT 3003 2024.xlsx"
FICHIER_2 = r"C:\Users\HP\Downloads\ACTES_NON_IONISANTS 30 03 2024.xlsx"

# ⭐ Lignes confirmées comme de vrais actes locaux SANS code officiel — ne
# jamais les supprimer même si elles n'ont pas de préfixe code (revues
# une par une avec le patron avant ce script).
NOMS_A_CONSERVER_SANS_CODE = {
    "MISE EN OBSERVATION (MEO)",
    "CARNET DE CONSULTATION",
    "DOSSIER DE CONSULTATION",
    "CARNET CPN",
    "Controle tension arterielle",
    "Suivi de test de Grossesse",
    "Acte de retrait de DIU",
    "Acte de retrait d'implant",
    "Carnet de consultation mere - enfant",
    "p120 carnet",
}


def charger_feuille(chemin, feuille):
    wb = openpyxl.load_workbook(chemin, data_only=True)
    ws = wb[feuille]
    out = {}
    for row in ws.iter_rows(min_row=1, values_only=True):
        code = row[0]
        if not code or not isinstance(code, str):
            continue
        code = code.strip().upper()
        if not re.match(r'^[A-Z]\d{3,4}$', code):
            continue
        prix = row[2]
        pbr = row[3]
        if not isinstance(prix, (int, float)):
            continue
        out[code] = {'prix': prix, 'pbr': pbr if isinstance(pbr, (int, float)) else prix}
    return out


def charger_reference_chu():
    lookup = {}
    for feuille in ['CONSULT CHU', 'SOINS INFIR CHU', 'LABO CHU et INH', 'IMAGERIE CHU', 'IRM']:
        lookup.update(charger_feuille(FICHIER_1, feuille))
    lookup.update(charger_feuille(FICHIER_2, 'ACTES NON IONISANTS CHU '))
    return lookup


def main():
    appliquer = '--appliquer' in sys.argv

    lookup = charger_reference_chu()
    print(f"📖 Référentiel CHU chargé : {len(lookup)} codes")

    sheets_helper.set_structure(STRUCTURE_ID, 'CLINIQUE VALEO')
    sheet_name = sheets_helper.get_sheet_name('actes')
    worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
    entetes = worksheet.row_values(1)
    idx_prix = entetes.index('prix') + 1
    idx_pbr = entetes.index('pbr') + 1

    valeurs = worksheet.get_all_values()  # [0] = en-tête, [1:] = données, ligne sheet = i+2
    idx_nom_col = entetes.index('nom')

    # ⭐ Compter les occurrences de chaque code AVANT toute action, pour
    # exclure les codes multi-variantes (décision du patron).
    occurrences = {}
    for row in valeurs[1:]:
        if len(row) <= idx_nom_col:
            continue
        nom = row[idx_nom_col]
        if 'Assurance privée locale' in nom:
            continue
        m = re.match(r'^([A-Z]\d{3,4})\s', nom)
        if m:
            occurrences[m.group(1)] = occurrences.get(m.group(1), 0) + 1

    corrections = []  # (ligne_sheet, code, nom, ancien_prix, ancien_pbr, nouveau_prix, nouveau_pbr)
    suppressions = []  # (ligne_sheet, nom)

    for i, row in enumerate(valeurs[1:], start=2):
        if len(row) <= idx_nom_col:
            continue
        nom = row[idx_nom_col]
        if not nom or 'Assurance privée locale' in nom:
            continue

        m = re.match(r'^([A-Z]\d{3,4})\s', nom)
        if m:
            code = m.group(1)
            if occurrences.get(code) != 1:
                continue  # code multi-variantes -> intact (décision du patron)
            ref = lookup.get(code)
            if not ref:
                continue  # pas de référence CHU pour ce code (ex. P157/P158/P160)
            ancien_prix = row[idx_prix - 1] if len(row) >= idx_prix else ''
            ancien_pbr = row[idx_pbr - 1] if len(row) >= idx_pbr else ''
            if str(ancien_prix) != str(ref['prix']) or str(ancien_pbr) != str(ref['pbr']):
                corrections.append((i, code, nom, ancien_prix, ancien_pbr, ref['prix'], ref['pbr']))
        else:
            # Pas de code -> ligne parasite, SAUF si dans la liste confirmée
            if nom.strip() not in NOMS_A_CONSERVER_SANS_CODE:
                suppressions.append((i, nom))

    print(f"\n📝 {len(corrections)} correction(s) de prix/pbr :")
    for c in corrections:
        print(f"   ligne {c[0]:4} {c[1]:6} {c[2][:50]:50} | {c[3]}/{c[4]} -> {c[5]}/{c[6]}")

    print(f"\n🗑️  {len(suppressions)} ligne(s) parasite(s) à supprimer :")
    for s in suppressions:
        print(f"   ligne {s[0]:4} {s[1]}")

    if not appliquer:
        print("\nℹ️  Aperçu seulement (dry-run) — relancer avec --appliquer pour exécuter réellement.")
        return

    if corrections:
        batch = []
        for (ligne, code, nom, ap, apbr, np, npbr) in corrections:
            cellule_prix = worksheet.cell(ligne, idx_prix).address
            cellule_pbr = worksheet.cell(ligne, idx_pbr).address
            batch.append({'range': cellule_prix, 'values': [[np]]})
            batch.append({'range': cellule_pbr, 'values': [[npbr]]})
        worksheet.batch_update(batch, value_input_option='USER_ENTERED')
        print(f"\n✅ {len(corrections)} ligne(s) corrigée(s).")

    if suppressions:
        # ⭐ Supprimer du bas vers le haut pour ne pas décaler les numéros
        # de ligne des suppressions suivantes.
        for (ligne, nom) in sorted(suppressions, key=lambda s: -s[0]):
            worksheet.delete_rows(ligne)
        print(f"✅ {len(suppressions)} ligne(s) parasite(s) supprimée(s).")

    sheets_helper.clear_cache(sheet_name)
    print("\n✅ Terminé.")


if __name__ == "__main__":
    main()
