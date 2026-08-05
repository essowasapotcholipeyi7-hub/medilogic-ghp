# routes/rh.py - VERSION CORRIGÉE ET OPTIMISÉE
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from datetime import datetime, date, timedelta
from sqlalchemy import or_, and_, extract, func
import json
import traceback

from models import db, Employe, Service, Conge, Permission, DocumentRH, SignatureRH

rh_bp = Blueprint('rh', __name__, url_prefix='/rh')

# ============================================================
# CONSTANTES
# ============================================================
CONGES_ANNUELS = 30  # ⭐ Nombre de jours de congés par année

# ============================================================
# DÉCORATEURS
# ============================================================
def require_structure(f):
    """Décorateur pour vérifier la structure en session"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        structure_id = session.get('structure_id')
        if not structure_id:
            if request.method == 'GET':
                flash('Structure non trouvée. Veuillez vous reconnecter.', 'danger')
                return redirect(url_for('auth.login'))
            return jsonify({'error': 'Structure non trouvée'}), 400
        return f(*args, structure_id=structure_id, **kwargs)
    return decorated


def get_structure_id():
    """Récupère le structure_id de la session"""
    return session.get('structure_id')


def get_statut_label(statut):
    """Retourne le libellé d'un statut"""
    labels = {
        'en_attente': '⏳ En attente',
        'approuve': '✅ Approuvé',
        'refuse': '❌ Refusé',
        'termine': '✔️ Terminé'
    }
    return labels.get(statut, statut)


def calculer_solde_conges(employe_id, annee):
    """
    Calcule le solde de congés pour un employé et une année donnée
    ⭐ 30 jours par an
    """
    # Congés pris dans l'année
    conges_pris = db.session.query(func.sum(Conge.nombre_jours)).filter(
        Conge.employe_id == employe_id,
        extract('year', Conge.date_debut) == annee,
        Conge.statut.in_(['en_attente', 'approuve', 'termine'])
    ).scalar() or 0
    
    # Permissions prises dans l'année
    permissions_pris = db.session.query(func.sum(Permission.nombre_jours)).filter(
        Permission.employe_id == employe_id,
        extract('year', Permission.date_debut) == annee,
        Permission.statut.in_(['en_attente', 'approuve'])
    ).scalar() or 0
    
    total_pris = conges_pris + permissions_pris
    solde = CONGES_ANNUELS - total_pris  # ⭐ 30 jours - pris
    
    return {
        'solde': max(0, solde),
        'pris': total_pris,
        'conges_pris': conges_pris,
        'permissions_pris': permissions_pris,
        'total_annuel': CONGES_ANNUELS
    }


def verifier_solde_avec_anticipation(employe_id, jours_demandes, annee_demande):
    """
    Vérifie si le solde est suffisant, sinon propose les années futures
    ⭐ 30 jours par an
    """
    # Solde pour l'année demandée
    solde_actuel = calculer_solde_conges(employe_id, annee_demande)
    
    if jours_demandes <= solde_actuel['solde']:
        return {
            'disponible': True,
            'solde_actuel': solde_actuel['solde'],
            'annee': annee_demande,
            'message': f'Solde suffisant: {solde_actuel["solde"]} jours restants'
        }
    
    # ⭐ Si solde insuffisant, vérifier les années futures
    annees_proposees = []
    for an in range(annee_demande + 1, annee_demande + 6):
        solde_futur = calculer_solde_conges(employe_id, an)
        if solde_futur['solde'] > 0:
            annees_proposees.append({
                'annee': an,
                'solde': solde_futur['solde'],
                'disponible': solde_futur['solde'] >= jours_demandes
            })
    
    return {
        'disponible': False,
        'solde_actuel': solde_actuel['solde'],
        'annee': annee_demande,
        'jours_demandes': jours_demandes,
        'annees_proposees': annees_proposees,
        'message': f'Solde insuffisant: {solde_actuel["solde"]} jours restants en {annee_demande}'
    }


# ============================================================
# ROUTES PAGES
# ============================================================

@rh_bp.route('/')
@require_structure
def gestion_rh(structure_id):
    """Page principale de gestion RH"""
    return render_template('rh/gestion_rh.html')


@rh_bp.route('/employes')
@require_structure
def employes(structure_id):
    """Liste des employés"""
    return render_template('rh/employes.html')


@rh_bp.route('/conges')
@require_structure
def conges(structure_id):
    """Gestion des congés"""
    return render_template('rh/conges.html')


@rh_bp.route('/permissions')
@require_structure
def permissions(structure_id):
    """Gestion des permissions"""
    return render_template('rh/permissions.html')


@rh_bp.route('/services')
@require_structure
def services(structure_id):
    """Gestion des services"""
    return render_template('rh/services.html')


@rh_bp.route('/dashboard')
@require_structure
def dashboard_rh(structure_id):
    """Dashboard RH"""
    return render_template('rh/dashboard_rh.html')


# ============================================================
# API - EMPLOYÉS
# ============================================================

