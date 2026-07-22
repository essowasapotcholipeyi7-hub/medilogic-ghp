# routes/comptabilite.py
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from datetime import datetime, date
import json

from models import (
    db, CompteComptable, EcritureComptable, LigneEcriture, 
    Budget, ValidationComptable, HistoriqueEcriture
)

compta_bp = Blueprint('comptabilite', __name__, url_prefix='/comptabilite')


# ============================================================
# PAGE PRINCIPALE (avec sous-onglets)
# ============================================================

@compta_bp.route('/')
def index():
    """Page principale avec sous-onglets"""
    return render_template('comptabilite/index.html')


# ============================================================
# TABLEAU DE BORD COMPTABILITE
# ============================================================


@compta_bp.route('/api/dashboard/stats')
def api_dashboard_stats():
    structure_id = session.get('structure_id')
    
    total_ecritures = EcritureComptable.query.filter_by(structure_id=structure_id).count()
    en_attente = EcritureComptable.query.filter_by(structure_id=structure_id, statut='en_attente').count()
    validees = EcritureComptable.query.filter_by(structure_id=structure_id, statut='valide').count()
    
    total_debit = db.session.query(db.func.sum(LigneEcriture.debit)).filter(
        LigneEcriture.ecriture.has(EcritureComptable.structure_id == structure_id)
    ).scalar() or 0
    
    total_credit = db.session.query(db.func.sum(LigneEcriture.credit)).filter(
        LigneEcriture.ecriture.has(EcritureComptable.structure_id == structure_id)
    ).scalar() or 0
    
    return jsonify({
        'total_ecritures': total_ecritures,
        'en_attente': en_attente,
        'validees': validees,
        'total_debit': float(total_debit),
        'total_credit': float(total_credit),
        'solde': float(total_debit - total_credit)
    })


# ============================================================
# PLAN COMPTABLE
# ============================================================


@compta_bp.route('/api/comptes')
def api_comptes():
    structure_id = session.get('structure_id')
    
    search = request.args.get('search', '')
    type_filter = request.args.get('type', '')
    
    query = CompteComptable.query.filter_by(structure_id=structure_id, actif=True)
    
    if search:
        query = query.filter(
            db.or_(
                CompteComptable.numero.ilike(f'%{search}%'),
                CompteComptable.nom.ilike(f'%{search}%')
            )
        )
    if type_filter:
        query = query.filter_by(type=type_filter)
    
    comptes = query.order_by(CompteComptable.numero).all()
    
    result = []
    for c in comptes:
        result.append({
            'id': c.id,
            'numero': c.numero,
            'nom': c.nom,
            'type': c.type,
            'classe': c.classe,
            'niveau': c.niveau,
            'parent_id': c.parent_id,
            'solde': c.get_solde()
        })
    
    return jsonify(result)


@compta_bp.route('/api/comptes', methods=['POST'])
def api_ajouter_compte():
    try:
        data = request.json
        structure_id = session.get('structure_id')
        
        if not structure_id:
            return jsonify({'error': 'Structure non trouvee'}), 400
        
        # 🔥 Vérifier si le compte existe déjà
        existing = CompteComptable.query.filter_by(
            structure_id=structure_id,
            numero=data.get('numero')
        ).first()
        
        if existing:
            return jsonify({
                'success': False, 
                'error': f'Le compte {data.get("numero")} existe deja pour cette structure'
            }), 400
        
        compte = CompteComptable(
            structure_id=structure_id,
            numero=data.get('numero'),
            nom=data.get('nom'),
            type=data.get('type'),
            classe=data.get('classe') or '',
            parent_id=data.get('parent_id') or None,
            niveau=data.get('niveau', 1)
        )
        
        db.session.add(compte)
        db.session.commit()
        
        return jsonify({'success': True, 'id': compte.id})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================
# ECRITURES COMPTABLES
# ============================================================

