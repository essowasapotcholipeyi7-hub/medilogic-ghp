# routes/comptabilite.py
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from datetime import datetime, date
import json
import re
# ⭐ AJOUTER EN HAUT DU FICHIER (après les imports)
from functools import lru_cache
from datetime import datetime, timedelta

from models import (
    db, CompteComptable, EcritureComptable, LigneEcriture, 
    Budget, ValidationComptable, HistoriqueEcriture, ReleveBancaire, LigneReleve, Cloture
)

compta_bp = Blueprint('comptabilite', __name__, url_prefix='/comptabilite')


# ⭐ Cache des comptes
_compte_cache = {}
_compte_cache_time = {}

def get_comptes_cached(structure_id):
    """Récupère les comptes avec cache (5 minutes)"""
    key = f"comptes_{structure_id}"
    
    # ⭐ Vérifier le cache
    if key in _compte_cache and (datetime.now() - _compte_cache_time.get(key, datetime.min)) < timedelta(minutes=5):
        return _compte_cache[key]
    
    # ⭐ Charger depuis la base
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
            'solde': c.get_solde()
        })
    
    # ⭐ Mettre en cache
    _compte_cache[key] = result
    _compte_cache_time[key] = datetime.now()
    
    return result

# ============================================================
# CACHE POUR LES RAPPORTS
# ============================================================

_rapport_cache = {}
_rapport_cache_time = {}
_rapport_special_cache = {}
_rapport_special_cache_time = {}

def get_rapport_cached(structure_id, type_rapport, date_debut, date_fin):
    """Récupère un rapport avec cache (10 minutes)"""
    key = f"rapport_{structure_id}_{type_rapport}_{date_debut}_{date_fin}"
    
    if key in _rapport_cache and (datetime.now() - _rapport_cache_time.get(key, datetime.min)) < timedelta(minutes=10):
        return _rapport_cache[key]
    
    result = generer_rapport(structure_id, type_rapport, date_debut, date_fin)
    
    _rapport_cache[key] = result
    _rapport_cache_time[key] = datetime.now()
    
    return result

# ============================================================
# FONCTION DE PARSING DES DATES - ACCEPTE MULTIPLES FORMATS
# ============================================================

