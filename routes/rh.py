# routes/rh.py
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from datetime import datetime, date, timedelta
import json

# 🔥 Importer db et les modèles depuis models.py
from models import db, Employe, Service, Conge, Permission, DocumentRH, SignatureRH

rh_bp = Blueprint('rh', __name__, url_prefix='/rh')

# ============================================================
# ROUTES
# ============================================================

@rh_bp.route('/')
def gestion_rh():
    return render_template('rh/gestion_rh.html')


@rh_bp.route('/employes')
def employes():
    return render_template('rh/employes.html')


@rh_bp.route('/api/employes')
def api_employes():
    search = request.args.get('search', '')
    service_id = request.args.get('service_id', '')
    statut = request.args.get('statut', '')
    sexe = request.args.get('sexe', '')
    
    query = Employe.query
    
    if search:
        query = query.filter(
            db.or_(
                Employe.nom.ilike(f'%{search}%'),
                Employe.prenom.ilike(f'%{search}%'),
                Employe.matricule.ilike(f'%{search}%')
            )
        )
    if service_id:
        query = query.filter_by(service_id=service_id)
    if statut:
        query = query.filter_by(statut=statut)
    if sexe:
        query = query.filter_by(sexe=sexe)
    
    employes = query.all()
    result = []
    for e in employes:
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
            'date_embauche': e.date_embauche.strftime('%d/%m/%Y') if e.date_embauche else '',
            'solde_conges': e.solde_conges(),
            'service_id': e.service_id
        })
    
    return jsonify(result)


@rh_bp.route('/api/employes/<int:id>')
def api_employe_detail(id):
    employe = Employe.query.get_or_404(id)
    return jsonify({
        'id': employe.id,
        'matricule': employe.matricule,
        'nom': employe.nom,
        'prenom': employe.prenom,
        'sexe': employe.sexe,
        'date_naissance': employe.date_naissance.strftime('%d/%m/%Y') if employe.date_naissance else '',
        'age': employe.calculer_age(),
        'nationalite': employe.nationalite,
        'quartier': employe.quartier,
        'telephone': employe.telephone,
        'email': employe.email,
        'service_id': employe.service_id,
        'service': employe.service.nom if employe.service else '',
        'poste': employe.poste,
        'numero_poste': employe.numero_poste,
        'date_embauche': employe.date_embauche.strftime('%d/%m/%Y') if employe.date_embauche else '',
        'anciennete': employe.calculer_anciennete(),
        'type_contrat': employe.type_contrat,
        'salaire_base': float(employe.salaire_base) if employe.salaire_base else 0,
        'personne_a_prevenir': employe.personne_a_prevenir,
        'telephone_prevenir': employe.telephone_prevenir,
        'lien_parente': employe.lien_parente,
        'statut': employe.statut,
        'solde_conges': employe.solde_conges(),
        'photo_url': employe.photo_url
    })


@rh_bp.route('/employe/ajouter', methods=['GET', 'POST'])
def employe_ajouter():
    if request.method == 'POST':
        data = request.json
        annee = datetime.now().year
        count = Employe.query.count() + 1
        matricule = f"EMP-{annee}-{str(count).zfill(3)}"
        
        employe = Employe(
            matricule=matricule,
            nom=data.get('nom'),
            prenom=data.get('prenom'),
            sexe=data.get('sexe'),
            date_naissance=datetime.strptime(data.get('date_naissance'), '%Y-%m-%d') if data.get('date_naissance') else None,
            nationalite=data.get('nationalite'),
            quartier=data.get('quartier'),
            telephone=data.get('telephone'),
            email=data.get('email'),
            service_id=data.get('service_id'),
            poste=data.get('poste'),
            numero_poste=data.get('numero_poste'),
            date_embauche=datetime.strptime(data.get('date_embauche'), '%Y-%m-%d') if data.get('date_embauche') else None,
            type_contrat=data.get('type_contrat'),
            salaire_base=data.get('salaire_base', 0),
            personne_a_prevenir=data.get('personne_a_prevenir'),
            telephone_prevenir=data.get('telephone_prevenir'),
            lien_parente=data.get('lien_parente'),
            statut='Actif'
        )
        
        db.session.add(employe)
        db.session.commit()
        
        return jsonify({'success': True, 'id': employe.id, 'matricule': matricule})
    
    services = Service.query.all()
    return render_template('rh/employe_form.html', services=services)


