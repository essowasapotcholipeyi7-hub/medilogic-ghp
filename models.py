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
# MODULES RH - CORRIGÉS AVEC structure_id
# ============================================================

class Service(db.Model):
    __tablename__ = 'services'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, db.ForeignKey('structures.id'), nullable=False)  # ⭐ AJOUTÉ
    nom = db.Column(db.String(100), nullable=False)
    responsable = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    employes = db.relationship('Employe', backref='service', lazy=True)


class Employe(db.Model):
    __tablename__ = 'employes'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, db.ForeignKey('structures.id'), nullable=False)
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

    # Suivi des congés
    conges_annuels = db.Column(db.Integer, default=30)
    conges_pris_annee = db.Column(db.Integer, default=0)
    annee_reference = db.Column(db.Integer, default=lambda: datetime.now().year)
    

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
        """Solde total des congés (ancien système)"""
        anciennete_mois = self.calculer_anciennete() * 12
        total_acquis = anciennete_mois * 2.5
        conges_pris = db.session.query(db.func.sum(Conge.nombre_jours)).filter(
            Conge.employe_id == self.id,
            Conge.statut == 'approuve'
        ).scalar() or 0
        return total_acquis - conges_pris
    
    def get_solde_par_annee(self, annee):
        """Retourne le solde de congés pour une année donnée"""
        conges_pris = db.session.query(db.func.sum(Conge.nombre_jours)).filter(
            Conge.employe_id == self.id,
            db.extract('year', Conge.date_debut) == annee,
            Conge.statut.in_(['en_attente', 'approuve', 'termine'])
        ).scalar() or 0
        
        permissions_pris = db.session.query(db.func.sum(Permission.nombre_jours)).filter(
            Permission.employe_id == self.id,
            db.extract('year', Permission.date_debut) == annee,
            Permission.statut.in_(['en_attente', 'approuve'])
        ).scalar() or 0
        
        total_pris = conges_pris + permissions_pris
        return 30 - total_pris
    
    def solde_conges_restant(self):
        """Calcule le solde de congés restant pour l'année en cours (incluant les permissions)"""
        annee_actuelle = datetime.now().year
        
        if self.annee_reference != annee_actuelle:
            self.conges_pris_annee = 0
            self.annee_reference = annee_actuelle
            db.session.commit()
        
        # ⭐ Utiliser la nouvelle méthode
        solde = self.get_solde_par_annee(annee_actuelle)
        
        # ⭐ Mettre à jour le champ conges_pris_annee
        conges_pris = db.session.query(db.func.sum(Conge.nombre_jours)).filter(
            Conge.employe_id == self.id,
            db.extract('year', Conge.date_debut) == annee_actuelle,
            Conge.statut.in_(['en_attente', 'approuve', 'termine'])
        ).scalar() or 0
        
        permissions_pris = db.session.query(db.func.sum(Permission.nombre_jours)).filter(
            Permission.employe_id == self.id,
            db.extract('year', Permission.date_debut) == annee_actuelle,
            Permission.statut.in_(['en_attente', 'approuve'])
        ).scalar() or 0
        
        total_pris = conges_pris + permissions_pris
        
        if self.conges_pris_annee != total_pris:
            self.conges_pris_annee = total_pris
            db.session.commit()
        
        return solde
    
    def verifier_conges_disponibles(self, jours_demandes, annee=None):
        """
        Vérifie si le nombre de jours demandés est disponible
        Si annee est spécifiée, vérifie pour cette année
        """
        if annee is None:
            annee = datetime.now().year
        
        solde = self.get_solde_par_annee(annee)
        
        if jours_demandes <= solde:
            return {
                'disponible': True, 
                'solde': solde, 
                'annee': annee,
                'message': f'Solde disponible: {solde} jours en {annee}'
            }
        else:
            # ⭐ Vérifier les années futures
            annees_futures = []
            for an in range(annee + 1, annee + 6):
                solde_futur = self.get_solde_par_annee(an)
                if solde_futur > 0:
                    annees_futures.append({
                        'annee': an,
                        'solde': solde_futur,
                        'disponible': solde_futur >= jours_demandes
                    })
            
            return {
                'disponible': False, 
                'solde': solde,
                'annee': annee,
                'jours_demandes': jours_demandes,
                'annees_futures': annees_futures,
                'message': f'Solde insuffisant. Restant: {solde} jours en {annee}, Demandé: {jours_demandes} jours'
            }
    
    def verifier_solde_avec_anticipation(self, jours_demandes, annee_demande):
        """Vérifie le solde avec anticipation sur les années futures"""
        return self.verifier_conges_disponibles(jours_demandes, annee_demande)

 
    def mettre_a_jour_statut(self):
        """Met à jour le statut de l'employé en fonction des congés"""
        today = date.today()
        
        # ⭐ 1. Vérifier si l'employé a un congé en cours (approuvé)
        conge_en_cours = Conge.query.filter(
            Conge.employe_id == self.id,
            Conge.statut == 'approuve',
            Conge.date_debut <= today,
            Conge.date_fin >= today
        ).first()
        
        if conge_en_cours:
            self.statut = 'En conge'
            db.session.commit()
            return 'En conge'
        
        # ⭐ 2. Vérifier si l'employé a un congé approuvé qui commence aujourd'hui
        conge_commence = Conge.query.filter(
            Conge.employe_id == self.id,
            Conge.statut == 'approuve',
            Conge.date_debut == today
        ).first()
        
        if conge_commence:
            self.statut = 'En conge'
            db.session.commit()
            return 'En conge'
        
        # ⭐ 3. Vérifier si l'employé était en congé et que la reprise est passée
        conge_termine = Conge.query.filter(
            Conge.employe_id == self.id,
            Conge.statut == 'approuve',
            Conge.date_fin < today
        ).order_by(Conge.date_fin.desc()).first()
        
        if conge_termine:
            # Vérifier si la date de reprise est passée
            if conge_termine.date_reprise and conge_termine.date_reprise <= today:
                self.statut = 'Actif'
                db.session.commit()
                return 'Actif'
        
        # ⭐ 4. Vérifier si l'employé a un solde négatif (a dépassé ses congés)
        solde = self.solde_conges_restant()
        if solde < 0:
            # Vérifier s'il a un congé en attente ou approuvé
            conges_actifs = Conge.query.filter(
                Conge.employe_id == self.id,
                Conge.statut.in_(['en_attente', 'approuve']),
                Conge.date_fin >= today
            ).first()
            
            if conges_actifs:
                self.statut = 'En conge'
                db.session.commit()
                return 'En conge'
        
        # ⭐ 5. Par défaut, Actif
        self.statut = 'Actif'
        db.session.commit()
        return 'Actif'


