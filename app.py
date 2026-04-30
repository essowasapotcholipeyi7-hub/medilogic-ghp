from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mail import Mail, Message
from config import Config
from sheets_helper import sheets_helper
import hashlib
import secrets
from datetime import datetime
import json
import os

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
        
        # 🔥 Chercher d'abord dans les utilisateurs (users)
        users = sheets_helper.get_all_records('users')
        for user in users:
            if user.get('email') == email:
                if user.get('mot_de_passe') == hash_password(password):
                    # Récupérer la structure du user
                    structure_id = user.get('structure_id')
                    structures = sheets_helper.get_all_records('structures', use_prefix=False)
                    structure = next((s for s in structures if s.get('ID') == structure_id), {})
                    
                    if structure.get('statut') == 'active':
                        session['user_id'] = user.get('ID')
                        session['user_name'] = user.get('nom')
                        session['structure_id'] = structure_id
                        session['structure_nom'] = structure.get('nom')
                        session['is_admin'] = (user.get('role') == 'admin')  # 🔥 True ou False
                        flash(f'Bienvenue {user.get("nom")}', 'success')
                        return redirect(url_for('dashboard'))
                    else:
                        flash('Structure non activée', 'warning')
                        return redirect(url_for('index'))
        
        # Si pas dans users, chercher dans structures (admin global)
        structures = sheets_helper.get_all_records('structures', use_prefix=False)
        for structure in structures:
            if structure.get('email') == email:
                if structure.get('mot_de_passe') == hash_password(password):
                    if structure.get('statut') == 'active':
                        session['user_id'] = structure.get('ID')
                        session['user_name'] = structure.get('nom')
                        session['structure_id'] = structure.get('ID')
                        session['structure_nom'] = structure.get('nom')
                        session['is_admin'] = True  # Le propriétaire est admin
                        flash(f'Bienvenue {structure.get("nom")}', 'success')
                        return redirect(url_for('dashboard'))
                    else:
                        flash('Structure en attente d\'activation', 'warning')
                        return redirect(url_for('index'))
                else:
                    flash('Mot de passe incorrect', 'danger')
                    return redirect(url_for('index'))
        
        flash('Email non trouvé', 'danger')
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
    
    # ========== PATIENTS ==========
    patients = sheets_helper.get_all_records('patients')
    patients = [p for p in patients if str(p.get('structure_id')) == str(structure_id)]
    total_patients = len(patients)
    
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
    patients_list = sheets_helper.get_all_records('patients')
    print(f"🔍 Patients trouvés pour structure {session.get('structure_id')}: {len(patients_list)}")
    return render_template('patients.html', patients=patients_list)

# MODIFIER la route d'ajout patient
@app.route('/api/patients', methods=['POST'])
@login_required
def api_add_patient():
    try:
        data = request.json
        patients = sheets_helper.get_all_records('patients')
        new_id = 1
        for p in patients:
            if p.get('ID', 0) >= new_id:
                new_id = p.get('ID') + 1
        
        new_patient = [
            new_id,
            data.get('nom'),
            data.get('prenom', ''),
            data.get('telephone'),
            data.get('adresse', ''),
            data.get('date_naissance', ''),
            data.get('type_assurance', 'non_assure'),
            str(data.get('taux_prise_charge', 0)),
            data.get('numero_assure', ''),
            str(session.get('structure_id')),
            datetime.now().isoformat()
        ]
        
        sheets_helper.add_record('patients', new_patient)
        return jsonify({'success': True, 'id': new_id})
    except Exception as e:
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

@app.route('/api/ventes/actes', methods=['POST'])
@login_required
def api_add_acte_vente():
    try:
        data = request.json
        
        ventes = sheets_helper.get_all_records('ventes_actes')
        new_id = get_next_id(ventes, 'ID')
        
        structure_id = session.get('structure_id')
        date_now = datetime.now().isoformat()
        
        # 🔥 Utilisation du BATCH pour tout envoyer en une fois
        for acte in data.get('actes', []):
            new_vente = [
                new_id, data.get('patient_id'), data.get('patient_nom'),
                acte.get('id'), acte.get('nom'), acte.get('prix'),
                acte.get('quantite'), acte.get('total'),
                data.get('taux_assurance', 0), data.get('prise_en_charge', 0),
                data.get('net_a_payer', 0), data.get('mode_paiement', 'especes'),
                date_now, structure_id
            ]
            sheets_helper.add_batch('ventes_actes', new_vente)  # ← Ajouter au lot
        
        # 🔥 Exécuter tout le lot
        sheets_helper.execute_batch()
        
        return jsonify({'success': True, 'vente_id': new_id})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/actes_vente')
@login_required
def actes_vente():
    actes = sheets_helper.get_all_records('actes')
    patients = sheets_helper.get_all_records('patients')
    
    print(f"🔍 Actes trouvés: {len(actes)}")  # Debug
    for a in actes:
        print(f"   - {a.get('nom')}: {a.get('prix')} FCFA")
    
    return render_template('actes_vente.html', actes=actes, patients=patients)

