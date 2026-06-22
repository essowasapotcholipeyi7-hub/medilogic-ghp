from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mail import Mail, Message
from config import Config
from sheets_helper import sheets_helper
import hashlib
import secrets
from datetime import datetime
from datetime import date
import json
import os
import pandas as pd
from io import BytesIO
from db_helper import db

# ========== DÉTECTION ENVIRONNEMENT ==========
IS_PRODUCTION = os.environ.get('RENDER') == 'true' or os.environ.get('PRODUCTION') == 'true'

if IS_PRODUCTION:
    BASE_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://medilogic-ghp.onrender.com')
else:
    BASE_URL = 'http://127.0.0.1:5000'

print(f"🔗 BASE_URL: {BASE_URL}")

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# ========== CONFIGURATION EMAIL ==========
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = app.config['MAIL_USERNAME']

# Vérification
if app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']:
    print("📧 Email configuré avec succès")
else:
    print("⚠️ Email non configuré (variables manquantes)")

mail = Mail(app)

# ========== FUNCTIONS ==========
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_next_id(records, id_field='ID'):
    """Génère un nouvel ID"""
    if not records:
        return 1
    try:
        max_id = 0
        for r in records:
            rid = r.get(id_field)
            if rid and str(rid).isdigit():
                max_id = max(max_id, int(rid))
        return max_id + 1
    except:
        return len(records) + 1

import threading

