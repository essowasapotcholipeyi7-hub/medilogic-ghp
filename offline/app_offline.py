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
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, redirect, request, session, jsonify

from offline.config_offline import OFFLINE_STRUCTURE_ID, ONLINE_APP_URL, OFFLINE_DB_PATH
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

def _obtenir_secret_key():
    """⭐ SÉCURITÉ : ne jamais utiliser de valeur par défaut codée en dur —
    ce dépôt est sur GitHub, une clé par défaut y serait publique et
    permettrait de forger une session sur n'importe quelle installation qui
    ne l'aurait pas explicitement changée. Si OFFLINE_SECRET_KEY n'est pas
    définie, une clé aléatoire est générée UNE FOIS et conservée dans un
    fichier local (à côté du fichier SQLite) — stable entre redémarrages,
    mais jamais partagée entre deux installations ni versionnée."""
    depuis_env = os.environ.get('OFFLINE_SECRET_KEY')
    if depuis_env:
        return depuis_env

    import secrets
    chemin = os.path.join(os.path.dirname(OFFLINE_DB_PATH), '.secret_key')
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    if os.path.exists(chemin):
        with open(chemin, 'r', encoding='utf-8') as f:
            cle = f.read().strip()
        if cle:
            return cle
    cle = secrets.token_hex(32)
    with open(chemin, 'w', encoding='utf-8') as f:
        f.write(cle)
    print(f"[offline] OFFLINE_SECRET_KEY absente — clé aléatoire générée et sauvegardée dans {chemin}")
    return cle


app = Flask(__name__, template_folder='templates')
app.secret_key = _obtenir_secret_key()

app.register_blueprint(bp_patients)
app.register_blueprint(bp_ventes)

initialiser_schema()

# Au démarrage, tente une fois de rafraîchir le point de départ des
# numero_local (voir catalog_sync.rafraichir_numeros_locaux) — best-effort :
# si le réseau est déjà coupé au lancement de l'appli, on garde la dernière
# valeur connue (ou 0 sur une toute première installation).
from offline.catalog_sync import (
    rafraichir_numeros_locaux, rafraichir_catalogue, rafraichir_utilisateurs,
    rafraichir_patients_existants, rafraichir_structure_info,
    rafraichir_pbr_complementaires,
)


def _rafraichir_au_demarrage():
    """⭐ Chaque rafraîchissement dans SON PROPRE try/except — jamais un seul
    bloc autour de tous. Sinon un simple hoquet réseau sur UN SEUL appel
    (ex: Neon injoignable une seconde au démarrage, déjà vu en vrai) empêche
    TOUS les suivants de s'exécuter, y compris ceux qui n'ont besoin QUE de
    Google Sheets (rafraichir_catalogue) et qui auraient sinon réussi sans
    problème. Bug réel trouvé le 2026-09-29 : catalogue_pbr_complementaires
    (le plafond CAC) pouvait rester vide indéfiniment à cause d'un échec
    Neon précédent dans la même séquence, sans lien avec les données PBR
    elles-mêmes — le plafond d'assurance ne s'appliquait alors jamais, avec
    le risque financier que ça représente."""
    for nom, fonction in (
        ('numéros locaux', rafraichir_numeros_locaux),
        ('catalogue', rafraichir_catalogue),
        ('utilisateurs', rafraichir_utilisateurs),
        ('infos structure', rafraichir_structure_info),
        ('plafonds PBR complémentaires (CAC)', rafraichir_pbr_complementaires),
        ('patients existants', rafraichir_patients_existants),
    ):
        try:
            resultat = fonction()
            if nom == 'patients existants' and resultat:
                print(f"[offline] {resultat} patient(s) existant(s) mis en cache au démarrage.")
        except Exception as e:
            print(f"[offline] Rafraîchissement '{nom}' impossible au démarrage (réseau coupé ?) : {e}")


_rafraichir_au_demarrage()

# Une première sauvegarde dès le lancement (pas seulement au premier cycle du
# watchdog, ~15 min plus tard) — utile si l'appli est redémarrée juste avant
# une coupure prolongée.
try:
    from offline.backup import sauvegarder
    ok, erreur = sauvegarder()
    if erreur:
        print(f"[offline] {erreur}")
except Exception as e:
    print(f"[offline] Sauvegarde initiale impossible : {e}")

watchdog_offline.demarrer()


@app.route('/')
def accueil():
    if app_en_ligne_joignable():
        return redirect(ONLINE_APP_URL)
    if not utilisateur_connecte():
        return redirect('/login')
    return redirect('/accueil')


@app.route('/login', methods=['GET', 'POST'])
def login():
    erreur = None
    if request.method == 'POST':
        ok, resultat = tenter_connexion(
            (request.form.get('email') or '').strip(),
            request.form.get('mot_de_passe') or ''
        )
        if ok:
            return redirect('/accueil')
        erreur = resultat
    return render_template('offline_login.html', erreur=erreur)


@app.route('/logout')
def logout():
    deconnecter()
    return redirect('/login')


@app.route('/accueil')
def page_accueil():
    """Page d'accueil hors-ligne (patron, 2026-10-05) : comme dans le grand
    système, une porte d'entrée avec les grandes actions (patients, vente,
    historique) et l'état de la synchro — plus une barre de navigation
    identique sur toutes les pages (offline_base.html)."""
    if not utilisateur_connecte():
        return redirect('/login')
    conn = get_connection()
    compter = lambda table: conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()['n']  # noqa: E731
    return render_template(
        'offline_accueil.html',
        nom_utilisateur=nom_utilisateur(),
        page_active='accueil',
        nb_actes=compter('catalogue_actes'),
        nb_produits=compter('catalogue_produits'),
        nb_patients=compter('offline_patients'),
    )