def parse_date(date_str):
    """
    Parse une date dans plusieurs formats et retourne un objet date
    Formats acceptés :
    - 2026-07-23 (YYYY-MM-DD)
    - 23/07/2026 (DD/MM/YYYY)
    - 23-07-2026 (DD-MM-YYYY)
    - 2026/07/23 (YYYY/MM/DD)
    - 23 July 2026 (texte)
    - 23 Jul 2026
    """
    if not date_str:
        return None
    
    # Nettoyer la chaîne
    date_str = str(date_str).strip()
    
    # Essayer les différents formats avec datetime.strptime
    formats = [
        '%Y-%m-%d',   # 2026-07-23
        '%d/%m/%Y',   # 23/07/2026
        '%d-%m-%Y',   # 23-07-2026
        '%Y/%m/%d',   # 2026/07/23
        '%d %b %Y',   # 23 Jul 2026
        '%d %B %Y',   # 23 July 2026
        '%b %d %Y',   # Jul 23 2026
        '%B %d %Y',   # July 23 2026
        '%Y%m%d',     # 20260723
        '%d.%m.%Y',   # 23.07.2026
        '%m/%d/%Y',   # 07/23/2026 (US)
        '%d/%m/%y',   # 23/07/26
        '%d-%m-%y',   # 23-07-26
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    
    # Essayer avec regex pour les formats plus flexibles
    # Format: 23/07/2026 ou 23-07-2026
    match = re.match(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$', date_str)
    if match:
        day, month, year = match.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            pass
    
    # Format: 2026/07/23 ou 2026-07-23
    match = re.match(r'^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$', date_str)
    if match:
        year, month, day = match.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            pass
    
    # Si tout échoue
    print(f"⚠️ Format de date non reconnu: '{date_str}'")
    return None


def format_date(date_obj, output_format='%Y-%m-%d'):
    """Formate une date selon le format souhaité"""
    if not date_obj:
        return ''
    if isinstance(date_obj, str):
        parsed = parse_date(date_obj)
        if parsed:
            return parsed.strftime(output_format)
        return date_obj
    if isinstance(date_obj, date):
        return date_obj.strftime(output_format)
    return ''


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
    
    # ⭐ Utiliser le cache
    comptes = get_comptes_cached(structure_id)
    
    # ⭐ Filtrer en mémoire (plus rapide que SQL)
    if search:
        search_lower = search.lower()
        comptes = [c for c in comptes if search_lower in (c['numero'] + ' ' + c['nom']).lower()]
    if type_filter:
        comptes = [c for c in comptes if c['type'] == type_filter]
    
    return jsonify(comptes)

# routes/comptabilite.py

@compta_bp.route('/api/cache/clear', methods=['POST'])
def api_clear_cache():
    """Vide le cache (admin seulement)"""
    global _compte_cache, _compte_cache_time, _dashboard_cache, _dashboard_cache_time
    
    _compte_cache = {}
    _compte_cache_time = {}
    _dashboard_cache = {}
    _dashboard_cache_time = {}
    
    return jsonify({'success': True, 'message': 'Cache vidé avec succès'})


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
    
    # ⭐ PAGINATION (20 par page)
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
    
    # Conversion des dates
    if date_debut:
        date_debut_obj = parse_date(date_debut)
        if date_debut_obj:
            query = query.filter(EcritureComptable.date_ecriture >= date_debut_obj)
    
    if date_fin:
        date_fin_obj = parse_date(date_fin)
        if date_fin_obj:
            query = query.filter(EcritureComptable.date_ecriture <= date_fin_obj)
    
    # ⭐ COMPTER avant de paginer
    total = query.count()
    
    # ⭐ PAGINER
    ecritures = query.order_by(EcritureComptable.date_ecriture.desc()).offset((page-1)*per_page).limit(per_page).all()
    
    result = []
    for e in ecritures:
        # ⭐ LIMITER les lignes chargées (5 max pour l'affichage)
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
            'date_ecriture': e.date_ecriture.strftime('%Y-%m-%d'),
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
            'nb_lignes': len(e.lignes)  # ⭐ Indiquer le nombre total de lignes
        })
    
    # ⭐ Retourner avec les infos de pagination
    return jsonify({
        'data': result,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

@compta_bp.route('/api/ecritures', methods=['POST'])
def api_creer_ecriture():
    data = request.json
    structure_id = session.get('structure_id')
    user_name = session.get('user_name', 'System')
    
    # ✅ Conversion de la date dans tous les formats
    date_ecriture = parse_date(data.get('date_ecriture'))
    if not date_ecriture:
        return jsonify({'success': False, 'error': 'Format de date invalide'}), 400
    
    # Verifier l'equilibre
    total_debit = sum(l.get('debit', 0) for l in data.get('lignes', []))
    total_credit = sum(l.get('credit', 0) for l in data.get('lignes', []))
    
    if total_debit != total_credit:
        return jsonify({'success': False, 'error': 'Les totaux debit et credit doivent etre egaux'}), 400
    
    ecriture = EcritureComptable(
        structure_id=structure_id,
        date_ecriture=date_ecriture,
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
        
        # ✅ Conversion de la date dans tous les formats
        date_ecriture = parse_date(data.get('date_ecriture'))
        if not date_ecriture:
            return jsonify({'success': False, 'error': 'Format de date invalide'}), 400
        
        # Verifier l'equilibre
        total_debit = sum(l.get('debit', 0) for l in data.get('lignes', []))
        total_credit = sum(l.get('credit', 0) for l in data.get('lignes', []))
        
        if total_debit != total_credit:
            return jsonify({'success': False, 'error': 'Les totaux debit et credit doivent etre egaux'}), 400
        
        ecriture.date_ecriture = date_ecriture
        ecriture.libelle = data.get('libelle')
        ecriture.piece_justificative = data.get('piece_justificative')
        ecriture.commentaire = data.get('commentaire')
        
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

@compta_bp.route('/api/rapports/journal')
def api_journal():
    structure_id = session.get('structure_id')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    
    # ⭐ Utiliser le cache
    return jsonify(get_rapport_cached(structure_id, 'journal', date_debut, date_fin))


@compta_bp.route('/api/rapports/grand_livre')
def api_grand_livre():
    structure_id = session.get('structure_id')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    compte_id = request.args.get('compte_id')
    
    # ⭐ Utiliser le cache
    return jsonify(get_rapport_cached(structure_id, 'grand_livre', date_debut, date_fin))


@compta_bp.route('/api/rapports/balance')
def api_balance():
    structure_id = session.get('structure_id')
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    
    # ⭐ Utiliser le cache
    return jsonify(get_rapport_cached(structure_id, 'balance', date_debut, date_fin))


def generer_rapport(structure_id, type_rapport, date_debut, date_fin):
    """Génère un rapport (version optimisée)"""
    
    # ⭐ Convertir les dates
    date_debut_obj = parse_date(date_debut) if date_debut else None
    date_fin_obj = parse_date(date_fin) if date_fin else None
    
    if type_rapport == 'journal':
        # ⭐ Utiliser la fonction existante generer_journal()
        return generer_journal(structure_id, date_debut_obj, date_fin_obj)
    elif type_rapport == 'grand_livre':
        # ⭐ Utiliser la fonction existante generer_grand_livre()
        return generer_grand_livre(structure_id, date_debut_obj, date_fin_obj)
    elif type_rapport == 'balance':
        return generer_balance_rapport(structure_id, date_debut_obj, date_fin_obj)
    elif type_rapport == 'resultat':
        return generer_rapport_resultat(structure_id, date_debut_obj, date_fin_obj)
    elif type_rapport == 'bilan':
        return generer_rapport_bilan(structure_id, date_fin_obj)
    else:
        return []

def generer_balance_rapport(structure_id, date_debut, date_fin):
    """Génère la balance (version optimisée)"""
    
    # ⭐ Récupérer tous les comptes
    comptes = CompteComptable.query.filter_by(
        structure_id=structure_id,
        actif=True
    ).order_by(CompteComptable.numero).all()
    
    result = []
    
    for compte in comptes:
        total_debit = 0
        total_credit = 0
        
        # ⭐ Utiliser une sous-requête pour optimiser
        for ligne in compte.lignes:
            if ligne.ecriture.statut != 'valide':
                continue
            
            if date_debut and ligne.ecriture.date_ecriture < date_debut:
                continue
            if date_fin and ligne.ecriture.date_ecriture > date_fin:
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

def generer_journal(structure_id, date_debut, date_fin):
    """Génère le journal"""
    from sqlalchemy import text
    
    result = db.session.execute(text("""
        SELECT 
            e.date_ecriture,
            e.piece_justificative,
            e.libelle,
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
        ORDER BY e.date_ecriture
    """), {
        'structure_id': structure_id,
        'date_debut': date_debut.strftime('%Y-%m-%d') if date_debut else None,
        'date_fin': date_fin.strftime('%Y-%m-%d') if date_fin else None
    })
    
    rows = result.fetchall()
    
    return [{
        'date': row.date_ecriture.strftime('%d/%m/%Y') if row.date_ecriture else '',
        'piece': row.piece_justificative or '',
        'libelle': row.libelle or '',
        'compte_numero': row.compte_numero or '',
        'compte_nom': row.compte_nom or '',
        'debit': float(row.debit or 0),
        'credit': float(row.credit or 0)
    } for row in rows]


def generer_grand_livre(structure_id, date_debut, date_fin):
    """Génère le grand livre"""
    from sqlalchemy import text
    
    result = db.session.execute(text("""
        SELECT 
            e.date_ecriture,
            c.numero as compte_numero,
            c.nom as compte_nom,
            e.libelle,
            l.debit,
            l.credit
        FROM ecritures_comptables e
        JOIN lignes_ecritures l ON e.id = l.ecriture_id
        JOIN comptes_comptables c ON l.compte_id = c.id
        WHERE e.structure_id = :structure_id
        AND e.statut = 'valide'
        AND (:date_debut IS NULL OR e.date_ecriture >= :date_debut)
        AND (:date_fin IS NULL OR e.date_ecriture <= :date_fin)
        ORDER BY c.numero, e.date_ecriture
    """), {
        'structure_id': structure_id,
        'date_debut': date_debut.strftime('%Y-%m-%d') if date_debut else None,
        'date_fin': date_fin.strftime('%Y-%m-%d') if date_fin else None
    })
    
    rows = result.fetchall()
    
    return [{
        'date': row.date_ecriture.strftime('%d/%m/%Y') if row.date_ecriture else '',
        'compte_numero': row.compte_numero or '',
        'compte_nom': row.compte_nom or '',
        'libelle': row.libelle or '',
        'debit': float(row.debit or 0),
        'credit': float(row.credit or 0),
        'solde': 0  # À calculer côté frontend
    } for row in rows]

# ============================================================
# GÉNÉRATEURS DE RAPPORTS
# ============================================================

def generer_rapport_resultat(structure_id, date_debut, date_fin):
    """Génère le compte de résultat (version optimisée)"""
    
    # ⭐ Utiliser la fonction existante get_compte_resultat
    from sqlalchemy import text
    
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
            AND (:date_debut IS NULL OR e.date_ecriture >= :date_debut)
            AND (:date_fin IS NULL OR e.date_ecriture <= :date_fin)
        )
        SELECT 
            compte_id,
            numero,
            nom,
            type,
            COALESCE(SUM(debit), 0) as total_debit,
            COALESCE(SUM(credit), 0) as total_credit
        FROM ecritures_periode
        GROUP BY compte_id, numero, nom, type
        ORDER BY type, numero
    """), {
        'structure_id': structure_id,
        'date_debut': date_debut.strftime('%Y-%m-%d') if date_debut else None,
        'date_fin': date_fin.strftime('%Y-%m-%d') if date_fin else None
    })
    
    rows = result.fetchall()
    
    charges = []
    produits = []
    total_charges = 0
    total_produits = 0
    
    for row in rows:
        type_compte = row.type
        numero = row.numero
        nom = row.nom
        total_debit = float(row.total_debit or 0)
        total_credit = float(row.total_credit or 0)
        
        if type_compte == 'charge':
            solde = total_debit - total_credit
            total_charges += solde
            charges.append({
                'numero': numero,
                'nom': nom,
                'montant': solde
            })
        else:  # produit
            solde = total_credit - total_debit
            total_produits += solde
            produits.append({
                'numero': numero,
                'nom': nom,
                'montant': solde
            })
    
    resultat = total_produits - total_charges
    
    return {
        'charges': charges,
        'produits': produits,
        'total_charges': total_charges,
        'total_produits': total_produits,
        'resultat': resultat,
        'resultat_text': 'Bénéfice' if resultat > 0 else 'Perte'
    }


def generer_rapport_bilan(structure_id, date_fin):
    """Génère le bilan (version optimisée)"""
    
    from sqlalchemy import text
    
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
            AND (:date_fin IS NULL OR e.date_ecriture <= :date_fin)
        )
        SELECT 
            compte_id,
            numero,
            nom,
            type,
            COALESCE(SUM(debit), 0) as total_debit,
            COALESCE(SUM(credit), 0) as total_credit
        FROM ecritures_bilan
        GROUP BY compte_id, numero, nom, type
        ORDER BY type, numero
    """), {
        'structure_id': structure_id,
        'date_fin': date_fin.strftime('%Y-%m-%d') if date_fin else None
    })
    
    rows = result.fetchall()
    
    actifs = []
    passifs = []
    capitaux_propres = []
    
    total_actif = 0
    total_passif = 0
    total_capitaux = 0
    
    for row in rows:
        type_compte = row.type
        numero = row.numero
        nom = row.nom
        total_debit = float(row.total_debit or 0)
        total_credit = float(row.total_credit or 0)
        
        if type_compte == 'actif':
            solde = total_debit - total_credit
            total_actif += solde
            actifs.append({
                'numero': numero,
                'nom': nom,
                'montant': solde
            })
        elif type_compte == 'passif':
            solde = total_credit - total_debit
            total_passif += solde
            passifs.append({
                'numero': numero,
                'nom': nom,
                'montant': solde
            })
        else:  # charge ou produit (capitaux propres)
            solde = total_credit - total_debit
            if solde > 0:
                total_capitaux += solde
                capitaux_propres.append({
                    'numero': numero,
                    'nom': nom,
                    'montant': solde
                })
    
    total_passif_capitaux = total_passif + total_capitaux
    
    return {
        'actifs': actifs,
        'passifs': passifs,
        'capitaux_propres': capitaux_propres,
        'total_actif': total_actif,
        'total_passif': total_passif,
        'total_capitaux': total_capitaux,
        'total_passif_capitaux': total_passif_capitaux,
        'est_equilibre': abs(total_actif - total_passif_capitaux) < 1
    }