def envoyer_email_async(structure_nom, structure_email, structure_id, proprietaire):
    """Envoie l'email dans un thread séparé - ne bloque pas l'inscription"""
    def _send():
        try:
            sujet = f"🏥 Nouvelle inscription - {structure_nom}"
            
            lien_activation = f"{BASE_URL}/admin/activate/{structure_id}"
            lien_admin = f"{BASE_URL}/admin_global"
            
            corps = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; }}
                    .info {{ background: white; padding: 15px; border-radius: 8px; margin: 15px 0; }}
                    .btn {{ display: inline-block; background: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>🏥 Nouvelle inscription</h2>
                        <p>Medilogic-GHP</p>
                    </div>
                    <div class="content">
                        <h3>Une nouvelle structure s'est inscrite !</h3>
                        <div class="info">
                            <p><strong>🏥 Structure :</strong> {structure_nom}</p>
                            <p><strong>👤 Propriétaire :</strong> {proprietaire}</p>
                            <p><strong>📧 Email :</strong> {structure_email}</p>
                            <p><strong>📅 Date :</strong> {datetime.now().strftime('%d/%m/%Y à %H:%M')}</p>
                        </div>
                        <div style="text-align: center;">
                            <a href="{lien_activation}" class="btn" style="color: white; background: #28a745;">✅ Activer la structure</a>
                            <br><br>
                            <a href="{lien_admin}" style="color: #667eea;">📊 Aller à l'admin global</a>
                        </div>
                    </div>
                    <div class="footer">
                        <p>Medilogic-GHP - Application de gestion hospitalière</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            msg = Message(
                subject=sujet,
                recipients=[Config.ADMIN_EMAIL],
                html=corps
            )
            
            mail.send(msg)
            print(f"✅ Email d'activation envoyé à {Config.ADMIN_EMAIL}")
            
        except Exception as e:
            print(f"⚠️ Email non envoyé: {e}")
    
    thread = threading.Thread(target=_send)
    thread.daemon = True
    thread.start()
    print(f"📧 Envoi email en arrière-plan pour {structure_nom}")


# ========== LOGIN REQUIRED DECORATOR ==========
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter', 'warning')
            return redirect(url_for('index'))
        sheets_helper.set_structure(session.get('structure_id'))
        return f(*args, **kwargs)
    return decorated_function

# ========== ADMIN REQUIRED DECORATOR ==========
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter', 'warning')
            return redirect(url_for('index'))
        if not session.get('is_admin', False):
            flash('Accès non autorisé. Réservé à l\'administrateur.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        print("=" * 50)
        print(f"🔐 TENTATIVE DE CONNEXION")
        print(f"📧 Email: {email}")
        print("=" * 50)
        
        try:
            spreadsheet = sheets_helper.spreadsheet
            all_worksheets = spreadsheet.worksheets()
        except Exception as e:
            print(f"❌ Erreur accès Google Sheets: {e}")
            flash('Erreur de connexion à la base de données', 'danger')
            return redirect(url_for('index'))
        
        user_trouve = False
        mdp_ok = False
        
        # ========== 1. RECHERCHE DANS LES FEUILLES UTILISATEURS ==========
        for worksheet in all_worksheets:
            title = worksheet.title
            if title.endswith('_users'):
                print(f"📂 Vérification dans: {title}")
                
                try:
                    row_count = len(worksheet.get_all_values())
                    if row_count <= 1:
                        continue
                    
                    records = worksheet.get_all_records()
                    if not records:
                        continue
                        
                except Exception as e:
                    print(f"   ⚠️ Erreur lecture feuille: {e}")
                    continue
                
                for row in records:
                    if str(row.get('email')) == email:
                        user_trouve = True
                        print(f"✅ Utilisateur trouvé dans {title}")
                        
                        # Vérifier si compte actif
                        statut = row.get('actif', 'oui')
                        if statut != 'oui':
                            print("❌ Compte désactivé")
                            flash('Compte désactivé. Veuillez contacter l\'administrateur.', 'danger')
                            return redirect(url_for('index'))
                        
                        if row.get('mot_de_passe') == hash_password(password):
                            mdp_ok = True
                            print("✅ Mot de passe OK")
                            
                            # 🔥 METTRE À JOUR LA DERNIÈRE CONNEXION
                            try:
                                cell = worksheet.find(str(row.get('ID')), in_column=1)
                                if cell:
                                    row_num = cell.row
                                    current_row = worksheet.row_values(row_num)
                                    
                                    while len(current_row) < 9:
                                        current_row.append('')
                                    
                                    date_connexion = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                                    current_row[8] = date_connexion
                                    
                                    worksheet.update(range_name=f'A{row_num}:I{row_num}', values=[current_row])
                                    print(f"✅ Dernière connexion mise à jour: {date_connexion}")
                            except Exception as e:
                                print(f"⚠️ Erreur mise à jour dernière connexion: {e}")
                            
                            try:
                                structure_id = int(title.split('_')[1])
                            except:
                                structure_id = 1
                            
                            structures = sheets_helper.get_all_records('structures', use_prefix=False)
                            structure = next((s for s in structures if str(s.get('ID')) == str(structure_id)), {})
                            
                            if structure.get('statut') == 'active':
                                # 🔥 Récupérer le rôle
                                role = row.get('role', 'caissier')
                                
                                session['user_id'] = row.get('ID')
                                session['user_name'] = row.get('nom')
                                session['structure_id'] = structure_id
                                session['structure_nom'] = structure.get('nom')
                                session['structure_email'] = structure.get('email', '')
                                session['structure_logo'] = structure.get('logo_url', '')
                                session['structure_telephone'] = structure.get('telephone', '')
                                session['role'] = role  # 🔥 AJOUT DU RÔLE
                                session['is_admin'] = (role == 'admin')  # 🔥 ADMIN SI ROLE = 'admin'
                                
                                print(f"✅ Connexion réussie pour {row.get('nom')} (rôle: {role})")
                                flash(f'Bienvenue {row.get("nom")}', 'success')
                                return redirect(url_for('dashboard'))
                            else:
                                print("❌ Structure non active")
                                flash('Structure non activée', 'warning')
                                return redirect(url_for('index'))
                        else:
                            print("❌ Mot de passe incorrect")
                            flash('Mot de passe incorrect', 'danger')
                            return redirect(url_for('index'))
        
        # ========== 2. RECHERCHE DANS ADMIN GLOBAL ==========
        if not mdp_ok:
            structures = sheets_helper.get_all_records('structures', use_prefix=False)
            for structure in structures:
                if structure.get('email') == email:
                    user_trouve = True
                    if structure.get('mot_de_passe') == hash_password(password):
                        mdp_ok = True
                        if structure.get('statut') == 'active':
                            # Mettre à jour la connexion admin
                            try:
                                sheet_structures = sheets_helper.spreadsheet.worksheet("structures")
                                cell = sheet_structures.find(str(structure.get('ID')), in_column=1)
                                if cell:
                                    row_num = cell.row
                                    current_row = sheet_structures.row_values(row_num)
                                    while len(current_row) < 13:
                                        current_row.append('')
                                    current_row[12] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                                    sheet_structures.update(range_name=f'A{row_num}:M{row_num}', values=[current_row])
                            except:
                                pass
                            
                            session['user_id'] = structure.get('ID')
                            session['user_name'] = structure.get('nom')
                            session['structure_id'] = structure.get('ID')
                            session['structure_nom'] = structure.get('nom')
                            session['structure_email'] = structure.get('email', '')
                            session['structure_telephone'] = structure.get('telephone', '')
                            session['role'] = 'admin'
                            session['is_admin'] = True
                            
                            flash(f'Bienvenue {structure.get("nom")}', 'success')
                            return redirect(url_for('dashboard'))
                        else:
                            flash('Structure en attente d\'activation', 'warning')
                            return redirect(url_for('index'))
                    else:
                        flash('Mot de passe incorrect', 'danger')
                        return redirect(url_for('index'))
        
        # ========== 3. GESTION DES ERREURS ==========
        if not user_trouve:
            flash('Email non trouvé', 'danger')
        elif not mdp_ok:
            flash('Mot de passe incorrect', 'danger')
        
        return redirect(url_for('index'))
    
    return render_template('index.html')

# MODIFIER la route d'inscription

def valider_mot_de_passe(password):
    """Vérifie que le mot de passe respecte les règles de sécurité"""
    if len(password) < 8:
        return False, "Le mot de passe doit contenir au moins 8 caractères"
    
    if not any(c.isupper() for c in password):
        return False, "Le mot de passe doit contenir au moins une majuscule"
    
    if not any(c.islower() for c in password):
        return False, "Le mot de passe doit contenir au moins une minuscule"
    
    if not any(c.isdigit() for c in password):
        return False, "Le mot de passe doit contenir au moins un chiffre"
    
    caracteres_speciaux = "!@#$%^&*()_+-=[]{}|;:,.<>?/"
    if not any(c in caracteres_speciaux for c in password):
        return False, "Le mot de passe doit contenir au moins un symbole (!@#$%^&*...)"
    
    return True, "OK"

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        structure_name = request.form.get('structure_name')
        proprietaire_nom = request.form.get('proprietaire_nom')
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # VALIDATION DU MOT DE PASSE
        valide, message = valider_mot_de_passe(password)
        if not valide:
            flash(message, 'danger')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Les mots de passe ne correspondent pas', 'danger')
            return redirect(url_for('register'))
        
        structures = sheets_helper.get_all_records('structures', use_prefix=False)
        
        # Trouver le prochain ID
        new_id = 1
        for s in structures:
            if s.get('ID', 0) >= new_id:
                new_id = s.get('ID') + 1
        
        # Créer la structure
        new_structure = [
            new_id,
            structure_name,
            email,
            phone,
            address,
            hash_password(password),
            'pending',
            secrets.token_hex(16),
            datetime.now().isoformat(),
            proprietaire_nom,
            ''
        ]
        
        sheets_helper.add_record('structures', new_structure, use_prefix=False)
        sheets_helper.init_structure_sheets(new_id)
        
        # 🔥 ENVOYER L'EMAIL EN ARRIÈRE-PLAN 🔥
        envoyer_email_async(structure_name, email, new_id, proprietaire_nom)
        
        flash(f'Structure "{structure_name}" créée avec succès ! En attente d\'activation.', 'success')
        return redirect(url_for('index'))
    
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    structure_id = session.get('structure_id')
    
    # ========== PATIENTS (depuis Neon) ==========
    patients = db.execute_query("""
        SELECT COUNT(*) as total FROM patients WHERE structure_id = %s
    """, (structure_id,))
    total_patients = patients[0]['total'] if patients else 0
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # ========== VENTES ACTES ==========
    ventes_actes = sheets_helper.get_all_records('ventes_actes')
    ventes_actes_filtrees = [v for v in ventes_actes if str(v.get('structure_id')) == str(structure_id)]
    
    actes_today = 0
    ca_actes_today = 0
    
    for v in ventes_actes_filtrees:
        date_vente = v.get('date', '')
        if date_vente and date_vente.startswith(today):
            actes_today += 1
            ca_actes_today += float(v.get('net_a_payer', 0))
    
    # ========== VENTES PHARMACIE ==========
    ventes_pharma = sheets_helper.get_all_records('ventes_pharma')
    ventes_pharma_filtrees = [v for v in ventes_pharma if str(v.get('structure_id')) == str(structure_id)]
    
    # DEBUG - Afficher dans la console
    print(f"\n📊 DASHBOARD DEBUG")
    print(f"Structure ID: {structure_id}")
    print(f"Ventes pharmacie totales pour cette structure: {len(ventes_pharma_filtrees)}")
    
    ventes_pharma_today = 0
    ca_pharma_today = 0
    
    for v in ventes_pharma_filtrees:
        date_vente = v.get('date', '')
        if date_vente and date_vente.startswith(today):
            ventes_pharma_today += 1
            ca_pharma_today += float(v.get('net_a_payer', 0))
            print(f"  - Vente pharma du jour: {date_vente} - {v.get('net_a_payer')} FCFA")
    
    # ========== CA TOTAL ==========
    ca_today = ca_actes_today + ca_pharma_today
    
    print(f"Ventes pharma aujourd'hui: {ventes_pharma_today}")
    print(f"CA pharma aujourd'hui: {ca_pharma_today} FCFA")
    print(f"CA total aujourd'hui: {ca_today} FCFA")
    
    # ========== ACTIVITÉS RÉCENTES ==========
    toutes_ventes = []
    
    for v in ventes_actes_filtrees:
        toutes_ventes.append({
            'id': v.get('ID'),
            'type': 'actes',
            'patient_nom': v.get('patient_nom', 'Patient'),
            'date': v.get('date', ''),
            'montant': float(v.get('net_a_payer', 0))
        })
    
    for v in ventes_pharma_filtrees:
        toutes_ventes.append({
            'id': v.get('ID'),
            'type': 'pharma',
            'patient_nom': v.get('patient_nom', 'Patient'),
            'date': v.get('date', ''),
            'montant': float(v.get('net_a_payer', 0))
        })
    
    toutes_ventes.sort(key=lambda x: x.get('date', ''), reverse=True)
    recentes = toutes_ventes[:10]
    
    return render_template('dashboard.html',
                         total_patients=total_patients,
                         actes_today=actes_today,
                         ventes_pharma_today=ventes_pharma_today,
                         ca_today=ca_today,
                         recentes=recentes)

@app.route('/debug_pharma')
@login_required
def debug_pharma():
    structure_id = session.get('structure_id')
    
    ventes_pharma = sheets_helper.get_all_records('ventes_pharma')
    
    result = {
        'structure_id': structure_id,
        'total_ventes_pharma': len(ventes_pharma),
        'ventes': []
    }
    
    for v in ventes_pharma:
        result['ventes'].append({
            'id': v.get('ID'),
            'structure_id': v.get('structure_id'),
            'date': v.get('date'),
            'net_a_payer': v.get('net_a_payer'),
            'type_date': type(v.get('date')).__name__,
            'type_net': type(v.get('net_a_payer')).__name__
        })
    
    return jsonify(result)

# MODIFIER la route des patients pour utiliser le bon format
@app.route('/patients')
@login_required
def patients():
    structure_id = session.get('structure_id')
    
    if not structure_id:
        flash('Structure non trouvée', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        patients = db.execute_query("""
            SELECT id, nom, prenom, telephone, adresse, date_naissance,
                   type_assurance, taux_prise_charge, numero_assure
            FROM patients 
            WHERE structure_id = %s 
            ORDER BY id DESC
        """, (structure_id,))
        
        patients_list = []
        if patients:
            for p in patients:
                if isinstance(p, dict):
                    date_naissance = p.get('date_naissance')
                    patients_list.append({
                        'ID': p.get('id'),
                        'nom': p.get('nom', ''),
                        'prenom': p.get('prenom', ''),
                        'telephone': p.get('telephone', ''),
                        'adresse': p.get('adresse', ''),
                        'date_naissance': date_naissance.strftime('%Y-%m-%d') if date_naissance else '',
                        'age': calculer_age(date_naissance) if date_naissance else None,
                        'type_assurance': p.get('type_assurance', 'non_assure'),
                        'taux_prise_charge': p.get('taux_prise_charge', 0),
                        'numero_assure': p.get('numero_assure', '')
                    })
                else:
                    date_naissance = p[5] if len(p) > 5 else None
                    patients_list.append({
                        'ID': p[0],
                        'nom': p[1] or '',
                        'prenom': p[2] or '',
                        'telephone': p[3] or '',
                        'adresse': p[4] or '',
                        'date_naissance': date_naissance.strftime('%Y-%m-%d') if date_naissance else '',
                        'age': calculer_age(date_naissance) if date_naissance else None,
                        'type_assurance': p[6] or 'non_assure',
                        'taux_prise_charge': p[7] or 0,
                        'numero_assure': p[8] or ''
                    })
        
        return render_template('patients.html', patients=patients_list)
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        flash(f'Erreur: {str(e)}', 'error')
        return render_template('patients.html', patients=[])

@app.route('/api/patients', methods=['POST'])
@login_required
def api_add_patient():
    try:
        data = request.json
        structure_id = session.get('structure_id') or 1
        
        result = db.execute_query("""
            INSERT INTO patients (structure_id, nom, prenom, telephone, adresse, 
                                  date_naissance, type_assurance, taux_prise_charge, numero_assure)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            structure_id,
            data.get('nom'),
            data.get('prenom', ''),
            data.get('telephone'),
            data.get('adresse', ''),
            data.get('date_naissance', ''),
            data.get('type_assurance', 'non_assure'),
            data.get('taux_prise_charge', 0),
            data.get('numero_assure', '')
        ))
        
        # Commit explicite
        if db.conn:
            db.conn.commit()
        
        if result and len(result) > 0:
            return jsonify({'success': True, 'id': result[0]['id']})
        else:
            return jsonify({'success': False, 'error': 'Erreur insertion'}), 500
        
    except Exception as e:
        if db.conn:
            db.conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/patients', methods=['GET'])
@login_required
def api_get_patients():
    """Récupérer tous les patients de la structure"""
    try:
        structure_id = session.get('structure_id')
        
        patients = db.execute_query("""
            SELECT id, nom, prenom, telephone, adresse, date_naissance,
                   type_assurance, taux_prise_charge, numero_assure
            FROM patients 
            WHERE structure_id = %s 
            ORDER BY nom, prenom
        """, (structure_id,))
        
        result = []
        for p in patients:
            if isinstance(p, dict):
                date_naissance = p.get('date_naissance')
                result.append({
                    'id': p.get('id'),
                    'nom': p.get('nom', ''),
                    'prenom': p.get('prenom', ''),
                    'telephone': p.get('telephone', ''),
                    'adresse': p.get('adresse', ''),
                    'date_naissance': date_naissance.strftime('%Y-%m-%d') if date_naissance else '',
                    'type_assurance': p.get('type_assurance', 'non_assure'),
                    'taux_prise_charge': p.get('taux_prise_charge', 0),
                    'numero_assure': p.get('numero_assure', '')
                })
            else:
                date_naissance = p[5] if len(p) > 5 else None
                result.append({
                    'id': p[0],
                    'nom': p[1] if len(p) > 1 else '',
                    'prenom': p[2] if len(p) > 2 else '',
                    'telephone': p[3] if len(p) > 3 else '',
                    'adresse': p[4] if len(p) > 4 else '',
                    'date_naissance': date_naissance.strftime('%Y-%m-%d') if date_naissance else '',
                    'type_assurance': p[6] if len(p) > 6 else 'non_assure',
                    'taux_prise_charge': p[7] if len(p) > 7 else 0,
                    'numero_assure': p[8] if len(p) > 8 else ''
                })
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur GET patients: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([]), 500

@app.route('/api/patients/<int:id>', methods=['GET'])
@login_required
def api_get_patient(id):
    try:
        structure_id = session.get('structure_id')
        
        patient = db.execute_query("""
            SELECT id, nom, prenom, telephone, adresse, date_naissance,
                   type_assurance, taux_prise_charge, numero_assure
            FROM patients 
            WHERE id = %s AND structure_id = %s
        """, (id, structure_id))
        
        if not patient or len(patient) == 0:
            return jsonify({'success': False, 'error': 'Patient non trouvé'}), 404
        
        if isinstance(patient[0], dict):
            p = patient[0]
            date_naissance = p.get('date_naissance')
            result = {
                'id': p.get('id'),
                'nom': p.get('nom', ''),
                'prenom': p.get('prenom', ''),
                'telephone': p.get('telephone', ''),
                'adresse': p.get('adresse', ''),
                'date_naissance': date_naissance.strftime('%Y-%m-%d') if date_naissance else '',
                'age': calculer_age(date_naissance) if date_naissance else None,
                'type_assurance': p.get('type_assurance', 'non_assure'),
                'taux_prise_charge': p.get('taux_prise_charge', 0),
                'numero_assure': p.get('numero_assure', '')
            }
        else:
            p = patient[0]
            date_naissance = p[5] if len(p) > 5 else None
            result = {
                'id': p[0],
                'nom': p[1],
                'prenom': p[2],
                'telephone': p[3],
                'adresse': p[4],
                'date_naissance': date_naissance.strftime('%Y-%m-%d') if date_naissance else '',
                'age': calculer_age(date_naissance) if date_naissance else None,
                'type_assurance': p[6] if len(p) > 6 else 'non_assure',
                'taux_prise_charge': p[7] if len(p) > 7 else 0,
                'numero_assure': p[8] if len(p) > 8 else ''
            }
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur GET patient: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ROUTE de vérification (pour debug)
@app.route('/check_sheets')
@login_required
def check_sheets():
    """Vérifier les feuilles de la structure"""
    try:
        patients = sheets_helper.get_all_records('patients')
        actes = sheets_helper.get_all_records('actes')
        produits = sheets_helper.get_all_records('produits')
        
        return jsonify({
            'structure_prefix': sheets_helper.structure_prefix,
            'structure_id': session.get('structure_id'),
            'patients_count': len(patients),
            'actes_count': len(actes),
            'produits_count': len(produits),
            'patients': patients[:5]  # 5 premiers patients
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/actes_vente')
@login_required
def actes_vente():
    # 🔥 Lire depuis Google Sheets (pas Neon)
    actes = sheets_helper.get_all_records('actes')
    patients = sheets_helper.get_all_records('patients')
    
    print(f"🔍 Actes trouvés dans Sheets: {len(actes)}")
    
    return render_template('actes_vente.html', actes=actes, patients=patients)
@app.route('/pharma_vente')
@login_required
def pharma_vente():
    # 🔥 Lire les produits depuis Google Sheets
    produits = sheets_helper.get_all_records('produits')
    
    # Filtrer par structure
    structure_id = session.get('structure_id')
    produits_filtres = [p for p in produits if str(p.get('structure_id')) == str(structure_id)]
    
    patients = sheets_helper.get_all_records('patients')
    
    print(f"🔍 Produits trouvés dans Sheets: {len(produits_filtres)}")
    
    return render_template('pharma_vente.html', produits=produits_filtres, patients=patients)

@app.route('/facture/<int:vente_id>/<string:type>')
@login_required
def facture(vente_id, type):
    from datetime import datetime
    import json
    
    structure_id = session.get('structure_id')
    
    # Récupérer les infos de la structure depuis Google Sheets
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    structure_info = next((s for s in structures if str(s.get('ID')) == str(structure_id)), {})
    
    articles = []
    sous_total = 0
    taux_assurance = 0
    prise_en_charge = 0
    net_a_payer = 0
    patient_nom = 'Patient'
    mode_paiement = 'Espèces'
    type_assurance = 'non_assure'
    numero_assure = ''
    patient_id = None
    
    # 🔥 Lire depuis NEON
    vente = db.execute_query("""
        SELECT v.*, p.nom, p.prenom, p.type_assurance, p.numero_assure
        FROM ventes v
        LEFT JOIN patients p ON v.patient_id = p.id
        WHERE v.id = %s AND v.structure_id = %s AND v.type = %s
    """, (vente_id, structure_id, type))
    
    if not vente or len(vente) == 0:
        return f"Vente {vente_id} non trouvée", 404
    
    if isinstance(vente[0], dict):
        v = vente[0]
        patient_nom = v.get('patient_nom', '')
        if not patient_nom:
            patient_nom = f"{v.get('nom', '')} {v.get('prenom', '')}".strip()
        if not patient_nom:
            patient_nom = 'Patient'
        
        patient_id = v.get('patient_id')
        mode_paiement = v.get('mode_paiement', 'Espèces')
        taux_assurance = float(v.get('taux_assurance', 0))
        prise_en_charge = float(v.get('prise_en_charge', 0))
        net_a_payer = float(v.get('net_a_payer', 0))
        sous_total = float(v.get('sous_total', 0))
        type_assurance = v.get('type_assurance', 'non_assure')
        numero_assure = v.get('numero_assure', '')
        
        # Récupérer les articles avec prix unitaire
        if type == 'actes':
            actes_data = v.get('actes', [])
            if isinstance(actes_data, str):
                actes_data = json.loads(actes_data)
            for a in actes_data:
                articles.append({
                    'nom': a.get('nom', 'Acte'),
                    'quantite': int(a.get('quantite', 1)),
                    'prix_unitaire': float(a.get('prix', 0)),
                    'total': float(a.get('total', 0))
                })
        else:  # pharmacie
            produits_data = v.get('produits', [])
            if isinstance(produits_data, str):
                produits_data = json.loads(produits_data)
            for p in produits_data:
                articles.append({
                    'nom': p.get('nom', 'Produit'),
                    'quantite': int(p.get('quantite', 1)),
                    'prix_unitaire': float(p.get('prix_reel', p.get('prix', 0))),
                    'total': float(p.get('total', 0))
                })
    else:
        # Format tuple
        v = vente[0]
        patient_nom = v[2] if len(v) > 2 and v[2] else ''
        if not patient_nom and len(v) > 12:
            patient_nom = f"{v[12] or ''} {v[13] or ''}".strip()
        if not patient_nom:
            patient_nom = 'Patient'
        
        patient_id = v[1] if len(v) > 1 else None
        mode_paiement = v[7] if len(v) > 7 else 'Espèces'
        taux_assurance = float(v[10]) if len(v) > 10 else 0
        prise_en_charge = float(v[5]) if len(v) > 5 else 0
        net_a_payer = float(v[6]) if len(v) > 6 else 0
        sous_total = float(v[4]) if len(v) > 4 else 0
        type_assurance = v[14] if len(v) > 14 else 'non_assure'
        numero_assure = v[15] if len(v) > 15 else ''
        
        # Récupérer les articles
        if type == 'actes' and len(v) > 10:
            actes_data = v[10]
            if isinstance(actes_data, str):
                actes_data = json.loads(actes_data)
            for a in actes_data:
                articles.append({
                    'nom': a.get('nom', 'Acte'),
                    'quantite': int(a.get('quantite', 1)),
                    'prix_unitaire': float(a.get('prix', 0)),
                    'total': float(a.get('total', 0))
                })
        elif type == 'pharmacie' and len(v) > 11:
            produits_data = v[11]
            if isinstance(produits_data, str):
                produits_data = json.loads(produits_data)
            for p in produits_data:
                articles.append({
                    'nom': p.get('nom', 'Produit'),
                    'quantite': int(p.get('quantite', 1)),
                    'prix_unitaire': float(p.get('prix_reel', p.get('prix', 0))),
                    'total': float(p.get('total', 0))
                })
    
    # Gestion des assurances personnalisées
    assurance_text = 'Non assuré'
    if type_assurance == 'amu_cnss':
        assurance_text = 'AMU-CNSS'
    elif type_assurance == 'amu_inam':
        assurance_text = 'AMU-INAM'
    elif type_assurance == 'autre':
        assurance_text = 'Autre assurance'
    elif type_assurance and type_assurance not in ['non_assure', 'amu_cnss', 'amu_inam', 'autre']:
        assurance_text = type_assurance
    
    # Générer un nom de fichier
    patient_nom_clean = patient_nom.replace(' ', '_').replace("'", "").replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('à', 'a').replace('ç', 'c')
    nom_fichier = f"facture_client_{patient_nom_clean}_{vente_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    structure_logo = structure_info.get('logo_url', '')
    nom_caissier = session.get('user_name', '')
    
    # 🔥 Récupérer l'email de la structure pour la facture
    structure_email = structure_info.get('email', 'contact@medilogic.com')
    
    return render_template('facture_client.html',
                         vente_id=vente_id,
                         articles=articles,
                         sous_total=sous_total,
                         taux_assurance=taux_assurance,
                         prise_en_charge=prise_en_charge,
                         net_a_payer=net_a_payer,
                         patient_nom=patient_nom,
                         type_assurance=assurance_text,
                         numero_assure=numero_assure,
                         mode_paiement=mode_paiement,
                         structure_nom=structure_info.get('nom', 'Medilogic-GHP'),
                         structure_adresse=structure_info.get('adresse', ''),
                         structure_telephone=structure_info.get('telephone', ''),
                         structure_email=structure_email,
                         date_actuelle=datetime.now().strftime('%d/%m/%Y %H:%M'),
                         nom_fichier=nom_fichier,
                         structure_logo=structure_logo,
                         nom_caissier=nom_caissier)

@app.route('/admin_global')
def admin_global():
    # 🔥 Vérifier si l'admin est connecté
    if 'super_admin' not in session:
        return redirect(url_for('admin_login'))
    
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    return render_template('admin_global.html', structures=structures)

@app.route('/admin/activate/<int:structure_id>')
def activate_structure(structure_id):
    """Activer une structure"""
    try:
        sheet_structures = sheets_helper.spreadsheet.worksheet("structures")
        
        # Trouver la ligne de la structure
        cell = sheet_structures.find(str(structure_id), in_column=1)
        
        if cell:
            row_num = cell.row
            # Lire toutes les valeurs de la ligne
            current_row = sheet_structures.row_values(row_num)
            
            # Modifier le statut (colonne 7 = index 6)
            if len(current_row) > 6:
                current_row[6] = 'active'  # statut = actif
            
            # Mettre à jour la ligne entière
            sheet_structures.update(f'A{row_num}:K{row_num}', [current_row])
            flash(f'Structure {structure_id} activée avec succès', 'success')
        else:
            flash(f'Structure {structure_id} non trouvée', 'danger')
    except Exception as e:
        flash(f'Erreur: {str(e)}', 'danger')
    
    return redirect(url_for('admin_global'))

@app.route('/admin/suspend/<int:structure_id>')
def suspend_structure(structure_id):
    """Suspendre une structure"""
    try:
        sheet_structures = sheets_helper.spreadsheet.worksheet("structures")
        
        # Trouver la ligne de la structure
        cell = sheet_structures.find(str(structure_id), in_column=1)
        
        if cell:
            row_num = cell.row
            # Lire toutes les valeurs de la ligne
            current_row = sheet_structures.row_values(row_num)
            
            # Modifier le statut (colonne 7 = index 6)
            if len(current_row) > 6:
                current_row[6] = 'suspended'  # statut = suspendu
            
            # Mettre à jour la ligne entière
            sheet_structures.update(f'A{row_num}:K{row_num}', [current_row])
            flash(f'Structure {structure_id} suspendue', 'warning')
        else:
            flash(f'Structure {structure_id} non trouvée', 'danger')
    except Exception as e:
        flash(f'Erreur: {str(e)}', 'danger')
    
    return redirect(url_for('admin_global'))

@app.route('/admin/delete/<int:structure_id>')
def delete_structure(structure_id):
    """Supprimer une structure"""
    try:
        sheet_structures = sheets_helper.spreadsheet.worksheet("structures")
        
        # Trouver la ligne de la structure
        cell = sheet_structures.find(str(structure_id), in_column=1)
        
        if cell:
            sheet_structures.delete_row(cell.row)
            flash(f'Structure {structure_id} supprimée', 'info')
        else:
            flash(f'Structure {structure_id} non trouvée', 'danger')
    except Exception as e:
        flash(f'Erreur: {str(e)}', 'danger')
    
    return redirect(url_for('admin_global'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Déconnecté', 'info')
    return redirect(url_for('index'))

@app.route('/test_sheets')
def test_sheets():
    try:
        structures = sheets_helper.get_all_records('structures', use_prefix=False)
        return jsonify({"status": "success", "count": len(structures), "data": structures})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/structures/disponibles', methods=['GET'])
def get_structures_disponibles():
    """Retourne la liste des structures disponibles"""
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    disponibles = [s for s in structures if s.get('statut') == 'disponible']
    return jsonify(disponibles)

@app.route('/recu/<int:vente_id>/<string:type>')
@login_required
def recu(vente_id, type):
    from datetime import datetime
    import json
    
    structure_id = session.get('structure_id')
    
    if not structure_id:
        return "Structure non trouvée", 404
    
    # Récupérer les infos de la structure
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    structure_info = next((s for s in structures if str(s.get('ID')) == str(structure_id)), {})
    
    structure_nom = structure_info.get('nom', 'Medilogic-GHP')
    structure_adresse = structure_info.get('adresse', '')
    structure_telephone = structure_info.get('telephone', '')
    structure_email = structure_info.get('email', '')  # 🔥 AJOUT
    structure_logo = structure_info.get('logo_url', '')
    
    articles = []
    sous_total = 0
    taux_assurance = 0
    prise_en_charge = 0
    net_a_payer = 0
    patient_nom = 'Patient'
    mode_paiement = 'Espèces'
    type_assurance = 'non_assure'
    numero_assure = ''
    
    # 🔥 CORRECTION : Accepter 'pharma' et 'pharmacie'
    type_bd = 'pharmacie' if type == 'pharma' else type
    
    print(f"🔍 Recherche vente {vente_id} (type reçu: {type}, type BD: {type_bd})")
    
    # 🔥 Lire depuis NEON avec le bon type
    vente = db.execute_query("""
        SELECT v.*, p.nom, p.prenom, p.type_assurance, p.numero_assure
        FROM ventes v
        LEFT JOIN patients p ON v.patient_id = p.id
        WHERE v.id = %s AND v.structure_id = %s AND v.type = %s
    """, (vente_id, structure_id, type_bd))
    
    if not vente or len(vente) == 0:
        return f"Vente {vente_id} non trouvée (type: {type_bd})", 404
    
    if isinstance(vente[0], dict):
        v = vente[0]
        patient_nom = v.get('patient_nom', '')
        if not patient_nom:
            patient_nom = f"{v.get('nom', '')} {v.get('prenom', '')}".strip()
        if not patient_nom:
            patient_nom = 'Patient'
        
        mode_paiement = v.get('mode_paiement', 'Espèces')
        taux_assurance = float(v.get('taux_assurance', 0))
        prise_en_charge = float(v.get('prise_en_charge', 0))
        net_a_payer = float(v.get('net_a_payer', 0))
        sous_total = float(v.get('sous_total', 0))
        type_assurance = v.get('type_assurance', 'non_assure')
        numero_assure = v.get('numero_assure', '')
        
        # Récupérer les produits
        if type_bd == 'pharmacie' or type_bd == 'pharma':
            produits_data = v.get('produits', [])
            if isinstance(produits_data, str):
                produits_data = json.loads(produits_data)
            for p in produits_data:
                articles.append({
                    'nom': p.get('nom', 'Produit'),
                    'quantite': int(p.get('quantite', 1)),
                    'prix_unitaire': float(p.get('prix_reel', p.get('prix', 0))),
                    'total': float(p.get('total', 0))
                })
        else:  # actes
            actes_data = v.get('actes', [])
            if isinstance(actes_data, str):
                actes_data = json.loads(actes_data)
            for a in actes_data:
                articles.append({
                    'nom': a.get('nom', 'Acte'),
                    'quantite': int(a.get('quantite', 1)),
                    'prix_unitaire': float(a.get('prix', 0)),
                    'total': float(a.get('total', 0))
                })
    
    # Gestion des assurances
    assurance_text = type_assurance
    if type_assurance == 'amu_cnss':
        assurance_text = 'AMU-CNSS'
    elif type_assurance == 'amu_inam':
        assurance_text = 'AMU-INAM'
    elif type_assurance == 'non_assure':
        assurance_text = 'Non assuré'
    
    print(f"=== REÇU {vente_id} ({type_bd}) ===")
    print(f"Patient: {patient_nom}")
    print(f"Articles: {len(articles)}")
    
    return render_template('recu_client.html',
                         vente_id=vente_id,
                         articles=articles,
                         sous_total=sous_total,
                         taux_assurance=taux_assurance,
                         prise_en_charge=prise_en_charge,
                         net_a_payer=net_a_payer,
                         patient_nom=patient_nom,
                         type_assurance=assurance_text,
                         numero_assure=numero_assure,
                         mode_paiement=mode_paiement,
                         structure_nom=structure_nom,
                         structure_adresse=structure_adresse,
                         structure_telephone=structure_telephone,
                         structure_email=structure_email,  # 🔥 AJOUT
                         date_actuelle=datetime.now().strftime('%d/%m/%Y %H:%M'),
                         structure_logo=structure_logo,
                         nom_caissier=session.get('user_name', ''))

@app.route('/historique_ventes')
@login_required
def historique_ventes():
    """Affiche l'historique des ventes avec stats"""
    structure_id = session.get('structure_id')
    
    # ========== 1. VENTES D'ACTES (Google Sheets) ==========
    ventes_actes = sheets_helper.get_all_records('ventes_actes')
    ventes_actes_filtrees = []
    for v in ventes_actes:
        if str(v.get('structure_id')) == str(structure_id):
            v['type'] = 'actes'
            v['acte_nom'] = v.get('acte_nom', 'Acte')
            date_val = v.get('date', '')
            v['date'] = str(date_val) if date_val else ''
            ventes_actes_filtrees.append(v)
    
    # ========== 2. VENTES PHARMACIE (Neon - exclure annulées) ==========
    ventes_pharma_db = db.execute_query("""
        SELECT 
            id, patient_nom, net_a_payer, taux_assurance, 
            date_vente, produits, created_by_nom
        FROM ventes 
        WHERE structure_id = %s 
        AND type IN ('pharma', 'pharmacie')
        AND (statut IS NULL OR statut != 'annulee')
        ORDER BY date_vente DESC
    """, (structure_id,))
    
    ventes_pharma = []
    for v in ventes_pharma_db:
        if isinstance(v, dict):
            import json
            produits_data = v.get('produits')
            if isinstance(produits_data, str):
                try:
                    produits_data = json.loads(produits_data)
                except:
                    produits_data = []
            
            nom_produit = 'Produit'
            if produits_data and len(produits_data) > 0:
                nom_produit = produits_data[0].get('nom', 'Produit')
            
            ventes_pharma.append({
                'ID': v.get('id'),
                'patient_nom': v.get('patient_nom', 'Patient'),
                'type': 'pharma',
                'acte_nom': nom_produit,
                'produit_nom': nom_produit,
                'net_a_payer': float(v.get('net_a_payer', 0)),
                'taux_assurance': v.get('taux_assurance', 0),
                'date': str(v.get('date_vente', '')),
                'created_by_nom': v.get('created_by_nom', 'System')
            })
    
    # ========== 3. FUSIONNER ET TRIER ==========
    toutes_ventes = ventes_actes_filtrees + ventes_pharma
    
    def get_date_key(x):
        date_val = x.get('date', '')
        return str(date_val) if date_val else ''
    
    toutes_ventes.sort(key=get_date_key, reverse=True)
    
    # ========== 4. STATISTIQUES ==========
    total_actes = len([v for v in ventes_actes_filtrees if str(v.get('structure_id')) == str(structure_id)])
    total_pharma = len([v for v in ventes_pharma if str(v.get('structure_id')) == str(structure_id)])
    
    # CA total = somme des net_a_payer (exclut annulées car filtrées)
    ca_total = sum([float(v.get('net_a_payer', 0)) for v in toutes_ventes])
    
    # Top actes
    actes_count = {}
    for v in ventes_actes_filtrees:
        nom = v.get('acte_nom', 'Acte')
        quantite = int(v.get('quantite', 1))
        total = float(v.get('total', 0))
        if nom not in actes_count:
            actes_count[nom] = {'quantite': 0, 'total': 0}
        actes_count[nom]['quantite'] += quantite
        actes_count[nom]['total'] += total
    
    top_actes = sorted(actes_count.items(), key=lambda x: x[1]['quantite'], reverse=True)[:5]
    top_actes_list = [{'nom': k, 'quantite': v['quantite'], 'total': v['total']} for k, v in top_actes]
    
    # Top produits
    produits_count = {}
    for v in ventes_pharma:
        nom = v.get('produit_nom', 'Produit')
        quantite = 1
        total = v.get('net_a_payer', 0)
        if nom not in produits_count:
            produits_count[nom] = {'quantite': 0, 'total': 0}
        produits_count[nom]['quantite'] += quantite
        produits_count[nom]['total'] += total
    
    top_produits = sorted(produits_count.items(), key=lambda x: x[1]['quantite'], reverse=True)[:5]
    top_produits_list = [{'nom': k, 'quantite': v['quantite'], 'total': v['total']} for k, v in top_produits]
    
    stats = {
        'total_ventes': len(toutes_ventes),
        'total_actes': total_actes,
        'total_pharma': total_pharma,
        'ca_total': ca_total,
        'top_actes': top_actes_list,
        'top_produits': top_produits_list
    }
    
    return render_template('historique_ventes.html', ventes=toutes_ventes, stats=stats)

# ========== ADMIN STRUCTURE API ==========
@app.route('/api/admin/users', methods=['POST'])
@login_required
def api_add_user():
    try:
        data = request.json
        structure_id = session.get('structure_id')
        
        sheet_name = f"struct_{structure_id}_users"
        
        # Récupérer la feuille
        try:
            worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
        except:
            # Si la feuille n'existe pas, la créer
            worksheet = sheets_helper.spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=10)
            # Ajouter les en-têtes
            headers = ['ID', 'nom', 'email', 'mot_de_passe', 'role', 'structure_id', 'created_at', 'actif']
            worksheet.append_row(headers)
        
        user_id = data.get('id')
        
        if user_id and user_id != '' and user_id != 'null' and user_id != 0:
            # Modification
            print(f"✏️ Modification ID: {user_id}")
            cell = worksheet.find(str(user_id), in_column=1)
            if cell:
                row_num = cell.row
                current_row = worksheet.row_values(row_num)
                while len(current_row) < 9:
                    current_row.append('')
                current_row[1] = data.get('nom')
                current_row[2] = data.get('email')
                if data.get('password') and data.get('password').strip():
                    current_row[3] = hash_password(data.get('password'))
                current_row[4] = data.get('role')
                current_row[7] = data.get('actif', 'oui')
                # current_row[8] = dernière connexion (ne pas toucher)

                worksheet.update(range_name=f'A{row_num}:H{row_num}', values=[current_row])
                return jsonify({'success': True, 'id': user_id})
            else:
                return jsonify({'success': False, 'error': 'Utilisateur non trouvé'}), 404
        else:
            # Ajout
            print(f"➕ Ajout nouvel utilisateur")
            all_records = worksheet.get_all_records()
            existing_ids = [int(r.get('ID', 0)) for r in all_records if r.get('ID')]
            new_id = max(existing_ids) + 1 if existing_ids else 1
            
            new_user = [
                new_id,
                data.get('nom'),
                data.get('email'),
                hash_password(data.get('password', 'default123')),
                data.get('role', 'caissier'),
                structure_id,
                datetime.now().isoformat(),
                data.get('actif', 'oui'),
                ''  # dernière connexion (vide)
            ]
            worksheet.append_row(new_user)
            return jsonify({'success': True, 'id': new_id})
            
    except Exception as e:
        print(f"Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/users/<int:user_id>/toggle', methods=['POST'])
@login_required
def api_toggle_user(user_id):
    """Activer/Désactiver un utilisateur"""
    try:
        data = request.json
        structure_id = session.get('structure_id')
        nouveau_statut = data.get('actif', 'non')
        
        sheet_name = f"struct_{structure_id}_users"
        worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
        
        # Trouver l'utilisateur
        cell = worksheet.find(str(user_id), in_column=1)
        if not cell:
            return jsonify({'success': False, 'error': 'Utilisateur non trouvé'}), 404
        
        row_num = cell.row
        current_row = worksheet.row_values(row_num)
        
        print(f"Ligne actuelle: {current_row}")
        print(f"Nombre de colonnes: {len(current_row)}")
        
        # Ajouter la colonne actif si elle n'existe pas
        if len(current_row) < 9:
            # Étendre la ligne jusqu'à la colonne I
            while len(current_row) < 9:
                current_row.append('')
        
        # Mettre à jour la colonne actif (index 7 = colonne H)
        current_row[7] = nouveau_statut
        
        # 🔥 Correction : update avec les bons paramètres
        worksheet.update(range_name=f'A{row_num}:I{row_num}', values=[current_row])
        
        return jsonify({'success': True, 'message': f'Statut mis à jour'})
        
    except Exception as e:
        print(f"Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@login_required
def api_delete_user(user_id):
    """Supprimer un utilisateur"""
    try:
        structure_id = session.get('structure_id')
        sheet_name = f"struct_{structure_id}_users"
        
        print(f"Recherche dans la feuille: {sheet_name}")
        
        # Récupérer la feuille
        worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
        
        # Chercher l'utilisateur
        cell = worksheet.find(str(user_id), in_column=1)
        
        if cell:
            print(f"Utilisateur trouvé à la ligne {cell.row}, suppression...")
            # 🔥 Utiliser delete_rows au lieu de delete_row
            worksheet.delete_rows(cell.row)
            return jsonify({'success': True, 'message': 'Utilisateur supprimé'})
        else:
            print(f"Utilisateur {user_id} non trouvé")
            return jsonify({'success': False, 'error': 'Utilisateur non trouvé'}), 404
            
    except Exception as e:
        print(f"Erreur suppression: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin_structure')
@login_required
def admin_structure():
    """Administration de la structure"""
    structure_id = session.get('structure_id')

    # Récupérer les utilisateurs avec la dernière connexion
    sheet_name = f"struct_{structure_id}_users"
    users = sheets_helper.get_all_records(sheet_name)
    
    users_list = []
    for u in users:
        users_list.append({
            'ID': u.get('ID'),
            'nom': u.get('nom'),
            'email': u.get('email'),
            'role': u.get('role'),
            'actif': u.get('actif', 'oui'),
            'derniere_connexion': u.get('derniere_connexion', '-'),
            'created_at': u.get('created_at', '')
        })
    
    # Récupérer les utilisateurs
    users = sheets_helper.get_all_records('users')
    users = [u for u in users if str(u.get('structure_id')) == str(structure_id)]
    
    # Récupérer les actes
    actes = sheets_helper.get_all_records('actes')
    actes = [a for a in actes if str(a.get('structure_id')) == str(structure_id)]
    
    # Récupérer les produits
    produits = sheets_helper.get_all_records('produits')
    produits = [p for p in produits if str(p.get('structure_id')) == str(structure_id)]
    
    # Récupérer les infos de la structure
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    structure_info = next((s for s in structures if str(s.get('ID')) == str(structure_id)), {})
    
    return render_template('admin_structure.html', 
                         users=users, 
                         actes=actes, 
                         produits=produits,
                         structure_info=structure_info)

@app.route('/api/admin/actes', methods=['POST'])
@login_required
def api_add_acte():
    """Ajouter ou modifier un acte dans Neon"""
    try:
        data = request.json
        structure_id = session.get('structure_id')
        
        if not structure_id:
            return jsonify({'success': False, 'error': 'Structure non trouvée'}), 400
        
        acte_id = data.get('id')
        
        if acte_id:
            # 🔥 MODIFICATION dans Neon
            db.execute_query("""
                UPDATE actes 
                SET nom = %s, prix = %s, description = %s, code = %s
                WHERE id = %s AND structure_id = %s
            """, (
                data.get('nom'),
                data.get('prix'),
                data.get('description', ''),
                data.get('code', ''),
                acte_id,
                structure_id
            ))
            print(f"✅ Acte {acte_id} modifié dans Neon")
        else:
            # 🔥 AJOUT dans Neon
            result = db.execute_query("""
                INSERT INTO actes (structure_id, code, nom, prix, description)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (
                structure_id,
                data.get('code', ''),
                data.get('nom'),
                data.get('prix'),
                data.get('description', '')
            ))
            
            if result and len(result) > 0:
                new_id = result[0]['id'] if isinstance(result[0], dict) else result[0][0]
                print(f"✅ Nouvel acte ajouté dans Neon avec ID: {new_id}")
            else:
                return jsonify({'success': False, 'error': 'Erreur insertion'}), 500
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/actes/<int:acte_id>', methods=['DELETE'])
@login_required
def api_delete_acte(acte_id):
    """Supprimer un acte dans Neon"""
    try:
        structure_id = session.get('structure_id')
        
        db.execute_query("""
            DELETE FROM actes 
            WHERE id = %s AND structure_id = %s
        """, (acte_id, structure_id))
        
        print(f"✅ Acte {acte_id} supprimé de Neon")
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/produits/<int:produit_id>', methods=['DELETE'])
@login_required
def api_delete_produit(produit_id):
    # À implémenter
    return jsonify({'success': True})

@app.route('/api/admin/structure', methods=['PUT'])
@login_required
@admin_required
def api_update_structure():
    data = request.json
    structure_id = session.get('structure_id')
    
    try:
        sheet_structures = sheets_helper.spreadsheet.worksheet("structures")
        cell = sheet_structures.find(str(structure_id), in_column=1)
        
        if cell:
            row_num = cell.row
            current_row = sheet_structures.row_values(row_num)
            
            # 🔥 INDEX CORRECTS (0-based)
            # A=0, B=1, C=2, D=3, E=4, F=5, G=6, H=7, I=8, J=9, K=10, L=11, M=12...
            
            # Mettre à jour les colonnes
            current_row[1] = data.get('nom')           # colonne B (nom)
            current_row[2] = data.get('email')         # colonne C (email)
            current_row[3] = data.get('telephone')     # colonne D (téléphone)
            current_row[4] = data.get('adresse')       # colonne E (adresse)
            
            # 🔥 LOGO_URL à l'index 11 (colonne L)
            if len(current_row) > 11:
                current_row[11] = data.get('logo_url', '')
            else:
                while len(current_row) <= 11:
                    current_row.append('')
                current_row[11] = data.get('logo_url', '')
            
            # Mettre à jour jusqu'à la colonne M (index 12)
            sheet_structures.update(f'A{row_num}:M{row_num}', [current_row])
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Structure non trouvée'}), 404
            
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/reset_password/<int:structure_id>', methods=['POST'])
def reset_password(structure_id):
    """Réinitialiser le mot de passe d'une structure"""
    try:
        import hashlib
        data = request.json
        new_password = data.get('password', 'medilogic2026')
        
        # Hasher le nouveau mot de passe
        hashed_password = hashlib.sha256(new_password.encode()).hexdigest()
        
        # Mettre à jour dans Google Sheets
        sheet_structures = sheets_helper.spreadsheet.worksheet("structures")
        
        # Trouver la ligne de la structure
        cell = sheet_structures.find(str(structure_id), in_column=1)
        
        if cell:
            row_num = cell.row
            # Lire la ligne actuelle
            current_row = sheet_structures.row_values(row_num)
            # Modifier le mot de passe (colonne 6 = index 5)
            if len(current_row) > 5:
                current_row[5] = hashed_password
                # Mettre à jour la ligne
                sheet_structures.update(f'A{row_num}:K{row_num}', [current_row])
                print(f"✅ Mot de passe réinitialisé pour structure {structure_id}")
                return jsonify({'success': True, 'message': 'Mot de passe réinitialisé'})
            else:
                return jsonify({'success': False, 'error': 'Structure invalide'}), 400
        else:
            return jsonify({'success': False, 'error': 'Structure non trouvée'}), 404
            
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/debug_ventes')
@login_required
def debug_ventes():
    structure_id = session.get('structure_id')
    
    ventes_actes = sheets_helper.get_all_records('ventes_actes')
    ventes_pharma = sheets_helper.get_all_records('ventes_pharma')
    
    result = {
        'structure_id': structure_id,
        'ventes_actes': [],
        'ventes_pharma': []
    }
    
    for v in ventes_actes:
        if str(v.get('structure_id')) == str(structure_id):
            result['ventes_actes'].append({
                'ID': v.get('ID'),
                'patient_nom': v.get('patient_nom'),
                'date': v.get('date'),
                'total': v.get('total')
            })
    
    for v in ventes_pharma:
        if str(v.get('structure_id')) == str(structure_id):
            result['ventes_pharma'].append({
                'ID': v.get('ID'),
                'patient_nom': v.get('patient_nom'),
                'date': v.get('date'),
                'total': v.get('total')
            })
    
    return jsonify(result)

# ========== RECU STRUCTURE (COPIE) ==========
@app.route('/recu_structure/<int:vente_id>/<string:type>')
@login_required
def recu_structure(vente_id, type):
    """Reçu pour la structure (copie comptable) - Lecture depuis Neon"""
    from datetime import datetime
    import json
    
    structure_id = session.get('structure_id')
    
    # Récupérer les infos de la structure depuis Google Sheets
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    structure_info = next((s for s in structures if str(s.get('ID')) == str(structure_id)), {})
    
    articles = []
    sous_total = 0
    taux_assurance = 0
    prise_en_charge = 0
    net_a_payer = 0
    patient_nom = 'Patient'
    mode_paiement = 'Espèces'
    type_assurance = 'non_assure'
    patient_id = None
    
    # 🔥 Lire depuis NEON
    vente = db.execute_query("""
        SELECT v.*, p.nom, p.prenom, p.type_assurance, p.numero_assure
        FROM ventes v
        LEFT JOIN patients p ON v.patient_id = p.id
        WHERE v.id = %s AND v.structure_id = %s AND v.type = %s
    """, (vente_id, structure_id, type))
    
    if not vente or len(vente) == 0:
        return f"Vente {vente_id} non trouvée", 404
    
    if isinstance(vente[0], dict):
        v = vente[0]
        patient_nom = v.get('patient_nom', '')
        if not patient_nom:
            patient_nom = f"{v.get('nom', '')} {v.get('prenom', '')}".strip()
        if not patient_nom:
            patient_nom = 'Patient'
        
        patient_id = v.get('patient_id')
        mode_paiement = v.get('mode_paiement', 'Espèces')
        taux_assurance = float(v.get('taux_assurance', 0))
        prise_en_charge = float(v.get('prise_en_charge', 0))
        net_a_payer = float(v.get('net_a_payer', 0))
        sous_total = float(v.get('sous_total', 0))
        type_assurance = v.get('type_assurance', 'non_assure')
        
        # Récupérer les articles
        if type == 'actes':
            actes_data = v.get('actes', [])
            if isinstance(actes_data, str):
                actes_data = json.loads(actes_data)
            for a in actes_data:
                articles.append({
                    'nom': a.get('nom', 'Acte'),
                    'quantite': int(a.get('quantite', 1)),
                    'total': float(a.get('total', 0))
                })
        else:
            produits_data = v.get('produits', [])
            if isinstance(produits_data, str):
                produits_data = json.loads(produits_data)
            for p in produits_data:
                articles.append({
                    'nom': p.get('nom', 'Produit'),
                    'quantite': int(p.get('quantite', 1)),
                    'total': float(p.get('total', 0))
                })
    else:
        v = vente[0]
        patient_nom = v[2] if len(v) > 2 and v[2] else ''
        if not patient_nom and len(v) > 12:
            patient_nom = f"{v[12] or ''} {v[13] or ''}".strip()
        if not patient_nom:
            patient_nom = 'Patient'
        
        patient_id = v[1] if len(v) > 1 else None
        mode_paiement = v[7] if len(v) > 7 else 'Espèces'
        taux_assurance = float(v[10]) if len(v) > 10 else 0
        prise_en_charge = float(v[5]) if len(v) > 5 else 0
        net_a_payer = float(v[6]) if len(v) > 6 else 0
        sous_total = float(v[4]) if len(v) > 4 else 0
        type_assurance = v[14] if len(v) > 14 else 'non_assure'
        
        # Récupérer les articles
        if type == 'actes' and len(v) > 10:
            actes_data = v[10]
            if isinstance(actes_data, str):
                actes_data = json.loads(actes_data)
            for a in actes_data:
                articles.append({
                    'nom': a.get('nom', 'Acte'),
                    'quantite': int(a.get('quantite', 1)),
                    'total': float(a.get('total', 0))
                })
        elif type == 'pharmacie' and len(v) > 11:
            produits_data = v[11]
            if isinstance(produits_data, str):
                produits_data = json.loads(produits_data)
            for p in produits_data:
                articles.append({
                    'nom': p.get('nom', 'Produit'),
                    'quantite': int(p.get('quantite', 1)),
                    'total': float(p.get('total', 0))
                })
    
    # Gestion des assurances
    assurance_text = 'Non assuré'
    if type_assurance == 'amu_cnss':
        assurance_text = 'AMU-CNSS'
    elif type_assurance == 'amu_inam':
        assurance_text = 'AMU-INAM'
    elif type_assurance and type_assurance not in ['non_assure', 'amu_cnss', 'amu_inam']:
        assurance_text = type_assurance
    
    patient_nom_clean = patient_nom.replace(' ', '_').replace("'", "").replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('à', 'a').replace('ç', 'c')
    nom_fichier = f"recu_structure_{patient_nom_clean}_{vente_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    return render_template('recu_structure.html',
                         vente_id=vente_id,
                         articles=articles,
                         sous_total=sous_total,
                         taux_assurance=taux_assurance,
                         prise_en_charge=prise_en_charge,
                         net_a_payer=net_a_payer,
                         patient_nom=patient_nom,
                         type_assurance=assurance_text,
                         mode_paiement=mode_paiement,
                         structure_nom=structure_info.get('nom', 'Medilogic-GHP'),
                         date_actuelle=datetime.now().strftime('%d/%m/%Y %H:%M'),
                         nom_fichier=nom_fichier,
                         structure_logo=structure_info.get('logo_url', ''),
                         nom_caissier=session.get('user_name', ''))


@app.route('/facture_structure/<int:vente_id>/<string:type>')
@login_required
def facture_structure(vente_id, type):
    """Facture pour la structure (archive) - Lecture depuis Neon"""
    from datetime import datetime
    import json
    
    structure_id = session.get('structure_id')
    
    # Récupérer les infos de la structure depuis Google Sheets
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    structure_info = next((s for s in structures if str(s.get('ID')) == str(structure_id)), {})
    
    articles = []
    sous_total = 0
    taux_assurance = 0
    prise_en_charge = 0
    net_a_payer = 0
    patient_nom = 'Patient'
    mode_paiement = 'Espèces'
    type_assurance = 'non_assure'
    numero_assure = ''
    patient_id = None
    
    # 🔥 Lire depuis NEON
    vente = db.execute_query("""
        SELECT v.*, p.nom, p.prenom, p.type_assurance, p.numero_assure
        FROM ventes v
        LEFT JOIN patients p ON v.patient_id = p.id
        WHERE v.id = %s AND v.structure_id = %s AND v.type = %s
    """, (vente_id, structure_id, type))
    
    if not vente or len(vente) == 0:
        return f"Vente {vente_id} non trouvée", 404
    
    if isinstance(vente[0], dict):
        v = vente[0]
        patient_nom = v.get('patient_nom', '')
        if not patient_nom:
            patient_nom = f"{v.get('nom', '')} {v.get('prenom', '')}".strip()
        if not patient_nom:
            patient_nom = 'Patient'
        
        patient_id = v.get('patient_id')
        mode_paiement = v.get('mode_paiement', 'Espèces')
        taux_assurance = float(v.get('taux_assurance', 0))
        prise_en_charge = float(v.get('prise_en_charge', 0))
        net_a_payer = float(v.get('net_a_payer', 0))
        sous_total = float(v.get('sous_total', 0))
        type_assurance = v.get('type_assurance', 'non_assure')
        numero_assure = v.get('numero_assure', '')
        
        # Récupérer les articles avec prix unitaire
        if type == 'actes':
            actes_data = v.get('actes', [])
            if isinstance(actes_data, str):
                actes_data = json.loads(actes_data)
            for a in actes_data:
                articles.append({
                    'nom': a.get('nom', 'Acte'),
                    'quantite': int(a.get('quantite', 1)),
                    'prix_unitaire': float(a.get('prix', 0)),
                    'total': float(a.get('total', 0))
                })
        else:
            produits_data = v.get('produits', [])
            if isinstance(produits_data, str):
                produits_data = json.loads(produits_data)
            for p in produits_data:
                articles.append({
                    'nom': p.get('nom', 'Produit'),
                    'quantite': int(p.get('quantite', 1)),
                    'prix_unitaire': float(p.get('prix_reel', p.get('prix', 0))),
                    'total': float(p.get('total', 0))
                })
    else:
        v = vente[0]
        patient_nom = v[2] if len(v) > 2 and v[2] else ''
        if not patient_nom and len(v) > 12:
            patient_nom = f"{v[12] or ''} {v[13] or ''}".strip()
        if not patient_nom:
            patient_nom = 'Patient'
        
        patient_id = v[1] if len(v) > 1 else None
        mode_paiement = v[7] if len(v) > 7 else 'Espèces'
        taux_assurance = float(v[10]) if len(v) > 10 else 0
        prise_en_charge = float(v[5]) if len(v) > 5 else 0
        net_a_payer = float(v[6]) if len(v) > 6 else 0
        sous_total = float(v[4]) if len(v) > 4 else 0
        type_assurance = v[14] if len(v) > 14 else 'non_assure'
        numero_assure = v[15] if len(v) > 15 else ''
        
        # Récupérer les articles
        if type == 'actes' and len(v) > 10:
            actes_data = v[10]
            if isinstance(actes_data, str):
                actes_data = json.loads(actes_data)
            for a in actes_data:
                articles.append({
                    'nom': a.get('nom', 'Acte'),
                    'quantite': int(a.get('quantite', 1)),
                    'prix_unitaire': float(a.get('prix', 0)),
                    'total': float(a.get('total', 0))
                })
        elif type == 'pharmacie' and len(v) > 11:
            produits_data = v[11]
            if isinstance(produits_data, str):
                produits_data = json.loads(produits_data)
            for p in produits_data:
                articles.append({
                    'nom': p.get('nom', 'Produit'),
                    'quantite': int(p.get('quantite', 1)),
                    'prix_unitaire': float(p.get('prix_reel', p.get('prix', 0))),
                    'total': float(p.get('total', 0))
                })
    
    # Gestion des assurances
    assurance_text = 'Non assuré'
    if type_assurance == 'amu_cnss':
        assurance_text = 'AMU-CNSS'
    elif type_assurance == 'amu_inam':
        assurance_text = 'AMU-INAM'
    elif type_assurance and type_assurance not in ['non_assure', 'amu_cnss', 'amu_inam']:
        assurance_text = type_assurance
    
    patient_nom_clean = patient_nom.replace(' ', '_').replace("'", "").replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('à', 'a').replace('ç', 'c')
    nom_fichier = f"facture_structure_{patient_nom_clean}_{vente_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    return render_template('facture_structure.html',
                         vente_id=vente_id,
                         articles=articles,
                         sous_total=sous_total,
                         taux_assurance=taux_assurance,
                         prise_en_charge=prise_en_charge,
                         net_a_payer=net_a_payer,
                         patient_nom=patient_nom,
                         type_assurance=assurance_text,
                         numero_assure=numero_assure,
                         mode_paiement=mode_paiement,
                         structure_nom=structure_info.get('nom', 'Medilogic-GHP'),
                         structure_adresse=structure_info.get('adresse', ''),
                         structure_telephone=structure_info.get('telephone', ''),
                         date_actuelle=datetime.now().strftime('%d/%m/%Y %H:%M'),
                         nom_fichier=nom_fichier,
                         structure_logo=structure_info.get('logo_url', ''),
                         nom_caissier=session.get('user_name', ''))
                     

# ========== RENDEZ-VOUS ==========
@app.route('/rendez_vous')
@login_required
def rendez_vous():
    """Page de gestion des rendez-vous avec données depuis Neon"""
    structure_id = session.get('structure_id')
    
    # 🔥 Récupérer les patients depuis NEON
    patients = db.execute_query("""
        SELECT id, nom, prenom, telephone 
        FROM patients 
        WHERE structure_id = %s 
        ORDER BY nom
    """, (structure_id,))
    
    patients_list = []
    for p in patients:
        if isinstance(p, dict):
            patients_list.append({
                'ID': p.get('id'),
                'nom': f"{p.get('nom', '')} {p.get('prenom', '')}".strip(),
                'telephone': p.get('telephone', '')
            })
        else:
            patients_list.append({
                'ID': p[0],
                'nom': f"{p[1]} {p[2]}".strip(),
                'telephone': p[3] if len(p) > 3 else ''
            })
    
    # 🔥 Récupérer les rendez-vous depuis NEON
    rendez_vous = db.execute_query("""
        SELECT 
            r.id, 
            r.patient_id, 
            r.date_rdv, 
            r.heure_rdv, 
            r.motif, 
            r.statut,
            p.nom,
            p.prenom,
            p.telephone
        FROM rendez_vous r
        LEFT JOIN patients p ON r.patient_id = p.id
        WHERE r.structure_id = %s
        ORDER BY r.date_rdv DESC, r.heure_rdv DESC
    """, (structure_id,))
    
    rdv_list = []
    for r in rendez_vous:
        if isinstance(r, dict):
            rdv_list.append({
                'ID': r.get('id'),
                'patient_id': r.get('patient_id'),
                'patient_nom': f"{r.get('nom', '')} {r.get('prenom', '')}".strip(),
                'patient_telephone': r.get('telephone', ''),
                'date_rendez_vous': r.get('date_rdv'),
                'heure_rendez_vous': r.get('heure_rdv'),
                'motif': r.get('motif', ''),
                'statut': r.get('statut', 'programme')
            })
        else:
            rdv_list.append({
                'ID': r[0],
                'patient_id': r[1],
                'patient_nom': f"{r[6]} {r[7]}".strip() if len(r) > 7 else 'Patient',
                'patient_telephone': r[8] if len(r) > 8 else '',
                'date_rendez_vous': r[2],
                'heure_rendez_vous': r[3],
                'motif': r[4] if len(r) > 4 else '',
                'statut': r[5] if len(r) > 5 else 'programme'
            })
    
    # 🔥 Récupérer les infos de la structure pour le template
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    structure_info = next((s for s in structures if str(s.get('ID')) == str(structure_id)), {})
    
    return render_template('rendez_vous.html', 
                         patients=patients_list, 
                         rendez_vous=rdv_list,
                         structure_logo=structure_info.get('logo_url', ''),
                         structure_email=structure_info.get('email', ''),
                         structure_telephone=structure_info.get('telephone', ''),
                         structure_nom=structure_info.get('nom', 'Medilogic-GHP'))

@app.route('/api/rendez_vous', methods=['POST'])
@login_required
def api_add_rendez_vous():
    """Ajouter un rendez-vous dans Neon"""
    try:
        data = request.json
        structure_id = session.get('structure_id')
        
        print("=" * 60)
        print("📅 AJOUT RENDEZ-VOUS DANS NEON")
        print(f"Patient ID: {data.get('patient_id')}")
        print(f"Date: {data.get('date')}")
        print(f"Heure: {data.get('heure')}")
        print("=" * 60)
        
        if not structure_id:
            return jsonify({'success': False, 'error': 'Structure non trouvée'}), 400
        
        # 🔥 Insérer dans Neon
        result = db.execute_query("""
            INSERT INTO rendez_vous (
                patient_id, 
                structure_id, 
                date_rdv, 
                heure_rdv, 
                motif, 
                statut
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data.get('patient_id'),
            structure_id,
            data.get('date'),
            data.get('heure'),
            data.get('motif', 'Consultation'),
            'programme'
        ))
        
        if result and len(result) > 0:
            rdv_id = result[0]['id'] if isinstance(result[0], dict) else result[0][0]
            print(f"✅ Rendez-vous ajouté avec ID: {rdv_id}")
            return jsonify({'success': True, 'id': rdv_id})
        else:
            return jsonify({'success': False, 'error': 'Erreur insertion'}), 500
            
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rendez_vous/reporter', methods=['POST'])
@login_required
def api_reporter_rendez_vous():
    """Reporter un rendez-vous avec notification WhatsApp"""
    try:
        data = request.json
        rdv_id = data.get('rdv_id')
        nouvelle_date = data.get('nouvelle_date')
        nouvelle_heure = data.get('nouvelle_heure')
        nouveau_motif = data.get('motif', '')
        envoyer_rappel = data.get('envoyer_rappel', True)
        
        structure_id = session.get('structure_id')
        
        # 🔥 Récupérer le rendez-vous depuis Neon
        rdv = db.execute_query("""
            SELECT r.*, p.nom, p.prenom, p.telephone
            FROM rendez_vous r
            JOIN patients p ON r.patient_id = p.id
            WHERE r.id = %s AND r.structure_id = %s
        """, (rdv_id, structure_id))
        
        if not rdv or len(rdv) == 0:
            return jsonify({'success': False, 'error': 'Rendez-vous non trouvé'}), 404
        
        if isinstance(rdv[0], dict):
            r = rdv[0]
            patient_nom = f"{r.get('nom', '')} {r.get('prenom', '')}".strip()
            patient_tel = r.get('telephone', '')
            ancienne_date = r.get('date_rdv')
            ancienne_heure = r.get('heure_rdv')
        else:
            r = rdv[0]
            patient_nom = f"{r[8]} {r[9]}".strip() if len(r) > 9 else 'Patient'
            patient_tel = r[10] if len(r) > 10 else ''
            ancienne_date = r[3]
            ancienne_heure = r[4]
        
        # Récupérer les infos de la structure
        structures = sheets_helper.get_all_records('structures', use_prefix=False)
        structure_info = next((s for s in structures if str(s.get('ID')) == str(structure_id)), {})
        structure_nom = structure_info.get('nom', 'Medilogic-GHP')
        structure_tel = structure_info.get('telephone', '')
        
        # 🔥 Mettre à jour dans Neon
        db.execute_query("""
            UPDATE rendez_vous 
            SET date_rdv = %s, 
                heure_rdv = %s, 
                motif = %s, 
                statut = 'programme'
            WHERE id = %s AND structure_id = %s
        """, (nouvelle_date, nouvelle_heure, nouveau_motif or 'Consultation', rdv_id, structure_id))
        
        # Envoyer WhatsApp si demandé
        whatsapp_url = None
        if envoyer_rappel and patient_tel:
            tel = str(patient_tel).replace(' ', '').replace('+', '')
            if not tel.startswith('228') and not tel.startswith('229') and not tel.startswith('221'):
                tel = '228' + tel
            
            message = f"🔄 *REPORT DE RENDEZ-VOUS* 🔄%0A%0A"
            message += f"🏥 *{structure_nom}*%0A"
            if structure_tel:
                message += f"📞 {structure_tel}%0A%0A"
            message += f"Bonjour *{patient_nom}*,%0A%0A"
            message += f"Votre rendez-vous initialement prévu le *{ancienne_date}* à *{ancienne_heure}*%0A"
            message += f"a été reporté au :%0A"
            message += f"📅 *{nouvelle_date}*%0A"
            message += f"⏰ *{nouvelle_heure}*%0A%0A"
            if nouveau_motif:
                message += f"📋 Nouveau motif : {nouveau_motif}%0A%0A"
            message += f"📞 Pour toute question : {structure_tel}%0A%0A"
            message += f"Merci de votre compréhension. 🙏"
            
            whatsapp_url = f"https://wa.me/{tel}?text={message}"
        
        return jsonify({'success': True, 'whatsapp_url': whatsapp_url})
        
    except Exception as e:
        print(f"❌ Erreur report: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rendez_vous/<int:rdv_id>/rappel', methods=['POST'])
@login_required
def api_envoyer_rappel(rdv_id):
    """Envoyer un rappel WhatsApp"""
    try:
        structure_id = session.get('structure_id')
        
        # 🔥 Récupérer le rendez-vous depuis Neon
        rdv = db.execute_query("""
            SELECT r.*, p.nom, p.prenom, p.telephone
            FROM rendez_vous r
            JOIN patients p ON r.patient_id = p.id
            WHERE r.id = %s AND r.structure_id = %s
        """, (rdv_id, structure_id))
        
        if not rdv or len(rdv) == 0:
            return jsonify({'success': False, 'error': 'Rendez-vous non trouvé'}), 404
        
        if isinstance(rdv[0], dict):
            r = rdv[0]
            patient_nom = f"{r.get('nom', '')} {r.get('prenom', '')}".strip()
            patient_tel = r.get('telephone', '')
            date_rdv = r.get('date_rdv')
            heure_rdv = r.get('heure_rdv')
            motif = r.get('motif', 'Consultation')
        else:
            r = rdv[0]
            patient_nom = f"{r[8]} {r[9]}".strip() if len(r) > 9 else 'Patient'
            patient_tel = r[10] if len(r) > 10 else ''
            date_rdv = r[3]
            heure_rdv = r[4]
            motif = r[5] if len(r) > 5 else 'Consultation'
        
        # Récupérer les infos de la structure
        structures = sheets_helper.get_all_records('structures', use_prefix=False)
        structure_info = next((s for s in structures if str(s.get('ID')) == str(structure_id)), {})
        structure_nom = structure_info.get('nom', 'Medilogic-GHP')
        
        tel = str(patient_tel).replace(' ', '').replace('+', '')
        if not tel.startswith('228') and not tel.startswith('229') and not tel.startswith('221'):
            tel = '228' + tel
        
        message = f"🔔 *RAPPEL DE RENDEZ-VOUS* 🔔%0A%0A"
        message += f"🏥 *{structure_nom}*%0A%0A"
        message += f"Cher(e) *{patient_nom}*,%0A%0A"
        message += f"Nous vous rappelons votre rendez-vous :%0A"
        message += f"📅 Date : *{date_rdv}*%0A"
        message += f"⏰ Heure : *{heure_rdv}*%0A"
        message += f"📋 Motif : *{motif}*%0A%0A"
        message += f"Merci de votre ponctualité ! 🙏"
        
        whatsapp_url = f"https://wa.me/{tel}?text={message}"
        
        return jsonify({'success': True, 'whatsapp_url': whatsapp_url})
        
    except Exception as e:
        print(f"❌ Erreur rappel: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rendez_vous/<int:rdv_id>/confirmer', methods=['POST'])
@login_required
def api_confirmer_rendez_vous(rdv_id):
    """Confirmer un rendez-vous"""
    try:
        structure_id = session.get('structure_id')
        
        # 🔥 Mettre à jour dans Neon
        db.execute_query("""
            UPDATE rendez_vous 
            SET statut = 'confirme'
            WHERE id = %s AND structure_id = %s
        """, (rdv_id, structure_id))
        
        return jsonify({'success': True, 'message': 'Rendez-vous confirmé'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rendez_vous/<int:rdv_id>/annuler', methods=['POST'])
@login_required
def api_annuler_rendez_vous(rdv_id):
    """Annuler un rendez-vous"""
    try:
        structure_id = session.get('structure_id')
        
        # 🔥 Mettre à jour dans Neon
        db.execute_query("""
            UPDATE rendez_vous 
            SET statut = 'annule'
            WHERE id = %s AND structure_id = %s
        """, (rdv_id, structure_id))
        
        return jsonify({'success': True, 'message': 'Rendez-vous annulé'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rendez_vous/<int:rdv_id>/terminer', methods=['POST'])
@login_required
def api_terminer_rendez_vous(rdv_id):
    """Marquer un rendez-vous comme terminé"""
    try:
        structure_id = session.get('structure_id')
        
        # 🔥 Mettre à jour dans Neon
        db.execute_query("""
            UPDATE rendez_vous 
            SET statut = 'termine'
            WHERE id = %s AND structure_id = %s
        """, (rdv_id, structure_id))
        
        return jsonify({'success': True, 'message': 'Rendez-vous terminé'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/mes_rendez_vous')
@login_required
def mes_rendez_vous():
    """Page patient pour voir ses rendez-vous"""
    structure_id = session.get('structure_id')
    patient_id = session.get('patient_id')  # Si patient connecté
    
    # Récupérer les informations du patient
    patients = sheets_helper.get_all_records('patients')
    patient_info = next((p for p in patients if str(p.get('ID')) == str(patient_id)), {})
    
    # Récupérer les rendez-vous du patient
    rendez_vous = sheets_helper.get_all_records('rendez_vous')
    mes_rendez_vous = [r for r in rendez_vous 
                       if str(r.get('patient_id')) == str(patient_id) 
                       and str(r.get('structure_id')) == str(structure_id)]
    mes_rendez_vous.sort(key=lambda x: x.get('date_rendez_vous', ''))
    
    return render_template('mes_rendez_vous.html', 
                         patient_info=patient_info,
                         mes_rendez_vous=mes_rendez_vous,
                         today=datetime.now().strftime('%Y-%m-%d'))


@app.route('/patient/rendez_vous/<int:patient_id>/<token>')
def patient_rendez_vous(patient_id, token):
    """Page patient pour CONSULTER ses rendez-vous (lecture seule)"""
    from datetime import datetime
    
    try:
        # 🔥 Récupérer les infos du patient depuis NEON
        patient = db.execute_query("""
            SELECT id, nom, prenom, telephone, structure_id
            FROM patients 
            WHERE id = %s
        """, (patient_id,))
        
        if not patient or len(patient) == 0:
            return "Patient non trouvé", 404
        
        if isinstance(patient[0], dict):
            patient_info = patient[0]
            structure_id = patient_info.get('structure_id')
        else:
            patient_info = {
                'id': patient[0][0],
                'nom': patient[0][1],
                'prenom': patient[0][2],
                'telephone': patient[0][3]
            }
            structure_id = patient[0][4] if len(patient[0]) > 4 else None
        
        # 🔥 Récupérer la structure depuis Google Sheets (ou Neon)
        structures = sheets_helper.get_all_records('structures', use_prefix=False)
        structure_info = next((s for s in structures if str(s.get('ID')) == str(structure_id)), {})
        
        structure_nom = structure_info.get('nom', 'Notre établissement')
        structure_telephone = structure_info.get('telephone', '')
        structure_adresse = structure_info.get('adresse', '')
        
        # 🔥 Récupérer ses rendez-vous depuis NEON
        rendez_vous = db.execute_query("""
            SELECT id, date_rdv, heure_rdv, motif, statut, notes
            FROM rendez_vous
            WHERE patient_id = %s
            ORDER BY date_rdv DESC
        """, (patient_id,))
        
        mes_rendez_vous = []
        for r in rendez_vous:
            if isinstance(r, dict):
                mes_rendez_vous.append({
                    'id': r.get('id'),
                    'date_rendez_vous': r.get('date_rdv'),
                    'heure_rendez_vous': r.get('heure_rdv'),
                    'motif': r.get('motif'),
                    'statut': r.get('statut', 'programme')
                })
            else:
                mes_rendez_vous.append({
                    'id': r[0],
                    'date_rendez_vous': r[1],
                    'heure_rendez_vous': r[2],
                    'motif': r[3],
                    'statut': r[4] if len(r) > 4 else 'programme'
                })
        
        return render_template('patient_rendez_vous.html',
                             patient=patient_info,
                             rendez_vous=mes_rendez_vous,
                             structure_nom=structure_nom,
                             structure_telephone=structure_telephone,
                             structure_adresse=structure_adresse)
                             
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return f"Erreur: {e}", 500
@app.route('/api/structure/nom')
@login_required
def api_structure_nom():
    """Retourne le nom de la structure"""
    structure_id = session.get('structure_id')
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    structure_info = next((s for s in structures if s.get('ID') == structure_id), {})
    return jsonify({'nom': structure_info.get('nom', 'Medilogic-GHP')})

@app.route('/api/structure/infos')
@login_required
def api_structure_infos():
    structure_id = session.get('structure_id')
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    structure_info = next((s for s in structures if s.get('ID') == structure_id), {})
    return jsonify({
        'nom': structure_info.get('nom', ''),
        'telephone': structure_info.get('telephone', ''),
        'logo_url': structure_info.get('logo_url', ''),   # ← AJOUT
        'email': structure_info.get('email', '')          # ← AJOUT
    })
# ========== RAPPELS AUTOMATIQUES RENDEZ-VOUS ==========
import threading
import time
from datetime import datetime, timedelta

def envoyer_rappel_auto(rdv, type_rappel, structure_info):
    """Envoie un rappel automatique WhatsApp"""
    try:
        patient_nom = rdv.get('patient_nom', 'Patient')
        patient_tel = rdv.get('patient_telephone', '')
        date_rdv = rdv.get('date_rendez_vous', '')
        heure_rdv = rdv.get('heure_rendez_vous', '')
        motif = rdv.get('motif', 'Consultation')
        structure_nom = structure_info.get('nom', 'Notre établissement')
        structure_tel = structure_info.get('telephone', '')
        
        if not patient_tel:
            return False
        
        # Nettoyer le numéro
        tel = str(patient_tel).replace(' ', '').replace('+', '').replace('-', '')
        if not tel.startswith('228') and not tel.startswith('229') and not tel.startswith('221'):
            tel = '228' + tel
        
        if type_rappel == 'j7':
            message = f"🔔 *RAPPEL DE RENDEZ-VOUS (J-7)* 🔔%0A%0A"
            message += f"🏥 *{structure_nom}*%0A"
            if structure_tel:
                message += f"📞 {structure_tel}%0A%0A"
            message += f"Bonjour *{patient_nom}*,%0A%0A"
            message += f"Nous vous rappelons votre rendez-vous dans une semaine :%0A"
            message += f"📅 Date : *{date_rdv}*%0A"
            message += f"⏰ Heure : *{heure_rdv}*%0A"
            message += f"📋 Motif : *{motif}*%0A%0A"
            message += f"Merci de votre ponctualité ! 🙏"
        else:
            message = f"🔔 *RAPPEL DE RENDEZ-VOUS (J-1)* 🔔%0A%0A"
            message += f"🏥 *{structure_nom}*%0A"
            if structure_tel:
                message += f"📞 {structure_tel}%0A%0A"
            message += f"Bonjour *{patient_nom}*,%0A%0A"
            message += f"Nous vous rappelons votre rendez-vous de demain :%0A"
            message += f"📅 Date : *{date_rdv}*%0A"
            message += f"⏰ Heure : *{heure_rdv}*%0A"
            message += f"📋 Motif : *{motif}*%0A%0A"
            message += f"À très vite ! 🏥"
        
        whatsapp_url = f"https://wa.me/{tel}?text={message}"
        print(f"📱 [RAPPEL AUTO] {patient_nom} - {type_rappel}")
        print(f"   🔗 Lien WhatsApp: {whatsapp_url}")
        return True
        
    except Exception as e:
        print(f"❌ Erreur envoi rappel: {e}")
        return False

def maj_statut_rappel(rdv_id, type_rappel, structure_id):
    """Met à jour le statut du rappel dans Neon"""
    try:
        # 🔥 Mettre à jour dans Neon
        db.execute_query("""
            UPDATE rendez_vous 
            SET rappel_envoye = %s
            WHERE id = %s AND structure_id = %s
        """, (type_rappel, rdv_id, structure_id))
        return True
    except Exception as e:
        print(f"❌ Erreur maj statut: {e}")
        return False

def verifier_rappels_automatiques():
    """Vérifie les rendez-vous et envoie les rappels si nécessaire"""
    print(f"🔍 Vérification des rappels - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 🔥 Récupérer toutes les structures actives
        structures = db.execute_query("SELECT id, nom, telephone FROM structures")
        
        for struct in structures:
            if isinstance(struct, dict):
                structure_id = struct.get('id')
                structure_nom = struct.get('nom', 'Notre établissement')
                structure_tel = struct.get('telephone', '')
            else:
                structure_id = struct[0]
                structure_nom = struct[1] if len(struct) > 1 else 'Notre établissement'
                structure_tel = struct[2] if len(struct) > 2 else ''
            
            # 🔥 Récupérer les rendez-vous depuis Neon
            rendez_vous = db.execute_query("""
                SELECT 
                    r.id,
                    r.patient_id,
                    r.date_rdv,
                    r.heure_rdv,
                    r.motif,
                    r.statut,
                    r.rappel_envoye,
                    p.nom,
                    p.prenom,
                    p.telephone
                FROM rendez_vous r
                LEFT JOIN patients p ON r.patient_id = p.id
                WHERE r.structure_id = %s
            """, (structure_id,))
            
            aujourdhui = datetime.now().date()
            j7 = aujourdhui + timedelta(days=7)
            j1 = aujourdhui + timedelta(days=1)
            
            structure_info = {'nom': structure_nom, 'telephone': structure_tel}
            
            for r in rendez_vous:
                if isinstance(r, dict):
                    rdv_id = r.get('id')
                    date_rdv_val = r.get('date_rdv')
                    statut = r.get('statut', 'programme')
                    rappel_envoye = r.get('rappel_envoye', 'non')
                    patient_nom = f"{r.get('nom', '')} {r.get('prenom', '')}".strip()
                    patient_tel = r.get('telephone', '')
                    heure_rdv = r.get('heure_rdv')
                    motif = r.get('motif', 'Consultation')
                else:
                    rdv_id = r[0]
                    date_rdv_val = r[2]
                    statut = r[5] if len(r) > 5 else 'programme'
                    rappel_envoye = r[6] if len(r) > 6 else 'non'
                    patient_nom = f"{r[7]} {r[8]}".strip() if len(r) > 8 else 'Patient'
                    patient_tel = r[9] if len(r) > 9 else ''
                    heure_rdv = r[3]
                    motif = r[4] if len(r) > 4 else 'Consultation'
                
                if not date_rdv_val:
                    continue
                
                try:
                    if isinstance(date_rdv_val, str):
                        date_rdv = datetime.strptime(date_rdv_val, '%Y-%m-%d').date()
                    else:
                        date_rdv = date_rdv_val
                    
                    # Ignorer les rendez-vous déjà terminés ou annulés
                    if statut in ['termine', 'annule']:
                        continue
                    
                    rdv_data = {
                        'ID': rdv_id,
                        'patient_nom': patient_nom,
                        'patient_telephone': patient_tel,
                        'date_rendez_vous': str(date_rdv),
                        'heure_rendez_vous': str(heure_rdv),
                        'motif': motif,
                        'statut': statut,
                        'rappel_envoye': rappel_envoye
                    }
                    
                    # Rappel J-7
                    if date_rdv == j7 and rappel_envoye not in ['j7', 'j1']:
                        if envoyer_rappel_auto(rdv_data, 'j7', structure_info):
                            maj_statut_rappel(rdv_id, 'j7', structure_id)
                            print(f"   ✅ Rappel J-7 envoyé à {patient_nom} (struct {structure_id})")
                    
                    # Rappel J-1
                    elif date_rdv == j1 and rappel_envoye != 'j1':
                        if envoyer_rappel_auto(rdv_data, 'j1', structure_info):
                            maj_statut_rappel(rdv_id, 'j1', structure_id)
                            print(f"   ✅ Rappel J-1 envoyé à {patient_nom} (struct {structure_id})")
                    
                    # Gestion des rendez-vous dépassés
                    elif date_rdv < aujourdhui and statut not in ['termine', 'annule', 'depasse']:
                        db.execute_query("""
                            UPDATE rendez_vous 
                            SET statut = 'depasse'
                            WHERE id = %s AND structure_id = %s
                        """, (rdv_id, structure_id))
                        print(f"   📆 RDV {rdv_id} marqué comme dépassé")
                        
                except Exception as e:
                    print(f"   ⚠️ Erreur traitement RDV {rdv_id}: {e}")
                    
    except Exception as e:
        print(f"❌ Erreur vérification: {e}")

def planifier_verification():
    """Planifie la vérification toutes les heures"""
    print("🚀 Service de rappels automatiques démarré")
    while True:
        time.sleep(3600)  # 1 heure
        with app.app_context():
            verifier_rappels_automatiques()

# Démarrer le thread de rappels automatiques
threading.Thread(target=planifier_verification, daemon=True).start()

@app.route('/api/test/rappels')
@login_required
def test_rappels():
    """Déclencher manuellement la vérification des rappels"""
    verifier_rappels_automatiques()
    return jsonify({'success': True, 'message': 'Vérification des rappels effectuée'})

@app.route('/rappels_rendez_vous')
@login_required
def rappels_rendez_vous():
    """Page des rappels - Rendez-vous à moins de 7 jours et dépassés"""
    from datetime import datetime, timedelta
    
    structure_id = session.get('structure_id')
    
    # 🔥 Récupérer les rendez-vous depuis NEON
    rendez_vous = db.execute_query("""
        SELECT 
            r.id,
            r.patient_id,
            r.date_rdv,
            r.heure_rdv,
            r.motif,
            r.statut,
            p.nom,
            p.prenom,
            p.telephone
        FROM rendez_vous r
        LEFT JOIN patients p ON r.patient_id = p.id
        WHERE r.structure_id = %s
        ORDER BY r.date_rdv DESC
    """, (structure_id,))
    
    aujourdhui = datetime.now().date()
    date_limite = aujourdhui + timedelta(days=7)
    
    moins_7_jours = []
    depasses = []
    
    for r in rendez_vous:
        if isinstance(r, dict):
            statut = r.get('statut', '')
            date_rdv_str = r.get('date_rdv')
            patient_nom = f"{r.get('nom', '')} {r.get('prenom', '')}".strip()
            patient_tel = r.get('telephone', '')
            rdv_id = r.get('id')
            heure_rdv = r.get('heure_rdv')
            motif = r.get('motif', 'Consultation')
        else:
            statut = r[5] if len(r) > 5 else ''
            date_rdv_str = r[2] if len(r) > 2 else None
            patient_nom = f"{r[6]} {r[7]}".strip() if len(r) > 7 else 'Patient'
            patient_tel = r[8] if len(r) > 8 else ''
            rdv_id = r[0]
            heure_rdv = r[3] if len(r) > 3 else ''
            motif = r[4] if len(r) > 4 else 'Consultation'
        
        if statut in ['termine', 'annule']:
            continue
        
        if not date_rdv_str:
            continue
        
        try:
            # Convertir la date si c'est un string
            if isinstance(date_rdv_str, str):
                date_rdv = datetime.strptime(date_rdv_str, '%Y-%m-%d').date()
            else:
                date_rdv = date_rdv_str
            
            rdv_data = {
                'ID': rdv_id,
                'patient_id': r.get('patient_id') if isinstance(r, dict) else r[1],
                'patient_nom': patient_nom,
                'patient_telephone': patient_tel,
                'date_rendez_vous': str(date_rdv),
                'heure_rendez_vous': str(heure_rdv),
                'motif': motif,
                'statut': statut
            }
            
            # Rendez-vous dépassés
            if date_rdv < aujourdhui:
                rdv_data['jours_depasse'] = (aujourdhui - date_rdv).days
                depasses.append(rdv_data)
            
            # Rendez-vous dans les 7 jours (à venir)
            elif date_rdv <= date_limite:
                rdv_data['jours_restants'] = (date_rdv - aujourdhui).days
                moins_7_jours.append(rdv_data)
                
        except Exception as e:
            print(f"⚠️ Erreur traitement date: {e}")
            continue
    
    # Trier par date
    moins_7_jours.sort(key=lambda x: x.get('date_rendez_vous', ''))
    depasses.sort(key=lambda x: x.get('date_rendez_vous', ''))
    
    return render_template('rappels_rendez_vous.html', 
                         moins_7_jours=moins_7_jours,
                         depasses=depasses)


@app.route('/api/rappels/stats')
@login_required
def api_rappels_stats():
    """API pour les statistiques des rappels depuis Neon"""
    from datetime import datetime, timedelta
    
    structure_id = session.get('structure_id')
    
    # 🔥 Récupérer les rendez-vous depuis NEON
    rendez_vous = db.execute_query("""
        SELECT id, date_rdv, statut
        FROM rendez_vous 
        WHERE structure_id = %s
    """, (structure_id,))
    
    aujourdhui = datetime.now().date()
    date_limite = aujourdhui + timedelta(days=7)
    
    moins_7 = 0
    depasses = 0
    aujourdhui_count = 0
    
    for r in rendez_vous:
        if isinstance(r, dict):
            statut = r.get('statut', '')
            date_rdv_val = r.get('date_rdv')
        else:
            statut = r[2] if len(r) > 2 else ''
            date_rdv_val = r[1] if len(r) > 1 else None
        
        if statut in ['termine', 'annule']:
            continue
        
        if not date_rdv_val:
            continue
        
        try:
            if isinstance(date_rdv_val, str):
                date_rdv = datetime.strptime(date_rdv_val, '%Y-%m-%d').date()
            else:
                date_rdv = date_rdv_val
            
            if date_rdv < aujourdhui:
                depasses += 1
            elif date_rdv <= date_limite:
                moins_7 += 1
            
            if date_rdv == aujourdhui:
                aujourdhui_count += 1
        except:
            continue
    
    return jsonify({
        'moins_7': moins_7,
        'depasses': depasses,
        'aujourdhui': aujourdhui_count
    })
@app.route('/test_email')
def test_email():
    try:
        msg = Message("Test Medilogic-GHP", 
                      recipients=["essowasainfo60@gmail.com"],
                      body="Ceci est un test d'envoi d'email")
        mail.send(msg)
        return "✅ Email envoyé !"
    except Exception as e:
        return f"❌ Erreur: {e}"
# ========== ADMIN GLOBAL LOGIN ==========
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    """Page de connexion pour l'admin global"""
    if 'super_admin' in session:
        return redirect(url_for('admin_global'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Identifiants par défaut
        ADMIN_EMAIL = "essowasainfo60@gmail.com"
        ADMIN_PASSWORD = "essowasa1234A"
        
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['super_admin'] = True
            session['super_admin_name'] = 'Super Admin'
            flash('Bienvenue dans l\'administration globale !', 'success')
            return redirect(url_for('admin_global'))
        else:
            flash('Email ou mot de passe incorrect', 'danger')
    
    return render_template('admin_login.html')

@app.route('/admin_logout')
def admin_logout():
    """Déconnexion de l'admin global"""
    session.pop('super_admin', None)
    flash('Déconnecté de l\'administration globale', 'info')
    return redirect(url_for('index'))

@app.route('/referentiel/cnss')
@login_required
def referentiel_cnss():
    return render_template('referentiel.html', 
                         titre="AMU-CNSS - Référentiel des prestataires",
                         url="https://referentiels.amu.tg/#/providers")

@app.route('/referentiel/inam')
@login_required
def referentiel_inam():
    return render_template('referentiel.html', 
                         titre="AMU-INAM - Portail Prestataire",
                         url="https://prestaplus.inam.tg/Vue/index.php")

@app.route('/api/import/actes', methods=['POST'])
@login_required
def import_actes():
    try:
        file = request.files['file']
        structure_id = session.get('structure_id')
        
        # Lire le fichier Excel
        df = pd.read_excel(BytesIO(file.read()))
        
        # Récupérer les actes existants
        actes = sheets_helper.get_all_records('actes')
        next_id = len(actes) + 1
        
        compteur = 0
        for _, row in df.iterrows():
            new_acte = [
                next_id + compteur,
                row.get('code', f"ACT-{compteur+1}"),
                row.get('nom', 'Acte'),
                row.get('prix', 0),
                row.get('description', ''),
                structure_id
            ]
            sheets_helper.add_record('actes', new_acte)
            compteur += 1
        
        return jsonify({'message': f'✅ {compteur} actes importés avec succès'})
        
    except Exception as e:
        return jsonify({'message': f'❌ Erreur: {str(e)}'}), 500

@app.route('/api/import/produits', methods=['POST'])
@login_required
def import_produits():
    try:
        file = request.files['file']
        structure_id = session.get('structure_id')
        
        df = pd.read_excel(BytesIO(file.read()))
        
        produits = sheets_helper.get_all_records('produits')
        next_id = len(produits) + 1
        
        compteur = 0
        for _, row in df.iterrows():
            new_produit = [
                next_id + compteur,
                row.get('code', f"PRD-{compteur+1}"),
                row.get('nom', 'Produit'),
                row.get('prix', 0),
                row.get('stock', 0),
                structure_id
            ]
            sheets_helper.add_record('produits', new_produit)
            compteur += 1
        
        return jsonify({'message': f'✅ {compteur} produits importés avec succès'})
        
    except Exception as e:
        return jsonify({'message': f'❌ Erreur: {str(e)}'}), 500

@app.route('/api/patients/<int:patient_id>', methods=['PUT'])
@login_required
def api_update_patient(patient_id):
    try:
        data = request.json
        structure_id = session.get('structure_id')
        
        db.execute_query("""
            UPDATE patients 
            SET nom = %s, prenom = %s, telephone = %s, adresse = %s,
                type_assurance = %s, taux_prise_charge = %s, numero_assure = %s
            WHERE id = %s AND structure_id = %s
        """, (
            data.get('nom'),
            data.get('prenom', ''),
            data.get('telephone'),
            data.get('adresse', ''),
            data.get('type_assurance', 'non_assure'),
            data.get('taux_prise_charge', 0),
            data.get('numero_assure', ''),
            patient_id,
            structure_id
        ))
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/produits', methods=['POST'])
@login_required
def api_add_produit():
    try:
        data = request.json
        structure_id = session.get('structure_id')
        
        result = db.execute_query("""
            INSERT INTO produits (structure_id, code, nom, prix_vente, prix_achat,
                                  quantite_stock, seuil_alerte, unite, categorie)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            structure_id,
            data.get('code'),
            data.get('nom'),
            data.get('prix_vente'),
            data.get('prix_achat', 0),
            data.get('quantite_stock', 0),
            data.get('seuil_alerte', 10),
            data.get('unite', 'unité'),
            data.get('categorie', '')
        ))
        
        if result:
            return jsonify({'success': True, 'id': result[0]['id']})
        return jsonify({'success': False, 'error': 'Erreur insertion'}), 500
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/produits/<int:produit_id>/stock', methods=['PUT'])
@login_required
def api_update_stock(produit_id):
    try:
        data = request.json
        structure_id = session.get('structure_id')
        quantite = data.get('quantite')
        operation = data.get('operation', 'vendre')  # vendre, ajouter, retirer
        
        if operation == 'vendre':
            sql = "UPDATE produits SET quantite_stock = quantite_stock - %s WHERE id = %s AND structure_id = %s"
        elif operation == 'ajouter':
            sql = "UPDATE produits SET quantite_stock = quantite_stock + %s WHERE id = %s AND structure_id = %s"
        else:
            sql = "UPDATE produits SET quantite_stock = %s WHERE id = %s AND structure_id = %s"
        
        db.execute_query(sql, (quantite, produit_id, structure_id))
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/produits')
@login_required
def api_get_produits():
    """Récupérer les produits depuis Google Sheets"""
    structure_id = session.get('structure_id')
    
    # 🔥 Lire depuis Sheets
    produits = sheets_helper.get_all_records('produits')
    
    # Filtrer par structure
    produits_liste = []
    for p in produits:
        if str(p.get('structure_id')) == str(structure_id):
            produits_liste.append({
                'id': p.get('ID'),
                'nom': p.get('nom', ''),
                'prix_vente': float(p.get('prix_vente', 0)),
                'quantite_stock': int(p.get('quantite_stock', 0)),
                'seuil_alerte': int(p.get('seuil_alerte', 10)),
                'unite': p.get('unite', 'unité')
            })
    
    return jsonify(produits_liste)

@app.route('/api/produits/search')
@login_required
def api_produits_search():
    """Rechercher des produits depuis Google Sheets (pour proforma)"""
    try:
        structure_id = session.get('structure_id')
        search = request.args.get('search', '').strip()
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        
        produits = sheets_helper.get_all_records('produits')
        
        produits_liste = []
        for p in produits:
            if str(p.get('structure_id')) == str(structure_id):
                produits_liste.append({
                    'id': p.get('ID'),
                    'nom': p.get('nom', ''),
                    'prix_vente': float(p.get('prix_vente', 0)),
                    'quantite_stock': int(p.get('quantite_stock', 0)),
                    'seuil_alerte': int(p.get('seuil_alerte', 10)),
                    'unite': p.get('unite', 'unité')
                })
        
        if search:
            search_lower = search.lower()
            produits_liste = [p for p in produits_liste 
                             if search_lower in p['nom'].lower()]
        
        total = len(produits_liste)
        paginated = produits_liste[offset:offset + limit]
        
        return jsonify({
            'data': paginated,
            'total': total,
            'limit': limit,
            'offset': offset,
            'has_more': (offset + limit) < total
        })
        
    except Exception as e:
        return jsonify({'data': [], 'total': 0, 'error': str(e)}), 500

# ========== GESTION PRODUITS (Google Sheets) ==========

@app.route('/api/admin/produits', methods=['POST'])
@login_required
def api_admin_add_produit():
    """Ajouter un produit dans Google Sheets"""
    try:
        data = request.json
        structure_id = session.get('structure_id')
        
        print(f"➕ Ajout produit - Données: {data}")
        
        # Récupérer les produits existants depuis Sheets
        produits = sheets_helper.get_all_records('produits')
        new_id = get_next_id(produits, 'ID')
        
        # Ajouter le nouveau produit
        new_produit = [
            new_id,
            data.get('nom'),
            float(data.get('prix_vente', 0)),
            int(data.get('quantite_stock', 0)),
            int(data.get('seuil_alerte', 10)),
            data.get('unite', 'unité'),
            structure_id
        ]
        
        sheets_helper.add_record('produits', new_produit)
        
        return jsonify({'success': True, 'id': new_id})
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/produits/<int:produit_id>', methods=['PUT'])
@login_required
def api_admin_update_produit(produit_id):
    try:
        data = request.json
        structure_id = session.get('structure_id')
        
        print(f"✏️ Modification produit ID: {produit_id}")
        print(f"   Données: {data}")
        print(f"   Structure ID: {structure_id}")
        
        # 🔥 Utiliser le bon nom de feuille
        sheet_name = f"struct_{structure_id}_produits"
        print(f"   Feuille: {sheet_name}")
        
        worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
        
        # Trouver le produit
        cell = worksheet.find(str(produit_id), in_column=1)
        if not cell:
            return jsonify({'success': False, 'error': 'Produit non trouvé'}), 404
        
        row_num = cell.row
        current_row = worksheet.row_values(row_num)
        
        # Mettre à jour les colonnes
        # A=ID, B=nom, C=prix_vente, D=quantite_stock, E=seuil_alerte, F=unite, G=structure_id
        current_row[1] = data.get('nom')
        current_row[2] = str(float(data.get('prix_vente', 0)))
        current_row[3] = str(int(data.get('quantite_stock', 0)))
        current_row[4] = str(int(data.get('seuil_alerte', 10)))
        current_row[5] = data.get('unite', 'unité')
        current_row[6] = str(structure_id)
        
        worksheet.update(range_name=f'A{row_num}:G{row_num}', values=[current_row])
        
        print(f"   ✅ Produit {produit_id} modifié avec succès")
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/produits/<int:produit_id>', methods=['DELETE'])
@login_required
def api_admin_delete_produit(produit_id):
    """Supprimer un produit de Google Sheets"""
    try:
        structure_id = session.get('structure_id')
        
        print(f"🗑️ Suppression produit ID: {produit_id}")
        
        worksheet = sheets_helper.spreadsheet.worksheet("produits")
        
        # Trouver le produit
        cell = worksheet.find(str(produit_id), in_column=1)
        if not cell:
            return jsonify({'success': False, 'error': 'Produit non trouvé'}), 404
        
        # Supprimer la ligne
        worksheet.delete_rows(cell.row)
        
        return jsonify({'success': True, 'message': 'Produit supprimé'})
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/produits/<int:id>/approvisionner', methods=['POST'])
@login_required
def api_approvisionner_produit(id):
    """Approvisionner un produit (ajouter au stock)"""
    try:
        data = request.json
        structure_id = session.get('structure_id')
        quantite = data.get('quantite', 0)
        
        print(f"📦 Approvisionnement produit ID: {id}")
        print(f"   Quantité: {quantite}")
        print(f"   Structure ID: {structure_id}")
        
        if not quantite or quantite <= 0:
            return jsonify({'success': False, 'error': 'Quantité invalide'}), 400
        
        # 🔥 Utiliser le bon nom de feuille
        sheet_name = f"struct_{structure_id}_produits"
        print(f"   Feuille: {sheet_name}")
        
        worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
        
        # Trouver le produit
        cell = worksheet.find(str(id), in_column=1)
        if not cell:
            return jsonify({'success': False, 'error': 'Produit non trouvé'}), 404
        
        row_num = cell.row
        current_row = worksheet.row_values(row_num)
        
        stock_actuel = int(current_row[3]) if len(current_row) > 3 else 0
        nouveau_stock = stock_actuel + quantite
        
        worksheet.update_cell(row_num, 4, nouveau_stock)
        
        print(f"   ✅ Stock: {stock_actuel} → {nouveau_stock}")
        
        return jsonify({'success': True, 'message': f'{quantite} unités ajoutées', 'stock': nouveau_stock})
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/produits/<int:id>/stock', methods=['PUT'])
@login_required
def api_modifier_stock(id):
    """Modifier le stock d'un produit (ajouter ou retirer) dans Google Sheets"""
    try:
        data = request.json
        structure_id = session.get('structure_id')
        quantite = data.get('quantite', 0)
        operation = data.get('operation', 'ajouter')
        
        print(f"📦 Modification stock produit ID: {id}")
        print(f"   Quantité: {quantite}, Opération: {operation}")
        
        if not quantite or quantite <= 0:
            return jsonify({'success': False, 'error': 'Quantité invalide'}), 400
        
        # 🔥 Lire depuis Google Sheets
        worksheet = sheets_helper.spreadsheet.worksheet("produits")
        
        # Trouver le produit par ID (colonne A)
        cell = worksheet.find(str(id), in_column=1)
        if not cell:
            return jsonify({'success': False, 'error': 'Produit non trouvé'}), 404
        
        row_num = cell.row
        current_row = worksheet.row_values(row_num)
        
        # Colonnes: A=ID, B=nom, C=prix_vente, D=quantite_stock, E=seuil_alerte, F=unite, G=structure_id
        stock_actuel = int(current_row[3]) if len(current_row) > 3 else 0
        nom_produit = current_row[1] if len(current_row) > 1 else 'Produit'
        
        print(f"   Stock actuel de {nom_produit}: {stock_actuel}")
        
        if operation == 'retirer':
            if quantite > stock_actuel:
                return jsonify({'success': False, 'error': f'Stock insuffisant. Stock: {stock_actuel}'}), 400
            nouvelle_quantite = stock_actuel - quantite
        else:
            nouvelle_quantite = stock_actuel + quantite
        
        # Mettre à jour dans Sheets (colonne D = quantite_stock, index 4)
        worksheet.update_cell(row_num, 4, nouvelle_quantite)
        
        print(f"   ✅ Nouveau stock: {nouvelle_quantite}")
        
        return jsonify({'success': True, 'stock': nouvelle_quantite})
        
    except Exception as e:
        print(f"❌ Erreur modification stock: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ventes/pharma', methods=['POST'])
@login_required
def api_vente_pharma():
    import json
    from datetime import datetime
    
    try:
        data = request.json
        structure_id = session.get('structure_id')
        
        vendeur = session.get('user_name')
        if not vendeur:
            vendeur = 'System'
        
        print("=" * 60)
        print("📦 VENTE PHARMACIE")
        print(f"Patient: {data.get('patient_nom')}")
        print(f"Vendeur: {vendeur}")
        print(f"Produits: {data.get('produits')}")
        print(f"Net à payer: {data.get('net_a_payer')} FCFA")
        print("=" * 60)
        
        if not structure_id:
            return jsonify({'success': False, 'error': 'Structure non trouvee'}), 400
        
        patient_id = data.get('patient_id')
        if not patient_id:
            return jsonify({'success': False, 'error': 'ID patient manquant'}), 400
        
        # ========== 1. ENREGISTRER LA VENTE DANS NEON ==========
        result = db.execute_query("""
            INSERT INTO ventes (
                patient_id, 
                patient_nom, 
                structure_id, 
                type, 
                sous_total, 
                prise_en_charge, 
                net_a_payer, 
                mode_paiement, 
                taux_assurance, 
                date_vente, 
                produits, 
                created_by_nom,
                statut
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s::jsonb, %s, 'validee')
            RETURNING id
        """, (
            patient_id,
            data.get('patient_nom', 'Patient'),
            structure_id,
            'pharmacie',
            float(data.get('sous_total', 0)),
            float(data.get('prise_en_charge', 0)),
            float(data.get('net_a_payer', 0)),
            data.get('mode_paiement', 'especes'),
            float(data.get('taux_assurance', 0)),
            json.dumps(data.get('produits', []), ensure_ascii=False),
            vendeur
        ))
        
        if not result or len(result) == 0:
            print("❌ Erreur: Aucun ID retourné pour la vente")
            return jsonify({'success': False, 'error': 'Erreur insertion vente'}), 500
        
        vente_id = result[0]['id']
        print(f"✅ Vente pharmacie enregistrée dans Neon avec ID: {vente_id}")
        
        # ========== 2. AJOUTER LA RECETTE DANS NEON ==========
        net_a_payer = float(data.get('net_a_payer', 0))
        if net_a_payer > 0:
            recette_result = db.execute_query("""
                INSERT INTO recettes (
                    structure_id, 
                    montant, 
                    source, 
                    source_id, 
                    source_type, 
                    description, 
                    created_by_nom,
                    date_recette
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
            """, (
                structure_id,
                net_a_payer,
                'patients',
                vente_id,
                'vente_pharma',
                'Vente pharmacie #' + str(vente_id) + ' - ' + data.get('patient_nom', 'Patient'),
                vendeur
            ))
            
            if recette_result and len(recette_result) > 0:
                print(f"✅ Recette ajoutée avec ID: {recette_result[0]['id']} pour {net_a_payer} FCFA")
            else:
                print("⚠️ Erreur lors de l'insertion de la recette")
        
        # ========== 3. METTRE À JOUR LE STOCK DANS GOOGLE SHEETS ==========
        try:
            sheet_name = f"struct_{structure_id}_produits"
            print(f"   📂 Accès à la feuille: {sheet_name}")
            
            worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
            
            for produit in data.get('produits', []):
                produit_id = str(produit.get('id'))
                quantite_vendue = int(produit.get('quantite', 0))
                produit_nom = produit.get('nom', 'Inconnu')
                
                print(f"   🔍 Recherche du produit ID: {produit_id} - {produit_nom}")
                
                # Chercher le produit dans Sheets (colonne A = ID)
                cell = worksheet.find(produit_id, in_column=1)
                if cell:
                    row_num = cell.row
                    current_row = worksheet.row_values(row_num)
                    stock_actuel = int(current_row[3]) if len(current_row) > 3 else 0
                    nouveau_stock = stock_actuel - quantite_vendue
                    
                    if nouveau_stock < 0:
                        print(f"   ⚠️ Stock négatif! {produit_nom}: {stock_actuel} - {quantite_vendue} = {nouveau_stock}")
                        # On force à 0 pour éviter les stocks négatifs
                        nouveau_stock = 0
                    
                    print(f"   📊 Stock: {stock_actuel} → {nouveau_stock}")
                    
                    # Mettre à jour la cellule du stock (colonne D = index 4)
                    worksheet.update_cell(row_num, 4, nouveau_stock)
                    print(f"   ✅ Stock Sheets mis à jour pour {produit_nom}")
                else:
                    print(f"   ❌ Produit ID {produit_id} non trouvé dans Sheets!")
                    print(f"   📋 IDs disponibles: {worksheet.col_values(1)}")
                    
        except Exception as e:
            print(f"   ❌ ERREUR mise à jour stock Sheets: {e}")
            import traceback
            traceback.print_exc()
        
        # ========== 4. METTRE À JOUR LE SOLDE DE CAISSE ==========
        try:
            # Recalculer le solde total
            recettes_total = db.execute_query("""
                SELECT COALESCE(SUM(montant), 0) as total 
                FROM recettes 
                WHERE structure_id = %s 
                AND (est_annulation IS NULL OR est_annulation = FALSE)
            """, (structure_id,))
            
            depenses_total = db.execute_query("""
                SELECT COALESCE(SUM(montant), 0) as total 
                FROM depenses 
                WHERE structure_id = %s
            """, (structure_id,))
            
            total_recettes = recettes_total[0]['total'] if recettes_total else 0
            total_depenses = depenses_total[0]['total'] if depenses_total else 0
            nouveau_solde = total_recettes - total_depenses
            
            db.execute_query("""
                INSERT INTO caisse (structure_id, solde_actuel, date_mise_a_jour)
                VALUES (%s, %s, NOW())
                ON CONFLICT (structure_id) DO UPDATE SET 
                    solde_actuel = EXCLUDED.solde_actuel,
                    date_mise_a_jour = NOW()
            """, (structure_id, nouveau_solde))
            
            print(f"💰 Solde de caisse mis à jour: {nouveau_solde} FCFA")
            
        except Exception as e:
            print(f"⚠️ Erreur mise à jour solde: {e}")
        
        print(f"✅ Vente pharmacie #{vente_id} terminée avec succès!")
        return jsonify({'success': True, 'vente_id': vente_id})
        
    except Exception as e:
        print(f"❌ ERREUR GENERALE: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/produits/<int:id>/stock', methods=['GET'])
@login_required
def api_get_stock_produit(id):
    """Récupérer le stock d'un produit depuis Google Sheets"""
    try:
        structure_id = session.get('structure_id')
        
        # 🔥 Utiliser le bon nom de feuille
        sheet_name = f"struct_{structure_id}_produits"
        worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
        
        # Trouver le produit par ID (colonne A)
        cell = worksheet.find(str(id), in_column=1)
        if not cell:
            return jsonify({'success': False, 'error': 'Produit non trouvé'}), 404
        
        row_num = cell.row
        current_row = worksheet.row_values(row_num)
        
        # Colonnes: A=ID, B=nom, C=prix_vente, D=quantite_stock, E=seuil_alerte, F=unite, G=structure_id
        produit = {
            'id': int(current_row[0]) if len(current_row) > 0 else None,
            'nom': current_row[1] if len(current_row) > 1 else '',
            'quantite_stock': int(current_row[3]) if len(current_row) > 3 else 0,
            'seuil_alerte': int(current_row[4]) if len(current_row) > 4 else 10
        }
        
        return jsonify({'success': True, 'stock': produit})
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/patients/count')
@login_required
def api_patients_count():
    """Retourne le nombre de patients"""
    try:
        structure_id = session.get('structure_id')
        result = db.execute_query("""
            SELECT COUNT(*) as total FROM patients WHERE structure_id = %s
        """, (structure_id,))
        total = result[0]['total'] if result else 0
        return jsonify({'total': total})
    except Exception as e:
        return jsonify({'total': 0}), 500

@app.route('/api/ventes/stats')
@login_required
def api_ventes_stats():
    """Retourne les statistiques des ventes (actes et pharmacie) depuis Neon"""
    try:
        structure_id = session.get('structure_id')
        
        # Date du jour
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 🔥 Récupérer UNIQUEMENT les ventes valides (non annulées)
        ventes = db.execute_query("""
            SELECT type, net_a_payer, sous_total, date_vente
            FROM ventes 
            WHERE structure_id = %s 
            AND (statut IS NULL OR statut != 'annulee')
        """, (structure_id,))
        
        actes_today = 0
        pharma_today = 0
        ca_net_today = 0
        ca_brut_today = 0
        
        for v in ventes:
            if isinstance(v, dict):
                date_vente = v.get('date_vente')
                if date_vente:
                    if hasattr(date_vente, 'strftime'):
                        date_vente_str = date_vente.strftime('%Y-%m-%d')
                    else:
                        date_vente_str = str(date_vente)[:10]
                    
                    if date_vente_str == today:
                        if v.get('type') == 'actes':
                            actes_today += 1
                        else:
                            pharma_today += 1
                        
                        ca_net_today += float(v.get('net_a_payer', 0))
                        ca_brut_today += float(v.get('sous_total', 0))
        
        return jsonify({
            'actes_today': actes_today,
            'pharma_today': pharma_today,
            'ca_net_today': ca_net_today,
            'ca_brut_today': ca_brut_today
        })
        
    except Exception as e:
        print(f"❌ Erreur stats: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'actes_today': 0, 
            'pharma_today': 0, 
            'ca_net_today': 0,
            'ca_brut_today': 0
        }), 500

@app.route('/api/activites/recentes')
@login_required
def api_activites_recentes():
    """Retourne les 10 dernières activités (hors annulées)"""
    try:
        structure_id = session.get('structure_id')
        
        # 🔥 Récupérer UNIQUEMENT les ventes valides (non annulées)
        ventes = db.execute_query("""
            SELECT 
                v.id,
                v.patient_id,
                v.patient_nom,
                v.type,
                v.net_a_payer,
                v.date_vente,
                p.nom,
                p.prenom
            FROM ventes v
            LEFT JOIN patients p ON v.patient_id = p.id
            WHERE v.structure_id = %s 
            AND (v.statut IS NULL OR v.statut != 'annulee')
            ORDER BY v.date_vente DESC
            LIMIT 10
        """, (structure_id,))
        
        result = []
        for v in ventes:
            if isinstance(v, dict):
                patient_name = v.get('patient_nom', '')
                if not patient_name or patient_name == '':
                    nom = v.get('nom', '')
                    prenom = v.get('prenom', '')
                    patient_name = f"{nom} {prenom}".strip()
                if not patient_name:
                    patient_name = 'Patient'
                
                date_vente = v.get('date_vente')
                if date_vente:
                    if hasattr(date_vente, 'strftime'):
                        date_str = date_vente.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        date_str = str(date_vente)
                else:
                    date_str = ''
                    
                result.append({
                    'id': v.get('id'),
                    'patient_nom': patient_name,
                    'type': v.get('type', 'unknown'),
                    'montant': float(v.get('net_a_payer', 0)),
                    'date': date_str
                })
            else:
                patient_name = v[2] if len(v) > 2 and v[2] else ''
                if not patient_name and len(v) > 6:
                    patient_name = f"{v[6] or ''} {v[7] or ''}".strip()
                if not patient_name:
                    patient_name = 'Patient'
                
                date_vente = v[5] if len(v) > 5 else None
                if date_vente:
                    if hasattr(date_vente, 'strftime'):
                        date_str = date_vente.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        date_str = str(date_vente)
                else:
                    date_str = ''
                    
                result.append({
                    'id': v[0],
                    'patient_nom': patient_name,
                    'type': v[3] if len(v) > 3 else 'unknown',
                    'montant': float(v[4]) if len(v) > 4 else 0,
                    'date': date_str
                })
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur activités: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([]), 500

@app.route('/api/ventes/actes', methods=['POST'])
@login_required
def api_add_acte_vente():
    import json
    from datetime import datetime
    
    try:
        data = request.json
        structure_id = session.get('structure_id')
        user_name = session.get('user_name', 'System')
        
        print("=" * 60)
        print("VENTE ACTES")
        print(f"Patient: {data.get('patient_nom')}")
        print(f"Vendeur: {user_name}")
        print("=" * 60)
        
        if not structure_id:
            return jsonify({'success': False, 'error': 'Structure non trouvee'}), 400
        
        patient_id = data.get('patient_id')
        if not patient_id:
            return jsonify({'success': False, 'error': 'ID patient manquant'}), 400
        
        result = db.execute_query("""
            INSERT INTO ventes (
                patient_id, 
                patient_nom, 
                structure_id, 
                type, 
                sous_total, 
                prise_en_charge, 
                net_a_payer, 
                mode_paiement, 
                taux_assurance, 
                date_vente, 
                actes,
                created_by_nom
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s)
            RETURNING id
        """, (
            patient_id,
            data.get('patient_nom', 'Patient'),
            structure_id,
            'actes',
            float(data.get('sous_total', 0)),
            float(data.get('prise_en_charge', 0)),
            float(data.get('net_a_payer', 0)),
            data.get('mode_paiement', 'especes'),
            float(data.get('taux_assurance', 0)),
            json.dumps(data.get('actes', []), ensure_ascii=False),
            user_name
        ))
        
        if result and len(result) > 0:
            vente_id = result[0]['id']
            print(f"Vente actes inseree ID: {vente_id} par {user_name}")
            
            # Ajout automatique de la recette
            net_a_payer = float(data.get('net_a_payer', 0))
            if net_a_payer > 0:
                db.execute_query("""
                    INSERT INTO recettes (structure_id, montant, source, source_id, source_type, description, created_by_nom)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    structure_id,
                    net_a_payer,
                    'patients',
                    vente_id,
                    'vente_acte',
                    'Vente actes #' + str(vente_id) + ' - ' + data.get('patient_nom', 'Patient'),
                    user_name
                ))
                print(f"Recette ajoutee: {net_a_payer} FCFA")
            
            return jsonify({'success': True, 'vente_id': vente_id})
        else:
            return jsonify({'success': False, 'error': 'Erreur insertion'}), 500
            
    except Exception as e:
        print(f"ERREUR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ventes/all')
@login_required
def api_get_all_ventes():
    """Récupérer toutes les ventes (actes + pharmacie) depuis Neon (hors annulées)"""
    try:
        structure_id = session.get('structure_id')
        
        # 🔥 Récupérer UNIQUEMENT les ventes non annulées
        ventes = db.execute_query("""
            SELECT 
                id, patient_nom, type, net_a_payer, taux_assurance, 
                date_vente, actes, produits, created_by_nom, statut
            FROM ventes 
            WHERE structure_id = %s 
            AND (statut IS NULL OR statut != 'annulee')
            ORDER BY date_vente DESC
        """, (structure_id,))
        
        result = []
        import json
        
        for v in ventes:
            if isinstance(v, dict):
                detail = ""
                
                # Pour les actes
                if v.get('type') == 'actes' and v.get('actes'):
                    actes_data = v.get('actes')
                    if isinstance(actes_data, str):
                        try:
                            actes_data = json.loads(actes_data)
                        except:
                            actes_data = []
                    if actes_data and len(actes_data) > 0:
                        articles = []
                        for a in actes_data:
                            nom = a.get('nom', 'Acte')
                            qte = a.get('quantite', 1)
                            if qte > 1:
                                articles.append(f"{nom} x{qte}")
                            else:
                                articles.append(nom)
                        detail = ", ".join(articles)
                
                # Pour la pharmacie (accepter 'pharma' ET 'pharmacie')
                elif v.get('type') in ['pharma', 'pharmacie'] and v.get('produits'):
                    produits_data = v.get('produits')
                    if isinstance(produits_data, str):
                        try:
                            produits_data = json.loads(produits_data)
                        except:
                            produits_data = []
                    if produits_data and len(produits_data) > 0:
                        articles = []
                        for p in produits_data:
                            nom = p.get('nom', 'Produit')
                            qte = p.get('quantite', 1)
                            if qte > 1:
                                articles.append(f"{nom} x{qte}")
                            else:
                                articles.append(nom)
                        detail = ", ".join(articles)
                    else:
                        detail = '-'
                
                # Ajouter la vente au résultat
                result.append({
                    'ID': v.get('id'),
                    'patient_nom': v.get('patient_nom', 'Patient'),
                    'type': v.get('type'),
                    'net_a_payer': float(v.get('net_a_payer', 0)),
                    'taux_assurance': v.get('taux_assurance', 0),
                    'date': str(v.get('date_vente', '')),
                    'detail': detail if detail else '-',
                    'created_by_nom': v.get('created_by_nom', None),
                    'statut': v.get('statut', 'validee')
                })
            else:
                # Format tuple
                detail = ""
                vente_type = v[3] if len(v) > 3 else ''
                
                # Pour les actes (tuple)
                if vente_type == 'actes' and len(v) > 6 and v[6]:
                    actes_data = v[6]
                    if isinstance(actes_data, str):
                        try:
                            actes_data = json.loads(actes_data)
                        except:
                            actes_data = []
                    if actes_data and len(actes_data) > 0:
                        articles = [f"{a.get('nom', 'Acte')} x{a.get('quantite', 1)}" for a in actes_data]
                        detail = ", ".join(articles)
                
                # Pour la pharmacie (tuple)
                elif vente_type in ['pharma', 'pharmacie'] and len(v) > 7 and v[7]:
                    produits_data = v[7]
                    if isinstance(produits_data, str):
                        try:
                            produits_data = json.loads(produits_data)
                        except:
                            produits_data = []
                    if produits_data and len(produits_data) > 0:
                        articles = [f"{p.get('nom', 'Produit')} x{p.get('quantite', 1)}" for p in produits_data]
                        detail = ", ".join(articles)
                
                result.append({
                    'ID': v[0],
                    'patient_nom': v[2] if len(v) > 2 else 'Patient',
                    'type': vente_type,
                    'net_a_payer': float(v[6]) if len(v) > 6 else 0,
                    'taux_assurance': v[9] if len(v) > 9 else 0,
                    'date': str(v[10]) if len(v) > 10 else '',
                    'detail': detail if detail else '-',
                    'created_by_nom': v[13] if len(v) > 13 else None,
                    'statut': v[16] if len(v) > 16 else 'validee'
                })
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur chargement ventes: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([]), 500

@app.route('/api/actes')
@login_required
def api_get_actes():
    """Récupérer les actes depuis Google Sheets avec recherche"""
    try:
        structure_id = session.get('structure_id')
        search = request.args.get('search', '').strip()
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        
        print(f"📂 Recherche actes: '{search}' (limit={limit}, offset={offset})")
        
        # 🔥 Utiliser le bon nom de feuille avec préfixe
        sheet_name = f"struct_{structure_id}_actes"
        print(f"   Feuille: {sheet_name}")
        
        try:
            # Essayer avec le préfixe
            worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
            actes = worksheet.get_all_records()
            print(f"📊 Total actes dans {sheet_name}: {len(actes)}")
        except Exception as e:
            print(f"⚠️ Feuille {sheet_name} non trouvée: {e}")
            # Fallback: essayer sans préfixe
            print("   Tentative avec 'actes' sans préfixe...")
            actes = sheets_helper.get_all_records('actes', use_prefix=False)
            print(f"📊 Total actes dans 'actes': {len(actes)}")
        
        # Filtrer par structure (si besoin)
        actes_struct = []
        for a in actes:
            sid = a.get('structure_id') or a.get('STRUCTURE_ID') or a.get('structureId')
            if sid is None or str(sid) == str(structure_id):
                actes_struct.append(a)
        
        # Filtrer par recherche
        if search:
            search_lower = search.lower()
            actes_struct = [a for a in actes_struct 
                           if search_lower in str(a.get('nom', '')).lower() 
                           or search_lower in str(a.get('code', '')).lower()]
        
        total = len(actes_struct)
        
        # Pagination
        paginated = actes_struct[offset:offset + limit]
        
        result = []
        for a in paginated:
            # Prix : gérer les valeurs non numériques
            prix_raw = a.get('prix') or a.get('PRIX') or a.get('Prix') or 0
            if prix_raw is None or prix_raw == '' or prix_raw == '-' or prix_raw == ' - ':
                prix_float = 0
            else:
                try:
                    prix_str = str(prix_raw).strip().replace(' ', '').replace(',', '').replace('FCFA', '')
                    prix_float = float(prix_str) if prix_str else 0
                except (ValueError, TypeError):
                    prix_float = 0
            
            acte_nom = a.get('nom') or a.get('NOM') or a.get('Nom')
            if acte_nom and str(acte_nom).strip():
                result.append({
                    'id': a.get('ID') or a.get('id'),
                    'code': str(a.get('code', '') or ''),
                    'nom': str(acte_nom).strip(),
                    'prix': prix_float,
                    'description': str(a.get('description', '') or '')
                })
        
        return jsonify({
            'data': result,
            'total': total,
            'limit': limit,
            'offset': offset,
            'has_more': (offset + limit) < total
        })
        
    except Exception as e:
        print(f"❌ Erreur GET actes: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'data': [], 'total': 0, 'error': str(e)}), 500

@app.route('/api/ventes/<int:vente_id>/annuler', methods=['POST'])
@login_required
def annuler_vente(vente_id):
    """Annuler une vente (admin uniquement)"""
    import json
    from datetime import datetime
    
    try:
        # Verifier que l'utilisateur est admin
        if not session.get('is_admin'):
            return jsonify({'success': False, 'error': 'Acces non autorise. Reserve a l administrateur.'}), 403
        
        data = request.json
        motif = data.get('motif', 'Annulation manuelle')
        structure_id = session.get('structure_id')
        user_id = session.get('user_id')
        user_name = session.get('user_name', 'Administrateur')
        
        # Recuperer la vente
        vente = db.execute_query("""
            SELECT * FROM ventes 
            WHERE id = %s AND structure_id = %s AND (statut = 'validee' OR statut IS NULL)
        """, (vente_id, structure_id))
        
        if not vente or len(vente) == 0:
            return jsonify({'success': False, 'error': 'Vente non trouvee ou deja annulee'}), 404
        
        v = vente[0] if isinstance(vente[0], dict) else vente[0]
        
        if isinstance(v, dict):
            vente_type = v.get('type')
            produits_data = v.get('produits')
            net_a_payer = float(v.get('net_a_payer', 0))
            sous_total = float(v.get('sous_total', 0))
        else:
            vente_type = v[3] if len(v) > 3 else None
            produits_data = v[12] if len(v) > 12 else None
            net_a_payer = float(v[6]) if len(v) > 6 else 0
            sous_total = float(v[4]) if len(v) > 4 else 0
        
        # ========== POUR LA PHARMACIE : RESTOCKER DANS SHEETS ==========
        if vente_type in ['pharma', 'pharmacie'] and produits_data:
            if isinstance(produits_data, str):
                produits_data = json.loads(produits_data)
            
            try:
                sheet_name = f"struct_{structure_id}_produits"
                worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
                
                for produit in produits_data:
                    produit_id = str(produit.get('id'))
                    quantite = int(produit.get('quantite', 0))
                    
                    if produit_id and quantite > 0:
                        cell = worksheet.find(produit_id, in_column=1)
                        if cell:
                            row_num = cell.row
                            current_row = worksheet.row_values(row_num)
                            stock_actuel = int(current_row[3]) if len(current_row) > 3 else 0
                            nouveau_stock = stock_actuel + quantite
                            worksheet.update_cell(row_num, 4, nouveau_stock)
                            print(f"📦 Restocké dans Sheets: {produit.get('nom')} +{quantite}")
            except Exception as e:
                print(f"⚠️ Erreur restock Sheets: {e}")
        
        # ========== POUR LES ACTES : PAS DE STOCK ==========
        
        # 🔥 ENREGISTRER L'ANNULATION DANS L'HISTORIQUE
        db.execute_query("""
            INSERT INTO annulations_ventes (
                vente_id, vente_type, motif, annule_par_id, annule_par_nom,
                ancien_net_a_payer, ancien_sous_total, data_avant, date_annulation
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            vente_id, vente_type, motif, user_id, user_name,
            net_a_payer, sous_total, json.dumps(v, default=str)
        ))
        
        # 🔥 Mettre à jour la recette (annuler)
        db.execute_query("""
            UPDATE recettes 
            SET est_annulation = TRUE, 
                description = CONCAT(description, ' [ANNULEE - ', %s, ']')
            WHERE source_id = %s 
            AND source_type IN ('vente_acte', 'vente_pharma') 
            AND structure_id = %s
        """, (motif, vente_id, structure_id))
        
        # 🔥 Marquer la vente comme annulée
        db.execute_query("""
            UPDATE ventes 
            SET statut = 'annulee', 
                annulee_le = NOW(), 
                annulee_par = %s,
                motif_annulation = %s
            WHERE id = %s AND structure_id = %s
        """, (user_id, motif, vente_id, structure_id))
        
        # 🔥 METTRE À JOUR LE SOLDE DE CAISSE (recalculer)
        recettes = db.execute_query("""
            SELECT COALESCE(SUM(montant), 0) as total 
            FROM recettes 
            WHERE structure_id = %s AND (est_annulation IS NULL OR est_annulation = FALSE)
        """, (structure_id,))
        
        depenses = db.execute_query("""
            SELECT COALESCE(SUM(montant), 0) as total 
            FROM depenses 
            WHERE structure_id = %s
        """, (structure_id,))
        
        total_recettes = recettes[0]['total'] if recettes else 0
        total_depenses = depenses[0]['total'] if depenses else 0
        nouveau_solde = total_recettes - total_depenses
        
        db.execute_query("""
            INSERT INTO caisse (structure_id, solde_actuel, date_mise_a_jour)
            VALUES (%s, %s, NOW())
            ON CONFLICT (structure_id) DO UPDATE SET 
                solde_actuel = EXCLUDED.solde_actuel,
                date_mise_a_jour = NOW()
        """, (structure_id, nouveau_solde))
        
        print(f"✅ Vente {vente_id} ({vente_type}) annulee par {user_name}")
        print(f"💰 Nouveau solde: {nouveau_solde} FCFA")
        
        return jsonify({
            'success': True, 
            'message': f'Vente #{vente_id} annulee avec succes',
            'type': vente_type,
            'nouveau_solde': nouveau_solde
        })
        
    except Exception as e:
        print(f"❌ Erreur annulation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/historique_annulations')
@login_required
def historique_annulations():
    """Page d'historique des annulations (admin uniquement)"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'danger')
        return redirect(url_for('dashboard'))
    
    structure_id = session.get('structure_id')
    
    annulations = db.execute_query("""
        SELECT 
            a.id,
            a.vente_id,
            a.vente_type,
            a.motif,
            a.annule_par_nom,
            a.ancien_net_a_payer,
            a.ancien_sous_total,
            a.date_annulation,
            v.patient_nom,
            v.date_vente as vente_date
        FROM annulations_ventes a
        LEFT JOIN ventes v ON a.vente_id = v.id
        WHERE v.structure_id = %s OR v.structure_id IS NULL
        ORDER BY a.date_annulation DESC
    """, (structure_id,))
    
    # Convertir les objets datetime en chaînes
    annulations_list = []
    for a in annulations:
        if isinstance(a, dict):
            date_annulation = a.get('date_annulation')
            if date_annulation and hasattr(date_annulation, 'strftime'):
                date_annulation_str = date_annulation.strftime('%Y-%m-%d %H:%M:%S')
            else:
                date_annulation_str = str(date_annulation) if date_annulation else ''
            
            annulations_list.append({
                'id': a.get('id'),
                'vente_id': a.get('vente_id'),
                'vente_type': a.get('vente_type'),
                'motif': a.get('motif'),
                'annule_par_nom': a.get('annule_par_nom'),
                'ancien_net_a_payer': a.get('ancien_net_a_payer'),
                'ancien_sous_total': a.get('ancien_sous_total'),
                'date_annulation': date_annulation_str,
                'patient_nom': a.get('patient_nom'),
                'vente_date': a.get('vente_date')
            })
        else:
            # Format tuple
            date_annulation = a[7] if len(a) > 7 else None
            if date_annulation and hasattr(date_annulation, 'strftime'):
                date_annulation_str = date_annulation.strftime('%Y-%m-%d %H:%M:%S')
            else:
                date_annulation_str = str(date_annulation) if date_annulation else ''
            
            annulations_list.append({
                'id': a[0],
                'vente_id': a[1],
                'vente_type': a[2],
                'motif': a[3],
                'annule_par_nom': a[4],
                'ancien_net_a_payer': a[5],
                'ancien_sous_total': a[6],
                'date_annulation': date_annulation_str,
                'patient_nom': a[8] if len(a) > 8 else None,
                'vente_date': a[9] if len(a) > 9 else None
            })
    
    return render_template('historique_annulations.html', annulations=annulations_list)

@app.route('/api/annulations')
@login_required
def api_get_annulations():
    """API pour récupérer les annulations (admin uniquement)"""
    if not session.get('is_admin'):
        return jsonify({'error': 'Non autorisé'}), 403
    
    structure_id = session.get('structure_id')
    
    annulations = db.execute_query("""
        SELECT 
            a.id,
            a.vente_id,
            a.vente_type,
            a.motif,
            a.annule_par_nom,
            a.ancien_net_a_payer,
            a.ancien_sous_total,
            a.date_annulation,
            v.patient_nom,
            v.date_vente as vente_date
        FROM annulations_ventes a
        LEFT JOIN ventes v ON a.vente_id = v.id
        WHERE v.structure_id = %s OR v.structure_id IS NULL
        ORDER BY a.date_annulation DESC
    """, (structure_id,))
    
    return jsonify(annulations)
# ========== GESTION FINANCIÈRE ==========

@app.route('/admin/finances')
@login_required
def admin_finances():
    """Page d'administration financière"""
    if not session.get('is_admin'):
        flash('Accès non autorisé', 'danger')
        return redirect(url_for('dashboard'))
    
    structure_id = session.get('structure_id')
    
    # 🔥 Récupérer les recettes (exclure les annulations)
    recettes = db.execute_query("""
        SELECT * FROM recettes 
        WHERE structure_id = %s 
        AND (est_annulation IS NULL OR est_annulation = FALSE)
        ORDER BY date_recette DESC
    """, (structure_id,))
    
    # Récupérer les dépenses
    depenses = db.execute_query("""
        SELECT * FROM depenses 
        WHERE structure_id = %s 
        ORDER BY date_depense DESC
    """, (structure_id,))
    
    # Récupérer le solde de caisse
    caisse = db.execute_query("""
        SELECT * FROM caisse WHERE structure_id = %s
    """, (structure_id,))
    
    solde = caisse[0]['solde_actuel'] if caisse and len(caisse) > 0 else 0
    
    # 🔥 Calculer les totaux (exclure annulations)
    total_recettes = db.execute_query("""
        SELECT COALESCE(SUM(montant), 0) as total 
        FROM recettes 
        WHERE structure_id = %s 
        AND (est_annulation IS NULL OR est_annulation = FALSE)
    """, (structure_id,))
    total_recettes = total_recettes[0]['total'] if total_recettes else 0
    
    total_depenses = db.execute_query("""
        SELECT COALESCE(SUM(montant), 0) as total 
        FROM depenses 
        WHERE structure_id = %s
    """, (structure_id,))
    total_depenses = total_depenses[0]['total'] if total_depenses else 0
    
    return render_template('admin_finances.html', 
                         recettes=recettes,
                         depenses=depenses,
                         solde=solde,
                         total_recettes=total_recettes,
                         total_depenses=total_depenses)


@app.route('/api/finances/recettes', methods=['POST'])
@login_required
def api_add_recette():
    """Ajouter une recette"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': 'Non autorisé'}), 403
    
    try:
        data = request.json
        structure_id = session.get('structure_id')
        user_name = session.get('user_name', 'Admin')
        
        result = db.execute_query("""
            INSERT INTO recettes (structure_id, montant, source, description, created_by_nom)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (
            structure_id,
            data.get('montant'),
            data.get('source', 'autres'),
            data.get('description', ''),
            user_name
        ))
        
        # 🔥 Mettre à jour le solde de caisse (exclure annulations)
        db.execute_query("""
            INSERT INTO caisse (structure_id, solde_actuel, date_mise_a_jour)
            VALUES (%s, 
                (SELECT COALESCE(SUM(montant), 0) FROM recettes WHERE structure_id = %s AND (est_annulation IS NULL OR est_annulation = FALSE)) - 
                (SELECT COALESCE(SUM(montant), 0) FROM depenses WHERE structure_id = %s), 
                NOW())
            ON CONFLICT (structure_id) DO UPDATE SET 
                solde_actuel = EXCLUDED.solde_actuel,
                date_mise_a_jour = NOW()
        """, (structure_id, structure_id, structure_id))
        
        return jsonify({'success': True, 'id': result[0]['id']})
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ========== API FINANCES ==========

@app.route('/api/finances/stats')
@login_required
def api_finances_stats():
    if not session.get('is_admin'):
        return jsonify({'error': 'Non autorise'}), 403
    
    try:
        structure_id = session.get('structure_id')
        date_debut = request.args.get('date_debut')
        date_fin = request.args.get('date_fin')
        
        # 🔥 Construction de la condition WHERE (exclure annulations)
        where_clause = "WHERE structure_id = %s AND (est_annulation IS NULL OR est_annulation = FALSE)"
        params = [structure_id]
        
        if date_debut and date_fin:
            date_debut_formatted = date_debut + " 00:00:00"
            date_fin_formatted = date_fin + " 23:59:59"
            where_clause += " AND date_recette BETWEEN %s AND %s"
            params.extend([date_debut_formatted, date_fin_formatted])
        
        # 🔥 Recettes (exclure annulations)
        recettes = db.execute_query(f"""
            SELECT COALESCE(SUM(montant), 0) as total
            FROM recettes 
            {where_clause}
        """, params)
        
        # Depenses
        params_dep = [structure_id]
        where_clause_dep = "WHERE structure_id = %s"
        if date_debut and date_fin:
            date_debut_formatted = date_debut + " 00:00:00"
            date_fin_formatted = date_fin + " 23:59:59"
            where_clause_dep += " AND date_depense BETWEEN %s AND %s"
            params_dep.extend([date_debut_formatted, date_fin_formatted])
        
        depenses = db.execute_query(f"""
            SELECT COALESCE(SUM(montant), 0) as total
            FROM depenses 
            {where_clause_dep}
        """, params_dep)
        
        # 🔥 Recettes par source (exclure annulations)
        recettes_par_source = db.execute_query(f"""
            SELECT source, COALESCE(SUM(montant), 0) as total
            FROM recettes 
            {where_clause}
            GROUP BY source
        """, params)
        
        total_recettes = recettes[0]['total'] if recettes else 0
        total_depenses = depenses[0]['total'] if depenses else 0
        
        return jsonify({
            'total_recettes': total_recettes,
            'total_depenses': total_depenses,
            'solde': total_recettes - total_depenses,
            'recettes_par_source': recettes_par_source
        })
        
    except Exception as e:
        print(f"Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/finances/recettes/detail')
@login_required
def api_recettes_detail():
    if not session.get('is_admin'):
        return jsonify({'error': 'Non autorise'}), 403
    
    try:
        structure_id = session.get('structure_id')
        date_debut = request.args.get('date_debut')
        date_fin = request.args.get('date_fin')
        
        # 🔥 Exclure les ventes annulées
        where_clause = "WHERE structure_id = %s AND (statut IS NULL OR statut != 'annulee')"
        params = [structure_id]
        
        if date_debut and date_fin:
            date_debut_formatted = date_debut + " 00:00:00"
            date_fin_formatted = date_fin + " 23:59:59"
            where_clause += " AND date_vente BETWEEN %s AND %s"
            params.extend([date_debut_formatted, date_fin_formatted])
        
        query = f"""
            SELECT 
                type,
                COUNT(*) as nombre_ventes,
                COALESCE(SUM(net_a_payer), 0) as total_recettes
            FROM ventes 
            {where_clause}
            GROUP BY type
        """
        recettes = db.execute_query(query, params)
        
        return jsonify(recettes)
        
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify([]), 500

@app.route('/api/finances/depenses', methods=['POST'])
@login_required
def api_add_depense():
    """Ajouter une depense"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': 'Non autorise'}), 403
    
    try:
        data = request.json
        structure_id = session.get('structure_id')
        user_name = session.get('user_name', 'Admin')
        
        # Verifier le solde suffisant
        recettes_total = db.execute_query("""
            SELECT COALESCE(SUM(net_a_payer), 0) as total
            FROM ventes 
            WHERE structure_id = %s AND (statut = 'validee' OR statut IS NULL)
        """, (structure_id,))
        
        depenses_total = db.execute_query("""
            SELECT COALESCE(SUM(montant), 0) as total
            FROM depenses 
            WHERE structure_id = %s
        """, (structure_id,))
        
        solde = (recettes_total[0]['total'] if recettes_total else 0) - (depenses_total[0]['total'] if depenses_total else 0)
        montant = float(data.get('montant', 0))
        
        if montant > solde:
            return jsonify({'success': False, 'error': f'Solde insuffisant. Solde actuel: {int(solde)} FCFA'}), 400
        
        result = db.execute_query("""
            INSERT INTO depenses (structure_id, montant, motif, motif_personnalise, description, created_by_nom)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            structure_id,
            montant,
            data.get('motif'),
            data.get('motif_personnalise', ''),
            data.get('description', ''),
            user_name
        ))
        
        return jsonify({'success': True, 'id': result[0]['id']})
        
    except Exception as e:
        print(f"Erreur api_add_depense: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/statistiques_ventes')
@login_required
def statistiques_ventes():
    """Page des statistiques de ventes pour les employes"""
    # Vérifier si l'utilisateur est admin
    if not session.get('is_admin'):
        flash('Accès non autorisé. Réservé à l\'administrateur.', 'danger')
        return redirect(url_for('dashboard'))
    
    structure_id = session.get('structure_id')
    
    # Recuperer toutes les ventes (y compris annulees pour les stats)
    ventes = db.execute_query("""
        SELECT 
            v.id,
            v.patient_nom,
            v.type,
            v.net_a_payer,
            v.sous_total,
            v.taux_assurance,
            v.date_vente,
            v.mode_paiement,
            v.statut,
            v.created_by_nom as vendeur,
            v.actes,
            v.produits
        FROM ventes v
        WHERE v.structure_id = %s
        ORDER BY v.date_vente DESC
    """, (structure_id,))
    
    return render_template('statistiques_ventes.html', ventes=ventes)

# ========== API ASSURANCES ==========
@app.route('/api/assurances/factures', methods=['POST'])
@login_required
def api_add_facture_assurance():
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': 'Non autorise'}), 403
    
    try:
        data = request.json
        structure_id = session.get('structure_id')
        user_name = session.get('user_name', 'Admin')
        
        result = db.execute_query("""
            INSERT INTO factures_assurance (
                structure_id, patient_nom, assurance, numero_assure,
                montant_facture, mois_reference, notes, created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            structure_id,
            data.get('patient_nom'),
            data.get('assurance'),
            data.get('numero_assure', ''),
            data.get('montant_facture'),
            data.get('mois_reference'),
            data.get('notes', ''),
            user_name
        ))
        
        return jsonify({'success': True, 'id': result[0]['id']})
        
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/assurances/factures/<int:facture_id>/paiement', methods=['POST'])
@login_required
def api_paiement_assurance(facture_id):
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': 'Non autorise'}), 403
    
    try:
        data = request.json
        structure_id = session.get('structure_id')
        montant = float(data.get('montant', 0))
        date_remboursement = data.get('date_remboursement')
        
        # Recuperer la facture
        facture = db.execute_query("""
            SELECT * FROM factures_assurance 
            WHERE id = %s AND structure_id = %s
        """, (facture_id, structure_id))
        
        if not facture:
            return jsonify({'success': False, 'error': 'Facture non trouvee'}), 404
        
        f = facture[0]
        deja_rembourse = float(f.get('montant_rembourse', 0))
        nouveau_rembourse = deja_rembourse + montant
        total_facture = float(f.get('montant_facture', 0))
        
        if nouveau_rembourse > total_facture:
            return jsonify({'success': False, 'error': 'Montant depasse le solde restant'}), 400
        
        if nouveau_rembourse >= total_facture:
            statut = 'payee'
        else:
            statut = 'partielle'
        
        # Mettre a jour la facture
        db.execute_query("""
            UPDATE factures_assurance 
            SET montant_rembourse = %s,
                statut = %s,
                date_remboursement = %s
            WHERE id = %s AND structure_id = %s
        """, (nouveau_rembourse, statut, date_remboursement, facture_id, structure_id))
        
        # Ajouter a la caisse (recette)
        db.execute_query("""
            INSERT INTO recettes (structure_id, montant, source, description, created_by_nom)
            VALUES (%s, %s, %s, %s, %s)
        """, (structure_id, montant, 'assurance', f'Remboursement assurance facture #{facture_id} - {f.get("patient_nom")}', session.get('user_name', 'Admin')))
        
        # Mettre a jour le solde de caisse
        db.execute_query("""
            INSERT INTO caisse (structure_id, solde_actuel, date_mise_a_jour)
            VALUES (%s, 
                (SELECT COALESCE(SUM(montant), 0) FROM recettes WHERE structure_id = %s) -
                (SELECT COALESCE(SUM(montant), 0) FROM depenses WHERE structure_id = %s),
                NOW())
            ON CONFLICT (structure_id) DO UPDATE SET 
                solde_actuel = EXCLUDED.solde_actuel,
                date_mise_a_jour = NOW()
        """, (structure_id, structure_id, structure_id))
        
        return jsonify({'success': True, 'message': 'Paiement enregistre'})
        
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/assurances/generer_factures', methods=['POST'])
@login_required
def generer_factures_assurance():
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': 'Non autorise'}), 403
    
    try:
        import calendar
        import json
        from datetime import datetime
        
        data = request.json
        structure_id = session.get('structure_id')
        mois_reference = data.get('mois_reference')
        
        if not mois_reference:
            return jsonify({'success': False, 'error': 'Mois reference requis'}), 400
        
        annee, mois = map(int, mois_reference.split('-'))
        date_debut = f"{annee}-{mois:02d}-01"
        dernier_jour = calendar.monthrange(annee, mois)[1]
        date_fin = f"{annee}-{mois:02d}-{dernier_jour}"
        
        print(f"Periode: du {date_debut} au {date_fin}")
        
        # 🔥 Recuperer les ventes AVEC assurance ET NON ANNULEES
        ventes = db.execute_query("""
            SELECT 
                v.id,
                v.patient_nom,
                v.sous_total,
                v.net_a_payer,
                v.taux_assurance,
                v.date_vente,
                p.type_assurance as assurance
            FROM ventes v
            JOIN patients p ON v.patient_id = p.id
            WHERE v.structure_id = %s 
            AND v.date_vente >= %s 
            AND v.date_vente <= %s
            AND (v.statut IS NULL OR v.statut != 'annulee')
            AND v.taux_assurance > 0
            AND p.type_assurance IS NOT NULL 
            AND p.type_assurance != 'non_assure'
            ORDER BY p.type_assurance
        """, (structure_id, date_debut, date_fin))
        
        print(f"Ventes avec assurance trouvees: {len(ventes)}")
        
        if not ventes:
            return jsonify({'success': False, 'error': 'Aucune vente avec assurance pour cette periode'}), 400
        
        factures_par_assurance = {}
        
        for v in ventes:
            assurance = v.get('assurance')
            if not assurance:
                continue
            
            if assurance not in factures_par_assurance:
                factures_par_assurance[assurance] = {
                    'total': 0,
                    'ventes': []
                }
            
            sous_total = float(v.get('sous_total') or 0)
            net_a_payer = float(v.get('net_a_payer') or 0)
            montant_assurance = sous_total - net_a_payer
            
            if montant_assurance > 0:
                factures_par_assurance[assurance]['total'] += montant_assurance
                factures_par_assurance[assurance]['ventes'].append({
                    'id': v.get('id'),
                    'patient_nom': v.get('patient_nom'),
                    'montant_assurance': montant_assurance,
                    'date_vente': str(v.get('date_vente'))
                })
        
        resultats = []
        
        for assurance, data_assurance in factures_par_assurance.items():
            if data_assurance['total'] == 0:
                continue
            
            # Verifier si une facture existe deja
            existing = db.execute_query("""
                SELECT id, montant_rembourse FROM factures_assurance 
                WHERE structure_id = %s AND mois_reference = %s AND assurance = %s
            """, (structure_id, mois_reference, assurance))
            
            if existing and len(existing) > 0:
                facture_id = existing[0]['id']
                deja_rembourse = float(existing[0]['montant_rembourse'] or 0)
                nouveau_total = data_assurance['total']
                
                if deja_rembourse >= nouveau_total:
                    nouveau_statut = 'payee'
                elif deja_rembourse > 0:
                    nouveau_statut = 'partielle'
                else:
                    nouveau_statut = 'en_attente'
                
                db.execute_query("""
                    UPDATE factures_assurance 
                    SET montant_total = %s, 
                        details = %s,
                        statut = %s
                    WHERE id = %s
                """, (nouveau_total, json.dumps(data_assurance['ventes']), nouveau_statut, facture_id))
                
                resultats.append({
                    'assurance': assurance, 
                    'montant': nouveau_total, 
                    'statut': 'mise_a_jour',
                    'reste': nouveau_total - deja_rembourse
                })
            else:
                result = db.execute_query("""
                    INSERT INTO factures_assurance (structure_id, mois_reference, assurance, montant_total, details)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """, (structure_id, mois_reference, assurance, data_assurance['total'], json.dumps(data_assurance['ventes'])))
                resultats.append({
                    'assurance': assurance, 
                    'montant': data_assurance['total'], 
                    'statut': 'nouvelle', 
                    'id': result[0]['id']
                })
        
        return jsonify({'success': True, 'factures': resultats, 'total_ventes': len(ventes)})
        
    except Exception as e:
        print(f"Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/assurances/factures')
@login_required
def api_get_factures_assurance():
    structure_id = session.get('structure_id')
    mois = request.args.get('mois')
    
    query = "SELECT * FROM factures_assurance WHERE structure_id = %s"
    params = [structure_id]
    
    if mois:
        query += " AND mois_reference = %s"
        params.append(mois)
    
    query += " ORDER BY mois_reference DESC, assurance"
    
    factures = db.execute_query(query, params)
    return jsonify(factures)
@app.route('/api/assurances/factures/<int:facture_id>/payer', methods=['POST'])
@login_required
def payer_facture_assurance(facture_id):
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': 'Non autorise'}), 403
    
    try:
        data = request.json
        structure_id = session.get('structure_id')
        montant = float(data.get('montant', 0))
        
        if montant <= 0:
            return jsonify({'success': False, 'error': 'Montant invalide'}), 400
        
        # Recuperer la facture
        facture = db.execute_query("""
            SELECT * FROM factures_assurance 
            WHERE id = %s AND structure_id = %s
        """, (facture_id, structure_id))
        
        if not facture or len(facture) == 0:
            return jsonify({'success': False, 'error': 'Facture non trouvee'}), 404
        
        f = facture[0]
        deja_rembourse = float(f.get('montant_rembourse', 0))
        total_facture = float(f.get('montant_total', 0))
        
        if montant > (total_facture - deja_rembourse):
            return jsonify({'success': False, 'error': f'Montant depasse le solde restant'}), 400
        
        nouveau_rembourse = deja_rembourse + montant
        
        if nouveau_rembourse >= total_facture:
            statut = 'payee'
        else:
            statut = 'partielle'
        
        # 1. Mettre a jour la facture
        db.execute_query("""
            UPDATE factures_assurance 
            SET montant_rembourse = %s, 
                statut = %s,
                date_remboursement = NOW()
            WHERE id = %s
        """, (nouveau_rembourse, statut, facture_id))
        
        # 2. Ajouter le remboursement dans les recettes (CAISSE)
        assurance_name = f.get('assurance')
        if assurance_name == 'amu_cnss':
            assurance_display = 'AMU-CNSS'
        elif assurance_name == 'amu_inam':
            assurance_display = 'AMU-INAM'
        else:
            assurance_display = assurance_name
        
        db.execute_query("""
            INSERT INTO recettes (structure_id, montant, source, description, created_by_nom)
            VALUES (%s, %s, 'assurance', %s, %s)
        """, (
            structure_id, 
            montant, 
            f'Remboursement assurance {assurance_display} - {f.get("mois_reference")}', 
            session.get('user_name', 'Admin')
        ))
        
        # 3. Mettre a jour le solde de la caisse
        # Recalculer le solde total = total_recettes - total_depenses
        db.execute_query("""
            INSERT INTO caisse (structure_id, solde_actuel, date_mise_a_jour)
            VALUES (%s, 
                (SELECT COALESCE(SUM(montant), 0) FROM recettes WHERE structure_id = %s) -
                (SELECT COALESCE(SUM(montant), 0) FROM depenses WHERE structure_id = %s),
                NOW())
            ON CONFLICT (structure_id) DO UPDATE SET 
                solde_actuel = EXCLUDED.solde_actuel,
                date_mise_a_jour = NOW()
        """, (structure_id, structure_id, structure_id))
        
        return jsonify({
            'success': True, 
            'message': f'Remboursement de {montant} FCFA enregistre',
            'reste': total_facture - nouveau_rembourse
        })
        
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/finances/recettes/source')
@login_required
def api_finances_recettes_source():
    """Recettes par source (patients, assurances, autres)"""
    if not session.get('is_admin'):
        return jsonify({'error': 'Non autorise'}), 403
    
    try:
        structure_id = session.get('structure_id')
        date_debut = request.args.get('date_debut')
        date_fin = request.args.get('date_fin')
        
        where_clause = "WHERE structure_id = %s"
        params = [structure_id]
        
        if date_debut and date_fin:
            where_clause += " AND date_recette BETWEEN %s AND %s"
            params.extend([date_debut, date_fin])
        
        recettes = db.execute_query(f"""
            SELECT 
                source,
                COALESCE(SUM(montant), 0) as total
            FROM recettes 
            {where_clause}
            GROUP BY source
            ORDER BY total DESC
        """, params)
        
        # Traduire les sources
        result = []
        for r in recettes:
            source = r.get('source')
            if source == 'patients':
                source_label = 'Patients'
            elif source == 'assurance':
                source_label = 'Assurances'
            else:
                source_label = 'Autres'
            result.append({
                'source': source_label,
                'total': r.get('total')
            })
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify([]), 500


@app.route('/api/finances/depenses/motif')
@login_required
def api_finances_depenses_motif():
    """Depenses par motif"""
    if not session.get('is_admin'):
        return jsonify({'error': 'Non autorise'}), 403
    
    try:
        structure_id = session.get('structure_id')
        date_debut = request.args.get('date_debut')
        date_fin = request.args.get('date_fin')
        
        where_clause = "WHERE structure_id = %s"
        params = [structure_id]
        
        if date_debut and date_fin:
            where_clause += " AND date_depense BETWEEN %s AND %s"
            params.extend([date_debut, date_fin])
        
        depenses = db.execute_query(f"""
            SELECT 
                motif,
                COALESCE(SUM(montant), 0) as total
            FROM depenses 
            {where_clause}
            GROUP BY motif
            ORDER BY total DESC
        """, params)
        
        return jsonify(depenses)
        
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify([]), 500

def calculer_age(date_naissance):
    """Calcule l'âge à partir d'une date de naissance"""
    if not date_naissance:
        return None
    today = date.today()
    age = today.year - date_naissance.year
    if (today.month, today.day) < (date_naissance.month, date_naissance.day):
        age -= 1
    return age

@app.route('/api/finances/recettes/source')
@login_required
def api_recettes_source():
    if not session.get('is_admin'):
        return jsonify({'error': 'Non autorise'}), 403
    
    try:
        structure_id = session.get('structure_id')
        date_debut = request.args.get('date_debut')
        date_fin = request.args.get('date_fin')
        
        where_clause = "WHERE structure_id = %s AND (est_annulation IS NULL OR est_annulation = FALSE)"
        params = [structure_id]
        
        if date_debut and date_fin:
            date_debut_formatted = date_debut + " 00:00:00"
            date_fin_formatted = date_fin + " 23:59:59"
            where_clause += " AND date_recette BETWEEN %s AND %s"
            params.extend([date_debut_formatted, date_fin_formatted])
        
        # 🔥 Recettes par source
        query = f"""
            SELECT 
                source,
                source_type,
                COUNT(*) as nombre,
                COALESCE(SUM(montant), 0) as total
            FROM recettes 
            {where_clause}
            GROUP BY source, source_type
            ORDER BY source, source_type
        """
        recettes = db.execute_query(query, params)
        
        return jsonify(recettes)
        
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify([]), 500

# ============================================
# ROUTES PROFORMA
# ============================================

@app.route('/proformas')
@login_required
def proformas():
    """Liste des proformas de la structure"""
    structure_id = session.get('structure_id')
    
    # Récupérer toutes les proformas
    proformas = db.execute_query("""
        SELECT 
            p.*,
            CASE 
                WHEN p.statut = 'en_attente' THEN 'En attente'
                WHEN p.statut = 'accepte' THEN 'Acceptée'
                WHEN p.statut = 'refuse' THEN 'Refusée'
                WHEN p.statut = 'converti_en_vente' THEN 'Convertie en vente'
                WHEN p.statut = 'expire' THEN 'Expirée'
                ELSE p.statut
            END as statut_label
        FROM proformas p
        WHERE p.structure_id = %s
        ORDER BY p.created_at DESC
    """, (structure_id,))
    
    # Statistiques
    stats = db.execute_query("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN statut = 'en_attente' THEN 1 END) as en_attente,
            COUNT(CASE WHEN statut = 'accepte' THEN 1 END) as acceptees,
            COUNT(CASE WHEN statut = 'converti_en_vente' THEN 1 END) as converties,
            COALESCE(SUM(CASE WHEN statut IN ('en_attente', 'accepte') THEN net_a_payer ELSE 0 END), 0) as total_montant
        FROM proformas
        WHERE structure_id = %s
    """, (structure_id,))
    
    stats = stats[0] if stats else {'total': 0, 'en_attente': 0, 'acceptees': 0, 'converties': 0, 'total_montant': 0}
    
    # 🔥 AJOUTER : Récupérer les actes et produits depuis Google Sheets
    actes = sheets_helper.get_all_records('actes')
    produits = sheets_helper.get_all_records('produits')
    
    # Filtrer par structure
    actes_filtres = [a for a in actes if str(a.get('structure_id')) == str(structure_id)]
    produits_filtres = [p for p in produits if str(p.get('structure_id')) == str(structure_id)]
    
    return render_template('proformas/proformas.html', 
                         proformas=proformas,
                         stats=stats,
                         actes=actes_filtres,    # 🔥 PASSER LES ACTES
                         produits=produits_filtres)  # 🔥 PASSER LES PRODUITS

@app.route('/api/proformas', methods=['POST'])
@login_required
def api_creer_proforma():
    """Créer une nouvelle proforma"""
    try:
        data = request.json
        structure_id = session.get('structure_id')
        user_name = session.get('user_name', 'System')
        
        print("=" * 60)
        print("📄 CRÉATION PROFORMA")
        print(f"Patient: {data.get('patient_nom')}")
        print(f"Articles: {len(data.get('articles', []))}")
        print("=" * 60)
        
        # Calculer les totaux
        articles = data.get('articles', [])
        sous_total = 0
        for article in articles:
            qte = float(article.get('quantite', 0))
            prix = float(article.get('prix_unitaire', 0))
            article['total'] = qte * prix
            sous_total += article['total']
        
        taux_assurance = float(data.get('taux_assurance', 0))
        prise_en_charge = sous_total * (taux_assurance / 100)
        net_a_payer = sous_total - prise_en_charge
        
        expires_at = datetime.now() + timedelta(days=7)
        
        # 🔥 Récupérer le prochain numéro pour cette structure
        next_numero = db.execute_query("""
            SELECT COALESCE(MAX(numero_proforma), 0) + 1 as next_num
            FROM proformas 
            WHERE structure_id = %s
        """, (structure_id,))
        
        prochain_numero = next_numero[0]['next_num'] if next_numero else 1
        print(f"   Numéro proforma pour structure {structure_id}: {prochain_numero}")
        
        # Insérer la proforma avec le numéro
        result = db.execute_query("""
            INSERT INTO proformas (
                structure_id, 
                patient_id, 
                patient_nom, 
                patient_telephone,
                assurance_nom,
                taux_assurance,
                numero_assure,
                type, 
                articles, 
                sous_total, 
                prise_en_charge, 
                net_a_payer, 
                notes,
                created_by,
                expires_at,
                numero_proforma
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            structure_id,
            data.get('patient_id'),
            data.get('patient_nom'),
            data.get('patient_telephone', ''),
            data.get('assurance_nom', 'Non assuré'),
            float(data.get('taux_assurance', 0)),
            data.get('numero_assure', ''),
            data.get('type', 'mixte'),
            json.dumps(articles, ensure_ascii=False),
            sous_total,
            prise_en_charge,
            net_a_payer,
            data.get('notes', ''),
            user_name,
            expires_at,
            prochain_numero
        ))
        
        proforma_id = result[0]['id']
        
        print(f"✅ Proforma #{proforma_id} créée (Numéro: {prochain_numero})")
        print(f"   Sous-total: {sous_total} FCFA")
        print(f"   Net à payer: {net_a_payer} FCFA")
        
        return jsonify({
            'success': True,
            'id': proforma_id,
            'numero': prochain_numero,
            'net_a_payer': net_a_payer,
            'sous_total': sous_total,
            'prise_en_charge': prise_en_charge
        })
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/proformas/<int:proforma_id>/statut', methods=['PUT'])
@login_required
def api_changer_statut_proforma(proforma_id):
    """Changer le statut d'une proforma"""
    try:
        data = request.json
        structure_id = session.get('structure_id')
        nouveau_statut = data.get('statut')
        
        if nouveau_statut not in ['en_attente', 'accepte', 'refuse', 'converti_en_vente', 'expire']:
            return jsonify({'success': False, 'error': 'Statut invalide'}), 400
        
        db.execute_query("""
            UPDATE proformas 
            SET statut = %s, updated_at = NOW()
            WHERE id = %s AND structure_id = %s
        """, (nouveau_statut, proforma_id, structure_id))
        
        return jsonify({
            'success': True,
            'message': f'Statut mis à jour vers {nouveau_statut}'
        })
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/proforma/<int:proforma_id>/print')
@login_required
def proforma_print(proforma_id):
    """Imprimer une proforma"""
    structure_id = session.get('structure_id')
    
    # Récupérer la proforma
    proforma = db.execute_query("""
        SELECT * FROM proformas 
        WHERE id = %s AND structure_id = %s
    """, (proforma_id, structure_id))
    
    if not proforma:
        flash('Proforma non trouvée', 'danger')
        return redirect(url_for('proformas'))
    
    proforma = proforma[0]
    
    # Récupérer les infos de la structure depuis Google Sheets
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    structure_info = next((s for s in structures if str(s.get('ID')) == str(structure_id)), {})
    
    # Récupérer le logo
    logo_url = structure_info.get('logo_url', '')
    
    return render_template('proformas/proforma_print.html', 
                         proforma=proforma,
                         structure=structure_info,
                         logo_url=logo_url)
@app.route('/api/proformas/count')
@login_required
def api_proformas_count():
    """Retourne le nombre de proformas en attente"""
    try:
        structure_id = session.get('structure_id')
        
        result = db.execute_query("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN statut = 'en_attente' THEN 1 END) as en_attente
            FROM proformas
            WHERE structure_id = %s
        """, (structure_id,))
        
        if result:
            return jsonify({
                'total': result[0]['total'],
                'en_attente': result[0]['en_attente']
            })
        return jsonify({'total': 0, 'en_attente': 0})
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'total': 0, 'en_attente': 0})
@app.route('/consultation')
@login_required
def consultation():
    """Page de consultation et prise en charge - Réservé aux admins, médecins et paramédicaux"""
    # Vérifier les droits
    if not session.get('is_admin') and session.get('role') not in ['medecin', 'paramedical']:
        flash('Accès non autorisé. Réservé au personnel médical.', 'danger')
        return redirect(url_for('dashboard'))
    
    return render_template('consultation.html')

if __name__ == '__main__':
    # Récupère le port depuis la variable d'environnement ou utilise 5000 par défaut
    port = int(os.environ.get("PORT", 5000))
    # Bind sur l'interface réseau 0.0.0.0 pour être accessible publiquement
    app.run(host='0.0.0.0', port=port, debug=False) # Mettez debug=False en production