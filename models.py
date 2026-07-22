# models.py - GHP
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
# ⭐ Créer db pour les modèles
db = SQLAlchemy()

# ============================================================
# STRUCTURE
# ============================================================
class Structure(db.Model):
    __tablename__ = 'structures'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(200), nullable=False)
    adresse = db.Column(db.Text)
    telephone = db.Column(db.String(50))
    email = db.Column(db.String(100), unique=True)
    statut = db.Column(db.String(20), default='en_attente')
    logo_url = db.Column(db.String(500))
    primary_color = db.Column(db.String(7), default='#0d6efd')
    secondary_color = db.Column(db.String(7), default='#6c757d')
    reset_question = db.Column(db.String(255))
    reset_answer_hash = db.Column(db.String(255))
    date_demande = db.Column(db.DateTime, default=datetime.utcnow)
    date_activation = db.Column(db.DateTime)
    
    utilisateurs = db.relationship('Utilisateur', backref='structure', lazy=True)
    patients = db.relationship('Patient', backref='structure', lazy=True)


# ============================================================
# UTILISATEUR
# ============================================================
class Utilisateur(db.Model):
    __tablename__ = 'utilisateurs'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nom = db.Column(db.String(100))
    prenom = db.Column(db.String(100))
    role = db.Column(db.String(50), default='admin')
    structure_id = db.Column(db.Integer, db.ForeignKey('structures.id'))
    actif = db.Column(db.Boolean, default=True)
    reset_token = db.Column(db.String(255))
    reset_token_expiry = db.Column(db.DateTime)
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    derniere_connexion = db.Column(db.DateTime)
    
    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)


# ============================================================
# PATIENT (version simplifiée - sans médecin référent)
# ============================================================
class Patient(db.Model):
    __tablename__ = 'patients'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, db.ForeignKey('structures.id'), nullable=False)
    
    # Identité
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100), nullable=False)
    date_naissance = db.Column(db.Date)
    telephone = db.Column(db.String(50))
    adresse = db.Column(db.Text)
    
    # Assurance
    type_assurance = db.Column(db.String(50))
    taux_prise_charge = db.Column(db.Float, default=0)
    numero_assure = db.Column(db.String(50))
    assurance2_nom = db.Column(db.String(100))
    taux_assurance2 = db.Column(db.Float, default=0)
    numero_assure2 = db.Column(db.String(50))
    personne_a_prevenir_nom = db.Column(db.String(100))
    personne_a_prevenir_telephone = db.Column(db.String(50))
    personne_a_prevenir_relation = db.Column(db.String(50))
    

# ============================================================
# STRUCTURE MAPPING (pour la synchronisation)
# ============================================================
class StructureMapping(db.Model):
    __tablename__ = 'structure_mappings'
    
    id = db.Column(db.Integer, primary_key=True)
    local_structure_id = db.Column(db.Integer, nullable=False)
    source_structure_id = db.Column(db.Integer, nullable=False)
    source_name = db.Column(db.String(50), default='ghp')
    api_url = db.Column(db.String(255), nullable=True)
    api_key = db.Column(db.String(255), nullable=True)
    last_sync = db.Column(db.DateTime, nullable=True)
    actif = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PrescriptionRecue(db.Model):
    __tablename__ = 'prescriptions_recues'
    
    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer)
    structure_id = db.Column(db.Integer, nullable=False)
    patient_id = db.Column(db.Integer)
    patient_nom = db.Column(db.String(100))
    patient_prenom = db.Column(db.String(100))
    medicament = db.Column(db.String(200), nullable=False)
    dosage = db.Column(db.String(50))
    forme = db.Column(db.String(50))
    quantite = db.Column(db.String(50))
    duree_jours = db.Column(db.Integer)
    frequence = db.Column(db.String(100))
    instructions = db.Column(db.Text)
    type_prescription = db.Column(db.String(20), default='medicament')
    date_prescription = db.Column(db.DateTime)
    prescripteur = db.Column(db.String(100))
    statut = db.Column(db.String(20), default='EN_ATTENTE')
    recu_le = db.Column(db.DateTime, default=datetime.utcnow)
    delivre_le = db.Column(db.DateTime)
    facture_le = db.Column(db.DateTime)