class Conge(db.Model):
    __tablename__ = 'conges'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, db.ForeignKey('structures.id'), nullable=False)
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
        """Calcule le nombre de jours ouvrés (du lundi au vendredi)"""
        from datetime import timedelta
        count = 0
        current = self.date_debut
        while current <= self.date_fin:
            if current.weekday() < 5:  # Lundi=0, Dimanche=6
                count += 1
            current += timedelta(days=1)
        return count
    
    def calculer_date_reprise(self):
        """Calcule la date de reprise = date_fin + 1 jour"""
        from datetime import timedelta
        return self.date_fin + timedelta(days=1)

class Permission(db.Model):
    __tablename__ = 'permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    employe_id = db.Column(db.Integer, db.ForeignKey('employes.id'), nullable=False)
    
    type_permission = db.Column(db.String(20), default='heures')
    
    date_permission = db.Column(db.Date, nullable=True)
    heure_debut = db.Column(db.Time, nullable=True)
    heure_fin = db.Column(db.Time, nullable=True)
    
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
    structure_id = db.Column(db.Integer, db.ForeignKey('structures.id'), nullable=False)  # ⭐ AJOUTÉ
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

    cloturee = db.Column(db.Boolean, default=False)
    date_cloture = db.Column(db.DateTime)
    
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

# models.py - Ajouter à la fin de la section comptabilité