# ============================================================
# RAPPORTS SPÉCIAUX - COMPTE DE RÉSULTAT & BILAN
# ============================================================

# ⭐ Cache pour les rapports spéciaux
_rapport_special_cache = {}
_rapport_special_cache_time = {}

@compta_bp.route('/api/rapports/resultat')
def api_rapport_resultat():
    """Génère le compte de résultat avec cache"""
    try:
        structure_id = session.get('structure_id')
        date_debut = request.args.get('date_debut')
        date_fin = request.args.get('date_fin')
        
        # ⭐ Cache de 10 minutes
        key = f"resultat_{structure_id}_{date_debut}_{date_fin}"
        if key in _rapport_special_cache and (datetime.now() - _rapport_special_cache_time.get(key, datetime.min)) < timedelta(minutes=10):
            return jsonify(_rapport_special_cache[key])
        
        date_debut_obj = parse_date(date_debut)
        date_fin_obj = parse_date(date_fin)
        
        result = get_compte_resultat(structure_id, date_debut_obj, date_fin_obj)
        
        _rapport_special_cache[key] = result
        _rapport_special_cache_time[key] = datetime.now()
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur api_rapport_resultat: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/rapports/bilan')
def api_rapport_bilan():
    """Génère le bilan avec cache"""
    try:
        structure_id = session.get('structure_id')
        date_fin = request.args.get('date_fin')
        
        # ⭐ Cache de 10 minutes
        key = f"bilan_{structure_id}_{date_fin}"
        if key in _rapport_special_cache and (datetime.now() - _rapport_special_cache_time.get(key, datetime.min)) < timedelta(minutes=10):
            return jsonify(_rapport_special_cache[key])
        
        date_fin_obj = parse_date(date_fin)
        
        result = get_bilan(structure_id, date_fin_obj)
        
        _rapport_special_cache[key] = result
        _rapport_special_cache_time[key] = datetime.now()
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur api_rapport_bilan: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def get_compte_resultat(structure_id, date_debut, date_fin):
    """Génère le compte de résultat (Revenus - Charges)"""
    try:
        result = db.execute_query("""
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
                WHERE e.structure_id = %s
                AND e.statut = 'valide'
                AND e.date_ecriture BETWEEN %s AND %s
            )
            SELECT 
                compte_id,
                numero,
                nom,
                type,
                COALESCE(SUM(debit), 0) as total_debit,
                COALESCE(SUM(credit), 0) as total_credit
            FROM ecritures_periode
            GROUP BY compte_id, numero, nom, type
            ORDER BY type, numero
        """, (structure_id, date_debut, date_fin))
        
        if not result:
            return {
                'charges': [],
                'produits': [],
                'total_charges': 0,
                'total_produits': 0,
                'resultat': 0,
                'resultat_text': 'Bénéfice'
            }
        
        charges = []
        produits = []
        total_charges = 0
        total_produits = 0
        
        for row in result:
            try:
                if isinstance(row, str):
                    print(f"⚠️ La requête a retourné une chaîne: {row[:100]}...")
                    continue
                
                if hasattr(row, '_mapping'):
                    row_dict = dict(row._mapping)
                    type_compte = row_dict.get('type')
                    numero = row_dict.get('numero')
                    nom = row_dict.get('nom')
                    total_debit = float(row_dict.get('total_debit', 0))
                    total_credit = float(row_dict.get('total_credit', 0))
                elif hasattr(row, 'type'):
                    type_compte = row.type
                    numero = row.numero
                    nom = row.nom
                    total_debit = float(row.total_debit or 0)
                    total_credit = float(row.total_credit or 0)
                elif isinstance(row, dict):
                    type_compte = row.get('type')
                    numero = row.get('numero')
                    nom = row.get('nom')
                    total_debit = float(row.get('total_debit', 0))
                    total_credit = float(row.get('total_credit', 0))
                elif isinstance(row, (list, tuple)):
                    if len(row) >= 6:
                        type_compte = row[3]
                        numero = row[1]
                        nom = row[2]
                        total_debit = float(row[4] or 0)
                        total_credit = float(row[5] or 0)
                    else:
                        continue
                else:
                    print(f"⚠️ Format de row non reconnu: {type(row)}")
                    continue
                
                if type_compte == 'charge':
                    solde = total_debit - total_credit
                    total_charges += solde
                    charges.append({
                        'numero': numero,
                        'nom': nom,
                        'montant': solde
                    })
                else:  # produit
                    solde = total_credit - total_debit
                    total_produits += solde
                    produits.append({
                        'numero': numero,
                        'nom': nom,
                        'montant': solde
                    })
            except Exception as e:
                print(f"⚠️ Erreur lors du traitement d'une ligne: {e}")
                continue
        
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
        import traceback
        traceback.print_exc()
        return {
            'charges': [],
            'produits': [],
            'total_charges': 0,
            'total_produits': 0,
            'resultat': 0,
            'resultat_text': 'Bénéfice'
        }


