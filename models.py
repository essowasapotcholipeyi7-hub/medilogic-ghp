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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

   

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
    taux_assurance = db.Column(db.Integer, default=0)
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
    
    # ⭐ Colonnes d'automatisation
    categorie_actes = db.Column(db.JSON, default=[])
    traite_comptable = db.Column(db.Boolean, default=False)
    ecriture_generee = db.Column(db.Boolean, default=False)
    ecriture_id = db.Column(db.Integer, nullable=True)
    
    # ⭐ Prescription IDs
    prescription_ids = db.Column(db.JSON, default=[])
    
    assurance_principale_active = db.Column(db.Boolean, default=True)

    # ⭐ NOUVELLES COLONNES À AJOUTER
    taux_aide = db.Column(db.Float, default=0)
    aide_hospitaliere = db.Column(db.Float, default=0)
    proforma_id = db.Column(db.Integer, nullable=True)

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

# ============================================================
# MODÈLES MANQUANTS (à ajouter)
# ============================================================

class AnnulationVente(db.Model):
    __tablename__ = 'annulations_ventes'
    id = db.Column(db.Integer, primary_key=True)
    vente_id = db.Column(db.Integer, nullable=False)
    vente_type = db.Column(db.String(50))
    motif = db.Column(db.String(255))
    annule_par_id = db.Column(db.Integer)
    annule_par_nom = db.Column(db.String(255))
    ancien_net_a_payer = db.Column(db.Numeric)
    ancien_sous_total = db.Column(db.Numeric)
    data_avant = db.Column(db.JSON)
    date_annulation = db.Column(db.DateTime, default=datetime.utcnow)


class Caisse(db.Model):
    __tablename__ = 'caisse'
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, nullable=False, unique=True)  # ⭐ AJOUTÉ
    solde_actuel = db.Column(db.Numeric, default=0)
    solde_initial = db.Column(db.Numeric, default=0)
    date_mise_a_jour = db.Column(db.DateTime, default=datetime.utcnow)


class Depense(db.Model):
    __tablename__ = 'depenses'
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, nullable=False)
    montant = db.Column(db.Numeric, nullable=False)
    motif = db.Column(db.String(255), nullable=False)
    motif_personnalise = db.Column(db.String(255))
    description = db.Column(db.Text)
    piece_jointe = db.Column(db.String(255))
    date_depense = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer)
    created_by_nom = db.Column(db.String(255))


class Facture(db.Model):
    __tablename__ = 'factures'
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, nullable=False)
    patient_id = db.Column(db.Integer, nullable=False)
    patient_nom = db.Column(db.String(255), nullable=False)
    patient_telephone = db.Column(db.String(50))
    numero_facture = db.Column(db.String(50), nullable=False)
    date_emission = db.Column(db.Date, default=db.func.current_date())
    date_echeance = db.Column(db.Date, nullable=False)
    sous_total = db.Column(db.Numeric, default=0, nullable=False)
    taux_assurance = db.Column(db.Numeric, default=0)
    prise_en_charge = db.Column(db.Numeric, default=0)
    taux_assurance2 = db.Column(db.Numeric, default=0)
    prise_en_charge2 = db.Column(db.Numeric, default=0)
    net_a_payer = db.Column(db.Numeric, default=0, nullable=False)
    montant_paye = db.Column(db.Numeric, default=0)
    reste_a_payer = db.Column(db.Numeric, default=0)
    statut = db.Column(db.String(50), default='en_attente')
    articles = db.Column(db.JSON)
    mode_paiement = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_by = db.Column(db.String(255))
    base_remboursement = db.Column(db.Numeric, default=0)
    assurances_data = db.Column(db.JSON)
    vente_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FactureAssurance(db.Model):
    __tablename__ = 'factures_assurance'
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, nullable=False)
    mois_reference = db.Column(db.String(20), nullable=False)
    assurance = db.Column(db.String(255), nullable=False)
    montant_total = db.Column(db.Numeric, nullable=False)
    montant_rembourse = db.Column(db.Numeric, default=0)
    statut = db.Column(db.String(50), default='en_attente')
    date_facture = db.Column(db.Date, default=db.func.current_date())
    date_remboursement = db.Column(db.Date)
    details = db.Column(db.JSON)
    type_assurance = db.Column(db.String(50), default='principale')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PaiementFacture(db.Model):
    __tablename__ = 'paiements_factures'
    id = db.Column(db.Integer, primary_key=True)
    facture_id = db.Column(db.Integer, nullable=False)
    montant = db.Column(db.Numeric, nullable=False)
    date_paiement = db.Column(db.DateTime, default=datetime.utcnow)
    mode_paiement = db.Column(db.String(50))
    reference = db.Column(db.String(255))
    notes = db.Column(db.Text)
    created_by = db.Column(db.String(255))
    recu_genere = db.Column(db.Boolean, default=False)


