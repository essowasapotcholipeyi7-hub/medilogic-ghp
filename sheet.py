from sheets_helper import sheets_helper
from datetime import datetime, timedelta

# Structure 1
sheets_helper.set_structure(1, "Hopital Central")

# Rendez-vous de test
test_rdvs = [
    ["RDV_A", "2026-05-10", "10:00", "programme"],
    ["RDV_B", "2026-05-11", "11:00", "confirme"],
    ["RDV_C", "2026-05-12", "09:00", "termine"],
    ["RDV_D", "2026-05-08", "14:00", "annule"],
    ["RDV_E", "2026-04-25", "08:00", "depasse"],  # Date passée
]

for i, (nom, date, heure, statut) in enumerate(test_rdvs, start=10):
    new_rdv = [
        i, "1", f"Patient {nom}", "90000000",
        date, heure, "Consultation", statut,
        datetime.now().isoformat(), "", "non", "1"
    ]
    sheets_helper.add_record('rendez_vous', new_rdv)
    print(f"✅ Ajouté: {nom} - {statut}")

print("🎉 5 rendez-vous de test ajoutés !")