# ============================================================
# NOUVEAU : MODULES RH
# ============================================================

class Service(db.Model):
    __tablename__ = 'services'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    responsable = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    employes = db.relationship('Employe', backref='service', lazy=True)


class Employe(db.Model):
    __tablename__ = 'employes'
    
    id = db.Column(db.Integer, primary_key=True)
    matricule = db.Column(db.String(20), unique=True, nullable=False)
    
    # Identite
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100), nullable=False)
    sexe = db.Column(db.String(10), nullable=False)
    date_naissance = db.Column(db.Date)
    age = db.Column(db.Integer)
    nationalite = db.Column(db.String(50))
    quartier = db.Column(db.String(200))
    telephone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100))
    
    # Professionnel
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'))
    poste = db.Column(db.String(100))
    numero_poste = db.Column(db.String(20))
    date_embauche = db.Column(db.Date, nullable=False)
    type_contrat = db.Column(db.String(50))
    salaire_base = db.Column(db.Numeric, default=0)
    
    # Urgence
    personne_a_prevenir = db.Column(db.String(200))
    telephone_prevenir = db.Column(db.String(20))
    lien_parente = db.Column(db.String(50))
    
    # Statut
    statut = db.Column(db.String(20), default='Actif')
    
    # Documents
    photo_url = db.Column(db.String(500))
    piece_identite_url = db.Column(db.String(500))
    contrat_url = db.Column(db.String(500))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    conges = db.relationship('Conge', backref='employe', lazy=True)
    permissions = db.relationship('Permission', backref='employe', lazy=True)

    # 🔥 Suivi des congés
    conges_annuels = db.Column(db.Integer, default=30)  # Nombre de jours par an
    conges_pris_annee = db.Column(db.Integer, default=0)  # Jours déjà pris cette année
    annee_reference = db.Column(db.Integer, default=lambda: datetime.now().year)  # Année de référence
    
    def calculer_age(self):
        if self.date_naissance:
            today = date.today()
            return today.year - self.date_naissance.year - ((today.month, today.day) < (self.date_naissance.month, self.date_naissance.day))
        return None
    
    def calculer_anciennete(self):
        if self.date_embauche:
            today = date.today()
            years = today.year - self.date_embauche.year - ((today.month, today.day) < (self.date_embauche.month, self.date_embauche.day))
            return years
        return 0
    
    def solde_conges(self):
        anciennete_mois = self.calculer_anciennete() * 12
        total_acquis = anciennete_mois * 2.5
        conges_pris = db.session.query(db.func.sum(Conge.nombre_jours)).filter(
            Conge.employe_id == self.id,
            Conge.statut == 'approuve'
        ).scalar() or 0
        return total_acquis - conges_pris
    
    def solde_conges_restant(self):
        """Calcule le solde de congés restant pour l'année en cours"""
        annee_actuelle = datetime.now().year
        if self.annee_reference != annee_actuelle:
            # Nouvelle année, réinitialiser
            self.conges_pris_annee = 0
            self.annee_reference = annee_actuelle
            db.session.commit()
        return self.conges_annuels - self.conges_pris_annee
    
    def verifier_conges_disponibles(self, jours_demandes):
        """Vérifie si le nombre de jours demandés est disponible"""
        solde = self.solde_conges_restant()
        if jours_demandes <= solde:
            return {'disponible': True, 'solde': solde, 'message': f'Solde disponible: {solde} jours'}
        else:
            return {
                'disponible': False, 
                'solde': solde, 
                'message': f'Solde insuffisant. Restant: {solde} jours, Demandé: {jours_demandes} jours'
            }