class Proforma(db.Model):
    __tablename__ = 'proformas'
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, nullable=False)
    patient_id = db.Column(db.Integer)
    patient_nom = db.Column(db.String(255), nullable=False)
    patient_telephone = db.Column(db.String(50))
    assurance_nom = db.Column(db.String(255))
    taux_assurance = db.Column(db.Numeric, default=0)
    numero_assure = db.Column(db.String(255))
    type = db.Column(db.String(50), nullable=False, default='mixte')
    articles = db.Column(db.JSON, nullable=False, default=[])
    sous_total = db.Column(db.Numeric, default=0, nullable=False)
    prise_en_charge = db.Column(db.Numeric, default=0, nullable=False)
    net_a_payer = db.Column(db.Numeric, default=0, nullable=False)
    statut = db.Column(db.String(50), default='en_attente')
    vente_id = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_by = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    vue_par_patient = db.Column(db.Boolean, default=False)
    date_vue = db.Column(db.DateTime)
    numero_proforma = db.Column(db.Integer)
    assurance2_nom = db.Column(db.String(255), default='')
    taux_assurance2 = db.Column(db.Numeric, default=0)
    numero_assure2 = db.Column(db.String(255), default='')
    assurance2_active = db.Column(db.Boolean, default=False)
    taux_modifie = db.Column(db.Boolean, default=False)
    taux_original = db.Column(db.Numeric, default=0)
    prise_en_charge2 = db.Column(db.Numeric, default=0)
    assurances_data = db.Column(db.JSON)
    base_remboursement = db.Column(db.Numeric, default=0)
    base_cac = db.Column(db.Numeric, default=0)


class ProformaLunette(db.Model):
    __tablename__ = 'proformas_lunettes'
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, nullable=False)
    patient_id = db.Column(db.Integer, nullable=False)
    patient_nom = db.Column(db.String(255))
    patient_telephone = db.Column(db.String(50))
    patient_date_naissance = db.Column(db.Date)
    patient_age = db.Column(db.Integer)
    numero = db.Column(db.String(255))
    articles = db.Column(db.JSON)
    sous_total = db.Column(db.Numeric, default=0)
    remise = db.Column(db.Numeric, default=0)
    type_remise = db.Column(db.String(50), default='pourcentage')
    valeur_remise = db.Column(db.Numeric, default=0)
    net_a_payer = db.Column(db.Numeric, default=0)
    tva_taux = db.Column(db.Numeric, default=18)
    medecin_prescripteur = db.Column(db.String(255))
    notes = db.Column(db.Text)
    statut = db.Column(db.String(50), default='en_attente')
    created_by = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    rib = db.Column(db.String(50))
    numero_affiliation = db.Column(db.String(255))