@compta_bp.route('/api/ecritures')
def api_ecritures():
    structure_id = session.get('structure_id')
    
    search = request.args.get('search', '')
    statut_filter = request.args.get('statut', '')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    
    query = EcritureComptable.query.filter_by(structure_id=structure_id)
    
    if search:
        query = query.filter(
            db.or_(
                EcritureComptable.libelle.ilike(f'%{search}%'),
                EcritureComptable.piece_justificative.ilike(f'%{search}%'),
                EcritureComptable.created_by_nom.ilike(f'%{search}%')
            )
        )
    if statut_filter:
        query = query.filter_by(statut=statut_filter)
    if date_debut:
        query = query.filter(EcritureComptable.date_ecriture >= date_debut)
    if date_fin:
        query = query.filter(EcritureComptable.date_ecriture <= date_fin)
    
    ecritures = query.order_by(EcritureComptable.date_ecriture.desc()).all()
    
    result = []
    for e in ecritures:
        result.append({
            'id': e.id,
            'date_ecriture': e.date_ecriture.strftime('%d/%m/%Y'),
            'libelle': e.libelle,
            'piece_justificative': e.piece_justificative,
            'statut': e.statut,
            'statut_label': e.get_statut_label(),
            'total_debit': float(e.get_total_debit()),
            'total_credit': float(e.get_total_credit()),
            'est_equilibree': e.est_equilibree(),
            'created_by_nom': e.created_by_nom,
            'created_at': e.created_at.strftime('%d/%m/%Y %H:%M'),
            'lignes': [{
                'compte_numero': l.compte.numero,
                'compte_nom': l.compte.nom,
                'debit': float(l.debit),
                'credit': float(l.credit),
                'libelle': l.libelle
            } for l in e.lignes]
        })
    
    return jsonify(result)


@compta_bp.route('/api/ecritures', methods=['POST'])
def api_creer_ecriture():
    data = request.json
    structure_id = session.get('structure_id')
    user_name = session.get('user_name', 'System')
    
    # Verifier l'equilibre
    total_debit = sum(l.get('debit', 0) for l in data.get('lignes', []))
    total_credit = sum(l.get('credit', 0) for l in data.get('lignes', []))
    
    if total_debit != total_credit:
        return jsonify({'success': False, 'error': 'Les totaux debit et credit doivent etre egaux'}), 400
    
    ecriture = EcritureComptable(
        structure_id=structure_id,
        date_ecriture=datetime.strptime(data.get('date_ecriture'), '%Y-%m-%d').date(),
        libelle=data.get('libelle'),
        piece_justificative=data.get('piece_justificative'),
        statut='brouillon' if data.get('soumettre') != 'true' else 'en_attente',
        created_by=session.get('user_id'),
        created_by_nom=user_name,
        commentaire=data.get('commentaire')
    )
    
    db.session.add(ecriture)
    db.session.flush()
    
    for ligne_data in data.get('lignes', []):
        ligne = LigneEcriture(
            ecriture_id=ecriture.id,
            compte_id=ligne_data.get('compte_id'),
            debit=ligne_data.get('debit', 0),
            credit=ligne_data.get('credit', 0),
            libelle=ligne_data.get('libelle', '')
        )
        db.session.add(ligne)
    
    # Si soumise, creer une validation de niveau 1
    if data.get('soumettre') == 'true':
        validation = ValidationComptable(
            ecriture_id=ecriture.id,
            niveau=1,
            statut='en_attente'
        )
        db.session.add(validation)
    
    db.session.commit()
    
    return jsonify({'success': True, 'id': ecriture.id})