class Cloture(db.Model):
    __tablename__ = 'clotures'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, nullable=False)
    annee = db.Column(db.Integer, nullable=False)
    date_cloture = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# models.py - Ajouter à la fin de la section comptabilité

class ReleveBancaire(db.Model):
    __tablename__ = 'releves_bancaires'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, nullable=False)
    date_releve = db.Column(db.Date, nullable=False)
    solde_initial = db.Column(db.Numeric, default=0)
    solde_final = db.Column(db.Numeric, default=0)
    total_credits = db.Column(db.Numeric, default=0)
    total_debits = db.Column(db.Numeric, default=0)
    statut = db.Column(db.String(20), default='brouillon')  # brouillon, en_attente, valide
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    valide_par = db.Column(db.String(100))
    date_validation = db.Column(db.Date)
    
    lignes = db.relationship('LigneReleve', backref='releve', lazy=True, cascade='all, delete-orphan')


class LigneReleve(db.Model):
    __tablename__ = 'lignes_releves'
    
    id = db.Column(db.Integer, primary_key=True)
    releve_id = db.Column(db.Integer, db.ForeignKey('releves_bancaires.id'), nullable=False)
    date_operation = db.Column(db.Date, nullable=False)
    libelle = db.Column(db.Text, nullable=False)
    reference = db.Column(db.String(100))
    debit = db.Column(db.Numeric, default=0)
    credit = db.Column(db.Numeric, default=0)
    solde = db.Column(db.Numeric, default=0)
    rapproche = db.Column(db.Boolean, default=False)
    ecriture_id = db.Column(db.Integer, db.ForeignKey('ecritures_comptables.id'), nullable=True)
    commentaire = db.Column(db.Text)

# models.py - Modèle Vente EXACT (correspond à ta base)

class Vente(db.Model):
    __tablename__ = 'ventes'
    
    # ⭐ Colonnes existantes dans ta base
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, nullable=False)
    patient_nom = db.Column(db.String(255), nullable=False)
    structure_id = db.Column(db.Integer, nullable=False)
    type = db.Column(db.String(50), nullable=False)
    sous_total = db.Column(db.Float, default=0)
    prise_en_charge = db.Column(db.Float, default=0)
    net_a_payer = db.Column(db.Float, default=0)
    mode_paiement = db.Column(db.String(50), default='especes')
    taux_assurance = db.Column(db.Integer, default=0)  # ⭐ INTEGER (pas Float)
    date_vente = db.Column(db.DateTime, default=datetime.utcnow)
    actes = db.Column(db.JSON)
    produits = db.Column(db.JSON)
    statut = db.Column(db.String(50), default='validee')
    annulee_le = db.Column(db.DateTime)
    annulee_par = db.Column(db.Integer)
    motif_annulation = db.Column(db.String(255))
    created_by_nom = db.Column(db.String(100))
    vendeur = db.Column(db.String(100))
    assurance = db.Column(db.String(50))
    numero_assure = db.Column(db.String(50))
    assurances = db.Column(db.JSON)
    assurance2_nom = db.Column(db.String(100))
    taux_assurance2 = db.Column(db.Float, default=0)
    prise_en_charge2 = db.Column(db.Float, default=0)
    numero_assure2 = db.Column(db.String(50))
    montant_donne = db.Column(db.Float, default=0)
    rendu = db.Column(db.Float, default=0)
    reste_a_payer = db.Column(db.Float, default=0)
    base_remboursement = db.Column(db.Float, default=0)
    taux_temp_modifie = db.Column(db.Boolean, default=False)
    taux_original = db.Column(db.Float, default=0)
    
    # ⭐ Colonnes d'automatisation (déjà en base ✅)
    categorie_actes = db.Column(db.JSON, default=[])
    traite_comptable = db.Column(db.Boolean, default=False)
    ecriture_generee = db.Column(db.Boolean, default=False)
    ecriture_id = db.Column(db.Integer, nullable=True)
    
    # ⭐ Prescription IDs (déjà en base ✅)
    prescription_ids = db.Column(db.JSON, default=[])
    
    assurance_principale_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================