class Recette(db.Model):
    __tablename__ = 'recettes'
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, nullable=False)
    montant = db.Column(db.Numeric, nullable=False)
    source = db.Column(db.String(255))
    description = db.Column(db.Text)
    date_recette = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer)
    created_by_nom = db.Column(db.String(255))
    source_id = db.Column(db.Integer)
    source_type = db.Column(db.String(255))
    est_annulation = db.Column(db.Boolean, default=False)


class VenteLunette(db.Model):
    __tablename__ = 'ventes_lunettes'
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, nullable=False)
    patient_id = db.Column(db.Integer, nullable=False)
    patient_nom = db.Column(db.String(255))
    lunette_id = db.Column(db.Integer)
    lunette_nom = db.Column(db.String(255))
    marque = db.Column(db.String(255))
    modele = db.Column(db.String(255))
    prix = db.Column(db.Float, default=0)
    remise = db.Column(db.Float, default=0)
    prix_avec_remise = db.Column(db.Float, default=0)
    quantite = db.Column(db.Integer, default=1)
    total = db.Column(db.Float, default=0)
    taux_assurance = db.Column(db.Float, default=0)
    prise_en_charge = db.Column(db.Float, default=0)
    prise_en_charge2 = db.Column(db.Float, default=0)
    net_a_payer = db.Column(db.Float, default=0)
    mode_paiement = db.Column(db.String(50), default='especes')
    montant_donne = db.Column(db.Float, default=0)
    rendu = db.Column(db.Float, default=0)
    reste_a_payer = db.Column(db.Float, default=0)
    created_by = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ============================================================
# MODÈLE RAPPEL RENDEZ-VOUS (À AJOUTER À LA FIN DE models.py)
# ============================================================

class RappelRendezVous(db.Model):
    """Modèle pour l'historique des rappels"""
    
    __tablename__ = 'rappels_rendez_vous'
    
    id = db.Column(db.Integer, primary_key=True)
    rendez_vous_id = db.Column(db.Integer, db.ForeignKey('rendez_vous.id'), nullable=False)
    
    type_rappel = db.Column(db.String(20), nullable=False)
    statut = db.Column(db.String(20), default='en_attente')
    
    date_planifiee = db.Column(db.DateTime, default=datetime.utcnow)
    date_envoyee = db.Column(db.DateTime)
    
    message_envoye = db.Column(db.Text)
    url_whatsapp = db.Column(db.String(500))
    
    erreur = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    rendez_vous = db.relationship('RendezVous', backref='rappels')

# ============================================================
# MODÈLES POUR LA GESTION DES PROTOCOLES ET MODÈLES
# ============================================================