@compta_bp.route('/api/ecritures/<int:id>/valider', methods=['POST'])
def api_valider_ecriture(id):
    data = request.json
    structure_id = session.get('structure_id')
    user_name = session.get('user_name', 'System')
    
    ecriture = EcritureComptable.query.filter_by(id=id, structure_id=structure_id).first_or_404()
    
    niveau = data.get('niveau', 1)
    action = data.get('action', 'approuve')
    commentaire = data.get('commentaire', '')
    
    # Verifier la validation existante
    validation = ValidationComptable.query.filter_by(
        ecriture_id=id,
        niveau=niveau
    ).first()
    
    if not validation:
        validation = ValidationComptable(
            ecriture_id=id,
            niveau=niveau
        )
        db.session.add(validation)
    
    validation.statut = action
    validation.valide_par = session.get('user_id')
    validation.valide_par_nom = user_name
    validation.date_validation = date.today()
    validation.commentaire = commentaire
    
    # Mettre a jour le statut de l'ecriture
    if niveau == 1 and action == 'approuve':
        ecriture.statut = 'en_attente'
    elif niveau == 2 and action == 'approuve':
        ecriture.statut = 'valide'
        ecriture.validated_by = session.get('user_id')
        ecriture.validated_by_nom = user_name
        ecriture.date_validation = date.today()
    elif action == 'refuse':
        ecriture.statut = 'refuse'
    
    # Historique
    historique = HistoriqueEcriture(
        ecriture_id=id,
        action=f'validation_niveau_{niveau}',
        ancien_statut=validation.statut,
        nouveau_statut=action,
        modifie_par=session.get('user_id'),
        modifie_par_nom=user_name,
        commentaire=commentaire
    )
    db.session.add(historique)
    
    db.session.commit()
    
    return jsonify({'success': True})


# ============================================================
# BUDGET
# ============================================================


@compta_bp.route('/api/budget')
def api_budget():
    structure_id = session.get('structure_id')
    annee = request.args.get('annee', datetime.now().year)
    compte_id = request.args.get('compte_id')
    
    # 🔥 Récupérer tous les comptes de la structure
    query_comptes = CompteComptable.query.filter_by(
        structure_id=structure_id,
        actif=True
    )
    
    if compte_id:
        query_comptes = query_comptes.filter_by(id=compte_id)
    
    comptes = query_comptes.order_by(CompteComptable.numero).all()
    
    # Récupérer les budgets existants
    budgets = Budget.query.filter_by(
        structure_id=structure_id,
        annee=annee
    ).all()
    
    # Créer un dictionnaire des budgets par compte et mois
    budget_dict = {}
    for b in budgets:
        key = (b.compte_id, b.mois)
        budget_dict[key] = b
    
    result = []
    for compte in comptes:
        # Créer une ligne pour ce compte avec tous les mois
        item = {
            'compte_id': compte.id,
            'compte_numero': compte.numero,
            'compte_nom': compte.nom,
            'mois': None,
            'montant_prevu': 0,
            'montant_reel': 0,
            'ecart': 0,
            'commentaire': ''
        }
        
        # Vérifier si ce compte a des budgets
        a_un_budget = False
        for mois in range(1, 13):
            key = (compte.id, mois)
            if key in budget_dict:
                a_un_budget = True
                b = budget_dict[key]
                # Retourner le premier mois trouvé pour l'affichage
                if item['mois'] is None:
                    item['mois'] = mois
                    item['montant_prevu'] = float(b.montant_prevu)
                    item['montant_reel'] = float(b.montant_reel)
                    item['ecart'] = float(b.ecart)
                    item['commentaire'] = b.commentaire
        
        # Si le compte a des budgets, ajouter toutes les données mensuelles
        if a_un_budget:
            # Récupérer tous les mois pour ce compte
            mois_data = []
            for mois in range(1, 13):
                key = (compte.id, mois)
                if key in budget_dict:
                    b = budget_dict[key]
                    mois_data.append({
                        'mois': mois,
                        'montant_prevu': float(b.montant_prevu),
                        'montant_reel': float(b.montant_reel),
                        'ecart': float(b.ecart)
                    })
                else:
                    mois_data.append({
                        'mois': mois,
                        'montant_prevu': 0,
                        'montant_reel': 0,
                        'ecart': 0
                    })
            item['mois_data'] = mois_data
        
        result.append(item)
    
    return jsonify(result)


@compta_bp.route('/api/budget', methods=['POST'])
def api_sauvegarder_budget():
    data = request.json
    structure_id = session.get('structure_id')
    
    budget = Budget.query.filter_by(
        structure_id=structure_id,
        compte_id=data.get('compte_id'),
        annee=data.get('annee'),
        mois=data.get('mois')
    ).first()
    
    if budget:
        budget.montant_prevu = data.get('montant_prevu', 0)
        budget.commentaire = data.get('commentaire', '')
    else:
        budget = Budget(
            structure_id=structure_id,
            compte_id=data.get('compte_id'),
            annee=data.get('annee'),
            mois=data.get('mois'),
            montant_prevu=data.get('montant_prevu', 0),
            commentaire=data.get('commentaire', '')
        )
        db.session.add(budget)
    
    db.session.commit()
    
    return jsonify({'success': True})


