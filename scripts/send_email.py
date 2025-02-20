import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Email configuration loaded from environment variables
sender_email = os.getenv("SENDER_EMAIL")
receiver_emails = os.getenv("RECEIVER_EMAILS").split(",")  # Comma-separated list in .env
smtp_server = os.getenv("SMTP_SERVER")
smtp_port = int(os.getenv("SMTP_PORT", 587))  # Default to 587 if not specified
smtp_username = os.getenv("SMTP_USERNAME")
smtp_password = os.getenv("SMTP_PASSWORD")

# 1. Extract the fill percentage threshold from a file instead of prompting the user
threshold_file = "data/threshold.txt"
try:
    with open(threshold_file, "r") as f:
        threshold = float(f.read().strip())
except Exception:
    print(f"⚠ Could not read threshold from {threshold_file}. Using default threshold of 80.")
    threshold = 80.0

# 2. Load the main dataset
collection_csv = "data/collection_points.csv"
df = pd.read_csv(collection_csv)

# 3. Filter the stores exceeding the threshold
urgent_stores = df[df["Fill_Percentage"] >= threshold].copy()

# Format the Fill_Percentage as an integer followed by a "%" for display purposes
if not urgent_stores.empty:
    urgent_stores["Fill_Percentage_Display"] = urgent_stores["Fill_Percentage"].apply(lambda x: f"{int(x)}%")

# Map Priority_Level to French: High -> élevé, Medium -> moyen, Low -> faible
priority_mapping = {"High": "élevé", "Medium": "moyen", "Low": "faible"}
if "Priority_Level" in urgent_stores.columns:
    urgent_stores["Priority_Level"] = urgent_stores["Priority_Level"].map(priority_mapping)

# 4. Load itinerary data and build a route summary with emojis
try:
    itinerary_df = pd.read_csv("data/itinerary.csv")
    if not itinerary_df.empty:
        # Build the route: start with the first row's Start_Point, then append each End_Point in order.
        route_points = [itinerary_df.iloc[0]["Start_Point"]]
        for _, row in itinerary_df.iterrows():
            route_points.append(row["End_Point"])
        # Build the emoji route: 🚩 for departure, ➡️ for intermediate stops, 🏁 for arrival.
        croix_rouge_name = "Croix-Rouge Calais"
        route_with_emojis = "🚩 " + croix_rouge_name
        for idx, point in enumerate(route_points[1:], start=1):
            if point == croix_rouge_name and idx == len(route_points) - 1:
                route_with_emojis += " 🏁 " + point
            else:
                route_with_emojis += " ➡️ " + point
        itinerary_route = route_with_emojis
    else:
        itinerary_route = "Aucun itinéraire n'a été calculé."
except FileNotFoundError:
    itinerary_route = "Fichier d'itinéraire non trouvé."

# 5. Load Google Maps link from file and create a button for it
maps_link_file = "data/maps_link.txt"
try:
    with open(maps_link_file, "r") as f:
        maps_link = f.read().strip()
    maps_link_html = f'''
      <p style="text-align:center; margin-top:20px;">
        <a href="{maps_link}" target="_blank" style="
           display:inline-block;
           background-color:#007BFF;
           color:#fff;
           padding:10px 20px;
           text-decoration:none;
           border-radius:5px;
           font-weight:bold;">
           Voir l'itinéraire sur Google Maps
        </a>
      </p>
    '''
except FileNotFoundError:
    maps_link_html = '<p style="text-align:center;">Le lien Google Maps n\'a pas été généré.</p>'

# 6. Compose the email body as HTML (in French)
body = f"""
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 0;
      padding: 20px;
      background-color: #ffffff;
      color: #333;
    }}
    .header {{
      text-align: center;
      margin-bottom: 20px;
    }}
    .header img {{
      max-width: 150px;
      display: block;
      margin: 0 auto;
    }}
    .header h1 {{
      margin: 10px 0 0 0;
      font-size: 24px;
      color: #d00;
    }}
    .content {{
      max-width: 600px;
      margin: 0 auto;
    }}
    .content p {{
      line-height: 1.6;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 20px;
    }}
    th, td {{
      border: 1px solid #ddd;
      padding: 8px;
      text-align: center;
    }}
    th {{
      background-color: #f2f2f2;
    }}
    footer {{
      text-align: center;
      margin-top: 20px;
      font-size: 0.9em;
      color: #777;
    }}
  </style>
</head>
<body>
  <div class="header">
    <img src="https://i.imgur.com/wd594DQ.png" alt="Logo de la Croix-Rouge">
    <h1>Itinéraire Optimisé pour la Collecte</h1>
  </div>
  <div class="content">
    <p>Chers collègues,</p>
    <p>Veuillez trouver ci-dessous l'itinéraire optimisé pour la collecte ainsi que le rapport d'urgence basé sur un seuil de remplissage de {threshold}%.</p>
    <h3>Itinéraire optimisé de collecte</h3>
    <p>{itinerary_route}</p>
    {maps_link_html}
    <h3>Rapport d'urgence</h3>
    <p>Les points relais suivants présentent un pourcentage de remplissage supérieur ou égal à {threshold}% :</p>
    {urgent_stores[["Store_Name", "Address", "Fill_Percentage_Display", "Priority_Level"]].rename(columns={
        "Store_Name": "Nom du point relais",
        "Address": "Adresse",
        "Fill_Percentage_Display": "Pourcentage de remplissage",
        "Priority_Level": "Niveau d'urgence"
    }).to_html(index=False, justify="center")}
    <p>Cordialement,<br>L'équipe Logistique</p>
  </div>
  <footer>
    &copy; 2023 Croix Rouge - Document généré automatiquement.
  </footer>
</body>
</html>
"""

# 7. Create the email message
msg = MIMEMultipart("alternative")
msg["Subject"] = "Itinéraire Optimisé et Rapport d'Urgence de Collecte"
msg["From"] = sender_email
msg["To"] = ", ".join(receiver_emails)
msg.attach(MIMEText(body, "html"))

# 8. Send the email using SMTP
try:
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()  # Secure the connection
        server.login(smtp_username, smtp_password)
        server.sendmail(sender_email, receiver_emails, msg.as_string())
    print("✅ Email sent successfully!")
except Exception as e:
    print(f"❌ Error sending email: {e}")
