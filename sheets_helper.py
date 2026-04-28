import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import Config
import json
import os
import time
import base64
from functools import lru_cache
from threading import Timer

def get_credentials():
    """Récupère les credentials depuis Render ou fichier local"""
    # Essayer depuis variable d'environnement (Render)
    if os.environ.get('GOOGLE_CREDENTIALS'):
        try:
            creds_json = base64.b64decode(os.environ.get('GOOGLE_CREDENTIALS')).decode()
            return json.loads(creds_json)
        except:
            pass
    
    # Fallback sur le fichier local
    if os.path.exists(Config.GOOGLE_SHEETS_CREDENTIALS):
        with open(Config.GOOGLE_SHEETS_CREDENTIALS, 'r') as f:
            return json.load(f)
    
    raise Exception("Credentials non trouvés")

class SheetsHelper:
    def __init__(self):
        self.scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        self.structure_prefix = None
        self.structure_id = None
        
        # CACHE pour réduire les appels API
        self._cache = {}
        self._cache_duration = 10
        self._batch_operations = []
        self._batch_timer = None
        
        try:
            if Config.SPREADSHEET_ID:
                # Récupère les credentials (variable env ou fichier)
                credentials_info = get_credentials_info()
                creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, self.scope)
                self.client = gspread.authorize(creds)
                self.spreadsheet = self.client.open_by_key(Config.SPREADSHEET_ID)
                print("✅ Connexion à Google Sheets réussie !")
                self.init_structures_sheet()
            else:
                raise Exception("SPREADSHEET_ID manquant")
        except Exception as e:
            print(f"⚠️ Erreur: {e}")
            raise e
    
    def init_structures_sheet(self):
        """Crée la feuille structures si elle n'existe pas"""
        try:
            worksheet = self.spreadsheet.worksheet("structures")
        except:
            worksheet = self.spreadsheet.add_worksheet(title="structures", rows=1000, cols=20)
            headers = ["ID", "nom", "email", "telephone", "adresse", "mot_de_passe", "statut", "token", "date_inscription", "proprietaire", "date_occupation"]
            worksheet.append_row(headers)
            print("✅ Feuille 'structures' créée")
    
    def set_structure(self, structure_id, structure_nom=None):
        """Définit la structure active - FORMAT: struct_ID"""
        self.structure_id = structure_id
        self.structure_prefix = f"struct_{structure_id}"
        print(f"📍 Structure active: {self.structure_prefix}")
    
    def get_sheet_name(self, base_name):
        """Retourne le nom de la feuille avec préfixe struct_ID"""
        if self.structure_prefix:
            return f"{self.structure_prefix}_{base_name}"
        return base_name
    
    # 🔥 MÉTHODE AVEC CACHE
    def get_all_records(self, base_name, use_prefix=True, force_refresh=False):
        """Récupère tous les enregistrements avec cache"""
        sheet_name = self.get_sheet_name(base_name) if use_prefix else base_name
        
        # Vérifier le cache
        if not force_refresh and sheet_name in self._cache:
            cached_data, timestamp = self._cache[sheet_name]
            if time.time() - timestamp < self._cache_duration:
                return cached_data
        
        # Sinon, aller chercher dans Google Sheets
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            data = worksheet.get_all_records()
            # Mettre en cache
            self._cache[sheet_name] = (data, time.time())
            return data
        except Exception as e:
            print(f"⚠️ Feuille {sheet_name} non trouvée: {e}")
            return []
    
    # 🔥 MÉTHODE POUR VIDER LE CACHE
    def clear_cache(self, sheet_name=None):
        """Vide le cache (toutes ou une feuille spécifique)"""
        if sheet_name:
            if sheet_name in self._cache:
                del self._cache[sheet_name]
        else:
            self._cache.clear()
    
    # 🔥 AJOUT OPTIMISÉ
    def add_record(self, base_name, data, use_prefix=True):
        """Ajoute un enregistrement et vide le cache"""
        try:
            sheet_name = self.get_sheet_name(base_name) if use_prefix else base_name
            
            try:
                worksheet = self.spreadsheet.worksheet(sheet_name)
            except:
                headers = [f"col_{i}" for i in range(len(data))]
                worksheet = self.spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
                worksheet.append_row(headers)
            
            worksheet.append_row(data)
            
            # 🔥 Vider le cache pour cette feuille
            self.clear_cache(sheet_name)
            return True
        except Exception as e:
            print(f"❌ Erreur ajout à {sheet_name}: {e}")
            return False
    
    # 🔥 MISE À JOUR OPTIMISÉE
    def update_record(self, base_name, row_num, data, use_prefix=True):
        """Met à jour un enregistrement et vide le cache"""
        try:
            sheet_name = self.get_sheet_name(base_name) if use_prefix else base_name
            worksheet = self.spreadsheet.worksheet(sheet_name)
            for col, value in enumerate(data, start=1):
                worksheet.update_cell(row_num, col, value)
            
            # 🔥 Vider le cache pour cette feuille
            self.clear_cache(sheet_name)
            return True
        except Exception as e:
            print(f"❌ Erreur mise à jour: {e}")
            return False
    
    # 🔥 AJOUT EN LOT (POUR FINALISER VENTE)
    def add_batch(self, base_name, data, use_prefix=True):
        """Ajoute une opération au lot"""
        sheet_name = self.get_sheet_name(base_name) if use_prefix else base_name
        self._batch_operations.append((sheet_name, data))
    
    def execute_batch(self):
        """Exécute toutes les opérations en lot"""
        if not self._batch_operations:
            return
        
        try:
            # Grouper par feuille
            grouped = {}
            for sheet_name, data in self._batch_operations:
                if sheet_name not in grouped:
                    grouped[sheet_name] = []
                grouped[sheet_name].append(data)
            
            # Exécuter chaque groupe
            for sheet_name, rows in grouped.items():
                try:
                    worksheet = self.spreadsheet.worksheet(sheet_name)
                    for row in rows:
                        worksheet.append_row(row)
                    self.clear_cache(sheet_name)
                except:
                    # Si la feuille n'existe pas, créer
                    headers = [f"col_{i}" for i in range(len(rows[0]))]
                    worksheet = self.spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
                    worksheet.append_row(headers)
                    for row in rows:
                        worksheet.append_row(row)
            
            self._batch_operations = []
        except Exception as e:
            print(f"❌ Erreur batch: {e}")
    
    def init_structure_sheets(self, structure_id, structure_nom=None):
        """Initialise toutes les feuilles pour une nouvelle structure"""
        self.set_structure(structure_id)
        
        sheets_config = {
            'patients': ["ID", "nom", "prenom", "telephone", "adresse", "date_naissance", "type_assurance", "taux_prise_charge", "numero_assure", "structure_id", "created_at"],
            'actes': ["ID", "nom", "prix", "description", "structure_id"],
            'produits': ["ID", "nom", "prix_vente", "quantite_stock", "structure_id"],
            'ventes_actes': ["ID", "patient_id", "patient_nom", "acte_id", "acte_nom", "prix", "quantite", "total", "taux_assurance", "prise_en_charge", "net_a_payer", "mode_paiement", "date", "structure_id"],
            'ventes_pharma': ["ID", "patient_id", "patient_nom", "produit_id", "produit_nom", "prix", "quantite", "total", "taux_assurance", "prise_en_charge", "net_a_payer", "mode_paiement", "avec_ordonnance", "date", "structure_id"],
            'users': ["ID", "nom", "email", "mot_de_passe", "role", "structure_id", "created_at"]
        }
        
        for sheet_name, headers in sheets_config.items():
            full_name = self.get_sheet_name(sheet_name)
            self.get_or_create_worksheet(full_name, headers)
        
        print(f"✅ Toutes les feuilles créées pour structure {structure_id}")
    
    def get_or_create_worksheet(self, sheet_name, headers):
        """Récupère ou crée une feuille"""
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            return worksheet
        except:
            worksheet = self.spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
            worksheet.append_row(headers)
            print(f"✅ Feuille créée: {sheet_name}")
            return worksheet

# Instance globale
sheets_helper = SheetsHelper()