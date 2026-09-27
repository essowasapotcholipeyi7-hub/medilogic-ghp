"""
Retire le statut "EP" (Entente Préalable) des actes de BIOLOGIE
"(Assurance privée locale)" de Clinique Valeo (structure_id=13) —
demande du patron.

Ces 56 lignes (importées par importer_tarifs_valeo.py, toutes avec une
description commençant par "Biologie ...") avaient toutes reçu le
statut "EP" par défaut à l'import, ce qui déclenche à chaque fois la
confirmation "⚠️ ENTENTE PRÉALABLE" côté caisse (voir actes_vente.html,
toggleMedecinRealisateur/ajouterActe) pour un patient assuré AMU — non
souhaité pour de simples tests de biologie courants (NFS, glycémie...).

Ne touche à AUCUNE autre ligne : ni les actes de biologie "normaux"
(codes R1xx-R9xx, qui n'ont déjà pas ce statut), ni les 78 lignes EP
restantes (radiologie/échographie "Assurance privée locale", et deux
consultations S100/S110 qui ont aussi EP mais ne sont pas de la
biologie — hors périmètre de cette demande précise).

Usage :
    python scripts/enlever_ep_biologie_valeo.py            # aperçu (dry-run)
    python scripts/enlever_ep_biologie_valeo.py --appliquer  # applique réellement
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

STRUCTURE_ID = 13


def main():
    appliquer = '--appliquer' in sys.argv

    sheets_helper.set_structure(STRUCTURE_ID, 'CLINIQUE VALEO')
    sheet_name = sheets_helper.get_sheet_name('actes')
    worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
    entetes = worksheet.row_values(1)
    idx_desc = entetes.index('description')
    idx_statut = entetes.index('statut')
    idx_nom = entetes.index('nom')

    valeurs = worksheet.get_all_values()
    cibles = []
    for i, row in enumerate(valeurs[1:], start=2):
        if len(row) <= max(idx_desc, idx_statut):
            continue
        desc = row[idx_desc].strip().lower()
        statut = row[idx_statut].strip().upper()
        if desc.startswith('biologie') and statut == 'EP':
            cibles.append((i, row[idx_nom]))

    print(f"📝 {len(cibles)} acte(s) de biologie avec statut EP à corriger (-> statut vide/direct) :")
    for (ligne, nom) in cibles:
        print(f"   ligne {ligne:4} {nom}")

    if not appliquer:
        print("\nℹ️  Aperçu seulement (dry-run) — relancer avec --appliquer pour exécuter réellement.")
        return

    if cibles:
        batch = [{'range': rowcol_to_a1(ligne, idx_statut + 1), 'values': [['']]} for (ligne, _) in cibles]
        worksheet.batch_update(batch, value_input_option='USER_ENTERED')
        print(f"\n✅ {len(cibles)} ligne(s) corrigée(s) (statut EP retiré).")

    sheets_helper.clear_cache(sheet_name)
    print("\n✅ Terminé.")


if __name__ == "__main__":
    main()
