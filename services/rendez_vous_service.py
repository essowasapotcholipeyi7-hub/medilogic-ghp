# ============================================================
# SERVICE DE GESTION DES RENDEZ-VOUS
# ============================================================

from datetime import datetime, date, timedelta
import re
from models import db, RendezVous, Medecin, Patient

class RendezVousService:
    """Service pour la gestion des rendez-vous"""
    
    STATUTS_VALIDES = ['programme', 'confirme', 'termine', 'annule', 'reporte', 'absent']
    STATUTS_ACTIFS = ['programme', 'confirme']
    DUREE_MIN = 15
    DUREE_MAX = 120
    DUREE_DEFAUT = 30

    # ⭐ Onglets de la liste (refonte "annulés à part, terminé à part, juste
    # les actifs visibles par défaut") — chaque onglet correspond à un
    # sous-ensemble de `statut`, orthogonal au flag `archive` (voir
    # get_rendez_vous_liste). 'archive' n'est pas un statut : c'est
    # justement les rendez-vous mis à la fourrière, quel que soit leur
    # statut réel.
    #
    # ⭐ 'actifs' et 'depasses' partagent les MÊMES statuts (programme/
    # confirme/reporte) — un rendez-vous "programmé" dont la date est
    # passée reste "programmé" en base (personne ne l'a marqué
    # terminé/absent/annulé), donc `statut` seul ne suffit pas à le sortir
    # de la liste active. Patron vécu : "nous sommes le 24/09/2026 mais
    # dans la liste il y a des rdv dont les dates sont antérieures... ça
    # doit aller dans rendez dépassé, ça ne doit plus s'afficher dans la
    # liste active" — d'où le filtre de DATE supplémentaire (voir
    # get_rendez_vous_liste), sur le même principe que
    # RendezVous.est_depasse() déjà existant sur le modèle.
    VUES_STATUTS = {
        'actifs': ['programme', 'confirme', 'reporte'],
        'depasses': ['programme', 'confirme', 'reporte'],
        'termines': ['termine', 'absent'],
        'annules': ['annule'],
        'tous': None,
    }
    VUE_DEFAUT = 'actifs'
    
    @classmethod
    def creer_rendez_vous(cls, data, structure_id, utilisateur_nom='Systeme'):
        """Crée un nouveau rendez-vous"""
        try:
            # Vérifier les champs obligatoires
            champs = ['patient_id', 'medecin_id', 'date', 'heure', 'motif']
            for champ in champs:
                if not data.get(champ):
                    return False, {'error': f'Le champ {champ} est obligatoire'}
            
            # Vérifier le patient
            patient = Patient.query.get(data['patient_id'])
            if not patient:
                return False, {'error': 'Patient non trouvé'}
            
            # Vérifier le médecin
            medecin = Medecin.query.filter_by(
                id=data['medecin_id'],
                structure_id=structure_id,
                actif=True
            ).first()
            if not medecin:
                return False, {'error': 'Médecin non trouvé ou inactif'}
            
            # Valider la date
            try:
                date_rdv = datetime.strptime(data['date'], '%Y-%m-%d').date()
            except ValueError:
                return False, {'error': 'Format de date invalide'}
            
            if date_rdv < date.today():
                return False, {'error': 'La date ne peut pas être dans le passé'}
            
            # Valider l'heure
            if not re.match(r'^([0-1][0-9]|2[0-3]):[0-5][0-9]$', data['heure']):
                return False, {'error': 'Format d\'heure invalide'}
            
            # Note : on autorise volontairement plusieurs patients sur le même
            # créneau (même médecin, même heure/minute) — un médecin peut avoir
            # plusieurs patients programmés en même temps. Pas de blocage ici.

            # Créer le rendez-vous
            rdv = RendezVous(
                structure_id=structure_id,
                patient_id=data['patient_id'],
                patient_nom=f"{patient.nom} {patient.prenom}".strip(),
                patient_telephone=patient.telephone,
                medecin_id=data['medecin_id'],
                date_rendez_vous=date_rdv,
                heure_rendez_vous=data['heure'],
                duree=data.get('duree', cls.DUREE_DEFAUT),
                motif=data['motif'],
                notes=data.get('notes', ''),
                statut='programme'
            )
            
            db.session.add(rdv)
            db.session.commit()
            
            return True, {
                'id': rdv.id,
                'message': 'Rendez-vous créé avec succès',
                'rendez_vous': rdv.to_dict()
            }
            
        except Exception as e:
            db.session.rollback()
            return False, {'error': str(e)}
    
    @classmethod
    def get_rendez_vous_liste(cls, structure_id, date_debut=None, date_fin=None,
                              statut=None, medecin_id=None, vue=None, recherche_patient=None):
        """Récupère la liste des rendez-vous.

        `vue` pilote le regroupement par onglet (Actifs/Terminés/Annulés/
        Archivés/Tous — voir VUES_STATUTS) ; `statut` reste accepté seul
        pour affiner À L'INTÉRIEUR d'un onglet (ex. ne montrer que les
        'reporte' dans l'onglet Actifs). Les rendez-vous archivés
        (`archive=True`) sont exclus de tous les onglets SAUF 'archive'
        lui-même, qui ne montre QUE ceux-là quel que soit leur statut."""
        query = RendezVous.query.filter_by(structure_id=structure_id)

        vue = vue or cls.VUE_DEFAUT
        if vue == 'archive':
            query = query.filter(RendezVous.archive.is_(True))
        else:
            query = query.filter(db.or_(RendezVous.archive.is_(False), RendezVous.archive.is_(None)))
            statuts_vue = cls.VUES_STATUTS.get(vue, cls.VUES_STATUTS[cls.VUE_DEFAUT])
            if statuts_vue:
                query = query.filter(RendezVous.statut.in_(statuts_vue))
            # ⭐ 'actifs' et 'depasses' partagent les mêmes statuts — c'est
            # la DATE qui les sépare : un programme/confirme/reporte dont
            # la date est déjà passée n'a plus sa place dans "Actifs",
            # même si personne ne l'a marqué terminé/absent/annulé.
            if vue == 'actifs':
                query = query.filter(RendezVous.date_rendez_vous >= date.today())
            elif vue == 'depasses':
                query = query.filter(RendezVous.date_rendez_vous < date.today())

        if date_debut:
            query = query.filter(RendezVous.date_rendez_vous >= date_debut)
        if date_fin:
            query = query.filter(RendezVous.date_rendez_vous <= date_fin)
        if statut and statut != 'tous':
            query = query.filter(RendezVous.statut == statut)
        if medecin_id:
            query = query.filter(RendezVous.medecin_id == medecin_id)
        if recherche_patient:
            query = query.filter(RendezVous.patient_nom.ilike(f'%{recherche_patient}%'))

        total = query.count()
        rendez_vous = query.order_by(
            RendezVous.id.desc()
        ).all()

        return rendez_vous, total

    @classmethod
    def archiver_rendez_vous(cls, rdv_id, structure_id):
        """Met un rendez-vous à la fourrière (masqué de la vue par défaut,
        statut inchangé) — libère l'espace pour les nouveaux rendez-vous
        sans avoir à l'annuler."""
        rdv = RendezVous.query.filter_by(id=rdv_id, structure_id=structure_id).first()
        if not rdv:
            return False, {'error': 'Rendez-vous non trouvé'}
        rdv.archive = True
        rdv.archived_at = datetime.utcnow()
        db.session.commit()
        return True, {'message': 'Rendez-vous archivé'}

    @classmethod
    def desarchiver_rendez_vous(cls, rdv_id, structure_id):
        """Retire un rendez-vous de la fourrière."""
        rdv = RendezVous.query.filter_by(id=rdv_id, structure_id=structure_id).first()
        if not rdv:
            return False, {'error': 'Rendez-vous non trouvé'}
        rdv.archive = False
        rdv.archived_at = None
        db.session.commit()
        return True, {'message': 'Rendez-vous désarchivé'}
    
    @classmethod
    def get_rendez_vous_par_id(cls, rdv_id, structure_id):
        """Récupère un rendez-vous par son ID"""
        return RendezVous.query.filter_by(id=rdv_id, structure_id=structure_id).first()
    
    @classmethod
    def verifier_conflit(cls, medecin_id, date, heure, duree=DUREE_DEFAUT, exclude_id=None):
        """Vérifie si un créneau est occupé"""
        query = RendezVous.query.filter(
            RendezVous.medecin_id == medecin_id,
            RendezVous.date_rendez_vous == date,
            RendezVous.statut.in_(cls.STATUTS_ACTIFS)
        )
        if exclude_id:
            query = query.filter(RendezVous.id != exclude_id)
        
        rendez_vous = query.all()
        
        # Convertir l'heure en minutes
        # (split(':')[:2] car certains rendez-vous existants ont été
        #  enregistrés avec les secondes, ex. "08:00:00")
        h, m = map(int, heure.split(':')[:2])
        debut = h * 60 + m
        fin = debut + duree

        for rdv in rendez_vous:
            h2, m2 = map(int, rdv.heure_rendez_vous.split(':')[:2])
            rdv_debut = h2 * 60 + m2
            rdv_fin = rdv_debut + (rdv.duree or cls.DUREE_DEFAUT)
            
            if (debut < rdv_fin and fin > rdv_debut):
                return rdv
        
        return None
    
    @classmethod
    def verifier_disponibilite_medecin(cls, medecin_id, date):
        """Vérifie la disponibilité d'un médecin"""
        try:
            medecin = Medecin.query.get(medecin_id)
            if not medecin or not medecin.actif:
                return {'disponible': False, 'motif': 'Médecin non disponible'}
            
            duree = medecin.duree_consultation or cls.DUREE_DEFAUT
            
            # Générer les créneaux
            creneaux = []
            for h in range(8, 17):
                for m in [0, 30]:
                    heure_str = f"{h:02d}:{m:02d}"
                    conflit = cls.verifier_conflit(medecin_id, date, heure_str, duree)
                    if not conflit:
                        creneaux.append(heure_str)
            
            return {
                'disponible': len(creneaux) > 0,
                'creneaux': creneaux[:10],
                'duree': duree
            }
            
        except Exception as e:
            return {'disponible': False, 'motif': str(e)}
    
    @classmethod
    def confirmer_rendez_vous(cls, rdv_id, structure_id, utilisateur_nom='Systeme'):
        """Confirme un rendez-vous"""
        return cls._changer_statut(rdv_id, structure_id, 'confirme', utilisateur_nom)
    
    @classmethod
    def terminer_rendez_vous(cls, rdv_id, structure_id, utilisateur_nom='Systeme'):
        """Termine un rendez-vous"""
        return cls._changer_statut(rdv_id, structure_id, 'termine', utilisateur_nom)
    
    @classmethod
    def annuler_rendez_vous(cls, rdv_id, structure_id, utilisateur_nom='Systeme', motif=None):
        """Annule un rendez-vous"""
        return cls._changer_statut(rdv_id, structure_id, 'annule', utilisateur_nom)
    
    @classmethod
    def _changer_statut(cls, rdv_id, structure_id, nouveau_statut, utilisateur_nom):
        """Change le statut d'un rendez-vous"""
        try:
            rdv = cls.get_rendez_vous_par_id(rdv_id, structure_id)
            if not rdv:
                return False, {'error': 'Rendez-vous non trouvé'}
            
            if nouveau_statut not in cls.STATUTS_VALIDES:
                return False, {'error': f'Statut invalide: {nouveau_statut}'}
            
            # Transitions valides
            transitions = {
                'programme': ['confirme', 'termine', 'annule', 'reporte'],  # ← MODIFIÉ
                'confirme': ['termine', 'annule', 'reporte'],
                'termine': [],
                'annule': [],
                'reporte': ['confirme', 'annule', 'programme'],
                'absent': []
            }
            
            if nouveau_statut not in transitions.get(rdv.statut, []):
                return False, {'error': f'Transition invalide: {rdv.statut} -> {nouveau_statut}'}
            
            rdv.statut = nouveau_statut
            db.session.commit()
            
            return True, {
                'message': f'Rendez-vous {nouveau_statut} avec succès',
                'rendez_vous': rdv.to_dict()
            }
            
        except Exception as e:
            db.session.rollback()
            return False, {'error': str(e)}
    
    @classmethod
    def reporter_rendez_vous(cls, rdv_id, structure_id, nouvelle_date, nouvelle_heure,
                            utilisateur_nom='Systeme', message=None):
        """Reporte un rendez-vous"""
        try:
            rdv = cls.get_rendez_vous_par_id(rdv_id, structure_id)
            if not rdv:
                return False, {'error': 'Rendez-vous non trouvé'}
            
            if rdv.statut in ['termine', 'annule']:
                return False, {'error': f'Impossible de reporter un rendez-vous {rdv.statut}'}
            
            try:
                date_obj = datetime.strptime(nouvelle_date, '%Y-%m-%d').date()
            except ValueError:
                return False, {'error': 'Format de date invalide'}
            
            if date_obj < date.today():
                return False, {'error': 'La date ne peut pas être dans le passé'}
            
            if not re.match(r'^([0-1][0-9]|2[0-3]):[0-5][0-9]$', nouvelle_heure):
                return False, {'error': 'Format d\'heure invalide'}
            
            # Pas de blocage sur créneau occupé (voir creer_rendez_vous) :
            # plusieurs patients peuvent être programmés au même moment.

            ancienne_date = rdv.date_rendez_vous.isoformat()
            ancienne_heure = rdv.heure_rendez_vous
            
            rdv.date_rendez_vous = date_obj
            rdv.heure_rendez_vous = nouvelle_heure
            rdv.statut = 'reporte'
            
            if message:
                rdv.notes = (rdv.notes or '') + f"\nReporté: {message}"
            
            db.session.commit()
            
            return True, {
                'message': 'Rendez-vous reporté avec succès',
                'rendez_vous': rdv.to_dict()
            }
            
        except Exception as e:
            db.session.rollback()
            return False, {'error': str(e)}
    
    @classmethod
    def get_statistiques(cls, structure_id):
        """Récupère les statistiques des rendez-vous"""
        query = RendezVous.query.filter_by(structure_id=structure_id)
        
        stats = {
            'total': query.count(),
            'par_statut': {}
        }
        
        for statut in cls.STATUTS_VALIDES:
            stats['par_statut'][statut] = query.filter_by(statut=statut).count()
        
        return stats