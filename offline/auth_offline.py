# offline/auth_offline.py
"""Connexion locale — vérifie contre le cache offline_users_cache
(rafraîchi périodiquement pendant que le réseau est bon, voir
catalog_sync.rafraichir_utilisateurs). Jamais de mot de passe en clair
stocké ni comparé : hash_password() est la même fonction que l'appli
principale (app.py) utilise pour comparer côté Sheets, donc le hash mis en
cache est directement comparable."""

import hashlib
from flask import session

from offline.db_offline import requeter_une
from offline.config_offline import OFFLINE_STRUCTURE_ID


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def tenter_connexion(email, mot_de_passe):
    ligne = requeter_une(
        "SELECT * FROM offline_users_cache WHERE email = ? AND actif = 1",
        (email,)
    )
    if not ligne:
        return False, "Email non trouvé (ou pas encore mis en cache — reconnectez-vous une fois en ligne pour rafraîchir)."
    if ligne['mot_de_passe_hash'] != hash_password(mot_de_passe):
        return False, "Mot de passe incorrect."

    session['offline_user_email'] = email
    session['offline_user_nom'] = ligne['nom']
    session['offline_user_role'] = ligne['role']
    session['offline_structure_id'] = OFFLINE_STRUCTURE_ID
    return True, ligne['nom']


def utilisateur_connecte():
    return session.get('offline_user_email') is not None


def nom_utilisateur():
    return session.get('offline_user_nom') or 'Personnel'


def deconnecter():
    session.pop('offline_user_email', None)
    session.pop('offline_user_nom', None)
    session.pop('offline_user_role', None)