# ============================================================
# RAPPORTS
# ============================================================


@compta_bp.route('/api/rapports/journal')
def api_journal():
    structure_id = session.get('structure_id')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    
    query = EcritureComptable.query.filter_by(
        structure_id=structure_id,
        statut='valide'
    )
    
    if date_debut:
        query = query.filter(EcritureComptable.date_ecriture >= date_debut)
    if date_fin:
        query = query.filter(EcritureComptable.date_ecriture <= date_fin)
    
    ecritures = query.order_by(EcritureComptable.date_ecriture).all()
    
    result = []
    for e in ecritures:
        for ligne in e.lignes:
            result.append({
                'date': e.date_ecriture.strftime('%d/%m/%Y'),
                'piece': e.piece_justificative or '',
                'libelle': e.libelle,
                'compte_numero': ligne.compte.numero,
                'compte_nom': ligne.compte.nom,
                'debit': float(ligne.debit),
                'credit': float(ligne.credit)
            })
    
    return jsonify(result)

@compta_bp.route('/api/ecritures/<int:id>')
def api_get_ecriture(id):
    """Recupere une ecriture pour modification ou visualisation"""
    try:
        structure_id = session.get('structure_id')
        
        if not structure_id:
            return jsonify({'error': 'Structure non trouvee'}), 400
        
        ecriture = EcritureComptable.query.filter_by(id=id, structure_id=structure_id).first()
        
        if not ecriture:
            return jsonify({'error': 'Ecriture non trouvee'}), 404
        
        result = {
            'id': ecriture.id,
            'date_ecriture': ecriture.date_ecriture.strftime('%Y-%m-%d'),
            'libelle': ecriture.libelle,
            'piece_justificative': ecriture.piece_justificative or '',
            'statut': ecriture.statut,
            'statut_label': ecriture.get_statut_label(),
            'commentaire': ecriture.commentaire or '',
            'created_by_nom': ecriture.created_by_nom or '',
            'created_at': ecriture.created_at.strftime('%d/%m/%Y %H:%M') if ecriture.created_at else '',
            'validated_by_nom': ecriture.validated_by_nom or '',
            'date_validation': ecriture.date_validation.strftime('%d/%m/%Y') if ecriture.date_validation else '',
            'total_debit': float(ecriture.get_total_debit()),
            'total_credit': float(ecriture.get_total_credit()),
            'est_equilibree': ecriture.est_equilibree(),
            'lignes': []
        }
        
        for ligne in ecriture.lignes:
            result['lignes'].append({
                'compte_id': ligne.compte_id,
                'compte_numero': ligne.compte.numero if ligne.compte else '',
                'compte_nom': ligne.compte.nom if ligne.compte else '',
                'debit': float(ligne.debit) if ligne.debit else 0,
                'credit': float(ligne.credit) if ligne.credit else 0,
                'libelle': ligne.libelle or ''
            })
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur api_get_ecriture: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@compta_bp.route('/api/ecritures/<int:id>', methods=['PUT'])
def api_modifier_ecriture(id):
    """Modifier une ecriture existante"""
    try:
        data = request.json
        structure_id = session.get('structure_id')
        user_name = session.get('user_name', 'System')
        
        ecriture = EcritureComptable.query.filter_by(id=id, structure_id=structure_id).first()
        
        if not ecriture:
            return jsonify({'error': 'Ecriture non trouvee'}), 404
        
        if ecriture.statut not in ['brouillon', 'refuse']:
            return jsonify({'error': 'Cette ecriture ne peut pas etre modifiee'}), 400
        
        # Verifier l'equilibre
        total_debit = sum(l.get('debit', 0) for l in data.get('lignes', []))
        total_credit = sum(l.get('credit', 0) for l in data.get('lignes', []))
        
        if total_debit != total_credit:
            return jsonify({'success': False, 'error': 'Les totaux debit et credit doivent etre egaux'}), 400
        
        # Mettre a jour les champs
        ecriture.date_ecriture = datetime.strptime(data.get('date_ecriture'), '%Y-%m-%d').date()
        ecriture.libelle = data.get('libelle')
        ecriture.piece_justificative = data.get('piece_justificative')
        ecriture.commentaire = data.get('commentaire')
        
        # Supprimer les anciennes lignes
        for ligne in ecriture.lignes:
            db.session.delete(ligne)
        
        # Ajouter les nouvelles lignes
        for ligne_data in data.get('lignes', []):
            ligne = LigneEcriture(
                ecriture_id=ecriture.id,
                compte_id=ligne_data.get('compte_id'),
                debit=ligne_data.get('debit', 0),
                credit=ligne_data.get('credit', 0),
                libelle=ligne_data.get('libelle', '')
            )
            db.session.add(ligne)
        
        # Si soumise, changer le statut
        if data.get('soumettre') == 'true':
            ecriture.statut = 'en_attente'
            # Creer une validation de niveau 1
            validation = ValidationComptable(
                ecriture_id=ecriture.id,
                niveau=1,
                statut='en_attente'
            )
            db.session.add(validation)
        
        db.session.commit()
        
        return jsonify({'success': True, 'id': ecriture.id})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur: {e}")
        return jsonify({'error': str(e)}), 500