# MODÈLES POUR LES MÉDECINS ET RENDEZ-VOUS
# ============================================================

class Medecin(db.Model):
    """
    Modèle pour les médecins de la clinique
    """
    __tablename__ = 'medecins'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, db.ForeignKey('structures.id'), nullable=False)
    
    # Identité
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100))
    titre = db.Column(db.String(20), default='Dr')  # Dr, Pr, etc.
    sexe = db.Column(db.String(10))
    date_naissance = db.Column(db.Date)
    telephone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    
    # Professionnel
    specialite = db.Column(db.String(100), nullable=False)
    sous_specialite = db.Column(db.String(100))
    numero_ordre = db.Column(db.String(50))  # Numéro d'inscription à l'ordre
    annees_experience = db.Column(db.Integer)
    
    # Honoraires
    honoraire_consultation = db.Column(db.Float, default=0)
    honoraire_visite = db.Column(db.Float, default=0)
    honoraire_acte = db.Column(db.Float, default=0)
    taux_partage = db.Column(db.Float, default=0)  # Pourcentage pour la clinique
    
    # Horaires par défaut
    horaire_debut = db.Column(db.Time, default='08:00:00')
    horaire_fin = db.Column(db.Time, default='17:00:00')
    duree_consultation = db.Column(db.Integer, default=30)  # en minutes
    jours_travail = db.Column(db.JSON, default=['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi'])
    
    # Statut
    actif = db.Column(db.Boolean, default=True)
    disponible = db.Column(db.Boolean, default=True)
    remarques = db.Column(db.Text)
    
    # Photo
    photo_url = db.Column(db.String(500))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    structure = db.relationship('Structure', backref='medecins')
    rendez_vous = db.relationship('RendezVous', backref='medecin', lazy=True)
    
    def get_nom_complet(self):
        """Retourne le nom complet du médecin avec son titre"""
        return f"{self.titre} {self.prenom or ''} {self.nom}".strip()
    
    def get_honoraire(self, type_consultation='consultation'):
        """Retourne l'honoraire selon le type"""
        if type_consultation == 'consultation':
            return self.honoraire_consultation or 0
        elif type_consultation == 'visite':
            return self.honoraire_visite or 0
        elif type_consultation == 'acte':
            return self.honoraire_acte or 0
        return 0
    
    def est_disponible(self, date, heure):
        """Vérifie si le médecin est disponible à une date et heure donnée"""
        from datetime import datetime, time
        
        if not self.actif or not self.disponible:
            return False
        
        # Vérifier le jour de la semaine
        jours_semaine = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
        jour_semaine = jours_semaine[date.weekday()]
        if jour_semaine not in (self.jours_travail or []):
            return False
        
        # Vérifier les horaires
        heure_obj = datetime.strptime(heure, '%H:%M').time() if isinstance(heure, str) else heure
        if heure_obj < self.horaire_debut or heure_obj > self.horaire_fin:
            return False
        
        # Vérifier les rendez-vous existants
        rdv_conflict = RendezVous.query.filter(
            RendezVous.medecin_id == self.id,
            RendezVous.date_rendez_vous == date,
            RendezVous.statut.in_(['programme', 'confirme']),
            RendezVous.heure_rendez_vous == heure
        ).first()
        
        return rdv_conflict is None
    
    def get_consultations_mois(self, annee=None, mois=None):
        """Retourne le nombre de consultations pour un mois donné"""
        if annee is None:
            annee = datetime.now().year
        if mois is None:
            mois = datetime.now().month
        
        return RendezVous.query.filter(
            RendezVous.medecin_id == self.id,
            db.extract('year', RendezVous.date_rendez_vous) == annee,
            db.extract('month', RendezVous.date_rendez_vous) == mois,
            RendezVous.statut == 'termine'
        ).count()
    
    def get_honoraires_mois(self, annee=None, mois=None):
        """Retourne le total des honoraires pour un mois donné"""
        if annee is None:
            annee = datetime.now().year
        if mois is None:
            mois = datetime.now().month
        
        consultations = RendezVous.query.filter(
            RendezVous.medecin_id == self.id,
            db.extract('year', RendezVous.date_rendez_vous) == annee,
            db.extract('month', RendezVous.date_rendez_vous) == mois,
            RendezVous.statut == 'termine'
        ).count()
        
        return consultations * (self.honoraire_consultation or 0)
    
    def to_dict(self):
        """Convertit en dictionnaire pour l'API"""
        return {
            'id': self.id,
            'nom': self.nom,
            'prenom': self.prenom,
            'titre': self.titre,
            'nom_complet': self.get_nom_complet(),
            'specialite': self.specialite,
            'telephone': self.telephone,
            'email': self.email,
            'honoraire_consultation': self.honoraire_consultation,
            'actif': self.actif,
            'disponible': self.disponible,
            'photo_url': self.photo_url
        }