@rh_bp.route('/conges')
def conges():
    return render_template('rh/conges.html')


@rh_bp.route('/api/conges')
def api_conges():
    search = request.args.get('search', '')
    statut = request.args.get('statut', '')
    type_conge = request.args.get('type', '')
    
    query = Conge.query.join(Employe)
    
    if search:
        query = query.filter(
            db.or_(
                Employe.nom.ilike(f'%{search}%'),
                Employe.prenom.ilike(f'%{search}%'),
                Employe.matricule.ilike(f'%{search}%')
            )
        )
    if statut:
        query = query.filter_by(statut=statut)
    if type_conge:
        query = query.filter_by(type_conge=type_conge)
    
    conges = query.order_by(Conge.created_at.desc()).all()
    result = []
    
    annee_actuelle = datetime.now().year
    
    for c in conges:
        # 🔥 Récupérer le solde de l'employé pour l'année en cours
        conges_pris_annee = db.session.query(db.func.sum(Conge.nombre_jours)).filter(
            Conge.employe_id == c.employe_id,
            db.extract('year', Conge.date_debut) == annee_actuelle,
            Conge.statut.in_(['en_attente', 'approuve'])
        ).scalar() or 0
        
        solde_restant = max(0, 30 - conges_pris_annee)
        solde_epuise = solde_restant <= 0
        
        # 🔥 Afficher l'année d'utilisation
        annee_util = c.annee_utilisation or c.date_debut.year
        
        result.append({
            'id': c.id,
            'employe_id': c.employe_id,
            'employe_nom': f"{c.employe.nom} {c.employe.prenom}",
            'type_conge': c.type_conge,
            'date_debut': c.date_debut.strftime('%d/%m/%Y'),
            'date_fin': c.date_fin.strftime('%d/%m/%Y'),
            'date_reprise': c.date_reprise.strftime('%d/%m/%Y') if c.date_reprise else '',
            'nombre_jours': c.nombre_jours,
            'annee_utilisation': annee_util,  # 🔥 NOUVEAU
            'solde_restant': solde_restant,   # 🔥 NOUVEAU
            'solde_epuise': solde_epuise,     # 🔥 NOUVEAU
            'motif': c.motif,
            'statut': c.statut,
            'created_at': c.created_at.strftime('%d/%m/%Y %H:%M')
        })
    
    return jsonify(result)