class ProtocoleMedical(db.Model):
    """Modèle pour les protocoles de soins et modèles médicaux"""
    
    __tablename__ = 'protocoles_medicaux'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, db.ForeignKey('structures.id'), nullable=False)
    
    # Catégorie du document
    categorie = db.Column(db.String(50), nullable=False)
    # protocole_soins, ordonnance_type, bulletin_examen, 
    # protocole_patient, fiche_information, protocole_infirmier
    
    # Identité
    titre = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    contenu = db.Column(db.Text, nullable=False)  # Contenu principal
    
    # Métadonnées
    specialite = db.Column(db.String(100))  # Cardiologie, Pédiatrie, etc.
    tags = db.Column(db.JSON, default=[])  # Mots-clés pour recherche
    version = db.Column(db.Integer, default=1)
    statut = db.Column(db.String(20), default='brouillon')
    # brouillon, en_validation, publie, archive
    
    # Auteur
    auteur_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id'))
    auteur_nom = db.Column(db.String(100))
    
    # Pour les ordonnances types
    medicaments = db.Column(db.JSON, default=[])  # Liste des médicaments
    examens = db.Column(db.JSON, default=[])  # Liste des examens
    
    # Pour les protocoles patient
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=True)
    date_debut = db.Column(db.Date)
    date_fin = db.Column(db.Date)
    
    # Pour les protocoles de soins
    etapes = db.Column(db.JSON, default=[])  # Étapes du protocole
    duree = db.Column(db.String(50))  # Durée estimée
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    structure = db.relationship('Structure', backref='protocoles')
    auteur = db.relationship('Utilisateur', backref='protocoles')
    patient = db.relationship('Patient', backref='protocoles')
    
    def to_dict(self):
        return {
            'id': self.id,
            'structure_id': self.structure_id,
            'categorie': self.categorie,
            'categorie_label': self.get_categorie_label(),
            'titre': self.titre,
            'description': self.description,
            'contenu': self.contenu,
            'specialite': self.specialite,
            'tags': self.tags or [],
            'version': self.version,
            'statut': self.statut,
            'statut_label': self.get_statut_label(),
            'auteur_id': self.auteur_id,
            'auteur_nom': self.auteur_nom,
            'medicaments': self.medicaments or [],
            'examens': self.examens or [],
            'patient_id': self.patient_id,
            'date_debut': self.date_debut.isoformat() if self.date_debut else None,
            'date_fin': self.date_fin.isoformat() if self.date_fin else None,
            'etapes': self.etapes or [],
            'duree': self.duree,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def get_categorie_label(self):
        labels = {
            'protocole_soins': 'Protocole de soins',
            'ordonnance_type': 'Ordonnance type',
            'bulletin_examen': 'Bulletin d\'examen',
            'protocole_patient': 'Protocole patient',
            'fiche_information': 'Fiche d\'information',
            'protocole_infirmier': 'Protocole infirmier'
        }
        return labels.get(self.categorie, self.categorie)
    
    def get_statut_label(self):
        labels = {
            'brouillon': 'Brouillon',
            'en_validation': 'En validation',
            'publie': 'Publié',
            'archive': 'Archivé'
        }
        return labels.get(self.statut, self.statut)
    
    def generer_ordonnance(self, patient_nom, date_rdv):
        """Génère une ordonnance à partir d'un modèle"""
        if self.categorie != 'ordonnance_type':
            return None
        
        content = self.contenu
        content = content.replace('{{patient_nom}}', patient_nom)
        content = content.replace('{{date}}', date_rdv)
        
        return content

    def generer_protocole(self, patient_nom):
        """Génère un protocole personnalisé pour un patient"""
        if self.categorie not in ['protocole_soins', 'protocole_patient']:
            return None
        
        content = self.contenu
        content = content.replace('{{patient_nom}}', patient_nom)
        
        return content


class HistoriqueProtocole(db.Model):
    """Historique des modifications des protocoles"""
    
    __tablename__ = 'historique_protocoles'
    
    id = db.Column(db.Integer, primary_key=True)
    protocole_id = db.Column(db.Integer, db.ForeignKey('protocoles_medicaux.id'), nullable=False)
    
    action = db.Column(db.String(50), nullable=False)  # creation, modification, validation, publication
    utilisateur_id = db.Column(db.Integer)
    utilisateur_nom = db.Column(db.String(100))
    ancien_contenu = db.Column(db.Text)
    nouveau_contenu = db.Column(db.Text)
    commentaire = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    protocole = db.relationship('ProtocoleMedical', backref='historique')


class ProtocolePatient(db.Model):
    """Lien entre un patient et un protocole de soins"""
    
    __tablename__ = 'protocoles_patients'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, db.ForeignKey('structures.id'), nullable=False)
    
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    protocole_id = db.Column(db.Integer, db.ForeignKey('protocoles_medicaux.id'), nullable=False)
    
    statut = db.Column(db.String(20), default='en_cours')
    # en_cours, termine, abandonne
    
    date_debut = db.Column(db.Date, nullable=False)
    date_fin = db.Column(db.Date)
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    patient = db.relationship('Patient', backref='protocoles_appliques')
    protocole = db.relationship('ProtocoleMedical', backref='patients_associes')
    structure = db.relationship('Structure', backref='protocoles_patients')