def get_bilan(structure_id, date_fin):
    """Génère le bilan (Actif = Passif + Capitaux propres)"""
    try:
        result = db.execute_query("""
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
                WHERE e.structure_id = %s
                AND e.statut = 'valide'
                AND e.date_ecriture <= %s
            )
            SELECT 
                compte_id,
                numero,
                nom,
                type,
                COALESCE(SUM(debit), 0) as total_debit,
                COALESCE(SUM(credit), 0) as total_credit
            FROM ecritures_bilan
            GROUP BY compte_id, numero, nom, type
            ORDER BY type, numero
        """, (structure_id, date_fin))
        
        if not result:
            return {
                'actifs': [],
                'passifs': [],
                'capitaux_propres': [],
                'total_actif': 0,
                'total_passif': 0,
                'total_capitaux': 0,
                'total_passif_capitaux': 0,
                'est_equilibre': True
            }
        
        actifs = []
        passifs = []
        capitaux_propres = []
        
        total_actif = 0
        total_passif = 0
        total_capitaux = 0
        
        for row in result:
            try:
                if isinstance(row, str):
                    print(f"⚠️ La requête a retourné une chaîne: {row[:100]}...")
                    continue
                
                if hasattr(row, '_mapping'):
                    row_dict = dict(row._mapping)
                    type_compte = row_dict.get('type')
                    numero = row_dict.get('numero')
                    nom = row_dict.get('nom')
                    total_debit = float(row_dict.get('total_debit', 0))
                    total_credit = float(row_dict.get('total_credit', 0))
                elif hasattr(row, 'type'):
                    type_compte = row.type
                    numero = row.numero
                    nom = row.nom
                    total_debit = float(row.total_debit or 0)
                    total_credit = float(row.total_credit or 0)
                elif isinstance(row, dict):
                    type_compte = row.get('type')
                    numero = row.get('numero')
                    nom = row.get('nom')
                    total_debit = float(row.get('total_debit', 0))
                    total_credit = float(row.get('total_credit', 0))
                elif isinstance(row, (list, tuple)):
                    if len(row) >= 6:
                        type_compte = row[3]
                        numero = row[1]
                        nom = row[2]
                        total_debit = float(row[4] or 0)
                        total_credit = float(row[5] or 0)
                    else:
                        continue
                else:
                    print(f"⚠️ Format de row non reconnu: {type(row)}")
                    continue
                
                if type_compte == 'actif':
                    solde = total_debit - total_credit
                    total_actif += solde
                    actifs.append({
                        'numero': numero,
                        'nom': nom,
                        'montant': solde
                    })
                elif type_compte == 'passif':
                    solde = total_credit - total_debit
                    total_passif += solde
                    passifs.append({
                        'numero': numero,
                        'nom': nom,
                        'montant': solde
                    })
                else:  # charge ou produit
                    solde = total_credit - total_debit
                    if solde > 0:
                        total_capitaux += solde
                        capitaux_propres.append({
                            'numero': numero,
                            'nom': nom,
                            'montant': solde
                        })
            except Exception as e:
                print(f"⚠️ Erreur traitement ligne: {e}")
                continue
        
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
        import traceback
        traceback.print_exc()
        return {
            'actifs': [],
            'passifs': [],
            'capitaux_propres': [],
            'total_actif': 0,
            'total_passif': 0,
            'total_capitaux': 0,
            'total_passif_capitaux': 0,
            'est_equilibre': True
        }