class Conge(db.Model):
    __tablename__ = 'conges'
    
    id = db.Column(db.Integer, primary_key=True)
    employe_id = db.Column(db.Integer, db.ForeignKey('employes.id'), nullable=False)
    
    type_conge = db.Column(db.String(50), nullable=False)
    date_debut = db.Column(db.Date, nullable=False)
    date_fin = db.Column(db.Date, nullable=False)
    date_reprise = db.Column(db.Date)
    nombre_jours = db.Column(db.Integer)
    annee_utilisation = db.Column(db.Integer, default=lambda: datetime.now().year)
    
    motif = db.Column(db.Text)
    piece_jointe = db.Column(db.String(500))
    signataire = db.Column(db.String(100))
    
    statut = db.Column(db.String(20), default='en_attente')
    approuve_par = db.Column(db.String(100))
    date_approbation = db.Column(db.Date)
    commentaire = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # ========== MÉTHODES DE CALCUL ==========
    
    def calculer_jours_ouvres(self):
        """Calcule le nombre de jours ouvrés entre date_debut et date_fin"""
        from datetime import timedelta
        count = 0
        current = self.date_debut
        while current <= self.date_fin:
            if current.weekday() < 5:  # Lundi=0, Dimanche=6
                count += 1
            current += timedelta(days=1)
        return count
    
    def calculer_date_reprise(self):
        """Calcule la date de reprise (saut week-ends)"""
        from datetime import timedelta
        reprise = self.date_fin + timedelta(days=1)
        while reprise.weekday() >= 5:  # Samedi=5, Dimanche=6
            reprise += timedelta(days=1)
        return reprise


class Permission(db.Model):
    __tablename__ = 'permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    employe_id = db.Column(db.Integer, db.ForeignKey('employes.id'), nullable=False)
    
    type_permission = db.Column(db.String(20), default='heures')
    
    # 🔥 Rendre ces colonnes NULLABLES (nullable=True)
    date_permission = db.Column(db.Date, nullable=True)  # ← nullable=True
    heure_debut = db.Column(db.Time, nullable=True)     # ← nullable=True
    heure_fin = db.Column(db.Time, nullable=True)       # ← nullable=True
    
    date_debut = db.Column(db.Date, nullable=True)
    date_fin = db.Column(db.Date, nullable=True)
    
    nombre_jours = db.Column(db.Integer, default=1)

    motif = db.Column(db.Text, nullable=False)
    signataire = db.Column(db.String(100))
    
    statut = db.Column(db.String(20), default='en_attente')
    approuve_par = db.Column(db.String(100))
    date_approbation = db.Column(db.Date)
    commentaire = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DocumentRH(db.Model):
    __tablename__ = 'documents_rh'
    
    id = db.Column(db.Integer, primary_key=True)
    type_document = db.Column(db.String(20), nullable=False)
    numero_ordre = db.Column(db.String(50), unique=True)
    employe_id = db.Column(db.Integer, db.ForeignKey('employes.id'))
    contenu_pdf = db.Column(db.Text)
    statut = db.Column(db.String(20), default='brouillon')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SignatureRH(db.Model):
    __tablename__ = 'signatures_rh'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents_rh.id'))
    validateur_niveau = db.Column(db.Integer)
    validateur_nom = db.Column(db.String(100))
    statut = db.Column(db.String(20), default='en_attente')
    signature_nom = db.Column(db.String(100))
    signature_date = db.Column(db.Date)
    commentaire = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ============================================================
# COMPTABILITE - MODELES (CORRIGES)
# ============================================================

class CompteComptable(db.Model):
    __tablename__ = 'comptes_comptables'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, nullable=False)
    numero = db.Column(db.String(20), nullable=False)
    nom = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    classe = db.Column(db.String(10))
    parent_id = db.Column(db.Integer, db.ForeignKey('comptes_comptables.id'))
    niveau = db.Column(db.Integer, default=1)
    actif = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    enfants = db.relationship('CompteComptable', backref='parent', remote_side=[id])
    lignes = db.relationship('LigneEcriture', backref='compte', lazy=True)
    
    def get_solde(self, date_debut=None, date_fin=None):
        query = db.session.query(db.func.sum(LigneEcriture.debit - LigneEcriture.credit)).filter(
            LigneEcriture.compte_id == self.id
        )
        if date_debut:
            query = query.filter(LigneEcriture.ecriture.has(EcritureComptable.date_ecriture >= date_debut))
        if date_fin:
            query = query.filter(LigneEcriture.ecriture.has(EcritureComptable.date_ecriture <= date_fin))
        return query.scalar() or 0