@rh_bp.route('/conge/demander', methods=['POST'])
def conge_demander():
    data = request.json
    
    signataire = data.get('signataire', '').strip()
    if not signataire:
        return jsonify({'success': False, 'error': 'Le nom du signataire est obligatoire'}), 400
    
    employe_id = data.get('employe_id')
    if not employe_id:
        return jsonify({'success': False, 'error': 'Employe obligatoire'}), 400
    
    date_debut = datetime.strptime(data.get('date_debut'), '%Y-%m-%d').date()
    date_fin = datetime.strptime(data.get('date_fin'), '%Y-%m-%d').date()
    type_conge = data.get('type_conge', 'annuel')
    motif = data.get('motif', '')
    
    # 🔥 Récupérer l'année choisie
    annee_choisie = data.get('annee_choisie')
    if annee_choisie:
        annee_choisie = int(annee_choisie)
    else:
        annee_choisie = date_debut.year
    
    # 🔥 Vérifier que les dates sont valides
    if date_debut > date_fin:
        return jsonify({'success': False, 'error': 'La date de fin doit etre apres la date de debut'}), 400
    
    jours_demandes = (date_fin - date_debut).days + 1
    
    # ========== 1. VÉRIFICATION DES DOUBLONS ==========
    conges_existants = Conge.query.filter(
        Conge.employe_id == employe_id,
        Conge.statut.in_(['en_attente', 'approuve']),
        db.or_(
            db.and_(
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
            'error': f"L'employe a deja un conge sur cette periode: {', '.join(chevauchement)}"
        }), 400
    
    # ========== 2. VÉRIFICATION DU SOLDE ==========
    conges_pris_annee = db.session.query(db.func.sum(Conge.nombre_jours)).filter(
        Conge.employe_id == employe_id,
        db.extract('year', Conge.date_debut) == annee_choisie,
        Conge.statut.in_(['en_attente', 'approuve'])
    ).scalar() or 0
    
    solde_restant = 30 - conges_pris_annee
    
    print(f"📊 Année: {annee_choisie}, Congés déjà pris: {conges_pris_annee}, Solde restant: {solde_restant}")
    
    # ========== 3. SI SOLDE INSUFFISANT ==========
    if jours_demandes > solde_restant:
        # 🔥 Vérifier les années futures
        annee_actuelle = datetime.now().year
        annees_futures = []
        
        for an in range(annee_actuelle, annee_actuelle + 6):
            if an == annee_choisie:
                continue
            conges_pris_futur = db.session.query(db.func.sum(Conge.nombre_jours)).filter(
                Conge.employe_id == employe_id,
                db.extract('year', Conge.date_debut) == an,
                Conge.statut.in_(['en_attente', 'approuve'])
            ).scalar() or 0
            solde_futur = 30 - conges_pris_futur
            if solde_futur > 0:
                annees_futures.append({
                    'annee': an,
                    'solde': solde_futur,
                    'disponible': solde_futur >= jours_demandes
                })
        
        return jsonify({
            'success': False,
            'error': f"Solde insuffisant pour {annee_choisie}",
            'solde_insuffisant': True,
            'solde_actuel': solde_restant,
            'jours_demandes': jours_demandes,
            'annee_courante': annee_choisie,
            'annees_futures': annees_futures,
            'message': f"L'employe a deja pris {conges_pris_annee} jours en {annee_choisie}. Solde restant: {solde_restant} jours."
        }), 400
    
    # ========== 4. CRÉER LE CONGÉ ==========
    conge = Conge(
        employe_id=employe_id,
        type_conge=type_conge,
        date_debut=date_debut,
        date_fin=date_fin,
        motif=motif,
        signataire=signataire,
        annee_utilisation=annee_choisie
    )
    
    # 🔥 Calculer les jours ouvrés et la date de reprise
    conge.nombre_jours = conge.calculer_jours_ouvres()
    conge.date_reprise = conge.calculer_date_reprise()
    
    db.session.add(conge)
    db.session.commit()
    
    print(f"✅ Congé créé pour {employe_id}: {conge.nombre_jours} jours en {annee_choisie}")
    
    return jsonify({'success': True, 'id': conge.id})


@rh_bp.route('/conge/<int:id>/statut', methods=['PUT'])
def conge_changer_statut(id):
    data = request.json
    conge = Conge.query.get_or_404(id)
    
    conge.statut = data.get('statut')
    conge.approuve_par = session.get('user_name', 'System')
    conge.date_approbation = date.today()
    conge.commentaire = data.get('commentaire')
    
    db.session.commit()
    return jsonify({'success': True})


@rh_bp.route('/conge/<int:id>/autorisation')
def conge_autorisation(id):
    conge = Conge.query.get_or_404(id)
    employe = conge.employe
    
    if conge.statut != 'approuve':
        flash('Seuls les conges approuves peuvent etre imprimes', 'warning')
        return redirect(url_for('rh.conges'))
    
    # 🔥 Utiliser le signataire saisi (obligatoire)
    signataire = conge.signataire
    
    if not signataire:
        flash('Aucun signataire defini pour ce conge', 'danger')
        return redirect(url_for('rh.conges'))
    
    annee = datetime.now().year
    count = DocumentRH.query.filter(
        DocumentRH.type_document == 'conge',
        db.extract('year', DocumentRH.created_at) == annee
    ).count() + 1
    
    numero_ordre = f"{annee}/{str(count).zfill(3)}/CONGE"
    
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
        signataire=signataire
    )