def init_plan_comptable(structure_id):
    """Initialise le plan comptable standard pour une structure"""
    
    comptes_standard = [
        {'numero': '211', 'nom': 'Caisse', 'type': 'actif'},
        {'numero': '212', 'nom': 'Banque', 'type': 'actif'},
        {'numero': '213', 'nom': 'Caisse d\'avance', 'type': 'actif'},
        {'numero': '214', 'nom': 'Dépôts et cautionnements', 'type': 'actif'},
        {'numero': '411', 'nom': 'Clients', 'type': 'actif'},
        {'numero': '412', 'nom': 'Clients - Effets à recevoir', 'type': 'actif'},
        {'numero': '413', 'nom': 'Clients - Douteux', 'type': 'actif'},
        {'numero': '414', 'nom': 'Clients - Autres', 'type': 'actif'},
        {'numero': '421', 'nom': 'Fournisseurs', 'type': 'passif'},
        {'numero': '422', 'nom': 'Fournisseurs - Effets à payer', 'type': 'passif'},
        {'numero': '611', 'nom': 'Salaires et traitements', 'type': 'charge'},
        {'numero': '612', 'nom': 'Charges sociales', 'type': 'charge'},
        {'numero': '613', 'nom': 'Loyers', 'type': 'charge'},
        {'numero': '614', 'nom': 'Électricité, eau, gaz', 'type': 'charge'},
        {'numero': '615', 'nom': 'Entretien et réparations', 'type': 'charge'},
        {'numero': '616', 'nom': 'Fournitures de bureau', 'type': 'charge'},
        {'numero': '617', 'nom': 'Frais de déplacement', 'type': 'charge'},
        {'numero': '618', 'nom': 'Frais de communication', 'type': 'charge'},
        {'numero': '619', 'nom': 'Honoraires et consultations', 'type': 'charge'},
        {'numero': '621', 'nom': 'Assurances', 'type': 'charge'},
        {'numero': '622', 'nom': 'Impôts et taxes', 'type': 'charge'},
        {'numero': '623', 'nom': 'Publicité et promotion', 'type': 'charge'},
        {'numero': '624', 'nom': 'Frais bancaires', 'type': 'charge'},
        {'numero': '625', 'nom': 'Amortissements et provisions', 'type': 'charge'},
        {'numero': '631', 'nom': 'Achats de matériel médical', 'type': 'charge'},
        {'numero': '632', 'nom': 'Achats de médicaments', 'type': 'charge'},
        {'numero': '633', 'nom': 'Achats de fournitures médicales', 'type': 'charge'},
        {'numero': '711', 'nom': 'Ventes d\'actes médicaux', 'type': 'produit'},
        {'numero': '712', 'nom': 'Ventes de pharmacie', 'type': 'produit'},
        {'numero': '713', 'nom': 'Ventes de lunettes', 'type': 'produit'},
        {'numero': '714', 'nom': 'Consultations', 'type': 'produit'},
        {'numero': '715', 'nom': 'Hospitalisation', 'type': 'produit'},
        {'numero': '716', 'nom': 'Examens de laboratoire', 'type': 'produit'},
        {'numero': '717', 'nom': 'Imagerie médicale', 'type': 'produit'},
        {'numero': '718', 'nom': 'Autres produits', 'type': 'produit'},
        {'numero': '721', 'nom': 'Subventions et dons', 'type': 'produit'},
        {'numero': '722', 'nom': 'Remboursements d\'assurances', 'type': 'produit'},
    ]
    
    for compte in comptes_standard:
        existing = CompteComptable.query.filter_by(
            structure_id=structure_id,
            numero=compte['numero']
        ).first()
        
        if not existing:
            nouveau_compte = CompteComptable(
                structure_id=structure_id,
                numero=compte['numero'],
                nom=compte['nom'],
                type=compte['type']
            )
            db.session.add(nouveau_compte)
    
    db.session.commit()
    return True