@rh_bp.route('/api/employes')
@require_structure
def api_employes(structure_id):
    """API: Liste des employés avec filtres"""
    search = request.args.get('search', '').strip()
    service_id = request.args.get('service_id', '').strip()
    statut = request.args.get('statut', '').strip()
    sexe = request.args.get('sexe', '').strip()
    
    query = Employe.query.filter_by(structure_id=structure_id)
    
    if search:
        query = query.filter(
            or_(
                Employe.nom.ilike(f'%{search}%'),
                Employe.prenom.ilike(f'%{search}%'),
                Employe.matricule.ilike(f'%{search}%'),
                Employe.email.ilike(f'%{search}%'),
                Employe.telephone.ilike(f'%{search}%')
            )
        )
    
    if service_id and service_id.isdigit():
        query = query.filter_by(service_id=int(service_id))
    
    if statut:
        query = query.filter_by(statut=statut)
    
    if sexe:
        query = query.filter_by(sexe=sexe)
    
    employes = query.all()
    annee_actuelle = datetime.now().year
    
    result = []
    for e in employes:
        # ⭐ Calcul du solde avec 30 jours
        solde_info = calculer_solde_conges(e.id, annee_actuelle)
        
        result.append({
            'id': e.id,
            'matricule': e.matricule,
            'nom': e.nom,
            'prenom': e.prenom,
            'sexe': e.sexe,
            'service': e.service.nom if e.service else '',
            'poste': e.poste,
            'statut': e.statut,
            'telephone': e.telephone,
            'email': e.email,
            'date_embauche': e.date_embauche.strftime('%d/%m/%Y') if e.date_embauche else '',
            'solde_conges': solde_info['solde'],
            'service_id': e.service_id,
            'age': e.calculer_age() if hasattr(e, 'calculer_age') else None,
            # ⭐ CORRECTION : utiliser la méthode calculer_anciennete()
            'anciennete': e.calculer_anciennete() if hasattr(e, 'calculer_anciennete') else 0
        })
    
    return jsonify(result)

@rh_bp.route('/api/employes/<int:id>')
@require_structure
def api_employe_detail(structure_id, id):
    """API: Détail d'un employé"""
    employe = Employe.query.filter_by(id=id, structure_id=structure_id).first()
    if not employe:
        return jsonify({'error': 'Employé non trouvé'}), 404
    
    annee_actuelle = datetime.now().year
    solde_info = calculer_solde_conges(employe.id, annee_actuelle)
    
    return jsonify({
        'id': employe.id,
        'matricule': employe.matricule,
        'nom': employe.nom,
        'prenom': employe.prenom,
        'sexe': employe.sexe,
        'date_naissance': employe.date_naissance.strftime('%d/%m/%Y') if employe.date_naissance else '',
        'age': employe.calculer_age() if hasattr(employe, 'calculer_age') else None,
        'nationalite': employe.nationalite,
        'quartier': employe.quartier,
        'telephone': employe.telephone,
        'email': employe.email,
        'service_id': employe.service_id,
        'service': employe.service.nom if employe.service else '',
        'poste': employe.poste,
        'numero_poste': employe.numero_poste,
        'date_embauche': employe.date_embauche.strftime('%d/%m/%Y') if employe.date_embauche else '',
        # ⭐ CORRECTION : utiliser la méthode calculer_anciennete()
        'anciennete': employe.calculer_anciennete() if hasattr(employe, 'calculer_anciennete') else 0,
        'type_contrat': employe.type_contrat,
        'salaire_base': float(employe.salaire_base) if employe.salaire_base else 0,
        'personne_a_prevenir': employe.personne_a_prevenir,
        'telephone_prevenir': employe.telephone_prevenir,
        'lien_parente': employe.lien_parente,
        'statut': employe.statut,
        'solde_conges': solde_info['solde'],
        'conges_pris': solde_info['conges_pris'],
        'permissions_pris': solde_info['permissions_pris'],
        'total_annuel': CONGES_ANNUELS,
        'photo_url': employe.photo_url
    })

@rh_bp.route('/employe/ajouter', methods=['POST'])
@require_structure
def employe_ajouter(structure_id):
    """Ajouter un employé"""
    try:
        data = request.json
        
        # Validation des champs obligatoires
        required_fields = ['nom', 'prenom', 'sexe', 'telephone', 'service_id', 'poste', 'date_embauche']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Le champ {field} est obligatoire'}), 400
        
        # Génération du matricule
        annee = datetime.now().year
        count = Employe.query.filter_by(structure_id=structure_id).count() + 1
        matricule = f"EMP-{annee}-{str(count).zfill(3)}"
        
        employe = Employe(
            structure_id=structure_id,
            matricule=matricule,
            nom=data.get('nom').strip(),
            prenom=data.get('prenom').strip(),
            sexe=data.get('sexe'),
            date_naissance=datetime.strptime(data.get('date_naissance'), '%Y-%m-%d').date() if data.get('date_naissance') else None,
            nationalite=data.get('nationalite', '').strip(),
            quartier=data.get('quartier', '').strip(),
            telephone=data.get('telephone').strip(),
            email=data.get('email', '').strip(),
            service_id=int(data.get('service_id')),
            poste=data.get('poste').strip(),
            numero_poste=data.get('numero_poste', '').strip(),
            date_embauche=datetime.strptime(data.get('date_embauche'), '%Y-%m-%d').date(),
            type_contrat=data.get('type_contrat', 'CDI'),
            salaire_base=data.get('salaire_base', 0),
            personne_a_prevenir=data.get('personne_a_prevenir', '').strip(),
            telephone_prevenir=data.get('telephone_prevenir', '').strip(),
            lien_parente=data.get('lien_parente', '').strip(),
            statut='Actif',
            conges_annuels=CONGES_ANNUELS  # ⭐ 30 jours
        )
        
        db.session.add(employe)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'id': employe.id,
            'matricule': matricule,
            'message': 'Employé ajouté avec succès'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur employe_ajouter: {e}")
        return jsonify({'error': str(e)}), 500


