import os

def display_menu():
    print("\n=== Menu de l'Application Croix-Rouge ===")
    print("1. Générer le fichier CSV initial (generate_csv.py)")
    print("2. Mettre à jour les données (update_data.py)")
    print("3. Sélectionner les meilleurs points relais (select_best_relays.py)")
    print("4. Calculer l'itinéraire optimisé (optimize_route.py)")
    print("5. Générer le lien Google Maps (generate_maps.py)")
    print("6. Envoyer l'email avec l'itinéraire (send_email.py)")
    print("7. Exécuter l'itinéraire complet (optimiser, générer lien Google Maps, envoyer email)")
    print("8. Quitter")

def main():
    while True:
        display_menu()
        choice = input("Choisissez une option (1-8): ").strip()

        if choice == "1":
            print("\nExécution de generate_csv.py...")
            os.system("python scripts/generate_csv.py")
        elif choice == "2":
            print("\nExécution de update_data.py...")
            os.system("python scripts/update_data.py")
        elif choice == "3":
            print("\nExécution de select_best_relays.py...")
            os.system("python scripts/select_best_relays.py")
        elif choice == "4":
            print("\nExécution de optimize_route.py...")
            os.system("python scripts/optimize_route.py")
        elif choice == "5":
            print("\nExécution de generate_maps.py...")
            os.system("python scripts/generate_maps.py")
        elif choice == "6":
            print("\nExécution de send_email.py...")
            os.system("python scripts/send_email.py")
        elif choice == "7":
            print("\nExécution de l'itinéraire complet:")
            print("-> Optimisation de l'itinéraire...")
            os.system("python scripts/optimize_route.py")
            print("-> Génération du lien Google Maps...")
            os.system("python scripts/generate_maps.py")
            print("-> Envoi de l'email...")
            os.system("python scripts/send_email.py")
        elif choice == "8":
            print("\nMerci d'avoir utilisé l'application. Au revoir!")
            break
        else:
            print("\nOption invalide. Veuillez choisir un nombre entre 1 et 8.")

if __name__ == "__main__":
    main()