@app.route('/pharma_vente')
@login_required
def pharma_vente():
    produits = sheets_helper.get_all_records('produits')
    patients = sheets_helper.get_all_records('patients')
    
    print(f"🔍 Produits trouvés: {len(produits)}")  # Debug
    for p in produits:
        print(f"   - {p.get('nom')}: {p.get('prix_vente')} FCFA (Stock: {p.get('quantite_stock')})")
    
    return render_template('pharma_vente.html', produits=produits, patients=patients)

@app.route('/api/ventes/pharma', methods=['POST'])
@login_required
def api_add_pharma_vente():
    try:
        data = request.json
        print("📦 Données reçues pharma:", data)
        
        ventes = sheets_helper.get_all_records('ventes_pharma')
        new_id = get_next_id(ventes, 'ID')
        
        structure_id = session.get('structure_id')
        date_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        enregistres = 0
        for produit in data.get('produits', []):
            new_vente = [
                new_id,                                    # ID
                data.get('patient_id'),                    # patient_id
                data.get('patient_nom'),                   # patient_nom
                produit.get('id'),                         # produit_id
                produit.get('nom'),                        # produit_nom
                produit.get('prix'),                       # prix
                produit.get('quantite'),                   # quantite
                produit.get('total'),                      # total
                data.get('taux_assurance', 0),             # taux_assurance
                data.get('prise_en_charge', 0),            # prise_en_charge
                data.get('net_a_payer', 0),                # net_a_payer
                data.get('mode_paiement', 'especes'),      # mode_paiement
                str(data.get('avec_ordonnance', False)),   # avec_ordonnance
                date_now,                                  # date
                structure_id                               # structure_id
            ]
            sheets_helper.add_record('ventes_pharma', new_vente)
            enregistres += 1
            print(f"✅ Produit enregistré: {produit.get('nom')}")
        
        print(f"📊 {enregistres} produits enregistrés pour la vente ID {new_id}")
        
        return jsonify({'success': True, 'vente_id': new_id})
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/facture/<int:vente_id>/<string:type>')
@login_required
def facture(vente_id, type):
    from datetime import datetime
    
    structure_id = session.get('structure_id')
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    structure_info = next((s for s in structures if s.get('ID') == structure_id), {})
    patients = sheets_helper.get_all_records('patients')
    
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
    
    if type == 'actes':
        ventes = sheets_helper.get_all_records('ventes_actes')
        for v in ventes:
            if v.get('ID') == vente_id:
                total = float(v.get('total', 0))
                sous_total += total
                articles.append({
                    'nom': v.get('acte_nom', 'Acte'),
                    'quantite': int(v.get('quantite', 1)),
                    'prix_unitaire': float(v.get('prix', 0)),
                    'total': total
                })
                patient_nom = v.get('patient_nom', 'Patient')
                mode_paiement = v.get('mode_paiement', 'Espèces')
                taux_assurance = float(v.get('taux_assurance', 0))
                prise_en_charge = float(v.get('prise_en_charge', 0))
                net_a_payer = float(v.get('net_a_payer', 0))
                patient_id = v.get('patient_id')
        
        if patient_id:
            patient_info = next((p for p in patients if str(p.get('ID')) == str(patient_id)), {})
            type_assurance = patient_info.get('type_assurance', 'non_assure')
            numero_assure = patient_info.get('numero_assure', '')
    
    else:
        ventes = sheets_helper.get_all_records('ventes_pharma')
        for v in ventes:
            if v.get('ID') == vente_id:
                total = float(v.get('total', 0))
                sous_total += total
                articles.append({
                    'nom': v.get('produit_nom', 'Produit'),
                    'quantite': int(v.get('quantite', 1)),
                    'prix_unitaire': float(v.get('prix', 0)),
                    'total': total
                })
                patient_nom = v.get('patient_nom', 'Patient')
                mode_paiement = v.get('mode_paiement', 'Espèces')
                taux_assurance = float(v.get('taux_assurance', 0))
                prise_en_charge = float(v.get('prise_en_charge', 0))
                net_a_payer = float(v.get('net_a_payer', 0))
                patient_id = v.get('patient_id')
        
        if patient_id:
            patient_info = next((p for p in patients if str(p.get('ID')) == str(patient_id)), {})
            type_assurance = patient_info.get('type_assurance', 'non_assure')
            numero_assure = patient_info.get('numero_assure', '')
    
    # 🔥 GESTION DES ASSURANCES PERSONNALISÉES
    assurance_text = 'Non assuré'
    if type_assurance == 'amu_cnss':
        assurance_text = 'AMU-CNSS'
    elif type_assurance == 'amu_inam':
        assurance_text = 'AMU-INAM'
    elif type_assurance == 'autre':
        assurance_text = 'Autre assurance'
    elif type_assurance and type_assurance not in ['non_assure', 'amu_cnss', 'amu_inam', 'autre']:
        assurance_text = type_assurance

    # 🔥 AJOUTER CETTE LIGNE - Générer un nom de fichier
    patient_nom_clean = patient_nom.replace(' ', '_').replace("'", "").replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('à', 'a').replace('ç', 'c')
    nom_fichier = f"archive_facture_{patient_nom_clean}_{vente_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    structure_logo = structure_info.get('logo_url', '')
    nom_caissier = session.get('user_name', '')

    
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
                         structure_email=structure_info.get('email', ''),
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
    
    structure_id = session.get('structure_id')
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    structure_info = next((s for s in structures if s.get('ID') == structure_id), {})
    patients = sheets_helper.get_all_records('patients')
    
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
    
    if type == 'actes':
        ventes = sheets_helper.get_all_records('ventes_actes')
        for v in ventes:
            if v.get('ID') == vente_id:
                total = float(v.get('total', 0))
                sous_total += total
                articles.append({
                    'nom': v.get('acte_nom', 'Acte'),
                    'quantite': int(v.get('quantite', 1)),
                    'prix_unitaire': float(v.get('prix', 0)),
                    'total': total
                })
                patient_nom = v.get('patient_nom', 'Patient')
                mode_paiement = v.get('mode_paiement', 'Espèces')
                taux_assurance = float(v.get('taux_assurance', 0))
                prise_en_charge = float(v.get('prise_en_charge', 0))
                net_a_payer = float(v.get('net_a_payer', 0))
                patient_id = v.get('patient_id')
        
        if patient_id:
            patient_info = next((p for p in patients if str(p.get('ID')) == str(patient_id)), {})
            type_assurance = patient_info.get('type_assurance', 'non_assure')
            numero_assure = patient_info.get('numero_assure', '')
    
    else:  # pharmacie
        ventes = sheets_helper.get_all_records('ventes_pharma')
        for v in ventes:
            if v.get('ID') == vente_id:
                total = float(v.get('total', 0))
                sous_total += total
                articles.append({
                    'nom': v.get('produit_nom', 'Produit'),
                    'quantite': int(v.get('quantite', 1)),
                    'prix_unitaire': float(v.get('prix', 0)),
                    'total': total
                })
                patient_nom = v.get('patient_nom', 'Patient')
                mode_paiement = v.get('mode_paiement', 'Espèces')
                taux_assurance = float(v.get('taux_assurance', 0))
                prise_en_charge = float(v.get('prise_en_charge', 0))
                net_a_payer = float(v.get('net_a_payer', 0))
                patient_id = v.get('patient_id')
        
        if patient_id:
            patient_info = next((p for p in patients if str(p.get('ID')) == str(patient_id)), {})
            type_assurance = patient_info.get('type_assurance', 'non_assure')
            numero_assure = patient_info.get('numero_assure', '')
    
    # 🔥 GESTION DES ASSURANCES PERSONNALISÉES
    assurance_text = 'Non assuré'
    if type_assurance == 'amu_cnss':
        assurance_text = 'AMU-CNSS'
    elif type_assurance == 'amu_inam':
        assurance_text = 'AMU-INAM'
    elif type_assurance == 'autre':
        assurance_text = 'Autre assurance'
    elif type_assurance and type_assurance not in ['non_assure', 'amu_cnss', 'amu_inam', 'autre']:
        # 🔥 C'est une assurance personnalisée !
        assurance_text = type_assurance

    # 🔥 AJOUTER CETTE LIGNE - Générer un nom de fichier
    patient_nom_clean = patient_nom.replace(' ', '_').replace("'", "").replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('à', 'a').replace('ç', 'c')
    nom_fichier = f"archive_facture_{patient_nom_clean}_{vente_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    structure_logo=structure_info.get('logo_url', '')
    nom_caissier = session.get('user_name', '')


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
                         structure_nom=structure_info.get('nom', 'Medilogic-GHP'),
                         structure_adresse=structure_info.get('adresse', ''),
                         structure_telephone=structure_info.get('telephone', ''),
                         date_actuelle=datetime.now().strftime('%d/%m/%Y %H:%M'),
                         nom_fichier=nom_fichier,
                         structure_logo=structure_logo,
                         nom_caissier=nom_caissier)

                       

