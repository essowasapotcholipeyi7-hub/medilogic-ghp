"""
Importe la convention tarifaire "Assurance privée locale" de Clinique
Valeo (structure_id=13) dans son catalogue d'actes Google Sheet
(struct_13_actes), à partir des fichiers Word remis par la clinique :

    C:\\Users\\HP\\Downloads\\CLINIQUE VALEO\\
        1_HOSPITALISATION_bis.docx
        2_RADIOLOGIE_ASSURE_LOCAL_normal.docx   (contient déjà le prix nuit
                                                  en dernière colonne — les
                                                  fichiers 3/5 nuit séparés
                                                  sont redondants, vérifié :
                                                  mêmes valeurs, PBR
                                                  inchangé)
        4_ECHOGRAPHIE_ASSURE LOCAL_normal.docx  (idem)
        6_BIOLOGIE_230_PRIVEES LOCALES_80_.docx (ELEMENTS/B230/ASSURE
                                                  identiques au fichier 90%,
                                                  seule la répartition
                                                  diffère — pas stockée ici,
                                                  c'est le taux du PATIENT
                                                  qui décide 80 vs 90)

N'ajoute QUE des lignes NOUVELLES, suffixées "(Assurance privée locale)" —
ne touche JAMAIS aux lignes AMU déjà en place (noms différents, codes
Q100/R607/... jamais réutilisés ici). Idempotent : si une ligne du même
nom existe déjà dans le Sheet, elle est sautée (pas de doublon si le
script est relancé).

Ajoute la colonne `prix_nuit` en fin d'en-tête si elle n'existe pas encore
(lue par est_tarif_nuit_actif()/actes_vente() via le nom de colonne, donc
rétrocompatible pour toutes les autres structures qui ne l'ont pas).

Usage :
    python scripts/importer_tarifs_valeo.py
"""
import io
import os
import re
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import docx
from sheets_helper import sheets_helper

STRUCTURE_ID = 13
DOSSIER = r"C:\Users\HP\Downloads\CLINIQUE VALEO"
SUFFIXE = "(Assurance privée locale)"


def _nombre(valeur):
    if valeur is None:
        return None
    txt = str(valeur).strip().replace(" ", "").replace(",", ".")
    if not txt:
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def _nom(txt):
    return " ".join((txt or "").split())


def lire_table(chemin, index_table):
    d = docx.Document(chemin)
    table = d.tables[index_table]
    return [[c.text.strip() for c in row.cells] for row in table.rows]


def parser_hospitalisation():
    """Fichier 1 : 4 catégories de chambre, prix/jour simple."""
    lignes = lire_table(os.path.join(DOSSIER, "1_HOSPITALISATION_bis.docx"), 0)
    chambres = []
    for row in lignes:
        if len(row) < 3:
            continue
        prix = _nombre(row[2])
        if prix is None or prix <= 0:
            continue
        nom = _nom(row[1]) or _nom(row[0])
        if not nom:
            continue
        chambres.append({'nom': f"{nom} {SUFFIXE}", 'prix': prix, 'pbr': prix, 'prix_nuit': None,
                          'statut': 'DIRECT', 'description': nom})
    return chambres


def parser_radiologie_ou_echo(chemin, description_categorie):
    """Fichiers 2/4 : N° | Produit | Z | Z=1000 | Prix unitaire | PBR |
    Part 80% | Part 90% | Prix férié/nuit dimanche — la dernière colonne
    EST le prix nuit, pas besoin des fichiers 3/5 séparés."""
    lignes = lire_table(chemin, 1)
    actes = []
    vus = set()
    for row in lignes:
        if len(row) < 9:
            continue
        if not row[0].strip().isdigit():
            continue  # en-tête de colonnes ou ligne de section ("Tête", "Thorax"...)
        nom_brut = _nom(row[1])
        if not nom_brut:
            continue
        prix = _nombre(row[4])
        pbr = _nombre(row[5])
        prix_nuit = _nombre(row[8])
        if prix is None or prix <= 0:
            continue
        nom = f"{nom_brut} {SUFFIXE}"
        if nom in vus:
            continue  # même acte listé sous 2 sections (valeurs identiques, vérifié)
        vus.add(nom)
        actes.append({'nom': nom, 'prix': prix, 'pbr': pbr or prix,
                      'prix_nuit': prix_nuit, 'statut': 'EP',
                      'description': f"{description_categorie} - {nom_brut}"})
    return actes