@rh_bp.route('/api/employes/<int:id>/solde_conges')
def api_solde_conges(id):
    employe = Employe.query.get_or_404(id)
    solde = employe.solde_conges_restant()
    
    return jsonify({
        'employe': f"{employe.nom} {employe.prenom}",
        'annee': datetime.now().year,
        'conges_annuels': employe.conges_annuels,
        'conges_pris': employe.conges_pris_annee,
        'solde_restant': solde
    })

@rh_bp.route('/permissions')
def permissions():
    return render_template('rh/permissions.html')


@rh_bp.route('/api/permissions')
def api_permissions():
    search = request.args.get('search', '')
    statut = request.args.get('statut', '')
    
    query = Permission.query.join(Employe)
    
    if search:
        query = query.filter(
            db.or_(
                Employe.nom.ilike(f'%{search}%'),
                Employe.prenom.ilike(f'%{search}%'),
                Employe.matricule.ilike(f'%{search}%')
            )
        )
    if statut:
        query = query.filter_by(statut=statut)
    
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
            'statut': p.statut
        })
    
    return jsonify(result)


@rh_bp.route('/permission/demander', methods=['POST'])
def permission_demander():
    data = request.json
    
    signataire = data.get('signataire', '').strip()
    if not signataire:
        return jsonify({'success': False, 'error': 'Le nom du signataire est obligatoire'}), 400
    
    type_permission = data.get('type_permission', 'heures')
    motif = data.get('motif', '').strip()
    
    if not motif:
        return jsonify({'success': False, 'error': 'Le motif est obligatoire'}), 400
    
    permission = Permission(
        employe_id=data.get('employe_id'),
        type_permission=type_permission,
        motif=motif,
        signataire=signataire
    )
    
    if type_permission == 'heures':
        date_permission = data.get('date_permission')
        heure_debut = data.get('heure_debut')
        heure_fin = data.get('heure_fin')
        
        if not date_permission or not heure_debut or not heure_fin:
            return jsonify({'success': False, 'error': 'Date et heures obligatoires'}), 400
        
        permission.date_permission = datetime.strptime(date_permission, '%Y-%m-%d').date()
        permission.heure_debut = datetime.strptime(heure_debut, '%H:%M').time()
        permission.heure_fin = datetime.strptime(heure_fin, '%H:%M').time()
        permission.nombre_jours = 1
        
    else:
        date_debut = data.get('date_debut')
        date_fin = data.get('date_fin')
        
        if not date_debut or not date_fin:
            return jsonify({'success': False, 'error': 'Dates obligatoires'}), 400
        
        permission.date_debut = datetime.strptime(date_debut, '%Y-%m-%d').date()
        permission.date_fin = datetime.strptime(date_fin, '%Y-%m-%d').date()
        
        # 🔥 Calculer le nombre de jours
        delta = permission.date_fin - permission.date_debut
        permission.nombre_jours = delta.days + 1
    
    db.session.add(permission)
    db.session.commit()
    return jsonify({'success': True, 'id': permission.id})


@rh_bp.route('/permission/<int:id>/statut', methods=['PUT'])
def permission_changer_statut(id):
    data = request.json
    permission = Permission.query.get_or_404(id)
    
    permission.statut = data.get('statut')
    permission.approuve_par = session.get('user_name', 'System')
    permission.date_approbation = date.today()
    permission.commentaire = data.get('commentaire')
    
    db.session.commit()
    return jsonify({'success': True})