@rh_bp.route('/employe/<int:id>', methods=['PUT'])
@require_structure
def api_modifier_employe(structure_id, id):
    """Modifier un employé"""
    try:
        employe = Employe.query.filter_by(id=id, structure_id=structure_id).first()
        if not employe:
            return jsonify({'error': 'Employé non trouvé'}), 404
        
        data = request.json
        
        # Mise à jour des champs
        if 'nom' in data:
            employe.nom = data['nom'].strip()
        if 'prenom' in data:
            employe.prenom = data['prenom'].strip()
        if 'sexe' in data:
            employe.sexe = data['sexe']
        if 'date_naissance' in data and data['date_naissance']:
            employe.date_naissance = datetime.strptime(data['date_naissance'], '%Y-%m-%d').date()
        if 'nationalite' in data:
            employe.nationalite = data['nationalite'].strip()
        if 'quartier' in data:
            employe.quartier = data['quartier'].strip()
        if 'telephone' in data:
            employe.telephone = data['telephone'].strip()
        if 'email' in data:
            employe.email = data['email'].strip()
        if 'service_id' in data:
            employe.service_id = int(data['service_id'])
        if 'poste' in data:
            employe.poste = data['poste'].strip()
        if 'numero_poste' in data:
            employe.numero_poste = data['numero_poste'].strip()
        if 'date_embauche' in data and data['date_embauche']:
            employe.date_embauche = datetime.strptime(data['date_embauche'], '%Y-%m-%d').date()
        if 'type_contrat' in data:
            employe.type_contrat = data['type_contrat']
        if 'salaire_base' in data:
            employe.salaire_base = data['salaire_base']
        if 'personne_a_prevenir' in data:
            employe.personne_a_prevenir = data['personne_a_prevenir'].strip()
        if 'telephone_prevenir' in data:
            employe.telephone_prevenir = data['telephone_prevenir'].strip()
        if 'lien_parente' in data:
            employe.lien_parente = data['lien_parente'].strip()
        if 'statut' in data:
            employe.statut = data['statut']
        
        employe.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'id': employe.id,
            'message': 'Employé modifié avec succès'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur api_modifier_employe: {e}")
        return jsonify({'error': str(e)}), 500


@rh_bp.route('/employe/<int:id>', methods=['DELETE'])
@require_structure
def api_supprimer_employe(structure_id, id):
    """Supprimer un employé"""
    try:
        employe = Employe.query.filter_by(id=id, structure_id=structure_id).first()
        if not employe:
            return jsonify({'error': 'Employé non trouvé'}), 404
        
        # Vérifier les dépendances
        conges = Conge.query.filter_by(employe_id=id).count()
        permissions = Permission.query.filter_by(employe_id=id).count()
        
        if conges > 0 or permissions > 0:
            return jsonify({
                'error': f'Impossible de supprimer. {conges} congé(s) et {permissions} permission(s) existent.'
            }), 400
        
        db.session.delete(employe)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Employé supprimé avec succès'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur api_supprimer_employe: {e}")
        return jsonify({'error': str(e)}), 500


@rh_bp.route('/employe/<int:id>')
@require_structure
def employe_detail(structure_id, id):
    """Page de détail d'un employé"""
    employe = Employe.query.filter_by(id=id, structure_id=structure_id).first()
    if not employe:
        flash('Employé non trouvé', 'danger')
        return redirect(url_for('rh.employes'))
    
    # ⭐⭐ CALCULER SOLDE_INFO ⭐⭐
    annee_actuelle = datetime.now().year
    solde_info = calculer_solde_conges(employe.id, annee_actuelle)
    
    return render_template('rh/employe_detail.html', 
                         employe=employe,
                         solde_info=solde_info)  # ⭐ AJOUTER solde_info


@rh_bp.route('/employe/modifier/<int:id>')
@require_structure
def employe_modifier(structure_id, id):
    """Page de modification d'un employé"""
    employe = Employe.query.filter_by(id=id, structure_id=structure_id).first()
    if not employe:
        flash('Employé non trouvé', 'danger')
        return redirect(url_for('rh.employes'))
    
    services = Service.query.filter_by(structure_id=structure_id).all()
    return render_template('rh/employe_modifier.html', employe=employe, services=services)


