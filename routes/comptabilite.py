# routes/comptabilite.py - Version complète
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from datetime import datetime, date, timedelta
import json
import re
from functools import lru_cache

from models import (
    db, CompteComptable, EcritureComptable, LigneEcriture,
    Budget, ValidationComptable, HistoriqueEcriture, ReleveBancaire,
    LigneReleve, Cloture, SequencePiece
)
from services.comptabilite_service import get_soldes_caisses

compta_bp = Blueprint('comptabilite', __name__, url_prefix='/comptabilite')


# ============================================================
# CACHE
# ============================================================
_compte_cache = {}
_compte_cache_time = {}
_rapport_cache = {}
_rapport_cache_time = {}
_rapport_special_cache = {}
_rapport_special_cache_time = {}


def invalidate_cache(structure_id):
    """Invalide le cache pour une structure"""
    global _compte_cache, _compte_cache_time, _rapport_cache, _rapport_cache_time
    global _rapport_special_cache, _rapport_special_cache_time
    
    keys_to_remove = []
    
    # Comptes
    for key in list(_compte_cache.keys()):
        if f"comptes_{structure_id}" in key:
            keys_to_remove.append(key)
    for key in keys_to_remove:
        if key in _compte_cache:
            del _compte_cache[key]
        if key in _compte_cache_time:
            del _compte_cache_time[key]
    
    # Rapports
    for key in list(_rapport_cache.keys()):
        if f"rapport_{structure_id}" in key:
            if key in _rapport_cache:
                del _rapport_cache[key]
            if key in _rapport_cache_time:
                del _rapport_cache_time[key]
    
    for key in list(_rapport_special_cache.keys()):
        if f"resultat_{structure_id}" in key or f"bilan_{structure_id}" in key:
            if key in _rapport_special_cache:
                del _rapport_special_cache[key]
            if key in _rapport_special_cache_time:
                del _rapport_special_cache_time[key]


# ============================================================
# FONCTION DE PARSING DES DATES
# ============================================================

def parse_date(date_str):
    if not date_str:
        return None
    
    date_str = str(date_str).strip()
    
    formats = [
        '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d',
        '%d %b %Y', '%d %B %Y', '%b %d %Y', '%B %d %Y',
        '%Y%m%d', '%d.%m.%Y', '%m/%d/%Y', '%d/%m/%y', '%d-%m-%y'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    
    # Format: DD/MM/YYYY ou DD-MM-YYYY
    match = re.match(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$', date_str)
    if match:
        day, month, year = match.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            pass
    
    # Format: YYYY/MM/DD ou YYYY-MM-DD
    match = re.match(r'^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$', date_str)
    if match:
        year, month, day = match.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            pass
    
    return None


# ============================================================
# PAGE PRINCIPALE
# ============================================================

@compta_bp.route('/')
def index():
    return render_template('comptabilite/index.html')


# ============================================================
# TABLEAU DE BORD
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
    
    comptes = CompteComptable.query.filter_by(
        structure_id=structure_id,
        actif=True
    ).order_by(CompteComptable.numero).all()
    
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
            'solde': float(c.get_solde()) if c.get_solde() else 0
        })
    
    if search:
        search_lower = search.lower()
        result = [c for c in result if search_lower in (c['numero'] + ' ' + c['nom']).lower()]
    if type_filter:
        result = [c for c in result if c['type'] == type_filter]
    
    return jsonify(result)