@rh_bp.route('/permission/<int:id>/autorisation')
def permission_autorisation(id):
    permission = Permission.query.get_or_404(id)
    employe = permission.employe
    
    if permission.statut != 'approuve':
        flash('Seules les permissions approuvees peuvent etre imprimees', 'warning')
        return redirect(url_for('rh.permissions'))
    
    # 🔥 Utiliser le signataire saisi
    signataire = permission.signataire
    
    if not signataire:
        flash('Aucun signataire defini pour cette permission', 'danger')
        return redirect(url_for('rh.permissions'))
    
    annee = datetime.now().year
    count = DocumentRH.query.filter(
        DocumentRH.type_document == 'permission',
        db.extract('year', DocumentRH.created_at) == annee
    ).count() + 1
    
    numero_ordre = f"{annee}/{str(count).zfill(3)}/PERM"
    
    if employe.sexe == 'Feminin':
        titre = 'Madame'
        autorisee = 'autorisee'
    else:
        titre = 'Monsieur'
        autorisee = 'autorise'
    
    return render_template('rh/autorisation_permission.html',
        permission=permission,
        employe=employe,
        titre=titre,
        autorisee=autorisee,
        numero_ordre=numero_ordre,
        date_actuelle=datetime.now().strftime('%d/%m/%Y'),
        datetime=datetime,
        signataire=signataire  # 🔥 AJOUT
    )



@rh_bp.route('/dashboard')
def dashboard_rh():
    return render_template('rh/dashboard_rh.html')


@rh_bp.route('/api/dashboard/stats')
def api_dashboard_stats():
    total_employes = Employe.query.count()
    actifs = Employe.query.filter_by(statut='Actif').count()
    en_conge = Employe.query.filter_by(statut='En conge').count()
    
    demandes_attente = Conge.query.filter_by(statut='en_attente').count()
    demandes_attente += Permission.query.filter_by(statut='en_attente').count()
    
    conges_en_cours = Conge.query.filter(
        Conge.date_debut <= date.today(),
        Conge.date_fin >= date.today(),
        Conge.statut == 'approuve'
    ).count()
    
    return jsonify({
        'total_employes': total_employes,
        'actifs': actifs,
        'en_conge': en_conge,
        'inactifs': total_employes - actifs - en_conge,
        'demandes_attente': demandes_attente,
        'conges_en_cours': conges_en_cours
    })


# ============================================================
# SERVICES
# ============================================================

@rh_bp.route('/services')
def services():
    return render_template('rh/services.html')


@rh_bp.route('/api/services')
def api_services():
    services = Service.query.order_by(Service.nom).all()
    result = []
    for s in services:
        result.append({
            'id': s.id,
            'nom': s.nom,
            'responsable': s.responsable,
            'nb_employes': len(s.employes) if s.employes else 0
        })
    return jsonify(result)


@rh_bp.route('/api/services', methods=['POST'])
def api_ajouter_service():
    data = request.json
    service = Service(
        nom=data.get('nom'),
        responsable=data.get('responsable')
    )
    db.session.add(service)
    db.session.commit()
    return jsonify({'success': True, 'id': service.id})


@rh_bp.route('/api/services/<int:id>', methods=['PUT'])
def api_modifier_service(id):
    data = request.json
    service = Service.query.get_or_404(id)
    service.nom = data.get('nom')
    service.responsable = data.get('responsable')
    db.session.commit()
    return jsonify({'success': True})


@rh_bp.route('/api/services/<int:id>', methods=['DELETE'])
def api_supprimer_service(id):
    service = Service.query.get_or_404(id)
    if service.employes and len(service.employes) > 0:
        return jsonify({'success': False, 'error': 'Ce service a des employes lies'}), 400
    db.session.delete(service)
    db.session.commit()
    return jsonify({'success': True})