class EcritureComptable(db.Model):
    __tablename__ = 'ecritures_comptables'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, nullable=False)
    date_ecriture = db.Column(db.Date, nullable=False)
    libelle = db.Column(db.Text, nullable=False)
    piece_justificative = db.Column(db.String(100))
    statut = db.Column(db.String(20), default='brouillon')
    created_by = db.Column(db.Integer, nullable=True)          # Sans ForeignKey
    created_by_nom = db.Column(db.String(100))
    validated_by = db.Column(db.Integer, nullable=True)        # Sans ForeignKey
    validated_by_nom = db.Column(db.String(100))
    date_validation = db.Column(db.Date)
    commentaire = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    lignes = db.relationship('LigneEcriture', backref='ecriture', lazy=True, cascade='all, delete-orphan')
    validations = db.relationship('ValidationComptable', backref='ecriture', lazy=True)
    
    def est_equilibree(self):
        total_debit = sum(l.debit for l in self.lignes) or 0
        total_credit = sum(l.credit for l in self.lignes) or 0
        return total_debit == total_credit
    
    def get_total_debit(self):
        return sum(l.debit for l in self.lignes) or 0
    
    def get_total_credit(self):
        return sum(l.credit for l in self.lignes) or 0
    
    def get_statut_label(self):
        labels = {
            'brouillon': 'Brouillon',
            'en_attente': 'En attente',
            'valide': 'Validee',
            'refuse': 'Refusee',
            'annulee': 'Annulee'
        }
        return labels.get(self.statut, self.statut)


class LigneEcriture(db.Model):
    __tablename__ = 'lignes_ecritures'
    
    id = db.Column(db.Integer, primary_key=True)
    ecriture_id = db.Column(db.Integer, db.ForeignKey('ecritures_comptables.id'), nullable=False)
    compte_id = db.Column(db.Integer, db.ForeignKey('comptes_comptables.id'), nullable=False)
    debit = db.Column(db.Numeric, default=0)
    credit = db.Column(db.Numeric, default=0)
    libelle = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Budget(db.Model):
    __tablename__ = 'budget'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, nullable=False)
    compte_id = db.Column(db.Integer, db.ForeignKey('comptes_comptables.id'))
    annee = db.Column(db.Integer, nullable=False)
    mois = db.Column(db.Integer, nullable=False)
    montant_prevu = db.Column(db.Numeric, default=0)
    montant_reel = db.Column(db.Numeric, default=0)
    ecart = db.Column(db.Numeric, default=0)
    commentaire = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ValidationComptable(db.Model):
    __tablename__ = 'validations_comptables'
    
    id = db.Column(db.Integer, primary_key=True)
    ecriture_id = db.Column(db.Integer, db.ForeignKey('ecritures_comptables.id'), nullable=False)
    niveau = db.Column(db.Integer, default=1)
    statut = db.Column(db.String(20), default='en_attente')
    valide_par = db.Column(db.Integer, nullable=True)          # Sans ForeignKey
    valide_par_nom = db.Column(db.String(100))
    date_validation = db.Column(db.Date)
    commentaire = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class HistoriqueEcriture(db.Model):
    __tablename__ = 'historique_ecritures'
    
    id = db.Column(db.Integer, primary_key=True)
    ecriture_id = db.Column(db.Integer, db.ForeignKey('ecritures_comptables.id'))
    action = db.Column(db.String(50), nullable=False)
    ancien_statut = db.Column(db.String(20))
    nouveau_statut = db.Column(db.String(20))
    modifie_par = db.Column(db.Integer, nullable=True)         # Sans ForeignKey
    modifie_par_nom = db.Column(db.String(100))
    commentaire = db.Column(db.Text)
    date_action = db.Column(db.DateTime, default=datetime.utcnow)