@compta_bp.route('/api/init-comptes', methods=['POST'])
def api_init_comptes():
    """Initialise le plan comptable standard"""
    structure_id = session.get('structure_id')
    result = init_plan_comptable(structure_id)
    return jsonify({'success': result})


def cloture_annuelle(structure_id, annee):
    """Verrouille les écritures d'une année"""
    try:
        # Vérifier si déjà clôturé
        existing = Cloture.query.filter_by(
            structure_id=structure_id,
            annee=annee
        ).first()
        
        if existing:
            return {'success': False, 'error': 'Cette année est déjà clôturée'}
        
        date_debut = f"{annee}-01-01"
        date_fin = f"{annee}-12-31"
        
        # Récupérer les écritures de l'année
        ecritures = EcritureComptable.query.filter(
            EcritureComptable.structure_id == structure_id,
            EcritureComptable.date_ecriture >= date_debut,
            EcritureComptable.date_ecriture <= date_fin,
            EcritureComptable.statut == 'valide'
        ).all()
        
        nb_ecritures = 0
        
        # Marquer les écritures comme clôturées
        for ecriture in ecritures:
            ecriture.cloturee = True
            ecriture.date_cloture = date.today()
            nb_ecritures += 1
        
        # Enregistrer la clôture
        cloture = Cloture(
            structure_id=structure_id,
            annee=annee,
            date_cloture=date.today(),
            created_by=session.get('user_name', 'System'),
            nb_ecritures=nb_ecritures
        )
        db.session.add(cloture)
        db.session.commit()
        
        return {'success': True, 'message': f'Clôture de l\'année {annee} effectuée avec succès ({nb_ecritures} écritures)'}
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur cloture_annuelle: {e}")
        return {'success': False, 'error': str(e)}