@app.route('/historique_ventes')
@login_required
def historique_ventes():
    """Affiche l'historique des ventes avec stats"""
    structure_id = session.get('structure_id')
    
    # Récupérer les ventes d'actes
    ventes_actes = sheets_helper.get_all_records('ventes_actes')
    for v in ventes_actes:
        v['type'] = 'actes'
        v['acte_nom'] = v.get('acte_nom', 'Acte')
        # S'assurer que la date est une chaîne
        date_val = v.get('date', '')
        if date_val is None:
            date_val = ''
        v['date'] = str(date_val) if date_val else ''
    
    # Récupérer les ventes de pharmacie
    ventes_pharma = sheets_helper.get_all_records('ventes_pharma')
    for v in ventes_pharma:
        v['type'] = 'pharma'
        v['produit_nom'] = v.get('produit_nom', 'Produit')
        date_val = v.get('date', '')
        if date_val is None:
            date_val = ''
        v['date'] = str(date_val) if date_val else ''
    
    # Fusionner et trier par date (plus récent d'abord)
    toutes_ventes = ventes_actes + ventes_pharma
    
    # Fonction de tri sécurisée
    def get_date_key(x):
        date_val = x.get('date', '')
        if date_val is None:
            return ''
        return str(date_val)
    
    toutes_ventes.sort(key=get_date_key, reverse=True)
    
    # Statistiques
    total_actes = len([v for v in ventes_actes if str(v.get('structure_id')) == str(structure_id)])
    total_pharma = len([v for v in ventes_pharma if str(v.get('structure_id')) == str(structure_id)])
    ca_total = sum([float(v.get('net_a_payer', 0)) for v in toutes_ventes if str(v.get('structure_id')) == str(structure_id)])
    
    # Top actes
    actes_count = {}
    for v in ventes_actes:
        if str(v.get('structure_id')) == str(structure_id):
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
        if str(v.get('structure_id')) == str(structure_id):
            nom = v.get('produit_nom', 'Produit')
            quantite = int(v.get('quantite', 1))
            total = float(v.get('total', 0))
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
    data = request.json
    users = sheets_helper.get_all_records('users')
    new_id = get_next_id(users, 'ID')
    
    password_hash = hash_password(data.get('password', 'default123'))
    
    new_user = [
        new_id,
        data.get('nom'),
        data.get('email'),
        password_hash,
        data.get('role', 'caissier'),
        session.get('structure_id'),
        datetime.now().isoformat()
    ]
    
    sheets_helper.add_record('users', new_user)
    return jsonify({'success': True})

