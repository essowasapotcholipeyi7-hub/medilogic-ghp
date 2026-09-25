"""
Retrouve, pour chaque acte "(Assurance privée locale)" déjà importé dans
struct_13_actes (radiologie/échographie/biologie, script
importer_tarifs_valeo.py), le code officiel + PBR AMU correspondant dans
les barèmes de référence (catégorie CHU), pour corriger la colonne `pbr`
de ces lignes — patron : "le PBR AMU ne varie pas selon l'assurance ou
l'heure, j'ai fabriqué un PBR à la place, il fallait retrouver la vraie
valeur AMU dans les fichiers de référence".

Le prix négocié par l'assureur privé (mal placé dans `pbr` au premier
import) va dans PbrComplementaire (compagnie "Assurance privée locale"),
PAS dans la colonne `pbr` du catalogue — voir corriger_pbr_valeo.py.

Ce script ne modifie RIEN — il produit uniquement un tableau de
correspondances proposées (nom Valeo -> code officiel + PBR), à valider
avant d'écrire quoi que ce soit (corriger_pbr_valeo.py, séparé).

Usage :
    python scripts/matcher_pbr_amu_valeo.py
"""
import io
import os
import re
import sys
import unicodedata
import difflib

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl
from sheets_helper import sheets_helper

STRUCTURE_ID = 13
FICHIER_1 = r"C:\Users\HP\Downloads\ACTES LABO -IMAGERIE- SI-CONSULT 3003 2024.xlsx"
FICHIER_2 = r"C:\Users\HP\Downloads\ACTES_NON_IONISANTS 30 03 2024.xlsx"


def normaliser(txt):
    txt = txt or ''
    txt = unicodedata.normalize('NFKD', txt)
    txt = ''.join(c for c in txt if not unicodedata.combining(c))
    txt = txt.lower()
    txt = re.sub(r'[^\w\s]', ' ', txt)
    txt = re.sub(r'\s+', ' ', txt).strip()
    return txt


def charger_reference(feuilles_par_fichier):
    """Retourne {libelle_normalise: (code, libelle_original, prix, pbr)}."""
    ref = {}
    for chemin, feuilles in feuilles_par_fichier:
        wb = openpyxl.load_workbook(chemin, data_only=True)
        for feuille in feuilles:
            ws = wb[feuille]
            for row in ws.iter_rows(min_row=1, values_only=True):
                code, libelle, prix, pbr = row[0], row[1], row[2], row[3]
                if not code or not isinstance(code, str) or not libelle:
                    continue
                code = code.strip().upper()
                if not re.match(r'^[A-Z]\d{3,4}$', code):
                    continue
                if not isinstance(prix, (int, float)):
                    continue
                ref[normaliser(libelle)] = (code, libelle.strip(), prix, pbr if isinstance(pbr, (int, float)) else prix)
    return ref


def meilleure_correspondance(nom_valeo, reference):
    nom_norm = normaliser(nom_valeo)
    if nom_norm in reference:
        return reference[nom_norm], 1.0
    candidats = difflib.get_close_matches(nom_norm, reference.keys(), n=1, cutoff=0.3)
    if not candidats:
        # repli : correspondance par inclusion de mots significatifs
        mots = [m for m in nom_norm.split() if len(m) > 3]
        meilleurs = []
        for cle in reference:
            if mots and all(m in cle for m in mots):
                meilleurs.append(cle)
        if meilleurs:
            cle = min(meilleurs, key=len)
            return reference[cle], 0.5
        return None, 0.0
    cle = candidats[0]
    score = difflib.SequenceMatcher(None, nom_norm, cle).ratio()
    return reference[cle], score


def main():
    reference = charger_reference([
        (FICHIER_1, ['CONSULT CHU', 'SOINS INFIR CHU', 'LABO CHU et INH', 'IMAGERIE CHU', 'IRM']),
        (FICHIER_2, ['ACTES NON IONISANTS CHU ']),
    ])
    print(f"📖 Référentiel CHU : {len(reference)} libellés uniques\n")

    sheets_helper.set_structure(STRUCTURE_ID, 'CLINIQUE VALEO')
    actes = sheets_helper.get_all_records('actes', use_prefix=True)
    valeo = [a for a in actes if 'Assurance privée locale' in (a.get('nom') or '')
             and not a.get('nom', '').startswith('B20')
             and 'Chambre' not in a.get('nom', '') and 'personnes' not in a.get('nom', '')]

    print(f"{len(valeo)} lignes Valeo (hors chambres/B20) à faire correspondre :\n")
    for a in valeo:
        nom = a.get('nom', '').replace(' (Assurance privée locale)', '')
        match, score = meilleure_correspondance(nom, reference)
        if match:
            code, libelle_off, prix_off, pbr_off = match
            marqueur = '✅' if score >= 0.6 else '❓'
            print(f"{marqueur} {nom:55} -> {code:6} {libelle_off[:45]:45} PBR={pbr_off} (score={score:.2f}) [pbr actuel: {a.get('pbr')}]")
        else:
            print(f"❌ {nom:55} -> AUCUNE correspondance trouvée [pbr actuel: {a.get('pbr')}]")


if __name__ == "__main__":
    main()