@compta_bp.route('/api/rapports/grand_livre')
def api_grand_livre():
    """Grand livre : toutes les écritures par compte"""
    structure_id = session.get('structure_id')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    compte_id = request.args.get('compte_id')
    
    query = LigneEcriture.query.join(EcritureComptable).filter(
        EcritureComptable.structure_id == structure_id,
        EcritureComptable.statut == 'valide'
    )
    
    if date_debut:
        query = query.filter(EcritureComptable.date_ecriture >= date_debut)
    if date_fin:
        query = query.filter(EcritureComptable.date_ecriture <= date_fin)
    if compte_id:
        query = query.filter(LigneEcriture.compte_id == compte_id)
    
    lignes = query.order_by(LigneEcriture.compte_id, EcritureComptable.date_ecriture).all()
    
    result = []
    for ligne in lignes:
        result.append({
            'date': ligne.ecriture.date_ecriture.strftime('%d/%m/%Y'),
            'compte_numero': ligne.compte.numero,
            'compte_nom': ligne.compte.nom,
            'libelle': ligne.ecriture.libelle,
            'debit': float(ligne.debit),
            'credit': float(ligne.credit),
            'solde': 0  # A calculer par compte
        })
    
    return jsonify(result)

@compta_bp.route('/api/rapports/balance')
def api_balance():
    """Balance : recapitulatif par compte"""
    try:
        structure_id = session.get('structure_id')
        
        if not structure_id:
            return jsonify({'error': 'Structure non trouvee'}), 400
        
        date_debut = request.args.get('date_debut')
        date_fin = request.args.get('date_fin')
        
        # 🔥 Convertir les dates en objets date si elles existent
        date_debut_obj = None
        date_fin_obj = None
        
        if date_debut:
            date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
        if date_fin:
            date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()
        
        # Recuperer tous les comptes
        comptes = CompteComptable.query.filter_by(
            structure_id=structure_id,
            actif=True
        ).order_by(CompteComptable.numero).all()
        
        result = []
        for compte in comptes:
            total_debit = 0
            total_credit = 0
            
            for ligne in compte.lignes:
                # Verifier que l'ecriture est valide
                if ligne.ecriture.statut != 'valide':
                    continue
                
                # 🔥 Comparer avec des objets date
                if date_debut_obj and ligne.ecriture.date_ecriture < date_debut_obj:
                    continue
                if date_fin_obj and ligne.ecriture.date_ecriture > date_fin_obj:
                    continue
                
                total_debit += float(ligne.debit) if ligne.debit else 0
                total_credit += float(ligne.credit) if ligne.credit else 0
            
            solde = total_debit - total_credit
            
            if total_debit > 0 or total_credit > 0:
                result.append({
                    'compte_numero': compte.numero,
                    'compte_nom': compte.nom,
                    'total_debit': total_debit,
                    'total_credit': total_credit,
                    'solde': solde
                })
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur api_balance: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500