class RendezVous(db.Model):
    """
    Modèle pour les rendez-vous des patients
    """
    __tablename__ = 'rendez_vous'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, db.ForeignKey('structures.id'), nullable=False)
    
    # Patient
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    patient_nom = db.Column(db.String(200), nullable=False)
    patient_telephone = db.Column(db.String(20))
    patient_email = db.Column(db.String(100))
    
    # Médecin
    medecin_id = db.Column(db.Integer, db.ForeignKey('medecins.id'), nullable=False)
    
    # Date et heure
    date_rendez_vous = db.Column(db.Date, nullable=False)
    heure_rendez_vous = db.Column(db.String(10), nullable=False)  # Format: HH:MM
    duree = db.Column(db.Integer, default=30)  # en minutes
    date_fin = db.Column(db.DateTime)  # Calculé automatiquement
    
    # Détails
    motif = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.Text)
    type_consultation = db.Column(db.String(50), default='consultation')
    priorite = db.Column(db.String(20), default='normal')  # normal, urgent, prioritaire
    
    # Statut
    statut = db.Column(db.String(20), default='programme')
    # programme, confirme, termine, annule, reporte, absent
    
    # Suivi
    rappel_envoye = db.Column(db.Boolean, default=False)
    date_rappel = db.Column(db.DateTime)
    confirme_le = db.Column(db.DateTime)
    termine_le = db.Column(db.DateTime)
    
    # Création
    created_by = db.Column(db.Integer)  # ID de l'utilisateur
    created_by_nom = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    structure = db.relationship('Structure', backref='rendez_vous')
    patient = db.relationship('Patient', backref='rendez_vous')
    # medecin est déjà défini via backref
    
    def __init__(self, **kwargs):
        super(RendezVous, self).__init__(**kwargs)
        # Calculer automatiquement la date de fin
        if self.date_rendez_vous and self.heure_rendez_vous and self.duree:
            from datetime import datetime, timedelta
            date_heure = datetime.combine(
                self.date_rendez_vous,
                datetime.strptime(self.heure_rendez_vous, '%H:%M').time()
            )
            self.date_fin = date_heure + timedelta(minutes=self.duree)
    
    def get_statut_label(self):
        """Retourne le libellé du statut"""
        labels = {
            'programme': 'Programmé',
            'confirme': 'Confirmé',
            'termine': 'Terminé',
            'annule': 'Annulé',
            'reporte': 'Reporté',
            'absent': 'Absent'
        }
        return labels.get(self.statut, self.statut)
    
    def get_statut_badge_class(self):
        """Retourne la classe CSS pour le badge de statut"""
        classes = {
            'programme': 'bg-warning text-dark',
            'confirme': 'bg-success',
            'termine': 'bg-secondary',
            'annule': 'bg-danger',
            'reporte': 'bg-info',
            'absent': 'bg-dark'
        }
        return classes.get(self.statut, 'bg-secondary')
    
    def est_depasse(self):
        """Vérifie si le rendez-vous est dépassé"""
        if self.statut in ['annule', 'termine', 'absent']:
            return False
        from datetime import datetime
        date_heure = datetime.combine(
            self.date_rendez_vous,
            datetime.strptime(self.heure_rendez_vous, '%H:%M').time()
        )
        return date_heure < datetime.now()
    
    def peut_annuler(self):
        """Vérifie si le rendez-vous peut être annulé"""
        return self.statut in ['programme', 'confirme']
    
    def peut_modifier(self):
        """Vérifie si le rendez-vous peut être modifié"""
        return self.statut not in ['annule', 'termine', 'absent']
    
    def confirmer(self):
        """Confirme le rendez-vous"""
        if self.statut == 'programme':
            self.statut = 'confirme'
            self.confirme_le = datetime.utcnow()
            return True
        return False
    
    def terminer(self):
        """Marque le rendez-vous comme terminé"""
        if self.statut in ['programme', 'confirme']:
            self.statut = 'termine'
            self.termine_le = datetime.utcnow()
            return True
        return False
    
    def annuler(self, motif=None):
        """Annule le rendez-vous"""
        if self.peut_annuler():
            self.statut = 'annule'
            if motif:
                self.notes = (self.notes or '') + f"\nMotif annulation: {motif}"
            return True
        return False
    
    def reporter(self, nouvelle_date, nouvelle_heure, nouveau_medecin_id=None):
        """Reporte le rendez-vous à une nouvelle date/heure"""
        if self.peut_modifier():
            ancien_medecin = self.medecin_id
            self.date_rendez_vous = nouvelle_date
            self.heure_rendez_vous = nouvelle_heure
            if nouveau_medecin_id:
                self.medecin_id = nouveau_medecin_id
            self.statut = 'reporte'
            self.notes = (self.notes or '') + f"\nReporté du {self.date_rendez_vous} au {nouvelle_date} à {nouvelle_heure}"
            if nouveau_medecin_id and nouveau_medecin_id != ancien_medecin:
                self.notes += f" (Médecin: {self.medecin.get_nom_complet()})"
            return True
        return False
    
    def to_dict(self):
        """Convertit en dictionnaire pour l'API"""
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'patient_nom': self.patient_nom,
            'patient_telephone': self.patient_telephone,
            'medecin_id': self.medecin_id,
            'medecin_nom': self.medecin.get_nom_complet() if self.medecin else None,
            'medecin_specialite': self.medecin.specialite if self.medecin else None,
            'date': self.date_rendez_vous.isoformat() if self.date_rendez_vous else None,
            'heure': self.heure_rendez_vous,
            'duree': self.duree,
            'motif': self.motif,
            'notes': self.notes,
            'statut': self.statut,
            'statut_label': self.get_statut_label(),
            'statut_badge': self.get_statut_badge_class(),
            'est_depasse': self.est_depasse(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class HistoriqueRendezVous(db.Model):
    """
    Historique des actions sur les rendez-vous
    """
    __tablename__ = 'historique_rendez_vous'
    
    id = db.Column(db.Integer, primary_key=True)
    rendez_vous_id = db.Column(db.Integer, db.ForeignKey('rendez_vous.id'), nullable=False)
    
    action = db.Column(db.String(50), nullable=False)  # creation, confirmation, annulation, report, etc.
    ancien_statut = db.Column(db.String(20))
    nouveau_statut = db.Column(db.String(20))
    anciennes_donnees = db.Column(db.JSON)
    nouvelles_donnees = db.Column(db.JSON)
    
    utilisateur_id = db.Column(db.Integer)
    utilisateur_nom = db.Column(db.String(100))
    ip_adresse = db.Column(db.String(50))
    commentaire = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relation
    rendez_vous = db.relationship('RendezVous', backref='historique')


class DisponibiliteMedecin(db.Model):
    """
    Gestion des disponibilités spécifiques des médecins
    (congés, jours fériés, horaires exceptionnels)
    """
    __tablename__ = 'disponibilites_medecins'
    
    id = db.Column(db.Integer, primary_key=True)
    medecin_id = db.Column(db.Integer, db.ForeignKey('medecins.id'), nullable=False)
    
    type = db.Column(db.String(20), nullable=False)  # conge, ferie, exception, indisponible
    date_debut = db.Column(db.Date, nullable=False)
    date_fin = db.Column(db.Date, nullable=False)
    heure_debut = db.Column(db.Time)
    heure_fin = db.Column(db.Time)
    
    motif = db.Column(db.String(255))
    approuve_par = db.Column(db.String(100))
    commentaire = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relation
    medecin = db.relationship('Medecin', backref='disponibilites')
    
    def est_disponible(self, date):
        """Vérifie si le médecin est disponible à une date donnée"""
        return not (self.date_debut <= date <= self.date_fin)


class RendezVousStats(db.Model):
    """
    Statistiques agrégées des rendez-vous (pour performance)
    """
    __tablename__ = 'rendez_vous_stats'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, db.ForeignKey('structures.id'), nullable=False)
    medecin_id = db.Column(db.Integer, db.ForeignKey('medecins.id'), nullable=False)
    
    mois = db.Column(db.Integer, nullable=False)  # 1-12
    annee = db.Column(db.Integer, nullable=False)
    
    nb_consultations = db.Column(db.Integer, default=0)
    nb_consultations_terminees = db.Column(db.Integer, default=0)
    nb_annulations = db.Column(db.Integer, default=0)
    nb_absences = db.Column(db.Integer, default=0)
    
    total_honoraires = db.Column(db.Float, default=0)
    taux_occupation = db.Column(db.Float, default=0)  # Pourcentage
    
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    structure = db.relationship('Structure', backref='rdv_stats')
    medecin = db.relationship('Medecin', backref='rdv_stats')
    
    @classmethod
    def calculer_stats(cls, medecin_id, mois, annee):
        """Calcule et met à jour les stats pour un médecin"""
        from datetime import datetime
        
        # Compter les rendez-vous
        rdvs = RendezVous.query.filter(
            RendezVous.medecin_id == medecin_id,
            db.extract('month', RendezVous.date_rendez_vous) == mois,
            db.extract('year', RendezVous.date_rendez_vous) == annee
        ).all()
        
        stats = {
            'nb_consultations': len(rdvs),
            'nb_consultations_terminees': sum(1 for r in rdvs if r.statut == 'termine'),
            'nb_annulations': sum(1 for r in rdvs if r.statut == 'annule'),
            'nb_absences': sum(1 for r in rdvs if r.statut == 'absent'),
            'total_honoraires': 0
        }
        
        # Calculer les honoraires
        medecin = Medecin.query.get(medecin_id)
        if medecin:
            stats['total_honoraires'] = stats['nb_consultations_terminees'] * (medecin.honoraire_consultation or 0)
        
        # Taux d'occupation (estimation)
        jours_ouvres = 22  # Mois moyen
        stats['taux_occupation'] = min(100, (stats['nb_consultations'] / (jours_ouvres * 8)) * 100) if jours_ouvres > 0 else 0
        
        # Mettre à jour ou créer
        stat_record = cls.query.filter(
            cls.medecin_id == medecin_id,
            cls.mois == mois,
            cls.annee == annee
        ).first()
        
        if stat_record:
            for key, value in stats.items():
                setattr(stat_record, key, value)
            stat_record.updated_at = datetime.utcnow()
        else:
            stat_record = cls(
                structure_id=medecin.structure_id if medecin else None,
                medecin_id=medecin_id,
                mois=mois,
                annee=annee,
                **stats
            )
            db.session.add(stat_record)
        
        db.session.commit()
        return stat_record