# ============================================================
# API - CONGÉS
# ============================================================

@rh_bp.route('/api/conges')
@require_structure
def api_conges(structure_id):
    """API: Liste des congés avec filtres"""
    search = request.args.get('search', '').strip()
    statut = request.args.get('statut', '').strip()
    type_conge = request.args.get('type', '').strip()
    
    query = Conge.query.join(Employe).filter(Employe.structure_id == structure_id)
    
    if search:
        query = query.filter(
            or_(
                Employe.nom.ilike(f'%{search}%'),
                Employe.prenom.ilike(f'%{search}%'),
                Employe.matricule.ilike(f'%{search}%')
            )
        )
    if statut:
        query = query.filter(Conge.statut == statut)
    if type_conge:
        query = query.filter(Conge.type_conge == type_conge)
    
    conges = query.order_by(Conge.created_at.desc()).all()
    annee_actuelle = datetime.now().year
    
    result = []
    for c in conges:
        # ⭐ Calcul du solde avec 30 jours
        solde_info = calculer_solde_conges(c.employe_id, annee_actuelle)
        
        result.append({
            'id': c.id,
            'employe_id': c.employe_id,
            'employe_nom': f"{c.employe.nom} {c.employe.prenom}",
            'type_conge': c.type_conge,
            'date_debut': c.date_debut.strftime('%d/%m/%Y'),
            'date_fin': c.date_fin.strftime('%d/%m/%Y'),
            'date_reprise': c.date_reprise.strftime('%d/%m/%Y') if c.date_reprise else '',
            'nombre_jours': c.nombre_jours,
            'annee_utilisation': c.annee_utilisation or c.date_debut.year,
            'solde_restant': solde_info['solde'],
            'solde_epuise': solde_info['solde'] <= 0,
            'motif': c.motif,
            'statut': c.statut,
            'signataire': c.signataire,
            'created_at': c.created_at.strftime('%d/%m/%Y %H:%M')
        })
    
    return jsonify(result)