@app.route('/admin_structure')
@login_required
def admin_structure():
    """Administration de la structure"""
    structure_id = session.get('structure_id')
    
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

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@login_required
def api_delete_user(user_id):
    # À implémenter: suppression d'un utilisateur
    return jsonify({'success': True})

@app.route('/api/admin/actes', methods=['POST'])
@login_required
def api_add_acte():
    data = request.json
    actes = sheets_helper.get_all_records('actes')
    
    if data.get('id'):
        # Modification
        pass
    else:
        # Ajout
        new_id = get_next_id(actes, 'ID')
        new_acte = [
            new_id,
            data.get('nom'),
            data.get('prix'),
            data.get('description', ''),
            session.get('structure_id')
        ]
        sheets_helper.add_record('actes', new_acte)
    
    return jsonify({'success': True})

@app.route('/api/admin/actes/<int:acte_id>', methods=['DELETE'])
@login_required
def api_delete_acte(acte_id):
    # À implémenter
    return jsonify({'success': True})

@app.route('/api/admin/produits', methods=['POST'])
@login_required
def api_add_produit():
    data = request.json
    produits = sheets_helper.get_all_records('produits')
    new_id = get_next_id(produits, 'ID')
    
    new_produit = [
        new_id,
        data.get('nom'),
        data.get('prix'),
        data.get('stock', 0),
        session.get('structure_id')
    ]
    
    sheets_helper.add_record('produits', new_produit)
    return jsonify({'success': True})

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
    """Reçu pour la structure (copie comptable)"""
    from datetime import datetime
    
    structure_id = session.get('structure_id')
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    structure_info = next((s for s in structures if s.get('ID') == structure_id), {})
    patients = sheets_helper.get_all_records('patients')
    
    articles = []
    sous_total = 0
    taux_assurance = 0
    prise_en_charge = 0
    net_a_payer = 0
    patient_nom = 'Patient'
    mode_paiement = 'Espèces'
    patient_id = None
    
    if type == 'actes':
        ventes = sheets_helper.get_all_records('ventes_actes')
        for v in ventes:
            if v.get('ID') == vente_id:
                total = float(v.get('total', 0))
                sous_total += total
                articles.append({
                    'nom': v.get('acte_nom', 'Acte'),
                    'quantite': int(v.get('quantite', 1)),
                    'total': total
                })
                patient_nom = v.get('patient_nom', 'Patient')
                mode_paiement = v.get('mode_paiement', 'Espèces')
                taux_assurance = float(v.get('taux_assurance', 0))
                prise_en_charge = float(v.get('prise_en_charge', 0))
                net_a_payer = float(v.get('net_a_payer', 0))
                patient_id = v.get('patient_id')
    
    else:
        ventes = sheets_helper.get_all_records('ventes_pharma')
        for v in ventes:
            if v.get('ID') == vente_id:
                total = float(v.get('total', 0))
                sous_total += total
                articles.append({
                    'nom': v.get('produit_nom', 'Produit'),
                    'quantite': int(v.get('quantite', 1)),
                    'total': total
                })
                patient_nom = v.get('patient_nom', 'Patient')
                mode_paiement = v.get('mode_paiement', 'Espèces')
                taux_assurance = float(v.get('taux_assurance', 0))
                prise_en_charge = float(v.get('prise_en_charge', 0))
                net_a_payer = float(v.get('net_a_payer', 0))
                patient_id = v.get('patient_id')
    
    # Récupérer le type d'assurance (optionnel pour structure)
    type_assurance = 'non_assure'
    if patient_id:
        patient_info = next((p for p in patients if str(p.get('ID')) == str(patient_id)), {})
        type_assurance = patient_info.get('type_assurance', 'non_assure')
    
    assurance_text = 'Non assuré'
    if type_assurance == 'amu_cnss':
        assurance_text = 'AMU-CNSS'
    elif type_assurance == 'amu_inam':
        assurance_text = 'AMU-INAM'
    elif type_assurance and type_assurance not in ['non_assure', 'amu_cnss', 'amu_inam', 'autre']:
        assurance_text = type_assurance

    # 🔥 AJOUTER CETTE LIGNE - Générer un nom de fichier
    patient_nom_clean = patient_nom.replace(' ', '_').replace("'", "").replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('à', 'a').replace('ç', 'c')
    nom_fichier = f"archive_facture_{patient_nom_clean}_{vente_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    structure_logo=structure_info.get('logo_url', '')
    nom_caissier = session.get('user_name', '')


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
                         structure_logo=structure_logo,
                         nom_caissier=nom_caissier)