def parser_biologie():
    """Fichier 6 : ELEMENTS | B(230) | ASSURE | ... — ASSURE est à la fois
    le prix facturé ET la base de remboursement (pas de plafond ici,
    vérifié : 80%/90% de ASSURE reproduit exactement les colonnes "Part
    Assuré" fournies)."""
    lignes = lire_table(os.path.join(DOSSIER, "6_BIOLOGIE_230_PRIVEES LOCALES_80_.docx"), 0)
    actes = []
    vus = set()
    for row in lignes:
        if len(row) < 3:
            continue
        assure = _nombre(row[2])
        if assure is None or assure <= 0:
            continue
        nom_brut = _nom(row[0])
        if not nom_brut or nom_brut.upper() == 'ELEMENTS':
            continue
        nom = f"{nom_brut} {SUFFIXE}"
        if nom in vus:
            continue  # même analyse listée sous 2 catégories (valeurs identiques, vérifié)
        vus.add(nom)
        actes.append({'nom': nom, 'prix': assure, 'pbr': assure, 'prix_nuit': None,
                      'statut': 'EP', 'description': f"Biologie B230 - {nom_brut}"})
    return actes


def majoration_biologie_nuit():
    """Forfait fixe (pas un 2e prix par analyse) : le fichier biologie
    précise "Faire le total des bilans, rajouter B20 soit 4600 FCFA" —
    ajouté manuellement au panier par le caissier pour un bilan de nuit,
    donc 100% patient (non remboursé)."""
    return [{'nom': f"B20 - Majoration nuit/férié/dimanche (biologie) {SUFFIXE}",
             'prix': 4600, 'pbr': 0, 'prix_nuit': None, 'statut': 'DIRECT',
             'description': "Majoration fixe biologie hors heures ouvrées"}]


def construire_lignes(entetes, acte, next_id):
    """Construit une ligne positionnelle dans l'ORDRE RÉEL de l'en-tête du
    Sheet (pas un ordre codé en dur) — robuste à un réordonnancement futur
    des colonnes."""
    valeurs = {
        'ID': next_id,
        'nom': acte['nom'],
        'prix': acte['prix'],
        'pbr': acte['pbr'],
        'description': acte.get('description', acte['nom']),
        'structure_id': STRUCTURE_ID,
        'prise_en_charge_amu': 'TRUE' if acte['pbr'] else 'FALSE',
        'commentaire_amu': '',
        'prise_en_charge_cac': 'TRUE' if acte['pbr'] else 'FALSE',
        'commentaire_cac': '',
        'statut': acte['statut'],
        'AMU-TNS': 'TRUE',
        'prix_nuit': acte.get('prix_nuit') or '',
    }
    return [valeurs.get(h, '') for h in entetes]


def main():
    sheets_helper.set_structure(STRUCTURE_ID, 'CLINIQUE VALEO')
    sheet_name = sheets_helper.get_sheet_name('actes')
    worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)

    entetes = worksheet.row_values(1)
    if 'prix_nuit' not in entetes:
        worksheet.update_cell(1, len(entetes) + 1, 'prix_nuit')
        entetes = worksheet.row_values(1)
        print("✅ Colonne 'prix_nuit' ajoutée à", sheet_name)
    else:
        print("ℹ️ Colonne 'prix_nuit' déjà présente")

    existants = sheets_helper.get_all_records('actes', use_prefix=True)
    noms_existants = {(_nom(a.get('nom', ''))) for a in existants}
    ids_existants = [_nombre(a.get('ID')) for a in existants if _nombre(a.get('ID')) is not None]
    next_id = int(max(ids_existants)) + 1 if ids_existants else 1

    chambres = parser_hospitalisation()
    radiologie = parser_radiologie_ou_echo(
        os.path.join(DOSSIER, "2_RADIOLOGIE_ASSURE_LOCAL_normal.docx"), "Radiologie")
    echographie = parser_radiologie_ou_echo(
        os.path.join(DOSSIER, "4_ECHOGRAPHIE_ASSURE LOCAL_normal.docx"), "Échographie")
    biologie = parser_biologie()
    majoration = majoration_biologie_nuit()

    categories = [
        ("Chambres d'hospitalisation", chambres),
        ("Radiologie", radiologie),
        ("Échographie", echographie),
        ("Biologie B230", biologie),
        ("Majoration biologie nuit", majoration),
    ]

    lignes_a_inserer = []
    resume = {}
    for label, actes in categories:
        ajoutees, sautees = 0, 0
        for acte in actes:
            if acte['nom'] in noms_existants:
                sautees += 1
                continue
            lignes_a_inserer.append(construire_lignes(entetes, acte, next_id))
            noms_existants.add(acte['nom'])
            next_id += 1
            ajoutees += 1
        resume[label] = (ajoutees, sautees)

    print(f"\n📋 {len(lignes_a_inserer)} nouvelle(s) ligne(s) à insérer dans {sheet_name} :")
    for label, (ajoutees, sautees) in resume.items():
        print(f"   - {label} : {ajoutees} ajoutée(s), {sautees} déjà présente(s) (sautée(s))")

    if not lignes_a_inserer:
        print("\nRien à insérer, catalogue déjà à jour.")
        return

    worksheet.append_rows(lignes_a_inserer, value_input_option='USER_ENTERED')
    sheets_helper.clear_cache(sheet_name)
    print(f"\n✅ {len(lignes_a_inserer)} ligne(s) insérée(s) dans {sheet_name}.")


if __name__ == "__main__":
    main()