@app.route('/patients')
def page_patients():
    if not utilisateur_connecte():
        return redirect('/login')
    return render_template('offline_patients.html', nom_utilisateur=nom_utilisateur(), page_active='patients')


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
        page_active='ventes',
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
        # ⭐ pbr : base de remboursement AMU (plafond) — voir
        # calculer_repartition_assurance(), services/hospitalisation_service.py.
        # Toujours présent (le catalogue en ligne retombe déjà sur le prix de
        # vente si la colonne PBR de la feuille Sheets est vide), jamais None.
        pbr = donnees.get('pbr') or prix
        items.append({
            'nom': ligne['nom'],
            'prix': prix,
            'pbr': pbr,
            'id': donnees.get('ID') or donnees.get('id'),
            'stock': donnees.get('quantite_stock'),
        })
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


@app.route('/api/offline/pbr-complementaires')
def pbr_complementaires():
    """Table des plafonds CAC par acte/produit pour la compagnie du
    patient — utilisée par le calcul d'assurance côté vente (offline_ventes.html)."""
    if not utilisateur_connecte():
        return jsonify({'success': False, 'error': 'Non connecté'}), 401
    compagnie = (request.args.get('compagnie') or '').strip()
    type_article = request.args.get('type', 'acte')
    if not compagnie:
        return jsonify({'success': True, 'items': {}})
    lignes = requeter(
        "SELECT nom_acte, pbr_1, pbr_2 FROM catalogue_pbr_complementaires WHERE type = ? AND compagnie = ?",
        (type_article, compagnie)
    )
    return jsonify({'success': True, 'items': {l['nom_acte']: {'pbr_1': l['pbr_1'], 'pbr_2': l['pbr_2']} for l in lignes}})


@app.route('/historique')
def historique():
    """Ventes ENREGISTRÉES DEPUIS CE POSTE aujourd'hui — pas l'historique
    complet de la structure (celui-ci vivrait sur Neon, injoignable la
    plupart du temps où cette page est utile). Permet de retrouver/
    réimprimer une vente sans avoir à retenir son lien juste après
    création."""
    if not utilisateur_connecte():
        return redirect('/login')

    import json as _json
    aujourdhui = datetime.now(timezone.utc).date().isoformat()
    ventes = requeter(
        """SELECT * FROM offline_ventes
           WHERE structure_id = ? AND date_vente >= ?
           ORDER BY date_vente DESC""",
        (OFFLINE_STRUCTURE_ID, aujourdhui)
    )
    lignes = []
    for v in ventes:
        v = dict(v)
        # ⭐ Colonne "Assuré" + part assurance — même esprit que l'historique
        # en ligne (historique_ventes.html) : le patron a demandé qu'on
        # voie ici aussi qui est assuré et ce que l'assurance a pris en
        # charge, pas seulement le net à payer. Ces champs existent déjà
        # dans offline_ventes (voir prise_en_charge/prise_en_charge2,
        # ajoutés aujourd'hui avec base_remboursement/reste_a_payer) —
        # juste jamais remontés jusqu'à cette page.
        prise_en_charge_totale = (v['prise_en_charge'] or 0) + (v['prise_en_charge2'] or 0)
        lignes.append({
            'uuid': v['uuid'],
            'numero_local': v['numero_local'],
            'patient_nom': v['patient_nom'],
            'type': v['type'],
            'net_a_payer': v['net_a_payer'],
            'date_vente': v['date_vente'],
            'synced': bool(v['neon_id']),
            'assurance_nom': v['assurances'] and _json.loads(v['assurances']).get('principale', {}).get('nom'),
            'assurance2_nom': v['assurance2_nom'],
            'prise_en_charge_totale': prise_en_charge_totale,
        })
    return render_template('offline_historique.html', ventes=lignes, nom_utilisateur=nom_utilisateur(), page_active='historique')


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

    assurances = _json.loads(vente.get('assurances') or '{}') or {}
    principale = assurances.get('principale') or {}
    vente['assurance_nom'] = principale.get('nom')

    # ⭐ FIX : repli à 'A4' au lieu de '80mm' — incohérent avec l'appli en
    # ligne (app.py), qui utilise toujours '80mm' par défaut quand le
    # format n'est pas précisé dans l'URL. Les boutons de offline_ventes.html/
    # offline_historique.html précisent déjà explicitement le format, donc
    # ça ne les touchait pas, mais tout lien ouvert sans paramètre (vieux
    # favori, lien partagé...) sortait en grand format par erreur.
    format_impression = request.args.get('format', '80mm')
    if format_impression not in ('A4', '80mm'):
        format_impression = '80mm'

    return render_template(
        'offline_recu.html',
        vente=vente,
        patient_nom=f"{dechiffrer(patient.get('nom')) or ''} {dechiffrer(patient.get('prenom')) or ''}".strip(),
        patient_numero_assure=patient.get('numero_assure'),
        structure=structure,
        articles=articles,
        deja_synchronise=bool(vente.get('neon_id')),
        format=format_impression,
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