# ========== FACTURE STRUCTURE (ARCHIVE) ==========
@app.route('/facture_structure/<int:vente_id>/<string:type>')
@login_required
def facture_structure(vente_id, type):
    """Facture pour la structure (archive)"""
    from datetime import datetime
    
    structure_id = session.get('structure_id')
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    structure_info = next((s for s in structures if s.get('ID') == structure_id), {})
    patients = sheets_helper.get_all_records('patients')  # ← AJOUTER
    
    articles = []
    sous_total = 0
    taux_assurance = 0
    prise_en_charge = 0
    net_a_payer = 0
    patient_nom = 'Patient'
    mode_paiement = 'Espèces'
    type_assurance = 'non_assure'
    numero_assure = ''
    patient_id = None  # ← AJOUTER
    
    if type == 'actes':
        ventes = sheets_helper.get_all_records('ventes_actes')
        for v in ventes:
            if v.get('ID') == vente_id:
                total = float(v.get('total', 0))
                sous_total += total
                articles.append({
                    'nom': v.get('acte_nom', 'Acte'),
                    'quantite': int(v.get('quantite', 1)),
                    'prix_unitaire': float(v.get('prix', 0)),
                    'total': total
                })
                patient_nom = v.get('patient_nom', 'Patient')
                mode_paiement = v.get('mode_paiement', 'Espèces')
                taux_assurance = float(v.get('taux_assurance', 0))
                prise_en_charge = float(v.get('prise_en_charge', 0))
                net_a_payer = float(v.get('net_a_payer', 0))
                patient_id = v.get('patient_id')
        
        # ← AJOUTER la récupération des infos patient
        if patient_id:
            patient_info = next((p for p in patients if str(p.get('ID')) == str(patient_id)), {})
            type_assurance = patient_info.get('type_assurance', 'non_assure')
            numero_assure = patient_info.get('numero_assure', '')
    
    else:  # pharmacie
        ventes = sheets_helper.get_all_records('ventes_pharma')
        for v in ventes:
            if v.get('ID') == vente_id:
                total = float(v.get('total', 0))
                sous_total += total
                articles.append({
                    'nom': v.get('produit_nom', 'Produit'),
                    'quantite': int(v.get('quantite', 1)),
                    'prix_unitaire': float(v.get('prix', 0)),
                    'total': total
                })
                patient_nom = v.get('patient_nom', 'Patient')
                mode_paiement = v.get('mode_paiement', 'Espèces')
                taux_assurance = float(v.get('taux_assurance', 0))
                prise_en_charge = float(v.get('prise_en_charge', 0))
                net_a_payer = float(v.get('net_a_payer', 0))
                patient_id = v.get('patient_id')
        
        # ← AJOUTER la récupération des infos patient
        if patient_id:
            patient_info = next((p for p in patients if str(p.get('ID')) == str(patient_id)), {})
            type_assurance = patient_info.get('type_assurance', 'non_assure')
            numero_assure = patient_info.get('numero_assure', '')
    
    # 🔥 GESTION DES ASSURANCES PERSONNALISÉES
    assurance_text = 'Non assuré'
    if type_assurance == 'amu_cnss':
        assurance_text = 'AMU-CNSS'
    elif type_assurance == 'amu_inam':
        assurance_text = 'AMU-INAM'
    elif type_assurance == 'autre':
        assurance_text = 'Autre assurance'
    elif type_assurance and type_assurance not in ['non_assure', 'amu_cnss', 'amu_inam', 'autre']:
        assurance_text = type_assurance

    # 🔥 AJOUTER CETTE LIGNE - Générer un nom de fichier
    patient_nom_clean = patient_nom.replace(' ', '_').replace("'", "").replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('à', 'a').replace('ç', 'c')
    nom_fichier = f"archive_facture_{patient_nom_clean}_{vente_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    structure_logo=structure_info.get('logo_url', '')
    nom_caissier = session.get('user_name', '')


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
                         date_actuelle=datetime.now().strftime('%d/%m/%Y %H:%M'),
                         nom_fichier=nom_fichier,
                         structure_logo=structure_logo,
                         nom_caissier=nom_caissier)

                     

