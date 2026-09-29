# offline/app_offline.py
"""Point d'entrée de l'appli hors-ligne — voir le plan pour le contexte.

Lancement : python -m waitress --listen=127.0.0.1:5100 offline.app_offline:app
(voir le .bat de la tâche planifiée Windows).

Le personnel utilise ce process (favori http://127.0.0.1:5100/) à la place
de l'URL en ligne habituelle. "/" teste la joignabilité de l'appli en ligne
à CHAQUE requête et redirige si elle répond — sinon sert l'interface locale
ci-dessous, branchée sur SQLite.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, redirect, request, session, jsonify

from offline.config_offline import OFFLINE_STRUCTURE_ID, ONLINE_APP_URL
from offline.models_offline import initialiser_schema
from offline.db_offline import get_connection, requeter
from offline.connectivity import app_en_ligne_joignable
from offline.auth_offline import tenter_connexion, utilisateur_connecte, nom_utilisateur, deconnecter
from offline.routes_patients import bp_patients
from offline.routes_ventes import bp_ventes
from offline import watchdog_offline

if not OFFLINE_STRUCTURE_ID:
    raise RuntimeError(
        "OFFLINE_STRUCTURE_ID doit être définie (voir offline/config_offline.py) — "
        "on ne démarre JAMAIS sans savoir quelle structure ce PC sert, pour ne "
        "jamais risquer de mélanger les données de deux cliniques différentes."
    )

app = Flask(__name__, template_folder='templates')
app.secret_key = os.environ.get('OFFLINE_SECRET_KEY', 'medilogic-offline-pilote-cle-dev')

app.register_blueprint(bp_patients)
app.register_blueprint(bp_ventes)

initialiser_schema()

# Au démarrage, tente une fois de rafraîchir le point de départ des
# numero_local (voir catalog_sync.rafraichir_numeros_locaux) — best-effort :
# si le réseau est déjà coupé au lancement de l'appli, on garde la dernière
# valeur connue (ou 0 sur une toute première installation).
try:
    from offline.catalog_sync import (
        rafraichir_numeros_locaux, rafraichir_catalogue, rafraichir_utilisateurs,
        rafraichir_patients_existants, rafraichir_structure_info,
    )
    rafraichir_numeros_locaux()
    rafraichir_catalogue()
    rafraichir_utilisateurs()
    rafraichir_structure_info()
    n = rafraichir_patients_existants()
    if n:
        print(f"[offline] {n} patient(s) existant(s) mis en cache au démarrage.")
except Exception as e:
    print(f"[offline] Rafraîchissement initial impossible (réseau coupé ?) : {e}")

watchdog_offline.demarrer()


@app.route('/')
def accueil():
    if app_en_ligne_joignable():
        return redirect(ONLINE_APP_URL)
    if not utilisateur_connecte():
        return redirect('/login')
    return redirect('/patients')


@app.route('/login', methods=['GET', 'POST'])
def login():
    erreur = None
    if request.method == 'POST':
        ok, resultat = tenter_connexion(
            (request.form.get('email') or '').strip(),
            request.form.get('mot_de_passe') or ''
        )
        if ok:
            return redirect('/patients')
        erreur = resultat
    return render_template('offline_login.html', erreur=erreur)


@app.route('/logout')
def logout():
    deconnecter()
    return redirect('/login')


@app.route('/patients')
def page_patients():
    if not utilisateur_connecte():
        return redirect('/login')
    return render_template('offline_patients.html', nom_utilisateur=nom_utilisateur())


@app.route('/ventes')
def page_ventes():
    if not utilisateur_connecte():
        return redirect('/login')
    conn = get_connection()
    actes = [dict(r) for r in conn.execute("SELECT nom, donnees FROM catalogue_actes ORDER BY nom")]
    produits = [dict(r) for r in conn.execute("SELECT nom, donnees FROM catalogue_produits ORDER BY nom")]
    return render_template(
        'offline_ventes.html',
        nom_utilisateur=nom_utilisateur(),
        nb_actes=len(actes),
        nb_produits=len(produits),
    )


def _chercher_catalogue(table, terme):
    conn = get_connection()
    if terme:
        lignes = conn.execute(
            f"SELECT nom, donnees FROM {table} WHERE LOWER(nom) LIKE ? ORDER BY nom LIMIT 20",
            (f"%{terme.lower()}%",)
        ).fetchall()
    else:
        lignes = conn.execute(f"SELECT nom, donnees FROM {table} ORDER BY nom LIMIT 20").fetchall()
    import json as _json
    items = []
    for ligne in lignes:
        donnees = _json.loads(ligne['donnees'])
        prix = donnees.get('prix_vente') or donnees.get('prix') or donnees.get('prix_unitaire') or 0
        items.append({'nom': ligne['nom'], 'prix': prix, 'id': donnees.get('ID') or donnees.get('id')})
    return items


@app.route('/api/offline/catalogue/actes')
def catalogue_actes():
    if not utilisateur_connecte():
        return jsonify({'success': False, 'error': 'Non connecté'}), 401
    return jsonify({'success': True, 'items': _chercher_catalogue('catalogue_actes', request.args.get('q', ''))})


@app.route('/api/offline/catalogue/produits')
def catalogue_produits():
    if not utilisateur_connecte():
        return jsonify({'success': False, 'error': 'Non connecté'}), 401
    return jsonify({'success': True, 'items': _chercher_catalogue('catalogue_produits', request.args.get('q', ''))})


@app.route('/recu/<vente_uuid>')
def recu(vente_uuid):
    if not utilisateur_connecte():
        return redirect('/login')

    import json as _json
    from crypto_helper import dechiffrer

    vente = requeter(
        "SELECT * FROM offline_ventes WHERE uuid = ? AND structure_id = ?",
        (vente_uuid, OFFLINE_STRUCTURE_ID)
    )
    if not vente:
        return "Vente introuvable", 404
    vente = dict(vente[0])

    patient = requeter("SELECT * FROM offline_patients WHERE uuid = ?", (vente['patient_uuid'],))
    patient = dict(patient[0]) if patient else {}

    structure = requeter("SELECT * FROM offline_structure_info WHERE id = 1")
    structure = dict(structure[0]) if structure else {}

    colonne_articles = 'actes' if vente['type'] == 'actes' else 'produits'
    articles = _json.loads(vente.get(colonne_articles) or '[]')

    return render_template(
        'offline_recu.html',
        vente=vente,
        patient_nom=f"{dechiffrer(patient.get('nom')) or ''} {dechiffrer(patient.get('prenom')) or ''}".strip(),
        structure=structure,
        articles=articles,
        deja_synchronise=bool(vente.get('neon_id')),
    )


@app.route('/api/offline/sync/status')
def sync_status():
    ligne = requeter("SELECT * FROM offline_sync_state WHERE id = 1")
    en_attente = requeter("SELECT COUNT(*) AS n FROM offline_outbox WHERE status = 'pending'")
    erreurs = requeter("SELECT COUNT(*) AS n FROM offline_outbox WHERE status = 'error'")
    etat = dict(ligne[0]) if ligne else {}
    etat['en_attente'] = en_attente[0]['n'] if en_attente else 0
    etat['erreurs'] = erreurs[0]['n'] if erreurs else 0
    return jsonify(etat)


@app.route('/api/offline/sync/forcer', methods=['POST'])
def sync_forcer():
    if not utilisateur_connecte():
        return jsonify({'success': False, 'error': 'Non connecté'}), 401
    from offline.outbox import push_pending
    try:
        resultats = push_pending()
        return jsonify({'success': True, **resultats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5100, debug=False)