@compta_bp.route('/api/cloture', methods=['POST'])
def api_cloture():
    """Clôture une année"""
    structure_id = session.get('structure_id')
    annee = request.json.get('annee')
    
    if not annee:
        return jsonify({'error': 'Année requise'}), 400
    
    result = cloture_annuelle(structure_id, int(annee))
    return jsonify(result)


# ============================================================
# RAPPROCHEMENT BANCAIRE - ROUTES COMPLÈTES
# ============================================================

@compta_bp.route('/api/rapprochement/releves', methods=['GET'])
def api_get_releves():
    """Récupère tous les relevés bancaires"""
    try:
        structure_id = session.get('structure_id')
        
        if not structure_id:
            return jsonify({'error': 'Structure non trouvée'}), 400
        
        releves = ReleveBancaire.query.filter_by(structure_id=structure_id).order_by(ReleveBancaire.date_releve.desc()).all()
        
        result = []
        for r in releves:
            result.append({
                'id': r.id,
                'date_releve': r.date_releve.strftime('%Y-%m-%d'),
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
        
    except Exception as e:
        print(f"❌ Erreur api_get_releves: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/rapprochement/releves/<int:releve_id>')
def api_get_releve(releve_id):
    """Récupère un relevé bancaire spécifique"""
    try:
        structure_id = session.get('structure_id')
        
        if not structure_id:
            return jsonify({'error': 'Structure non trouvée'}), 400
        
        releve = ReleveBancaire.query.filter_by(id=releve_id, structure_id=structure_id).first()
        
        if not releve:
            return jsonify({'error': 'Relevé non trouvé'}), 404
        
        result = {
            'id': releve.id,
            'date_releve': releve.date_releve.strftime('%Y-%m-%d'),
            'solde_initial': float(releve.solde_initial),
            'solde_final': float(releve.solde_final),
            'total_credits': float(releve.total_credits) if releve.total_credits else 0,
            'total_debits': float(releve.total_debits) if releve.total_debits else 0,
            'statut': releve.statut,
            'created_by': releve.created_by or '-',
            'created_at': releve.created_at.strftime('%Y-%m-%d %H:%M') if releve.created_at else '',
            'valide_par': releve.valide_par or '-',
            'date_validation': releve.date_validation.strftime('%Y-%m-%d') if releve.date_validation else '',
            'commentaire': releve.commentaire or '',
            'nb_lignes': len(releve.lignes),
            'nb_rapproche': sum(1 for l in releve.lignes if l.rapproche)
        }
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur api_get_releve: {e}")
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/rapprochement/releves', methods=['POST'])
def api_creer_releve():
    """Crée un nouveau relevé bancaire"""
    try:
        data = request.json
        structure_id = session.get('structure_id')
        user_name = session.get('user_name', 'System')
        
        if not structure_id:
            return jsonify({'error': 'Structure non trouvée'}), 400
        
        # ✅ Conversion de la date dans tous les formats
        date_releve = parse_date(data.get('date_releve'))
        if not date_releve:
            return jsonify({'error': 'Format de date invalide'}), 400
        
        releve = ReleveBancaire(
            structure_id=structure_id,
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
            
            # ✅ Conversion de la date d'opération
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
        print(f"❌ Erreur api_creer_releve: {e}")
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/rapprochement/releves/<int:releve_id>/lignes')
def api_get_lignes_releve(releve_id):
    """Récupère les lignes d'un relevé"""
    try:
        structure_id = session.get('structure_id')
        
        if not structure_id:
            return jsonify({'error': 'Structure non trouvée'}), 400
        
        releve = ReleveBancaire.query.filter_by(id=releve_id, structure_id=structure_id).first()
        
        if not releve:
            return jsonify({'error': 'Relevé non trouvé'}), 404
        
        result = []
        for ligne in releve.lignes:
            result.append({
                'id': ligne.id,
                'date_operation': ligne.date_operation.strftime('%Y-%m-%d'),
                'libelle': ligne.libelle,
                'reference': ligne.reference or '',
                'debit': float(ligne.debit),
                'credit': float(ligne.credit),
                'solde': float(ligne.solde),
                'est_rapproche': ligne.rapproche,
                'ecriture_id': ligne.ecriture_id
            })
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur api_get_lignes_releve: {e}")
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/rapprochement/releves/<int:releve_id>/rapprocher', methods=['POST'])
def api_rapprocher_releve(releve_id):
    """Rapproche automatiquement les lignes du relevé avec les écritures comptables"""
    try:
        structure_id = session.get('structure_id')
        
        if not structure_id:
            return jsonify({'error': 'Structure non trouvée'}), 400
        
        releve = ReleveBancaire.query.filter_by(id=releve_id, structure_id=structure_id).first()
        
        if not releve:
            return jsonify({'error': 'Relevé non trouvé'}), 404
        
        compte_bancaire = CompteComptable.query.filter_by(
            structure_id=structure_id,
            numero='212'
        ).first()
        
        if not compte_bancaire:
            return jsonify({'error': 'Compte bancaire (212) non trouvé'}), 400
        
        ecritures = db.session.query(EcritureComptable, LigneEcriture).join(
            LigneEcriture, EcritureComptable.id == LigneEcriture.ecriture_id
        ).filter(
            EcritureComptable.structure_id == structure_id,
            EcritureComptable.statut == 'valide',
            LigneEcriture.compte_id == compte_bancaire.id
        ).order_by(EcritureComptable.date_ecriture).all()
        
        ecritures_dict = {}
        for ecriture, ligne in ecritures:
            montant = float(ligne.debit) if ligne.debit > 0 else float(ligne.credit)
            date_str = ecriture.date_ecriture.strftime('%Y-%m-%d')
            key = f"{date_str}_{montant}"
            if key not in ecritures_dict:
                ecritures_dict[key] = []
            ecritures_dict[key].append({
                'ecriture': ecriture,
                'ligne': ligne,
                'montant': montant
            })
        
        nb_rapproche = 0
        
        for ligne in releve.lignes:
            if ligne.rapproche:
                continue
            
            montant = float(ligne.debit) if ligne.debit > 0 else float(ligne.credit)
            date_str = ligne.date_operation.strftime('%Y-%m-%d')
            key = f"{date_str}_{montant}"
            
            if key in ecritures_dict and ecritures_dict[key]:
                match = ecritures_dict[key].pop(0)
                ligne.rapproche = True
                ligne.ecriture_id = match['ecriture'].id
                nb_rapproche += 1
        
        total_lignes = len(releve.lignes)
        total_rapproche = sum(1 for l in releve.lignes if l.rapproche)
        
        if total_rapproche == total_lignes and total_lignes > 0:
            releve.statut = 'en_attente'
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'nb_rapproche': nb_rapproche,
            'total_lignes': total_lignes,
            'total_rapproche': total_rapproche,
            'statut': releve.statut
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur api_rapprocher_releve: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@compta_bp.route('/api/rapprochement/releves/<int:releve_id>/valider', methods=['POST'])
def api_valider_releve(releve_id):
    """Valide un relevé bancaire rapproché"""
    try:
        structure_id = session.get('structure_id')
        user_name = session.get('user_name', 'System')
        
        if not structure_id:
            return jsonify({'error': 'Structure non trouvée'}), 400
        
        releve = ReleveBancaire.query.filter_by(id=releve_id, structure_id=structure_id).first()
        
        if not releve:
            return jsonify({'error': 'Relevé non trouvé'}), 404
        
        total_lignes = len(releve.lignes)
        total_rapproche = sum(1 for l in releve.lignes if l.rapproche)
        
        if total_lignes > 0 and total_rapproche < total_lignes:
            return jsonify({
                'error': f'Impossible de valider : {total_lignes - total_rapproche} ligne(s) non rapprochée(s)'
            }), 400
        
        releve.statut = 'valide'
        releve.valide_par = user_name
        releve.date_validation = date.today()
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Relevé validé avec succès'})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur api_valider_releve: {e}")
        return jsonify({'error': str(e)}), 500


def get_compte_bancaire(structure_id):
    """Récupère l'ID du compte bancaire (212)"""
    compte = CompteComptable.query.filter_by(
        structure_id=structure_id,
        numero='212'
    ).first()
    return compte.id if compte else None