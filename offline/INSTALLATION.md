# Installation du pilote hors-ligne — Clinique pilote (structure 1)

Ce guide sert à installer l'application hors-ligne sur **le PC désigné chez
le client** (pas ce PC de développement). À suivre dans l'ordre.

## ⚠️ Point critique à ne pas sauter : PATIENT_ENCRYPTION_KEY

Les noms/prénoms/téléphones des patients sont chiffrés avec une clé
(`PATIENT_ENCRYPTION_KEY`). **Cette machine de développement ne l'a pas** —
elle n'existe que dans les variables d'environnement de Render (production).

**Il faut récupérer cette valeur EXACTE depuis Render** (Dashboard Render →
service GHP → Environment → `PATIENT_ENCRYPTION_KEY`) avant l'installation.

Si le PC client démarre avec une clé différente (ou absente) :
- Absente → les patients créés hors-ligne seraient enregistrés **en clair**
  dans Neon au moment de la synchro, au milieu de données par ailleurs
  chiffrées — incohérence de sécurité réelle.
- Différente → les données resteraient illisibles (déchiffrement impossible)
  une fois synchronisées.

**Ne jamais démarrer l'appli hors-ligne en production sans avoir vérifié
que cette clé est bien la même qu'en production.**

## Prérequis sur le PC client

- Windows (10/11).
- Python 3.11+ installé (télécharger depuis python.org si absent — cocher
  "Add python.exe to PATH" à l'installation).
- Une copie du dépôt `medilogic_ghp` (voir étape 1).
- Le fichier `credentials.json` (compte de service Google Sheets) —
  **idéalement un compte de service dédié à portée réduite**, pas celui de
  production, pour limiter l'exposition si ce PC est compromis. À défaut,
  copier celui de production.

## Étape 1 — Copier le projet

Sur le PC client, copier le dossier `medilogic_ghp` (via clé USB, ou un
`git clone` du dépôt si ce PC a un accès internet au moment de
l'installation) vers, par exemple, `C:\medilogic_ghp`.

**⚠️ Ne JAMAIS copier le dossier `venv`** s'il existe déjà sur la machine
source — un environnement virtuel Python contient des chemins absolus
propres à la machine où il a été créé (`venv\Scripts\pip.exe`,
`python.exe`... pointent en dur vers l'ancien chemin) : copié tel quel, il
plante avec une erreur du type *"Unable to create process..."* /
*"Fatal error in launcher"*. Il doit toujours être recréé sur place (étape
2 ci-dessous), jamais transporté.

## Étape 2 — Installer les dépendances

Ouvrir une invite de commandes dans `C:\medilogic_ghp` :

```bat
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

## Étape 3 — Fichier `credentials.json`

Copier le fichier `credentials.json` (compte de service Google) à la racine
de `C:\medilogic_ghp` (à côté de `app.py`).

## Étape 4 — Fichier `.env`

Créer `C:\medilogic_ghp\.env` avec ce contenu (remplacer les valeurs par
les vraies, récupérées depuis Render ou ce PC de développement) :

```
DATABASE_URL=<la même URL Neon que la production Render>
SPREADSHEET_ID=<le même identifiant de feuille Google Sheets>
PATIENT_ENCRYPTION_KEY=<EXACTEMENT la même clé que Render — voir avertissement ci-dessus>
OFFLINE_STRUCTURE_ID=1
ONLINE_APP_URL=https://medilogic-ghp.onrender.com
```

`OFFLINE_STRUCTURE_ID=1` : ce PC est dédié à la structure 1 (clinique
pilote) — jamais une autre structure sur ce même PC.

## Étape 5 — Tester manuellement avant d'automatiser

Toujours dans `C:\medilogic_ghp`, avec le venv activé :

```bat
python -m waitress --listen=127.0.0.1:5100 offline.app_offline:app
```

Ouvrir `http://127.0.0.1:5100/` dans un navigateur :
- Si internet fonctionne → redirection automatique vers
  `https://medilogic-ghp.onrender.com` (comportement normal, rien de
  visible ne change pour le personnel).
- Pour tester le mode hors-ligne sans couper vraiment le réseau : arrêter
  (Ctrl+C), relancer avec `set OFFLINE_FORCE=1` avant la commande —
  l'appli sert alors sa propre page de connexion locale. **Ne jamais
  laisser `OFFLINE_FORCE=1` en usage réel.**

Si tout fonctionne, fermer cette fenêtre (Ctrl+C) et passer à
l'automatisation.

## Étape 6 — Automatiser le démarrage

Deux méthodes, selon les droits disponibles sur le PC client.

### Avec droits administrateur (préférée)

Depuis une invite de commandes **en tant qu'administrateur**, dans
`C:\medilogic_ghp` :

```bat
offline\installer_tache_planifiee.bat
```

Ce script crée une tâche planifiée Windows ("MediLogicOffline") qui lance
`offline\lancer_offline.bat` à chaque connexion de l'utilisateur, et la
démarre immédiatement pour vérifier que ça fonctionne.

### Sans droits administrateur

Si le compte utilisateur du PC client n'a pas accès à "Exécuter en tant
qu'administrateur" (poste verrouillé), utiliser à la place, depuis une
invite de commandes normale, dans `C:\medilogic_ghp` :

```bat
offline\installer_sans_admin.bat
```

Aucune élévation nécessaire : ce script dépose un petit fichier dans le
dossier "Démarrage" personnel de l'utilisateur Windows
(`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`), que Windows
exécute automatiquement à chaque connexion — sans passer par le
Planificateur de tâches. Le script indique ensuite la commande à lancer
pour démarrer immédiatement sans attendre une reconnexion.

## Étape 7 — Basculer le personnel sur la nouvelle adresse

Remplacer le favori/raccourci habituel par `http://127.0.0.1:5100/` sur ce
poste. Le comportement est transparent : en ligne, ça redirige vers
l'appli normale ; hors-ligne, ça sert l'appli locale avec un bandeau
d'avertissement bien visible.

## Vérification finale

1. Redémarrer le PC — vérifier que `http://127.0.0.1:5100/` répond bien
   après le redémarrage (sans rien relancer à la main).
2. Simuler une coupure (débrancher le câble réseau ou couper le Wi-Fi) —
   vérifier que la page de connexion hors-ligne apparaît après quelques
   secondes, se connecter, créer un patient de test, une vente de test.
3. Rebrancher le réseau — attendre ~1 minute, vérifier dans les logs (ou
   `http://127.0.0.1:5100/api/offline/sync/status`) que la synchronisation
   s'est faite (`en_attente: 0`, `erreurs: 0`).
4. Vérifier côté Neon que le patient/la vente de test sont bien arrivés,
   puis les supprimer (données de test, pas de vrais patients).