@rh_bp.route('/conge/demander', methods=['POST'])
@require_structure
def conge_demander(structure_id):
    """Demander un congé"""
    try:
        data = request.json
        print(f"📥 Demande de congé reçue: {data}")
        
        # ⭐ Validation du signataire
        signataire = data.get('signataire', '').strip()
        if not signataire:
            return jsonify({
                'success': False,
                'error': 'Le nom du signataire est obligatoire'
            }), 400
        
        # ⭐ Validation de l'employé
        employe_id = data.get('employe_id')
        if not employe_id:
            return jsonify({
                'success': False,
                'error': 'Veuillez sélectionner un employé'
            }), 400
        
        employe = Employe.query.filter_by(id=employe_id, structure_id=structure_id).first()
        if not employe:
            return jsonify({
                'success': False,
                'error': 'Employé non trouvé dans cette structure'
            }), 404
        
        # ⭐ Validation des dates
        date_debut_str = data.get('date_debut')
        date_fin_str = data.get('date_fin')
        
        if not date_debut_str or not date_fin_str:
            return jsonify({
                'success': False,
                'error': 'Les dates de début et de fin sont obligatoires'
            }), 400
        
        try:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Format de date invalide'
            }), 400
        
        if date_debut > date_fin:
            return jsonify({
                'success': False,
                'error': 'La date de fin doit être après la date de début'
            }), 400
        
        # ⭐ Calcul des jours
        jours_demandes = (date_fin - date_debut).days + 1
        type_conge = data.get('type_conge', 'annuel')
        motif = data.get('motif', '').strip()
        
        # ⭐ Vérification des doublons
        conges_existants = Conge.query.filter(
            Conge.employe_id == employe_id,
            Conge.statut.in_(['en_attente', 'approuve']),
            or_(
                and_(
                    Conge.date_debut <= date_fin,
                    Conge.date_fin >= date_debut
                )
            )
        ).all()
        
        if conges_existants:
            chevauchement = []
            for c in conges_existants:
                chevauchement.append(f"{c.date_debut.strftime('%d/%m/%Y')} -> {c.date_fin.strftime('%d/%m/%Y')} ({c.statut})")
            return jsonify({
                'success': False,
                'error': f"L'employé a déjà un congé sur cette période: {', '.join(chevauchement)}"
            }), 400
        
        # ⭐ Récupérer l'année choisie
        annee_choisie = data.get('annee_choisie')
        if annee_choisie:
            annee_choisie = int(annee_choisie)
        else:
            annee_choisie = date_debut.year
        
        print(f"📅 Année choisie: {annee_choisie}")
        
        # ⭐⭐ VÉRIFICATION DU SOLDE AVEC 30 JOURS ⭐⭐
        verification = verifier_solde_avec_anticipation(employe_id, jours_demandes, annee_choisie)
        
        if not verification['disponible']:
            return jsonify({
                'success': False,
                'error': f"Solde insuffisant pour {annee_choisie}",
                'solde_insuffisant': True,
                'solde_actuel': verification['solde_actuel'],
                'jours_demandes': verification['jours_demandes'],
                'annee_courante': verification['annee'],
                'annees_futures': verification['annees_proposees'],
                'message': verification['message']
            }), 400
        
        # ⭐ Créer le congé
        conge = Conge(
            structure_id=structure_id,
            employe_id=employe_id,
            type_conge=type_conge,
            date_debut=date_debut,
            date_fin=date_fin,
            motif=motif,
            signataire=signataire,
            annee_utilisation=annee_choisie,
            nombre_jours=jours_demandes,
            statut='en_attente'
        )
        
        # Calculer les jours ouvrés et la date de reprise
        conge.nombre_jours = conge.calculer_jours_ouvres()
        conge.date_reprise = conge.calculer_date_reprise()
        
        db.session.add(conge)
        db.session.commit()
        
        # ⭐ Calcul du nouveau solde
        nouveau_solde = verification['solde_actuel'] - jours_demandes
        
        print(f"✅ Congé créé pour {employe.nom} {employe.prenom} (ID: {conge.id})")
        
        return jsonify({
            'success': True,
            'id': conge.id,
            'message': 'Demande de congé soumise avec succès',
            'solde_restant': nouveau_solde,
            'annee_utilisation': annee_choisie
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur conge_demander: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@rh_bp.route('/conge/<int:id>/statut', methods=['PUT'])
@require_structure
def conge_changer_statut(structure_id, id):
    """Changer le statut d'un congé"""
    try:
        data = request.json
        nouveau_statut = data.get('statut')
        
        if nouveau_statut not in ['en_attente', 'approuve', 'refuse', 'termine']:
            return jsonify({'error': 'Statut invalide'}), 400
        
        conge = Conge.query.join(Employe).filter(
            Conge.id == id,
            Employe.structure_id == structure_id
        ).first()
        
        if not conge:
            return jsonify({'error': 'Congé non trouvé'}), 404
        
        conge.statut = nouveau_statut
        conge.approuve_par = session.get('user_name', 'System')
        conge.date_approbation = date.today()
        conge.commentaire = data.get('commentaire', '')
        
        # ⭐ Mettre à jour le statut de l'employé
        employe = conge.employe
        employe.mettre_a_jour_statut()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Statut du congé mis à jour en "{nouveau_statut}"',
            'employe_statut': employe.statut
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur conge_changer_statut: {e}")
        return jsonify({'error': str(e)}), 500


@rh_bp.route('/conge/<int:id>/autorisation')
@require_structure
def conge_autorisation(structure_id, id):
    """Page d'autorisation de congé"""
    conge = Conge.query.join(Employe).filter(
        Conge.id == id,
        Employe.structure_id == structure_id
    ).first()
    
    if not conge:
        flash('Congé non trouvé', 'danger')
        return redirect(url_for('rh.conges'))
    
    if conge.statut != 'approuve':
        flash('Seuls les congés approuvés peuvent être imprimés', 'warning')
        return redirect(url_for('rh.conges'))
    
    employe = conge.employe
    
    if not conge.signataire:
        flash('Aucun signataire défini pour ce congé', 'danger')
        return redirect(url_for('rh.conges'))
    
    # Génération du numéro d'ordre
    annee = datetime.now().year
    count = DocumentRH.query.filter(
        DocumentRH.type_document == 'conge',
        extract('year', DocumentRH.created_at) == annee
    ).count() + 1
    numero_ordre = f"{annee}/{str(count).zfill(3)}/CONGE"
    
    # Détermination des pronoms
    if employe.sexe == 'Feminin':
        titre = 'Madame'
        pronom = 'elle'
        autorisee = 'autorisee'
        interessee = 'interessee'
        reprise = 'Elle reprendra'
    else:
        titre = 'Monsieur'
        pronom = 'il'
        autorisee = 'autorise'
        interessee = 'interesse'
        reprise = 'Il reprendra'
    
    return render_template('rh/autorisation_conge.html',
        conge=conge,
        employe=employe,
        titre=titre,
        pronom=pronom,
        autorisee=autorisee,
        interessee=interessee,
        reprise=reprise,
        numero_ordre=numero_ordre,
        date_actuelle=datetime.now().strftime('%d/%m/%Y'),
        datetime=datetime,
        signataire=conge.signataire
    )


# ============================================================
# API - PERMISSIONS
# ============================================================

@rh_bp.route('/api/permissions')
@require_structure
def api_permissions(structure_id):
    """API: Liste des permissions avec filtres"""
    search = request.args.get('search', '').strip()
    statut = request.args.get('statut', '').strip()
    
    query = Permission.query.join(Employe).filter(Employe.structure_id == structure_id)
    
    if search:
        query = query.filter(
            or_(
                Employe.nom.ilike(f'%{search}%'),
                Employe.prenom.ilike(f'%{search}%'),
                Employe.matricule.ilike(f'%{search}%')
            )
        )
    if statut:
        query = query.filter(Permission.statut == statut)
    
    permissions = query.order_by(Permission.created_at.desc()).all()
    result = []
    
    for p in permissions:
        result.append({
            'id': p.id,
            'employe_id': p.employe_id,
            'employe_nom': f"{p.employe.nom} {p.employe.prenom}",
            'type_permission': p.type_permission,
            'date_permission': p.date_permission.strftime('%d/%m/%Y') if p.date_permission else '',
            'heure_debut': p.heure_debut.strftime('%H:%M') if p.heure_debut else '',
            'heure_fin': p.heure_fin.strftime('%H:%M') if p.heure_fin else '',
            'date_debut': p.date_debut.strftime('%d/%m/%Y') if p.date_debut else '',
            'date_fin': p.date_fin.strftime('%d/%m/%Y') if p.date_fin else '',
            'nombre_jours': p.nombre_jours or 1,
            'motif': p.motif,
            'statut': p.statut,
            'signataire': p.signataire
        })
    
    return jsonify(result)


@rh_bp.route('/permission/demander', methods=['POST'])
@require_structure
def permission_demander(structure_id):
    """Demander une permission"""
    try:
        data = request.json
        
        # ⭐ Validation du signataire
        signataire = data.get('signataire', '').strip()
        if not signataire:
            return jsonify({
                'success': False,
                'error': 'Le nom du signataire est obligatoire'
            }), 400
        
        # ⭐ Validation de l'employé
        employe_id = data.get('employe_id')
        if not employe_id:
            return jsonify({
                'success': False,
                'error': 'Veuillez sélectionner un employé'
            }), 400
        
        employe = Employe.query.filter_by(id=employe_id, structure_id=structure_id).first()
        if not employe:
            return jsonify({
                'success': False,
                'error': 'Employé non trouvé dans cette structure'
            }), 404
        
        type_permission = data.get('type_permission', 'heures')
        motif = data.get('motif', '').strip()
        
        if not motif:
            return jsonify({
                'success': False,
                'error': 'Le motif est obligatoire'
            }), 400
        
        # ⭐ Calcul des jours selon le type
        if type_permission == 'heures':
            date_permission = datetime.strptime(data.get('date_permission'), '%Y-%m-%d').date()
            date_debut = date_permission
            date_fin = date_permission
            nombre_jours = 0.5  # Demi-journée
        else:
            date_debut = datetime.strptime(data.get('date_debut'), '%Y-%m-%d').date()
            date_fin = datetime.strptime(data.get('date_fin'), '%Y-%m-%d').date()
            nombre_jours = (date_fin - date_debut).days + 1
        
        # ⭐ Vérification du solde avec 30 jours
        annee_courante = date_debut.year
        verification = verifier_solde_avec_anticipation(employe_id, nombre_jours, annee_courante)
        
        if not verification['disponible']:
            return jsonify({
                'success': False,
                'error': f'Solde de congés insuffisant pour {annee_courante}',
                'solde_insuffisant': True,
                'solde_actuel': verification['solde_actuel'],
                'jours_demandes': verification['jours_demandes'],
                'annee_courante': verification['annee'],
                'annees_futures': verification['annees_proposees'],
                'message': verification['message']
            }), 400
        
        # ⭐ Créer la permission
        permission = Permission(
            employe_id=employe_id,
            type_permission=type_permission,
            motif=motif,
            signataire=signataire,
            nombre_jours=nombre_jours,
            statut='en_attente'
        )
        
        if type_permission == 'heures':
            permission.date_permission = date_permission
            permission.heure_debut = datetime.strptime(data.get('heure_debut'), '%H:%M').time() if data.get('heure_debut') else None
            permission.heure_fin = datetime.strptime(data.get('heure_fin'), '%H:%M').time() if data.get('heure_fin') else None
            permission.date_debut = date_permission
            permission.date_fin = date_permission
        else:
            permission.date_debut = date_debut
            permission.date_fin = date_fin
        
        db.session.add(permission)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'id': permission.id,
            'message': 'Permission demandée avec succès',
            'solde_restant': verification['solde_actuel'] - nombre_jours
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur permission_demander: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@rh_bp.route('/permission/<int:id>/statut', methods=['PUT'])
@require_structure
def permission_changer_statut(structure_id, id):
    """Changer le statut d'une permission"""
    try:
        data = request.json
        nouveau_statut = data.get('statut')
        
        if nouveau_statut not in ['en_attente', 'approuve', 'refuse']:
            return jsonify({'error': 'Statut invalide'}), 400
        
        permission = Permission.query.join(Employe).filter(
            Permission.id == id,
            Employe.structure_id == structure_id
        ).first()
        
        if not permission:
            return jsonify({'error': 'Permission non trouvée'}), 404
        
        permission.statut = nouveau_statut
        permission.approuve_par = session.get('user_name', 'System')
        permission.date_approbation = date.today()
        permission.commentaire = data.get('commentaire', '')
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Statut de la permission mis à jour en "{nouveau_statut}"'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur permission_changer_statut: {e}")
        return jsonify({'error': str(e)}), 500


@rh_bp.route('/permission/<int:id>/autorisation')
@require_structure
def permission_autorisation(structure_id, id):
    """Page d'autorisation de permission"""
    permission = Permission.query.join(Employe).filter(
        Permission.id == id,
        Employe.structure_id == structure_id
    ).first()
    
    if not permission:
        flash('Permission non trouvée', 'danger')
        return redirect(url_for('rh.permissions'))
    
    if permission.statut != 'approuve':
        flash('Seules les permissions approuvées peuvent être imprimées', 'warning')
        return redirect(url_for('rh.permissions'))
    
    employe = permission.employe
    
    if not permission.signataire:
        flash('Aucun signataire défini pour cette permission', 'danger')
        return redirect(url_for('rh.permissions'))
    
    # Génération du numéro d'ordre
    annee = datetime.now().year
    count = DocumentRH.query.filter(
        DocumentRH.type_document == 'permission',
        extract('year', DocumentRH.created_at) == annee
    ).count() + 1
    numero_ordre = f"{annee}/{str(count).zfill(3)}/PERM"
    
    # Détermination du titre
    titre = 'Madame' if employe.sexe == 'Feminin' else 'Monsieur'
    autorisee = 'autorisee' if employe.sexe == 'Feminin' else 'autorise'
    
    return render_template('rh/autorisation_permission.html',
        permission=permission,
        employe=employe,
        titre=titre,
        autorisee=autorisee,
        numero_ordre=numero_ordre,
        date_actuelle=datetime.now().strftime('%d/%m/%Y'),
        datetime=datetime,
        signataire=permission.signataire
    )


# ============================================================
# API - SERVICES
# ============================================================

@rh_bp.route('/api/services')
@require_structure
def api_services(structure_id):
    """API: Liste des services"""
    services = Service.query.filter_by(structure_id=structure_id).order_by(Service.nom).all()
    result = []
    for s in services:
        result.append({
            'id': s.id,
            'nom': s.nom,
            'responsable': s.responsable,
            'nb_employes': Employe.query.filter_by(service_id=s.id, structure_id=structure_id).count()
        })
    return jsonify(result)


@rh_bp.route('/api/services', methods=['POST'])
@require_structure
def api_ajouter_service(structure_id):
    """Ajouter un service"""
    try:
        data = request.json
        nom = data.get('nom', '').strip()
        
        if not nom:
            return jsonify({'error': 'Le nom du service est obligatoire'}), 400
        
        service = Service(
            structure_id=structure_id,
            nom=nom,
            responsable=data.get('responsable', '').strip()
        )
        
        db.session.add(service)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'id': service.id,
            'message': 'Service ajouté avec succès'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur api_ajouter_service: {e}")
        return jsonify({'error': str(e)}), 500


@rh_bp.route('/api/services/<int:id>', methods=['PUT'])
@require_structure
def api_modifier_service(structure_id, id):
    """Modifier un service"""
    try:
        service = Service.query.filter_by(id=id, structure_id=structure_id).first()
        if not service:
            return jsonify({'error': 'Service non trouvé'}), 404
        
        data = request.json
        if 'nom' in data:
            service.nom = data['nom'].strip()
        if 'responsable' in data:
            service.responsable = data['responsable'].strip()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Service modifié avec succès'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur api_modifier_service: {e}")
        return jsonify({'error': str(e)}), 500


@rh_bp.route('/api/services/<int:id>', methods=['DELETE'])
@require_structure
def api_supprimer_service(structure_id, id):
    """Supprimer un service"""
    try:
        service = Service.query.filter_by(id=id, structure_id=structure_id).first()
        if not service:
            return jsonify({'error': 'Service non trouvé'}), 404
        
        # Vérifier si des employés y sont rattachés
        nb_employes = Employe.query.filter_by(service_id=id, structure_id=structure_id).count()
        if nb_employes > 0:
            return jsonify({
                'error': f'Ce service a {nb_employes} employé(s) rattaché(s). Impossible de le supprimer.'
            }), 400
        
        db.session.delete(service)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Service supprimé avec succès'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur api_supprimer_service: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================
# API - DASHBOARD
# ============================================================

@rh_bp.route('/api/dashboard/stats')
@require_structure
def api_dashboard_stats(structure_id):
    """API: Statistiques du dashboard"""
    try:
        # Mettre à jour les statuts
        employes = Employe.query.filter_by(structure_id=structure_id).all()
        for employe in employes:
            employe.mettre_a_jour_statut()
        db.session.commit()
        
        # Statistiques
        total_employes = len(employes)
        actifs = sum(1 for e in employes if e.statut == 'Actif')
        en_conge = sum(1 for e in employes if e.statut == 'En conge')
        inactifs = total_employes - actifs - en_conge
        
        # Demandes en attente
        demandes_attente = Conge.query.join(Employe).filter(
            Employe.structure_id == structure_id,
            Conge.statut == 'en_attente'
        ).count()
        
        demandes_attente += Permission.query.join(Employe).filter(
            Employe.structure_id == structure_id,
            Permission.statut == 'en_attente'
        ).count()
        
        # Congés en cours
        today = date.today()
        conges_en_cours = Conge.query.join(Employe).filter(
            Employe.structure_id == structure_id,
            Conge.statut == 'approuve',
            Conge.date_debut <= today,
            Conge.date_fin >= today
        ).count()
        
        return jsonify({
            'total_employes': total_employes,
            'actifs': actifs,
            'en_conge': en_conge,
            'inactifs': inactifs,
            'demandes_attente': demandes_attente,
            'conges_en_cours': conges_en_cours
        })
        
    except Exception as e:
        print(f"❌ Erreur api_dashboard_stats: {e}")
        return jsonify({'error': str(e)}), 500


@rh_bp.route('/api/update_all_status', methods=['POST'])
@require_structure
def update_all_status(structure_id):
    """Met à jour le statut de tous les employés"""
    try:
        employes = Employe.query.filter_by(structure_id=structure_id).all()
        stats = {
            'Actif': 0,
            'En conge': 0,
            'Inactif': 0
        }
        
        for employe in employes:
            nouveau_statut = employe.mettre_a_jour_statut()
            stats[nouveau_statut] = stats.get(nouveau_statut, 0) + 1
        
        return jsonify({
            'success': True,
            'message': f"{len(employes)} employé(s) mis à jour",
            'stats': stats
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur update_all_status: {e}")
        return jsonify({'error': str(e)}), 500


@rh_bp.route('/api/update_conge_status', methods=['POST'])
@require_structure
def update_conge_status(structure_id):
    """Met à jour le statut des employés en fonction des congés en cours"""
    try:
        today = date.today()
        employes = Employe.query.filter_by(structure_id=structure_id).all()
        count = 0
        
        for employe in employes:
            # Vérifier si l'employé a un congé approuvé en cours
            conge_en_cours = Conge.query.filter(
                Conge.employe_id == employe.id,
                Conge.statut == 'approuve',
                Conge.date_debut <= today,
                Conge.date_fin >= today
            ).first()
            
            if conge_en_cours:
                if employe.statut != 'En conge':
                    employe.statut = 'En conge'
                    count += 1
            else:
                # Vérifier si reprise après congé
                conge_termine = Conge.query.filter(
                    Conge.employe_id == employe.id,
                    Conge.statut == 'approuve',
                    Conge.date_fin < today
                ).order_by(Conge.date_fin.desc()).first()
                
                if conge_termine and conge_termine.date_reprise and conge_termine.date_reprise <= today:
                    if employe.statut != 'Actif':
                        employe.statut = 'Actif'
                        count += 1
                elif employe.statut == 'En conge':
                    employe.statut = 'Actif'
                    count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{count} employé(s) mis à jour',
            'total_employes': len(employes)
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur update_conge_status: {e}")
        return jsonify({'error': str(e)}), 500


@rh_bp.route('/api/employes/<int:id>/solde_conges')
@require_structure
def api_solde_conges(structure_id, id):
    """API: Solde de congés d'un employé"""
    employe = Employe.query.filter_by(id=id, structure_id=structure_id).first()
    if not employe:
        return jsonify({'error': 'Employé non trouvé'}), 404
    
    annee_actuelle = datetime.now().year
    solde_info = calculer_solde_conges(employe.id, annee_actuelle)
    
    return jsonify({
        'employe': f"{employe.nom} {employe.prenom}",
        'matricule': employe.matricule,
        'annee': annee_actuelle,
        'total_annuel': CONGES_ANNUELS,
        'conges_pris': solde_info['conges_pris'],
        'permissions_pris': solde_info['permissions_pris'],
        'total_pris': solde_info['pris'],
        'solde_restant': solde_info['solde']
    })


@rh_bp.route('/api/conges/stats/<int:employe_id>')
@require_structure
def api_conges_stats(structure_id, employe_id):
    """API: Statistiques des congés par année"""
    employe = Employe.query.filter_by(id=employe_id, structure_id=structure_id).first()
    if not employe:
        return jsonify({'error': 'Employé non trouvé'}), 404
    
    annee_actuelle = datetime.now().year
    stats = []
    
    for an in range(annee_actuelle - 2, annee_actuelle + 3):
        solde_info = calculer_solde_conges(employe_id, an)
        
        stats.append({
            'annee': an,
            'conges_pris': solde_info['conges_pris'],
            'permissions_pris': solde_info['permissions_pris'],
            'total_pris': solde_info['pris'],
            'solde_restant': solde_info['solde'],
            'est_epuise': solde_info['solde'] <= 0
        })
    
    return jsonify({
        'employe': f"{employe.nom} {employe.prenom}",
        'total_annuel': CONGES_ANNUELS,
        'stats': stats,
        'annee_courante': annee_actuelle
    })