@compta_bp.route('/api/comptes', methods=['POST'])
def api_ajouter_compte():
    try:
        data = request.json
        structure_id = session.get('structure_id')
        
        if not structure_id:
            return jsonify({'error': 'Structure non trouvee'}), 400
        
        existing = CompteComptable.query.filter_by(
            structure_id=structure_id,
            numero=data.get('numero')
        ).first()
        
        if existing:
            return jsonify({
                'success': False, 
                'error': f'Le compte {data.get("numero")} existe deja'
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
        
        invalidate_cache(structure_id)
        
        return jsonify({'success': True, 'id': compte.id})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/comptes/<int:id>', methods=['PUT'])
def api_modifier_compte(id):
    try:
        data = request.json
        structure_id = session.get('structure_id')
        
        compte = CompteComptable.query.filter_by(id=id, structure_id=structure_id).first()
        if not compte:
            return jsonify({'error': 'Compte non trouve'}), 404
        
        compte.numero = data.get('numero')
        compte.nom = data.get('nom')
        compte.type = data.get('type')
        compte.classe = data.get('classe') or ''
        compte.parent_id = data.get('parent_id') or None
        compte.niveau = data.get('niveau', 1)
        compte.updated_at = datetime.utcnow()
        
        db.session.commit()
        invalidate_cache(structure_id)
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/comptes/<int:id>', methods=['DELETE'])
def api_supprimer_compte(id):
    try:
        structure_id = session.get('structure_id')
        
        compte = CompteComptable.query.filter_by(id=id, structure_id=structure_id).first()
        if not compte:
            return jsonify({'error': 'Compte non trouve'}), 404
        
        # Verifier si le compte a des enfants
        enfants = CompteComptable.query.filter_by(parent_id=id).count()
        if enfants > 0:
            return jsonify({'error': 'Ce compte a des sous-comptes'}), 400
        
        compte.actif = False
        db.session.commit()
        invalidate_cache(structure_id)
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================================
# SEQUENCES - NUMEROS DE PIECE
# ============================================================

@compta_bp.route('/api/sequence/next/<type_piece>', methods=['GET'])
def api_get_next_sequence(type_piece):
    """Récupère le prochain numéro de pièce sans l'incrémenter"""
    try:
        structure_id = session.get('structure_id')
        
        if not structure_id:
            return jsonify({'error': 'Structure non trouvee'}), 400
        
        info = SequencePiece.get_info(structure_id, type_piece)
        
        if not info:
            # Créer une séquence si elle n'existe pas
            prochain = SequencePiece.get_next_number(structure_id, type_piece)
            return jsonify({
                'success': True,
                'prochain_numero': prochain,
                'type_piece': type_piece,
                'est_nouvelle_sequence': True
            })
        
        return jsonify({
            'success': True,
            'prochain_numero': info['prochain_numero'],
            'type_piece': info['type_piece'],
            'prefixe': info['prefixe'],
            'annee': info['annee'],
            'numero_actuel': info['numero_actuel']
        })
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/sequence/reset/<type_piece>', methods=['POST'])
def api_reset_sequence(type_piece):
    """Réinitialise une séquence (admin seulement)"""
    try:
        structure_id = session.get('structure_id')
        
        if not structure_id:
            return jsonify({'error': 'Structure non trouvee'}), 400
        
        annee = request.json.get('annee', datetime.now().year)
        
        result = SequencePiece.reset_sequence(structure_id, type_piece, annee)
        
        return jsonify({
            'success': result,
            'message': 'Sequence reinitialisee' if result else 'Sequence non trouvee'
        })
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
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
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
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
        date_debut_obj = parse_date(date_debut)
        if date_debut_obj:
            query = query.filter(EcritureComptable.date_ecriture >= date_debut_obj)
    
    if date_fin:
        date_fin_obj = parse_date(date_fin)
        if date_fin_obj:
            query = query.filter(EcritureComptable.date_ecriture <= date_fin_obj)
    
    total = query.count()
    
    ecritures = query.order_by(
        EcritureComptable.date_ecriture.desc(),
        EcritureComptable.id.desc()
    ).offset((page-1)*per_page).limit(per_page).all()
    
    result = []
    for e in ecritures:
        lignes = []
        for l in e.lignes[:5]:
            lignes.append({
                'compte_numero': l.compte.numero if l.compte else '',
                'compte_nom': l.compte.nom if l.compte else '',
                'debit': float(l.debit),
                'credit': float(l.credit),
                'libelle': l.libelle
            })
        
        result.append({
            'id': e.id,
            'date_ecriture': e.date_ecriture.strftime('%Y-%m-%d') if e.date_ecriture else '',
            'libelle': e.libelle,
            'piece_justificative': e.piece_justificative,
            'statut': e.statut,
            'statut_label': e.get_statut_label(),
            'total_debit': float(e.get_total_debit()),
            'total_credit': float(e.get_total_credit()),
            'est_equilibree': e.est_equilibree(),
            'created_by_nom': e.created_by_nom,
            'created_at': e.created_at.strftime('%Y-%m-%d %H:%M') if e.created_at else '',
            'lignes': lignes,
            'nb_lignes': len(e.lignes)
        })
    
    return jsonify({
        'data': result,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })


@compta_bp.route('/api/ecritures', methods=['POST'])
def api_creer_ecriture():
    try:
        data = request.json
        structure_id = session.get('structure_id')
        user_name = session.get('user_name', 'System')
        
        if not structure_id:
            return jsonify({'success': False, 'error': 'Structure non trouvee'}), 400
        
        date_ecriture = parse_date(data.get('date_ecriture'))
        if not date_ecriture:
            return jsonify({'success': False, 'error': 'Format de date invalide'}), 400
        
        total_debit = sum(l.get('debit', 0) for l in data.get('lignes', []))
        total_credit = sum(l.get('credit', 0) for l in data.get('lignes', []))
        
        if total_debit != total_credit:
            return jsonify({'success': False, 'error': 'Les totaux debit et credit doivent etre egaux'}), 400
        
        # Generer le numero de piece automatiquement
        numero_piece = SequencePiece.get_next_number(structure_id, 'ecriture')
        
        ecriture = EcritureComptable(
            structure_id=structure_id,
            date_ecriture=date_ecriture,
            libelle=data.get('libelle'),
            piece_justificative=numero_piece,
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
        
        if data.get('soumettre') == 'true':
            validation = ValidationComptable(
                ecriture_id=ecriture.id,
                niveau=1,
                statut='en_attente'
            )
            db.session.add(validation)
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'id': ecriture.id,
            'numero_piece': numero_piece
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@compta_bp.route('/api/ecritures/<int:id>', methods=['GET'])
def api_get_ecriture(id):
    try:
        structure_id = session.get('structure_id')
        
        ecriture = EcritureComptable.query.filter_by(id=id, structure_id=structure_id).first()
        
        if not ecriture:
            return jsonify({'error': 'Ecriture non trouvee'}), 404
        
        result = {
            'id': ecriture.id,
            'date_ecriture': ecriture.date_ecriture.strftime('%Y-%m-%d') if ecriture.date_ecriture else '',
            'libelle': ecriture.libelle,
            'piece_justificative': ecriture.piece_justificative or '',
            'statut': ecriture.statut,
            'statut_label': ecriture.get_statut_label(),
            'commentaire': ecriture.commentaire or '',
            'created_by_nom': ecriture.created_by_nom or '',
            'created_at': ecriture.created_at.strftime('%Y-%m-%d %H:%M') if ecriture.created_at else '',
            'validated_by_nom': ecriture.validated_by_nom or '',
            'date_validation': ecriture.date_validation.strftime('%Y-%m-%d') if ecriture.date_validation else '',
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
        print(f"❌ Erreur: {e}")
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/ecritures/<int:id>', methods=['PUT'])
def api_modifier_ecriture(id):
    try:
        data = request.json
        structure_id = session.get('structure_id')
        user_name = session.get('user_name', 'System')
        
        ecriture = EcritureComptable.query.filter_by(id=id, structure_id=structure_id).first()
        
        if not ecriture:
            return jsonify({'error': 'Ecriture non trouvee'}), 404
        
        if ecriture.statut not in ['brouillon', 'refuse']:
            return jsonify({'error': 'Cette ecriture ne peut pas etre modifiee'}), 400
        
        date_ecriture = parse_date(data.get('date_ecriture'))
        if not date_ecriture:
            return jsonify({'success': False, 'error': 'Format de date invalide'}), 400
        
        total_debit = sum(l.get('debit', 0) for l in data.get('lignes', []))
        total_credit = sum(l.get('credit', 0) for l in data.get('lignes', []))
        
        if total_debit != total_credit:
            return jsonify({'success': False, 'error': 'Les totaux debit et credit doivent etre egaux'}), 400
        
        ecriture.date_ecriture = date_ecriture
        ecriture.libelle = data.get('libelle')
        ecriture.commentaire = data.get('commentaire')
        # Ne pas modifier le numero de piece
        
        for ligne in ecriture.lignes:
            db.session.delete(ligne)
        
        for ligne_data in data.get('lignes', []):
            ligne = LigneEcriture(
                ecriture_id=ecriture.id,
                compte_id=ligne_data.get('compte_id'),
                debit=ligne_data.get('debit', 0),
                credit=ligne_data.get('credit', 0),
                libelle=ligne_data.get('libelle', '')
            )
            db.session.add(ligne)
        
        if data.get('soumettre') == 'true':
            ecriture.statut = 'en_attente'
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


@compta_bp.route('/api/ecritures/<int:id>/valider', methods=['POST'])
def api_valider_ecriture(id):
    data = request.json
    structure_id = session.get('structure_id')
    user_name = session.get('user_name', 'System')
    
    ecriture = EcritureComptable.query.filter_by(id=id, structure_id=structure_id).first_or_404()
    
    niveau = data.get('niveau', 1)
    action = data.get('action', 'approuve')
    commentaire = data.get('commentaire', '')
    
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
    
    if niveau == 1 and action == 'approuve':
        ecriture.statut = 'en_attente'
    elif niveau == 2 and action == 'approuve':
        ecriture.statut = 'valide'
        ecriture.validated_by = session.get('user_id')
        ecriture.validated_by_nom = user_name
        ecriture.date_validation = date.today()
    elif action == 'refuse':
        ecriture.statut = 'refuse'
    
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
    
    query_comptes = CompteComptable.query.filter_by(
        structure_id=structure_id,
        actif=True
    )
    
    if compte_id:
        query_comptes = query_comptes.filter_by(id=compte_id)
    
    comptes = query_comptes.order_by(CompteComptable.numero).all()
    
    budgets = Budget.query.filter_by(
        structure_id=structure_id,
        annee=annee
    ).all()
    
    budget_dict = {}
    for b in budgets:
        key = (b.compte_id, b.mois)
        budget_dict[key] = b
    
    result = []
    for compte in comptes:
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
        
        a_un_budget = False
        for mois in range(1, 13):
            key = (compte.id, mois)
            if key in budget_dict:
                a_un_budget = True
                b = budget_dict[key]
                if item['mois'] is None:
                    item['mois'] = mois
                    item['montant_prevu'] = float(b.montant_prevu)
                    item['montant_reel'] = float(b.montant_reel)
                    item['ecart'] = float(b.ecart)
                    item['commentaire'] = b.commentaire
        
        if a_un_budget:
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
        budget.updated_at = datetime.utcnow()
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


@compta_bp.route('/api/exercice/statut')
def api_exercice_statut():
    """⭐ NOUVEAU : statut de l'exercice comptable en cours — onglet
    "Exercice comptable" (SYSCOHADA : l'exercice comptable coïncide avec
    l'année civile, sauf dérogation)."""
    structure_id = session.get('structure_id')
    annee_courante = datetime.now().year

    clotures = Cloture.query.filter_by(structure_id=structure_id).order_by(Cloture.annee.desc()).all()
    annees_cloturees = {c.annee for c in clotures}

    nb_ecritures_annee = EcritureComptable.query.filter(
        EcritureComptable.structure_id == structure_id,
        EcritureComptable.date_ecriture >= f"{annee_courante}-01-01",
        EcritureComptable.date_ecriture <= f"{annee_courante}-12-31",
    ).count()

    nb_brouillons = EcritureComptable.query.filter(
        EcritureComptable.structure_id == structure_id,
        EcritureComptable.statut.in_(['brouillon', 'en_attente']),
    ).count()

    return jsonify({
        'annee_courante': annee_courante,
        'exercice_ouvert': annee_courante not in annees_cloturees,
        'nb_ecritures_exercice_courant': nb_ecritures_annee,
        'nb_ecritures_a_valider': nb_brouillons,
        'clotures': [{
            'annee': c.annee,
            'date_cloture': c.date_cloture.strftime('%Y-%m-%d %H:%M') if c.date_cloture else '',
            'created_by': c.created_by or '-',
        } for c in clotures],
    })


@compta_bp.route('/api/cloture', methods=['POST'])
def api_cloture():
    structure_id = session.get('structure_id')
    annee = request.json.get('annee')
    
    if not annee:
        return jsonify({'error': 'Annee requise'}), 400
    
    try:
        existing = Cloture.query.filter_by(
            structure_id=structure_id,
            annee=annee
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'Cette annee est deja cloturee'}), 400
        
        date_debut = f"{annee}-01-01"
        date_fin = f"{annee}-12-31"
        
        ecritures = EcritureComptable.query.filter(
            EcritureComptable.structure_id == structure_id,
            EcritureComptable.date_ecriture >= date_debut,
            EcritureComptable.date_ecriture <= date_fin,
            EcritureComptable.statut == 'valide'
        ).all()
        
        nb_ecritures = 0
        for ecriture in ecritures:
            ecriture.cloturee = True
            ecriture.date_cloture = datetime.utcnow()
            nb_ecritures += 1
        
        cloture = Cloture(
            structure_id=structure_id,
            annee=annee,
            date_cloture=datetime.utcnow(),
            created_by=session.get('user_name', 'System')
        )
        db.session.add(cloture)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Cloture de l\'annee {annee} effectuee ({nb_ecritures} ecritures)'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================================
# RAPPORTS
# ============================================================

@compta_bp.route('/api/rapports/journal')
def api_journal():
    structure_id = session.get('structure_id')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    journal_code = request.args.get('journal_code')  # VTE / CAI / BQ / ACH / OD / None = tous

    return jsonify(generer_journal(structure_id, date_debut, date_fin, journal_code))


@compta_bp.route('/api/rapports/journaux/liste')
def api_liste_journaux():
    """Liste des journaux auxiliaires disponibles (pour le sélecteur)."""
    return jsonify([{'code': code, 'nom': nom} for code, nom in EcritureComptable.JOURNAUX.items()])


@compta_bp.route('/api/rapports/grand_livre')
def api_grand_livre():
    structure_id = session.get('structure_id')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    compte_id = request.args.get('compte_id', type=int)  # vue "grand livre d'un seul compte"

    return jsonify(generer_grand_livre(structure_id, date_debut, date_fin, compte_id))


@compta_bp.route('/api/caisses')
def api_caisses():
    """Les deux caisses bien visibles : Trésorerie (disponible réel) et
    Chiffre d'affaires (total des ventes de la période)."""
    structure_id = session.get('structure_id')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')

    date_debut_obj = parse_date(date_debut) if date_debut else None
    date_fin_obj = parse_date(date_fin) if date_fin else None

    return jsonify(get_soldes_caisses(structure_id, date_debut_obj, date_fin_obj))


@compta_bp.route('/api/rapports/balance')
def api_balance():
    structure_id = session.get('structure_id')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    
    return jsonify(generer_balance(structure_id, date_debut, date_fin))


@compta_bp.route('/api/rapports/resultat')
def api_rapport_resultat():
    structure_id = session.get('structure_id')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    
    return jsonify(get_compte_resultat(structure_id, date_debut, date_fin))


@compta_bp.route('/api/rapports/bilan')
def api_rapport_bilan():
    structure_id = session.get('structure_id')
    date_fin = request.args.get('date_fin')
    
    return jsonify(get_bilan(structure_id, date_fin))


def generer_journal(structure_id, date_debut, date_fin, journal_code=None):
    from sqlalchemy import text

    date_debut_obj = parse_date(date_debut) if date_debut else None
    date_fin_obj = parse_date(date_fin) if date_fin else None

    result = db.session.execute(text("""
        SELECT
            e.date_ecriture,
            e.piece_justificative,
            e.libelle,
            e.journal_code,
            e.generee_auto,
            c.numero as compte_numero,
            c.nom as compte_nom,
            l.debit,
            l.credit
        FROM ecritures_comptables e
        JOIN lignes_ecritures l ON e.id = l.ecriture_id
        JOIN comptes_comptables c ON l.compte_id = c.id
        WHERE e.structure_id = :structure_id
        AND e.statut = 'valide'
        AND (:date_debut IS NULL OR e.date_ecriture >= :date_debut)
        AND (:date_fin IS NULL OR e.date_ecriture <= :date_fin)
        AND (:journal_code IS NULL OR e.journal_code = :journal_code)
        ORDER BY e.date_ecriture
    """), {
        'structure_id': structure_id,
        'date_debut': date_debut_obj.strftime('%Y-%m-%d') if date_debut_obj else None,
        'date_fin': date_fin_obj.strftime('%Y-%m-%d') if date_fin_obj else None,
        'journal_code': journal_code or None,
    })

    rows = result.fetchall()

    return [{
        'date': row.date_ecriture.strftime('%Y-%m-%d') if row.date_ecriture else '',
        'piece': row.piece_justificative or '',
        'libelle': row.libelle or '',
        'journal_code': row.journal_code or '',
        'generee_auto': bool(row.generee_auto),
        'compte_numero': row.compte_numero or '',
        'compte_nom': row.compte_nom or '',
        'debit': float(row.debit or 0),
        'credit': float(row.credit or 0)
    } for row in rows]


def generer_grand_livre(structure_id, date_debut, date_fin, compte_id=None):
    from sqlalchemy import text

    date_debut_obj = parse_date(date_debut) if date_debut else None
    date_fin_obj = parse_date(date_fin) if date_fin else None

    result = db.session.execute(text("""
        SELECT
            e.date_ecriture,
            c.numero as compte_numero,
            c.nom as compte_nom,
            e.libelle,
            e.piece_justificative,
            l.debit,
            l.credit
        FROM ecritures_comptables e
        JOIN lignes_ecritures l ON e.id = l.ecriture_id
        JOIN comptes_comptables c ON l.compte_id = c.id
        WHERE e.structure_id = :structure_id
        AND e.statut = 'valide'
        AND (:date_debut IS NULL OR e.date_ecriture >= :date_debut)
        AND (:date_fin IS NULL OR e.date_ecriture <= :date_fin)
        AND (:compte_id IS NULL OR l.compte_id = :compte_id)
        ORDER BY c.numero, e.date_ecriture
    """), {
        'structure_id': structure_id,
        'date_debut': date_debut_obj.strftime('%Y-%m-%d') if date_debut_obj else None,
        'date_fin': date_fin_obj.strftime('%Y-%m-%d') if date_fin_obj else None,
        'compte_id': compte_id,
    })

    rows = result.fetchall()

    return [{
        'date': row.date_ecriture.strftime('%Y-%m-%d') if row.date_ecriture else '',
        'compte_numero': row.compte_numero or '',
        'compte_nom': row.compte_nom or '',
        'libelle': row.libelle or '',
        'piece': row.piece_justificative or '',
        'debit': float(row.debit or 0),
        'credit': float(row.credit or 0)
    } for row in rows]


def generer_balance(structure_id, date_debut, date_fin):
    date_debut_obj = parse_date(date_debut) if date_debut else None
    date_fin_obj = parse_date(date_fin) if date_fin else None
    
    comptes = CompteComptable.query.filter_by(
        structure_id=structure_id,
        actif=True
    ).order_by(CompteComptable.numero).all()
    
    result = []
    for compte in comptes:
        total_debit = 0
        total_credit = 0
        
        for ligne in compte.lignes:
            if ligne.ecriture.statut != 'valide':
                continue
            
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
    
    return result


def get_compte_resultat(structure_id, date_debut, date_fin):
    from sqlalchemy import text
    
    date_debut_obj = parse_date(date_debut) if date_debut else None
    date_fin_obj = parse_date(date_fin) if date_fin else None
    
    try:
        result = db.session.execute(text("""
            WITH ecritures_periode AS (
                SELECT 
                    e.id,
                    e.date_ecriture,
                    l.compte_id,
                    c.numero,
                    c.nom,
                    c.type,
                    l.debit,
                    l.credit
                FROM ecritures_comptables e
                JOIN lignes_ecritures l ON e.id = l.ecriture_id
                JOIN comptes_comptables c ON l.compte_id = c.id
                WHERE e.structure_id = :structure_id
                AND e.statut = 'valide'
                AND c.type IN ('charge', 'produit')
                AND (:date_debut IS NULL OR e.date_ecriture >= :date_debut)
                AND (:date_fin IS NULL OR e.date_ecriture <= :date_fin)
            )
            SELECT
                numero,
                nom,
                type,
                COALESCE(SUM(debit), 0) as total_debit,
                COALESCE(SUM(credit), 0) as total_credit
            FROM ecritures_periode
            GROUP BY numero, nom, type
            ORDER BY type, numero
        """), {
            'structure_id': structure_id,
            'date_debut': date_debut_obj.strftime('%Y-%m-%d') if date_debut_obj else None,
            'date_fin': date_fin_obj.strftime('%Y-%m-%d') if date_fin_obj else None
        })

        rows = result.fetchall()

        charges = []
        produits = []
        total_charges = 0
        total_produits = 0

        for row in rows:
            # ⭐ FIX : ne bucketer QUE les comptes de charge/produit (la
            # requête SQL les filtre déjà) — l'ancien `else` avalait tout
            # compte non-charge (trésorerie, tiers...) dans les "produits".
            type_compte = row.type
            numero = row.numero
            nom = row.nom
            total_debit = float(row.total_debit or 0)
            total_credit = float(row.total_credit or 0)

            if type_compte == 'charge':
                solde = total_debit - total_credit
                total_charges += solde
                charges.append({'numero': numero, 'nom': nom, 'montant': solde})
            elif type_compte == 'produit':
                solde = total_credit - total_debit
                total_produits += solde
                produits.append({'numero': numero, 'nom': nom, 'montant': solde})
        
        resultat = total_produits - total_charges
        
        return {
            'charges': charges,
            'produits': produits,
            'total_charges': total_charges,
            'total_produits': total_produits,
            'resultat': resultat,
            'resultat_text': 'Bénéfice' if resultat > 0 else 'Perte'
        }
        
    except Exception as e:
        print(f"❌ Erreur get_compte_resultat: {e}")
        return {'charges': [], 'produits': [], 'total_charges': 0, 'total_produits': 0, 'resultat': 0, 'resultat_text': 'Bénéfice'}


def get_bilan(structure_id, date_fin):
    from sqlalchemy import text
    
    date_fin_obj = parse_date(date_fin) if date_fin else None
    
    try:
        result = db.session.execute(text("""
            WITH ecritures_bilan AS (
                SELECT 
                    e.id,
                    l.compte_id,
                    c.numero,
                    c.nom,
                    c.type,
                    l.debit,
                    l.credit
                FROM ecritures_comptables e
                JOIN lignes_ecritures l ON e.id = l.ecriture_id
                JOIN comptes_comptables c ON l.compte_id = c.id
                WHERE e.structure_id = :structure_id
                AND e.statut = 'valide'
                AND c.type IN ('actif', 'passif')
                AND (:date_fin IS NULL OR e.date_ecriture <= :date_fin)
            )
            SELECT
                numero,
                nom,
                type,
                COALESCE(SUM(debit), 0) as total_debit,
                COALESCE(SUM(credit), 0) as total_credit
            FROM ecritures_bilan
            GROUP BY numero, nom, type
            ORDER BY type, numero
        """), {
            'structure_id': structure_id,
            'date_fin': date_fin_obj.strftime('%Y-%m-%d') if date_fin_obj else None
        })

        rows = result.fetchall()

        actifs = []
        passifs = []
        capitaux_propres = []

        total_actif = 0
        total_passif = 0
        total_capitaux = 0

        # ⭐ FIX : ne bucketer QUE les comptes actif/passif (filtrés en SQL).
        # L'ancien `else` récupérait tout compte de charge/produit dont le
        # solde créditeur était positif et l'affichait comme "capitaux
        # propres", ce qui n'a aucun sens comptablement.
        for row in rows:
            type_compte = row.type
            numero = row.numero
            nom = row.nom
            total_debit = float(row.total_debit or 0)
            total_credit = float(row.total_credit or 0)

            if type_compte == 'actif':
                solde = total_debit - total_credit
                total_actif += solde
                actifs.append({'numero': numero, 'nom': nom, 'montant': solde})
            elif type_compte == 'passif':
                solde = total_credit - total_debit
                total_passif += solde
                passifs.append({'numero': numero, 'nom': nom, 'montant': solde})

        # ⭐ Le résultat de l'exercice (charges/produits, non clôturés) fait
        # partie des capitaux propres au bilan tant que l'exercice n'est pas
        # clôturé — présentation OHADA standard : une seule ligne "Résultat
        # net de l'exercice", pas le détail des comptes de charge/produit.
        resultat_periode = get_compte_resultat(structure_id, None, date_fin)
        resultat_net = resultat_periode.get('resultat', 0)
        if abs(resultat_net) > 0.5:
            capitaux_propres.append({
                'numero': '120' if resultat_net >= 0 else '129',
                'nom': f"Résultat net de l'exercice ({resultat_periode.get('resultat_text', '')})",
                'montant': resultat_net,
            })
            total_capitaux += resultat_net

        return {
            'actifs': actifs,
            'passifs': passifs,
            'capitaux_propres': capitaux_propres,
            'total_actif': total_actif,
            'total_passif': total_passif,
            'total_capitaux': total_capitaux,
            'total_passif_capitaux': total_passif + total_capitaux,
            'est_equilibre': abs(total_actif - (total_passif + total_capitaux)) < 1
        }
        
    except Exception as e:
        print(f"❌ Erreur get_bilan: {e}")
        return {'actifs': [], 'passifs': [], 'capitaux_propres': [], 'total_actif': 0, 'total_passif': 0, 'total_capitaux': 0, 'total_passif_capitaux': 0, 'est_equilibre': True}


# ============================================================
# RAPPROCHEMENT BANCAIRE
# ============================================================

def _compte_banque_par_defaut(structure_id):
    """Compte de trésorerie utilisé quand un relevé n'a pas de compte_id
    explicite (anciens relevés créés avant le support multi-comptes)."""
    return CompteComptable.query.filter_by(structure_id=structure_id, numero='521').first()


@compta_bp.route('/api/rapprochement/comptes')
def api_rapprochement_comptes():
    """⭐ NOUVEAU : liste des comptes de trésorerie (classe 5 — banques et
    caisses) disponibles pour le rapprochement, pour gérer plusieurs comptes
    bancaires séparément."""
    structure_id = session.get('structure_id')
    comptes = CompteComptable.query.filter(
        CompteComptable.structure_id == structure_id,
        CompteComptable.classe == '5',
        CompteComptable.actif == True,
    ).order_by(CompteComptable.numero).all()

    return jsonify([{
        'id': c.id, 'numero': c.numero, 'nom': c.nom,
        'solde_comptable': float(c.get_solde() or 0),
    } for c in comptes])


@compta_bp.route('/api/rapprochement/releves', methods=['GET'])
def api_get_releves():
    structure_id = session.get('structure_id')

    compte_id_filtre = request.args.get('compte_id', type=int)

    query = ReleveBancaire.query.filter_by(structure_id=structure_id)
    if compte_id_filtre:
        query = query.filter_by(compte_id=compte_id_filtre)

    releves = query.order_by(ReleveBancaire.date_releve.desc()).all()

    result = []
    for r in releves:
        compte = r.compte_id and CompteComptable.query.get(r.compte_id)
        result.append({
            'id': r.id,
            'date_releve': r.date_releve.strftime('%Y-%m-%d') if r.date_releve else '',
            'compte_id': r.compte_id,
            'compte_numero': compte.numero if compte else '521',
            'compte_nom': compte.nom if compte else 'Banque (compte par défaut)',
            'solde_initial': float(r.solde_initial),
            'solde_final': float(r.solde_final),
            'total_credits': float(r.total_credits) if r.total_credits else 0,
            'total_debits': float(r.total_debits) if r.total_debits else 0,
            'statut': r.statut,
            'created_by': r.created_by or '-',
            'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
            'nb_lignes': len(r.lignes),
            'nb_rapproche': sum(1 for l in r.lignes if l.rapproche)
        })

    return jsonify(result)


@compta_bp.route('/api/rapprochement/releves', methods=['POST'])
def api_creer_releve():
    try:
        data = request.json
        structure_id = session.get('structure_id')
        user_name = session.get('user_name', 'System')
        
        date_releve = parse_date(data.get('date_releve'))
        if not date_releve:
            return jsonify({'error': 'Format de date invalide'}), 400

        compte_id = data.get('compte_id')
        if compte_id:
            compte = CompteComptable.query.filter_by(id=compte_id, structure_id=structure_id).first()
            if not compte:
                return jsonify({'error': 'Compte de trésorerie invalide'}), 400
        else:
            compte = _compte_banque_par_defaut(structure_id)
            compte_id = compte.id if compte else None

        releve = ReleveBancaire(
            structure_id=structure_id,
            compte_id=compte_id,
            date_releve=date_releve,
            solde_initial=data.get('solde_initial', 0),
            created_by=user_name,
            statut='brouillon'
        )
        db.session.add(releve)
        db.session.flush()
        
        total_credits = 0
        total_debits = 0
        solde_courant = float(data.get('solde_initial', 0))
        
        for ligne_data in data.get('lignes', []):
            debit = float(ligne_data.get('debit', 0))
            credit = float(ligne_data.get('credit', 0))
            solde_courant += credit - debit
            total_credits += credit
            total_debits += debit
            
            date_operation = parse_date(ligne_data.get('date_operation'))
            if not date_operation:
                date_operation = date_releve
            
            ligne = LigneReleve(
                releve_id=releve.id,
                date_operation=date_operation,
                libelle=ligne_data.get('libelle'),
                reference=ligne_data.get('reference', ''),
                debit=debit,
                credit=credit,
                solde=solde_courant
            )
            db.session.add(ligne)
        
        releve.total_credits = total_credits
        releve.total_debits = total_debits
        releve.solde_final = solde_courant
        
        db.session.commit()
        
        return jsonify({'success': True, 'id': releve.id, 'solde_final': solde_courant})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur: {e}")
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/rapprochement/releves/<int:releve_id>/lignes')
def api_get_lignes_releve(releve_id):
    structure_id = session.get('structure_id')
    
    releve = ReleveBancaire.query.filter_by(id=releve_id, structure_id=structure_id).first()
    
    if not releve:
        return jsonify({'error': 'Releve non trouve'}), 404
    
    result = []
    for ligne in releve.lignes:
        result.append({
            'id': ligne.id,
            'date_operation': ligne.date_operation.strftime('%Y-%m-%d') if ligne.date_operation else '',
            'libelle': ligne.libelle,
            'reference': ligne.reference or '',
            'debit': float(ligne.debit),
            'credit': float(ligne.credit),
            'solde': float(ligne.solde),
            'est_rapproche': ligne.rapproche,
            'ecriture_id': ligne.ecriture_id
        })
    
    return jsonify(result)


@compta_bp.route('/api/rapprochement/releves/<int:releve_id>/rapprocher', methods=['POST'])
def api_rapprocher_releve(releve_id):
    """Rapprochement automatique, en 2 passes :
    1) date exacte + montant exact (le plus fiable)
    2) montant exact mais date à ± TOLERANCE_JOURS (la banque poste souvent
       avec un décalage de quelques jours par rapport à la date de l'écriture)
    Tout ce qui n'est pas apparié automatiquement reste disponible pour une
    association manuelle (voir /lignes/<id>/associer)."""
    TOLERANCE_JOURS = 3
    try:
        structure_id = session.get('structure_id')

        releve = ReleveBancaire.query.filter_by(id=releve_id, structure_id=structure_id).first()

        if not releve:
            return jsonify({'error': 'Releve non trouve'}), 404

        # ⭐ FIX : le compte "212" (ancienne numérotation) n'existe plus
        # depuis la migration SYSCOHADA — on utilise le compte du relevé
        # (multi-comptes) ou "521 Banque" par défaut pour les anciens relevés.
        if releve.compte_id:
            compte_bancaire = CompteComptable.query.get(releve.compte_id)
        else:
            compte_bancaire = _compte_banque_par_defaut(structure_id)

        if not compte_bancaire:
            return jsonify({'error': 'Compte de trésorerie introuvable pour ce relevé'}), 400

        ecritures = db.session.query(EcritureComptable, LigneEcriture).join(
            LigneEcriture, EcritureComptable.id == LigneEcriture.ecriture_id
        ).filter(
            EcritureComptable.structure_id == structure_id,
            EcritureComptable.statut == 'valide',
            LigneEcriture.compte_id == compte_bancaire.id
        ).order_by(EcritureComptable.date_ecriture).all()

        # Écritures déjà rapprochées (sur ce compte, tous relevés confondus) à exclure
        deja_utilisees = {
            l.ecriture_id for l in LigneReleve.query.join(ReleveBancaire).filter(
                ReleveBancaire.compte_id == compte_bancaire.id,
                LigneReleve.rapproche == True,
                LigneReleve.ecriture_id != None,
            ).all()
        }

        candidats = []
        for ecriture, ligne in ecritures:
            if ecriture.id in deja_utilisees:
                continue
            montant = float(ligne.debit) if ligne.debit > 0 else float(ligne.credit)
            candidats.append({'ecriture_id': ecriture.id, 'date': ecriture.date_ecriture, 'montant': montant})

        nb_rapproche = 0
        nb_pass1 = 0

        # --- Passe 1 : date exacte + montant exact ---
        for ligne in releve.lignes:
            if ligne.rapproche:
                continue
            montant = float(ligne.debit) if ligne.debit > 0 else float(ligne.credit)
            for c in candidats:
                if c['ecriture_id'] in deja_utilisees:
                    continue
                if c['date'] == ligne.date_operation and abs(c['montant'] - montant) < 0.5:
                    ligne.rapproche = True
                    ligne.ecriture_id = c['ecriture_id']
                    deja_utilisees.add(c['ecriture_id'])
                    nb_rapproche += 1
                    nb_pass1 += 1
                    break

        # --- Passe 2 : montant exact, date à ± TOLERANCE_JOURS ---
        for ligne in releve.lignes:
            if ligne.rapproche:
                continue
            montant = float(ligne.debit) if ligne.debit > 0 else float(ligne.credit)
            meilleur = None
            for c in candidats:
                if c['ecriture_id'] in deja_utilisees:
                    continue
                if abs(c['montant'] - montant) >= 0.5:
                    continue
                ecart_jours = abs((c['date'] - ligne.date_operation).days)
                if ecart_jours <= TOLERANCE_JOURS and (meilleur is None or ecart_jours < meilleur[1]):
                    meilleur = (c, ecart_jours)
            if meilleur:
                c = meilleur[0]
                ligne.rapproche = True
                ligne.ecriture_id = c['ecriture_id']
                deja_utilisees.add(c['ecriture_id'])
                nb_rapproche += 1

        total_lignes = len(releve.lignes)
        total_rapproche = sum(1 for l in releve.lignes if l.rapproche)

        if total_rapproche == total_lignes and total_lignes > 0:
            releve.statut = 'en_attente'

        db.session.commit()

        return jsonify({
            'success': True,
            'nb_rapproche': nb_rapproche,
            'nb_rapproche_exact': nb_pass1,
            'nb_rapproche_tolerance': nb_rapproche - nb_pass1,
            'total_lignes': total_lignes,
            'total_rapproche': total_rapproche,
            'statut': releve.statut
        })

    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur: {e}")
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/rapprochement/releves/<int:releve_id>/lignes/<int:ligne_id>/candidats')
def api_candidats_association(releve_id, ligne_id):
    """⭐ NOUVEAU : liste des écritures candidates (même compte, montant
    identique, non déjà rapprochées) pour associer manuellement une ligne de
    relevé qui n'a pas été appariée automatiquement."""
    structure_id = session.get('structure_id')
    releve = ReleveBancaire.query.filter_by(id=releve_id, structure_id=structure_id).first()
    if not releve:
        return jsonify({'error': 'Releve non trouve'}), 404
    ligne = LigneReleve.query.filter_by(id=ligne_id, releve_id=releve_id).first()
    if not ligne:
        return jsonify({'error': 'Ligne non trouvee'}), 404

    compte = CompteComptable.query.get(releve.compte_id) if releve.compte_id else _compte_banque_par_defaut(structure_id)
    if not compte:
        return jsonify([])

    montant = float(ligne.debit) if ligne.debit > 0 else float(ligne.credit)
    deja_utilisees = {
        l.ecriture_id for l in LigneReleve.query.filter(
            LigneReleve.rapproche == True, LigneReleve.ecriture_id != None
        ).all()
    }

    ecritures = db.session.query(EcritureComptable, LigneEcriture).join(
        LigneEcriture, EcritureComptable.id == LigneEcriture.ecriture_id
    ).filter(
        EcritureComptable.structure_id == structure_id,
        EcritureComptable.statut == 'valide',
        LigneEcriture.compte_id == compte.id,
    ).order_by(EcritureComptable.date_ecriture.desc()).all()

    result = []
    for ecriture, l in ecritures:
        if ecriture.id in deja_utilisees and ecriture.id != ligne.ecriture_id:
            continue
        m = float(l.debit) if l.debit > 0 else float(l.credit)
        result.append({
            'ecriture_id': ecriture.id,
            'date': ecriture.date_ecriture.strftime('%Y-%m-%d'),
            'libelle': ecriture.libelle,
            'piece': ecriture.piece_justificative or '',
            'montant': m,
            'correspond_exactement': abs(m - montant) < 0.5,
        })

    result.sort(key=lambda r: (not r['correspond_exactement'], r['date']), reverse=False)
    return jsonify(result)


@compta_bp.route('/api/rapprochement/releves/<int:releve_id>/lignes/<int:ligne_id>/associer', methods=['POST'])
def api_associer_ligne(releve_id, ligne_id):
    """Association manuelle (ou modification d'une association) d'une
    ligne de relevé à une écriture comptable précise."""
    try:
        structure_id = session.get('structure_id')
        releve = ReleveBancaire.query.filter_by(id=releve_id, structure_id=structure_id).first()
        if not releve:
            return jsonify({'error': 'Releve non trouve'}), 404
        ligne = LigneReleve.query.filter_by(id=ligne_id, releve_id=releve_id).first()
        if not ligne:
            return jsonify({'error': 'Ligne non trouvee'}), 404

        ecriture_id = request.json.get('ecriture_id')
        ecriture = EcritureComptable.query.filter_by(id=ecriture_id, structure_id=structure_id).first()
        if not ecriture:
            return jsonify({'error': 'Ecriture non trouvee'}), 404

        ligne.rapproche = True
        ligne.ecriture_id = ecriture.id
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/rapprochement/releves/<int:releve_id>/lignes/<int:ligne_id>/dissocier', methods=['POST'])
def api_dissocier_ligne(releve_id, ligne_id):
    """Annule un rapprochement (manuel ou automatique) sur une ligne."""
    try:
        structure_id = session.get('structure_id')
        releve = ReleveBancaire.query.filter_by(id=releve_id, structure_id=structure_id).first()
        if not releve:
            return jsonify({'error': 'Releve non trouve'}), 404
        ligne = LigneReleve.query.filter_by(id=ligne_id, releve_id=releve_id).first()
        if not ligne:
            return jsonify({'error': 'Ligne non trouvee'}), 404

        ligne.rapproche = False
        ligne.ecriture_id = None
        if releve.statut == 'en_attente':
            releve.statut = 'brouillon'
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/rapprochement/releves/import', methods=['POST'])
def api_importer_releve():
    """⭐ NOUVEAU : import d'un relevé bancaire depuis un fichier CSV ou
    Excel (.xlsx) au lieu de saisir chaque ligne à la main.

    Colonnes attendues (insensible à la casse, ordre libre) : une colonne
    date, une colonne libellé, et soit deux colonnes débit/crédit séparées,
    soit une seule colonne "montant" (négatif = débit, positif = crédit).
    """
    try:
        structure_id = session.get('structure_id')
        user_name = session.get('user_name', 'System')

        fichier = request.files.get('fichier')
        if not fichier or not fichier.filename:
            return jsonify({'error': 'Aucun fichier fourni'}), 400

        date_releve = parse_date(request.form.get('date_releve')) or date.today()
        solde_initial = float(request.form.get('solde_initial', 0) or 0)
        compte_id = request.form.get('compte_id', type=int)
        if compte_id:
            compte = CompteComptable.query.filter_by(id=compte_id, structure_id=structure_id).first()
            if not compte:
                return jsonify({'error': 'Compte de trésorerie invalide'}), 400
        else:
            compte = _compte_banque_par_defaut(structure_id)
            compte_id = compte.id if compte else None

        nom_fichier = fichier.filename.lower()
        lignes_brutes = []  # liste de dicts {date, libelle, reference, debit, credit}

        def _trouver_colonne(en_tetes, *candidats):
            for i, h in enumerate(en_tetes):
                h_norm = (h or '').strip().lower()
                if any(c in h_norm for c in candidats):
                    return i
            return None

        def _to_float_safe(v):
            if v is None or v == '':
                return 0.0
            try:
                return float(str(v).replace(' ', '').replace(',', '.'))
            except ValueError:
                return 0.0

        if nom_fichier.endswith('.xlsx') or nom_fichier.endswith('.xls'):
            import openpyxl
            wb = openpyxl.load_workbook(fichier, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return jsonify({'error': 'Fichier vide'}), 400
            entetes = [str(c) if c is not None else '' for c in rows[0]]
            data_rows = rows[1:]
        else:
            import csv as csv_module
            import io
            contenu = fichier.read().decode('utf-8-sig', errors='replace')
            delimiter = ';' if contenu.count(';') > contenu.count(',') else ','
            reader = csv_module.reader(io.StringIO(contenu), delimiter=delimiter)
            rows = list(reader)
            if not rows:
                return jsonify({'error': 'Fichier vide'}), 400
            entetes = rows[0]
            data_rows = rows[1:]

        idx_date = _trouver_colonne(entetes, 'date')
        idx_libelle = _trouver_colonne(entetes, 'libell', 'description', 'intitul', 'motif')
        idx_ref = _trouver_colonne(entetes, 'ref', 'piece', 'pièce')
        idx_debit = _trouver_colonne(entetes, 'debit', 'débit')
        idx_credit = _trouver_colonne(entetes, 'credit', 'crédit')
        idx_montant = _trouver_colonne(entetes, 'montant', 'amount')

        if idx_date is None:
            return jsonify({'error': "Colonne 'date' introuvable dans le fichier. En-têtes lus : " + ', '.join(entetes)}), 400

        for row in data_rows:
            if not row or all(c in (None, '') for c in row):
                continue
            raw_date = row[idx_date] if idx_date is not None and idx_date < len(row) else None
            if hasattr(raw_date, 'strftime'):
                date_operation = raw_date.date() if hasattr(raw_date, 'date') else raw_date
            else:
                date_operation = parse_date(str(raw_date)) if raw_date else None
            if not date_operation:
                continue

            libelle = str(row[idx_libelle]) if idx_libelle is not None and idx_libelle < len(row) and row[idx_libelle] else 'Opération'
            reference = str(row[idx_ref]) if idx_ref is not None and idx_ref < len(row) and row[idx_ref] else ''

            if idx_debit is not None and idx_credit is not None:
                debit = _to_float_safe(row[idx_debit] if idx_debit < len(row) else 0)
                credit = _to_float_safe(row[idx_credit] if idx_credit < len(row) else 0)
            elif idx_montant is not None:
                montant = _to_float_safe(row[idx_montant] if idx_montant < len(row) else 0)
                debit = abs(montant) if montant < 0 else 0
                credit = montant if montant > 0 else 0
            else:
                continue

            lignes_brutes.append({
                'date_operation': date_operation, 'libelle': libelle,
                'reference': reference, 'debit': debit, 'credit': credit,
            })

        if not lignes_brutes:
            return jsonify({'error': 'Aucune ligne exploitable trouvée dans le fichier'}), 400

        releve = ReleveBancaire(
            structure_id=structure_id, compte_id=compte_id, date_releve=date_releve,
            solde_initial=solde_initial, created_by=user_name, statut='brouillon',
        )
        db.session.add(releve)
        db.session.flush()

        solde_courant = solde_initial
        total_credits = 0.0
        total_debits = 0.0
        for l in sorted(lignes_brutes, key=lambda x: x['date_operation']):
            solde_courant += l['credit'] - l['debit']
            total_credits += l['credit']
            total_debits += l['debit']
            db.session.add(LigneReleve(
                releve_id=releve.id, date_operation=l['date_operation'], libelle=l['libelle'],
                reference=l['reference'], debit=l['debit'], credit=l['credit'], solde=solde_courant,
            ))

        releve.total_credits = total_credits
        releve.total_debits = total_debits
        releve.solde_final = solde_courant
        db.session.commit()

        return jsonify({'success': True, 'id': releve.id, 'nb_lignes': len(lignes_brutes), 'solde_final': solde_courant})

    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur import relevé: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/rapprochement/releves/<int:releve_id>/valider', methods=['POST'])
def api_valider_releve(releve_id):
    try:
        structure_id = session.get('structure_id')
        user_name = session.get('user_name', 'System')
        
        releve = ReleveBancaire.query.filter_by(id=releve_id, structure_id=structure_id).first()
        
        if not releve:
            return jsonify({'error': 'Releve non trouve'}), 404
        
        total_lignes = len(releve.lignes)
        total_rapproche = sum(1 for l in releve.lignes if l.rapproche)
        
        if total_lignes > 0 and total_rapproche < total_lignes:
            return jsonify({
                'error': f'Impossible de valider : {total_lignes - total_rapproche} ligne(s) non rapprochee(s)'
            }), 400
        
        releve.statut = 'valide'
        releve.valide_par = user_name
        releve.date_validation = date.today()
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Releve valide avec succes'})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================
# INITIALISATION PLAN COMPTABLE
# ============================================================

@compta_bp.route('/api/init-comptes', methods=['POST'])
def api_init_comptes():
    """Initialise (ou complète) le plan comptable SYSCOHADA de la structure.
    Voir utils/plan_comptable_syscohada.py pour la nomenclature de référence,
    partagée avec scripts/seed_plan_comptable_syscohada.py."""
    structure_id = session.get('structure_id')
    if not structure_id:
        return jsonify({'success': False, 'error': 'Structure non trouvee'}), 400

    from scripts.seed_plan_comptable_syscohada import seed_pour_structure
    seed_pour_structure(structure_id)
    invalidate_cache(structure_id)

    return jsonify({'success': True})

# routes/comptabilite.py - Ajouter cette route

# routes/comptabilite.py - Route simplifiée

@compta_bp.route('/rapport/print/<type_rapport>')
def print_rapport(type_rapport):
    """Génère une version imprimable d'un rapport (PDF via impression)"""
    structure_id = session.get('structure_id')
    
    if not structure_id:
        flash('Structure non trouvée', 'danger')
        return redirect(url_for('comptabilite.index'))
    
    # Récupérer les paramètres
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    
    # Récupérer les données du rapport
    if type_rapport == 'journal':
        data = generer_journal(structure_id, date_debut, date_fin)
        titre = "Journal comptable"
    elif type_rapport == 'grand_livre':
        data = generer_grand_livre(structure_id, date_debut, date_fin)
        titre = "Grand livre"
    elif type_rapport == 'balance':
        data = generer_balance(structure_id, date_debut, date_fin)
        titre = "Balance comptable"
    elif type_rapport == 'resultat':
        data = get_compte_resultat(structure_id, date_debut, date_fin)
        titre = "Compte de résultat"
    elif type_rapport == 'bilan':
        data = get_bilan(structure_id, date_fin)
        titre = "Bilan comptable"
    else:
        flash('Type de rapport invalide', 'danger')
        return redirect(url_for('comptabilite.index'))
    
    # ⭐ PAS DE RECHERCHE DE STRUCTURE - On passe juste les données
    return render_template('comptabilite/print_rapport.html',
                         type_rapport=type_rapport,
                         titre=titre,
                         data=data,
                         date_debut=date_debut,
                         date_fin=date_fin,
                         now=datetime.now())

# routes/comptabilite.py - Ajouter cette route

@compta_bp.route('/budget/print')
def print_budget():
    """Génère une version imprimable du budget"""
    structure_id = session.get('structure_id')
    
    if not structure_id:
        flash('Structure non trouvée', 'danger')
        return redirect(url_for('comptabilite.index'))
    
    annee = request.args.get('annee', datetime.now().year)
    compte_id = request.args.get('compte_id')
    
    # Récupérer les comptes avec budget
    query_comptes = CompteComptable.query.filter_by(
        structure_id=structure_id,
        actif=True
    )
    
    if compte_id:
        query_comptes = query_comptes.filter_by(id=compte_id)
    
    comptes = query_comptes.order_by(CompteComptable.numero).all()
    
    # Récupérer les budgets
    budgets = Budget.query.filter_by(
        structure_id=structure_id,
        annee=annee
    ).all()
    
    budget_dict = {}
    for b in budgets:
        key = (b.compte_id, b.mois)
        budget_dict[key] = b
    
    # Construire les données
    data = []
    for compte in comptes:
        item = {
            'compte_id': compte.id,
            'compte_numero': compte.numero,
            'compte_nom': compte.nom,
            'total_prevu': 0,
            'total_reel': 0,
            'mois_data': []
        }
        
        total_prevu = 0
        for mois in range(1, 13):
            key = (compte.id, mois)
            if key in budget_dict:
                b = budget_dict[key]
                montant_prevu = float(b.montant_prevu)
                total_prevu += montant_prevu
                item['mois_data'].append({
                    'mois': mois,
                    'montant_prevu': montant_prevu,
                    'montant_reel': float(b.montant_reel) if b.montant_reel else 0
                })
            else:
                item['mois_data'].append({
                    'mois': mois,
                    'montant_prevu': 0,
                    'montant_reel': 0
                })
        
        item['total_prevu'] = total_prevu
        
        # Ne garder que les comptes avec budget
        if total_prevu > 0:
            data.append(item)
    
    # Récupérer les infos de la structure depuis localStorage (passer en variable)
    structure_info = {
        'nom': 'Mon Etablissement',
        'adresse': '',
        'telephone': '',
        'email': '',
        'logo_url': ''
    }
    
    return render_template('comptabilite/print_budget.html',
                         data=data,
                         annee=annee,
                         structure_info=structure_info,
                         now=datetime.now())