# ============================================================
# MODÈLE JOURNAL DES MOUVEMENTS
# ============================================================

class JournalMouvement(db.Model):
    """Journal centralisé des mouvements de l'établissement"""
    
    __tablename__ = 'journal_mouvements'
    
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.Integer, db.ForeignKey('structures.id'), nullable=False)
    
    # Catégorie et type
    categorie = db.Column(db.String(50), nullable=False)
    # vente_actes, vente_pharmacie, vente_lunettes, annulation_vente,
    # paiement_facture, paiement_assurance, facture_emise, avoir_emis,
    # recette_encaisee, depense_enregistree, proforma_cree, rendez_vous_pris
    
    sous_categorie = db.Column(db.String(50))
    
    # Référence
    reference_type = db.Column(db.String(50))  # vente, facture, paiement, etc.
    reference_id = db.Column(db.Integer)
    
    # Date du mouvement
    date_mouvement = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Description
    description = db.Column(db.Text)
    
    # Montant
    montant = db.Column(db.Numeric, default=0)
    type_montant = db.Column(db.String(10), default='neutre')  # credit, debit, neutre
    
    # Patient
    patient_id = db.Column(db.Integer)
    patient_nom = db.Column(db.String(200))
    
    # Utilisateur
    utilisateur_id = db.Column(db.Integer)
    utilisateur_nom = db.Column(db.String(100))
    
    # Détails supplémentaires (JSON)
    details = db.Column(db.JSON, default={})
    
    # Statut
    statut = db.Column(db.String(20), default='valide')  # valide, annule, en_attente
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    structure = db.relationship('Structure', backref='journal_mouvements')
    
    def to_dict(self):
        return {
            'id': self.id,
            'structure_id': self.structure_id,
            'categorie': self.categorie,
            'categorie_label': self.get_categorie_label(),
            'sous_categorie': self.sous_categorie,
            'reference_type': self.reference_type,
            'reference_id': self.reference_id,
            'date_mouvement': self.date_mouvement.isoformat() if self.date_mouvement else None,
            'date_affichage': self.date_mouvement.strftime('%d/%m/%Y %H:%M') if self.date_mouvement else '',
            'description': self.description,
            'montant': float(self.montant) if self.montant else 0,
            'type_montant': self.type_montant,
            'montant_affichage': self.get_montant_affichage(),
            'patient_id': self.patient_id,
            'patient_nom': self.patient_nom,
            'utilisateur_id': self.utilisateur_id,
            'utilisateur_nom': self.utilisateur_nom,
            'details': self.details or {},
            'statut': self.statut,
            'statut_label': self.get_statut_label(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def get_categorie_label(self):
        labels = {
            'vente_actes': 'Vente d\'actes',
            'vente_pharmacie': 'Vente pharmacie',
            'vente_lunettes': 'Vente lunettes',
            'annulation_vente': 'Annulation vente',
            'paiement_facture': 'Paiement facture',
            'paiement_assurance': 'Paiement assurance',
            'facture_emise': 'Facture émise',
            'avoir_emis': 'Avoir émis',
            'recette_encaisee': 'Recette encaissée',
            'depense_enregistree': 'Dépense enregistrée',
            'proforma_cree': 'Proforma créé',
            'rendez_vous_pris': 'Rendez-vous pris',
            'consultation_terminee': 'Consultation terminée'
        }
        return labels.get(self.categorie, self.categorie)
    
    def get_statut_label(self):
        labels = {
            'valide': 'Valide',
            'annule': 'Annulé',
            'en_attente': 'En attente'
        }
        return labels.get(self.statut, self.statut)
    
    def get_montant_affichage(self):
        if self.type_montant == 'credit':
            return f"+ {abs(float(self.montant)):,.0f} F"
        elif self.type_montant == 'debit':
            return f"- {abs(float(self.montant)):,.0f} F"
        else:
            return f"{float(self.montant):,.0f} F"