# ========== RENDEZ-VOUS ==========
@app.route('/rendez_vous')
@login_required
def rendez_vous():
    """Page de gestion des rendez-vous"""
    structure_id = session.get('structure_id')
    
    # Récupérer les patients
    patients = sheets_helper.get_all_records('patients')
    patients = [p for p in patients if str(p.get('structure_id')) == str(structure_id)]
    
    # Récupérer les rendez-vous
    rendez_vous = sheets_helper.get_all_records('rendez_vous')
    rendez_vous = [r for r in rendez_vous if str(r.get('structure_id')) == str(structure_id)]
    rendez_vous.sort(key=lambda x: x.get('date_rendez_vous', ''))
    
    return render_template('rendez_vous.html', 
                         patients=patients,
                         rendez_vous=rendez_vous)

@app.route('/api/rendez_vous', methods=['POST'])
@login_required
def api_add_rendez_vous():
    try:
        data = request.json
        structure_id = session.get('structure_id')
        
        rendez_vous = sheets_helper.get_all_records('rendez_vous')
        new_id = get_next_id(rendez_vous, 'ID')
        
        new_rdv = [
            new_id,
            data.get('patient_id'),
            data.get('patient_nom'),
            data.get('patient_telephone'),
            data.get('date'),
            data.get('heure'),
            data.get('motif'),
            'programme',  # statut
            datetime.now().isoformat(),
            '',  # date_rappel
            'non',  # rappel_envoye
            structure_id
        ]
        
        sheets_helper.add_record('rendez_vous', new_rdv)
        return jsonify({'success': True, 'id': new_id})
    except Exception as e:
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
        
        # Récupérer le rendez-vous
        rendez_vous = sheets_helper.get_all_records('rendez_vous')
        rdv = next((r for r in rendez_vous if r.get('ID') == rdv_id), None)
        
        if not rdv:
            return jsonify({'success': False, 'error': 'Rendez-vous non trouvé'}), 404
        
        patient_nom = rdv.get('patient_nom')
        patient_tel = rdv.get('patient_telephone')
        ancienne_date = rdv.get('date_rendez_vous')
        ancienne_heure = rdv.get('heure_rendez_vous')
        
        # Récupérer la structure
        structure_id = session.get('structure_id')
        structures = sheets_helper.get_all_records('structures', use_prefix=False)
        structure_info = next((s for s in structures if s.get('ID') == structure_id), {})
        structure_nom = structure_info.get('nom', 'Medilogic-GHP')
        structure_tel = structure_info.get('telephone', '')
        
        # Mettre à jour dans Google Sheets
        sheet_name = f"struct_{structure_id}_rendez_vous"
        worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
        cell = worksheet.find(str(rdv_id), in_column=1)
        
        if not cell:
            return jsonify({'success': False, 'error': 'Rendez-vous non trouvé'}), 404
        
        row_num = cell.row
        current_row = worksheet.row_values(row_num)
        
        # Mettre à jour date, heure, motif, statut
        current_row[4] = nouvelle_date   # date_rendez_vous
        current_row[5] = nouvelle_heure  # heure_rendez_vous
        if nouveau_motif:
            current_row[6] = nouveau_motif  # motif
        current_row[7] = 'programme'    # statut (reprogrammé)
        current_row[10] = 'non'          # rappel_envoye (remettre à zéro)
        
        worksheet.update(f'A{row_num}:L{row_num}', [current_row])
        
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
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/rendez_vous/<int:rdv_id>/rappel', methods=['POST'])
@login_required
def api_envoyer_rappel(rdv_id):
    """Envoyer un rappel WhatsApp"""
    try:
        rendez_vous = sheets_helper.get_all_records('rendez_vous')
        rdv = next((r for r in rendez_vous if r.get('ID') == rdv_id), None)
        
        if not rdv:
            return jsonify({'success': False, 'error': 'Rendez-vous non trouvé'}), 404
        
        patient_nom = rdv.get('patient_nom')
        patient_tel = rdv.get('patient_telephone')
        date_rdv = rdv.get('date_rendez_vous')
        heure_rdv = rdv.get('heure_rendez_vous')
        motif = rdv.get('motif')
        
        # Récupérer les infos de la structure
        structure_id = session.get('structure_id')
        structures = sheets_helper.get_all_records('structures', use_prefix=False)
        structure_info = next((s for s in structures if s.get('ID') == structure_id), {})
        structure_nom = structure_info.get('nom', 'Medilogic-GHP')
        
        # 🔥 CORRECTION: Nettoyer le numéro en Python
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
        sheet_name = f"struct_{structure_id}_rendez_vous"
        worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
        
        # Trouver la ligne du rendez-vous
        cell = worksheet.find(str(rdv_id), in_column=1)
        if cell:
            row_num = cell.row
            # Mettre à jour le statut (colonne 8 = statut)
            worksheet.update_cell(row_num, 8, 'confirme')
            return jsonify({'success': True, 'message': 'Rendez-vous confirmé'})
        return jsonify({'success': False, 'error': 'Rendez-vous non trouvé'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/rendez_vous/<int:rdv_id>/annuler', methods=['POST'])
@login_required
def api_annuler_rendez_vous(rdv_id):
    """Annuler un rendez-vous"""
    try:
        structure_id = session.get('structure_id')
        sheet_name = f"struct_{structure_id}_rendez_vous"
        worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
        
        cell = worksheet.find(str(rdv_id), in_column=1)
        if cell:
            row_num = cell.row
            worksheet.update_cell(row_num, 8, 'annule')
            return jsonify({'success': True, 'message': 'Rendez-vous annulé'})
        return jsonify({'success': False, 'error': 'Rendez-vous non trouvé'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/rendez_vous/<int:rdv_id>/terminer', methods=['POST'])
@login_required
def api_terminer_rendez_vous(rdv_id):
    """Marquer un rendez-vous comme terminé"""
    try:
        structure_id = session.get('structure_id')
        sheet_name = f"struct_{structure_id}_rendez_vous"
        worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
        
        cell = worksheet.find(str(rdv_id), in_column=1)
        if cell:
            row_num = cell.row
            worksheet.update_cell(row_num, 8, 'termine')
            return jsonify({'success': True, 'message': 'Rendez-vous terminé'})
        return jsonify({'success': False, 'error': 'Rendez-vous non trouvé'})
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
    
    # Récupérer les infos du patient
    patients = sheets_helper.get_all_records('patients')
    patient_info = next((p for p in patients if p.get('ID') == patient_id), None)
    
    if not patient_info:
        return "Patient non trouvé", 404
    
    # Récupérer la structure
    structure_id = patient_info.get('structure_id')
    structures = sheets_helper.get_all_records('structures', use_prefix=False)
    structure_info = next((s for s in structures if s.get('ID') == structure_id), {})
    
    # 🔥 Récupérer le nom de l'hôpital
    structure_nom = structure_info.get('nom', 'Notre établissement')
    structure_telephone = structure_info.get('telephone', '')
    structure_adresse = structure_info.get('adresse', '')
    
    # Récupérer ses rendez-vous
    rendez_vous = sheets_helper.get_all_records('rendez_vous')
    mes_rendez_vous = [r for r in rendez_vous if str(r.get('patient_id')) == str(patient_id)]
    mes_rendez_vous.sort(key=lambda x: x.get('date_rendez_vous', ''))
    
    return render_template('patient_rendez_vous.html',
                         patient=patient_info,
                         rendez_vous=mes_rendez_vous,
                         structure_nom=structure_nom,
                         structure_telephone=structure_telephone,
                         structure_adresse=structure_adresse)

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
        'telephone': structure_info.get('telephone', '')
    })

# ========== RAPPELS AUTOMATIQUES RENDEZ-VOUS ==========
import threading
import time
from datetime import datetime, timedelta

def envoyer_rappel_auto(rdv, type_rappel):
    """Envoie un rappel automatique WhatsApp"""
    try:
        patient_nom = rdv.get('patient_nom', 'Patient')
        patient_tel = rdv.get('patient_telephone', '')
        date_rdv = rdv.get('date_rendez_vous', '')
        heure_rdv = rdv.get('heure_rendez_vous', '')
        motif = rdv.get('motif', 'Consultation')
        
        if not patient_tel:
            return False
        
        # Nettoyer le numéro
        tel = str(patient_tel).replace(' ', '').replace('+', '').replace('-', '')
        if not tel.startswith('228') and not tel.startswith('229') and not tel.startswith('221'):
            tel = '228' + tel
        
        if type_rappel == 'j7':
            message = f"🔔 *RAPPEL DE RENDEZ-VOUS (J-7)* 🔔%0A%0A"
            message += f"Bonjour *{patient_nom}*,%0A%0A"
            message += f"Nous vous rappelons votre rendez-vous dans une semaine :%0A"
            message += f"📅 Date : *{date_rdv}*%0A"
            message += f"⏰ Heure : *{heure_rdv}*%0A"
            message += f"📋 Motif : *{motif}*%0A%0A"
            message += f"Merci de votre ponctualité ! 🙏"
        else:
            message = f"🔔 *RAPPEL DE RENDEZ-VOUS (J-1)* 🔔%0A%0A"
            message += f"Bonjour *{patient_nom}*,%0A%0A"
            message += f"Nous vous rappelons votre rendez-vous de demain :%0A"
            message += f"📅 Date : *{date_rdv}*%0A"
            message += f"⏰ Heure : *{heure_rdv}*%0A"
            message += f"📋 Motif : *{motif}*%0A%0A"
            message += f"À très vite ! 🏥"
        
        whatsapp_url = f"https://wa.me/{tel}?text={message}"
        print(f"📱 [RAPPEL AUTO] {patient_nom} - {type_rappel}")
        # Optionnel: ouvrir WhatsApp automatiquement (décommenter si souhaité)
        # import webbrowser
        # webbrowser.open(whatsapp_url)
        return True
        
    except Exception as e:
        print(f"❌ Erreur envoi rappel: {e}")
        return False

def maj_statut_rappel(rdv_id, type_rappel):
    """Met à jour le statut du rappel dans Google Sheets"""
    try:
        structure_id = 1  # À adapter selon ta structure
        sheet_name = f"struct_{structure_id}_rendez_vous"
        worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
        
        cell = worksheet.find(str(rdv_id), in_column=1)
        if cell:
            worksheet.update_cell(cell.row, 11, type_rappel)  # colonne rappel_envoye
            return True
    except Exception as e:
        print(f"❌ Erreur maj statut: {e}")
    return False

def verifier_rappels_automatiques():
    """Vérifie les rendez-vous et envoie les rappels si nécessaire"""
    print(f"🔍 Vérification des rappels - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        rendez_vous = sheets_helper.get_all_records('rendez_vous')
        aujourdhui = datetime.now().date()
        j7 = aujourdhui + timedelta(days=7)
        j1 = aujourdhui + timedelta(days=1)
        
        for rdv in rendez_vous:
            date_rdv_str = rdv.get('date_rendez_vous')
            if not date_rdv_str:
                continue
            
            try:
                date_rdv = datetime.strptime(date_rdv_str, '%Y-%m-%d').date()
                statut = rdv.get('statut', 'programme')
                rappel_envoye = rdv.get('rappel_envoye', 'non')
                
                # Ignorer les rendez-vous déjà terminés ou annulés
                if statut in ['termine', 'annule']:
                    continue
                
                # Rappel J-7
                if date_rdv == j7 and rappel_envoye not in ['j7', 'j1']:
                    if envoyer_rappel_auto(rdv, 'j7'):
                        maj_statut_rappel(rdv.get('ID'), 'j7')
                        print(f"   ✅ Rappel J-7 envoyé à {rdv.get('patient_nom')}")
                
                # Rappel J-1
                elif date_rdv == j1 and rappel_envoye != 'j1':
                    if envoyer_rappel_auto(rdv, 'j1'):
                        maj_statut_rappel(rdv.get('ID'), 'j1')
                        print(f"   ✅ Rappel J-1 envoyé à {rdv.get('patient_nom')}")
                
                # Gestion des rendez-vous dépassés
                elif date_rdv < aujourdhui and statut not in ['termine', 'annule', 'depasse']:
                    # Marquer comme dépassé
                    structure_id = 1
                    sheet_name = f"struct_{structure_id}_rendez_vous"
                    worksheet = sheets_helper.spreadsheet.worksheet(sheet_name)
                    cell = worksheet.find(str(rdv.get('ID')), in_column=1)
                    if cell:
                        worksheet.update_cell(cell.row, 8, 'depasse')
                        print(f"   📆 RDV {rdv.get('ID')} marqué comme dépassé")
                        
            except Exception as e:
                print(f"   ⚠️ Erreur traitement RDV {rdv.get('ID')}: {e}")
                
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

@app.route('/api/rendez_vous/test_rappels')
@login_required
def test_rappels():
    """Route de test pour déclencher manuellement la vérification"""
    verifier_rappels_automatiques()
    return jsonify({'success': True, 'message': 'Vérification effectuée'})

@app.route('/rappels_rendez_vous')
@login_required
def rappels_rendez_vous():
    """Page des rappels - Rendez-vous à moins de 7 jours et dépassés"""
    from datetime import datetime, timedelta
    
    structure_id = session.get('structure_id')
    rendez_vous = sheets_helper.get_all_records('rendez_vous')
    
    aujourdhui = datetime.now().date()
    date_limite = aujourdhui + timedelta(days=7)
    
    moins_7_jours = []
    depasses = []
    
    for rdv in rendez_vous:
        if str(rdv.get('structure_id')) != str(structure_id):
            continue
        
        statut = rdv.get('statut', '')
        if statut in ['termine', 'annule']:
            continue
        
        date_rdv_str = rdv.get('date_rendez_vous')
        if not date_rdv_str:
            continue
        
        try:
            date_rdv = datetime.strptime(date_rdv_str, '%Y-%m-%d').date()
            
            # Rendez-vous dépassés
            if date_rdv < aujourdhui:
                rdv['jours_depasse'] = (aujourdhui - date_rdv).days
                depasses.append(rdv)
            
            # Rendez-vous dans les 7 jours (à venir)
            elif date_rdv <= date_limite:
                rdv['jours_restants'] = (date_rdv - aujourdhui).days
                moins_7_jours.append(rdv)
                
        except:
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
    """API pour les statistiques des rappels"""
    from datetime import datetime, timedelta
    
    structure_id = session.get('structure_id')
    rendez_vous = sheets_helper.get_all_records('rendez_vous')
    
    aujourdhui = datetime.now().date()
    date_limite = aujourdhui + timedelta(days=7)
    
    moins_7 = 0
    depasses = 0
    aujourdhui_count = 0
    
    for rdv in rendez_vous:
        if str(rdv.get('structure_id')) != str(structure_id):
            continue
        
        date_rdv_str = rdv.get('date_rendez_vous')
        if not date_rdv_str:
            continue
        
        try:
            date_rdv = datetime.strptime(date_rdv_str, '%Y-%m-%d').date()
            
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


if __name__ == '__main__':
    # Récupère le port depuis la variable d'environnement ou utilise 5000 par défaut
    port = int(os.environ.get("PORT", 5000))
    # Bind sur l'interface réseau 0.0.0.0 pour être accessible publiquement
    app.run(host='0.0.0.0', port=port, debug=False) # Mettez debug=False en production