# models.py - À ajouter dans la section COMPTABILITE, après Cloture

class SequencePiece(db.Model):
    """
    Gestion des séquences de numéros de pièce comptable
    Chaque structure a ses propres séquences par type de pièce et par année
    """
    __tablename__ = 'sequences_piece'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, nullable=False, index=True)
    
    # Type de pièce (ecriture, facture, avoir, bon, etc.)
    type_piece = db.Column(db.String(50), nullable=False, index=True)
    
    # Préfixe (ex: ECR, FAC, AVO, BON)
    prefixe = db.Column(db.String(10), nullable=False)
    
    # Numéro actuel (incrémenté automatiquement)
    numero_actuel = db.Column(db.Integer, default=0, nullable=False)
    
    # Année de référence
    annee = db.Column(db.Integer, nullable=False, index=True)
    
    # Format d'affichage
    # Exemple: {prefixe}-{annee}-{numero:06d} -> ECR-2026-000042
    format_affichage = db.Column(db.String(100), default='{prefixe}-{annee}-{numero:06d}')
    
    # Dates
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Contrainte d'unicité
    __table_args__ = (
        db.UniqueConstraint('structure_id', 'type_piece', 'annee', name='uq_sequence_structure_type_annee'),
    )
    
    @classmethod
    def get_next_number(cls, structure_id, type_piece, prefixe=None):
        """
        Récupère et incrémente le prochain numéro de pièce
        
        Args:
            structure_id: ID de la structure
            type_piece: Type de pièce (ecriture, facture, etc.)
            prefixe: Préfixe personnalisé (optionnel)
        
        Returns:
            str: Numéro de pièce formaté
        """
        now = datetime.now()
        annee = now.year
        
        # Déterminer le préfixe par défaut selon le type
        prefixes_par_defaut = {
            'ecriture': 'ECR',
            'facture': 'FAC',
            'avoir': 'AVO',
            'bon': 'BON',
            'paiement': 'PAI',
            'recette': 'REC',
            'depense': 'DEP'
        }
        
        if not prefixe:
            prefixe = prefixes_par_defaut.get(type_piece, 'PCE')
        
        # Chercher la séquence existante
        sequence = cls.query.filter_by(
            structure_id=structure_id,
            type_piece=type_piece,
            annee=annee
        ).first()
        
        if not sequence:
            # Créer une nouvelle séquence pour l'année
            sequence = cls(
                structure_id=structure_id,
                type_piece=type_piece,
                prefixe=prefixe,
                annee=annee,
                numero_actuel=0
            )
            db.session.add(sequence)
            db.session.flush()
        
        # Incrémenter le numéro
        sequence.numero_actuel += 1
        sequence.updated_at = datetime.utcnow()
        
        # Formater le numéro
        numero_formate = sequence.format_affichage.format(
            prefixe=sequence.prefixe,
            annee=sequence.annee,
            numero=sequence.numero_actuel
        )
        
        db.session.commit()
        
        return numero_formate
    
    @classmethod
    def get_current_number(cls, structure_id, type_piece, annee=None):
        """Récupère le numéro actuel sans l'incrémenter"""
        if not annee:
            annee = datetime.now().year
        
        sequence = cls.query.filter_by(
            structure_id=structure_id,
            type_piece=type_piece,
            annee=annee
        ).first()
        
        if not sequence:
            return None
        
        return sequence.format_affichage.format(
            prefixe=sequence.prefixe,
            annee=sequence.annee,
            numero=sequence.numero_actuel
        )
    
    @classmethod
    def reset_sequence(cls, structure_id, type_piece, annee=None):
        """Réinitialise une séquence à zéro (à utiliser avec précaution)"""
        if not annee:
            annee = datetime.now().year
        
        sequence = cls.query.filter_by(
            structure_id=structure_id,
            type_piece=type_piece,
            annee=annee
        ).first()
        
        if sequence:
            sequence.numero_actuel = 0
            sequence.updated_at = datetime.utcnow()
            db.session.commit()
            return True
        return False
    
    @classmethod
    def get_info(cls, structure_id, type_piece, annee=None):
        """Retourne les informations de la séquence"""
        if not annee:
            annee = datetime.now().year
        
        sequence = cls.query.filter_by(
            structure_id=structure_id,
            type_piece=type_piece,
            annee=annee
        ).first()
        
        if not sequence:
            return None
        
        return {
            'id': sequence.id,
            'type_piece': sequence.type_piece,
            'prefixe': sequence.prefixe,
            'annee': sequence.annee,
            'numero_actuel': sequence.numero_actuel,
            'prochain_numero': sequence.format_affichage.format(
                prefixe=sequence.prefixe,
                annee=sequence.annee,
                numero=sequence.numero_actuel + 1
            ),
            'format_affichage': sequence.format_affichage
        }

