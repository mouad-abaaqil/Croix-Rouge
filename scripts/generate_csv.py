import pandas as pd
import random
import os

# Define CSV file paths
collection_csv = "data/collection_points.csv"
history_csv = "data/collection_history.csv"

# Define column names for main dataset
columns = [
    "Store_Name", "Latitude", "Longitude", "Address", "Type",
    "Max_Capacity", "Current_Stock", "Fill_Percentage",
    "Distance_to_CroixRouge", "Estimated_Pickup_Time", "Priority_Level",
    "Connected_Stores", "Distance_to_Next"
]

# Define box sizes and their capacities (in grams)
box_sizes = {
    "Small": 5000,    # 5000 g (5 KG)
    "Medium": 10000,  # 10,000 g (10 KG)
    "Big": 15000,     # 15,000 g (15 KG)
}

# Function to let the user choose the box size for a given store
def get_max_capacity(store_name):
    while True:
        print(f"\nChoose a box size for {store_name}:")
        print("1️⃣  Small (5000 g)  |  2️⃣  Medium (10,000 g)  |  3️⃣  Big (15,000 g)")
        user_input = input("Enter choice (1/2/3): ").strip()
        if user_input == "1":
            return box_sizes["Small"]
        elif user_input == "2":
            return box_sizes["Medium"]
        elif user_input == "3":
            return box_sizes["Big"]
        else:
            print("⚠ Invalid input! Please enter 1, 2, or 3.")

# Function to generate random stock values given a max capacity
def generate_stock_values(max_capacity):
    current_stock = random.randint(0, max_capacity)  # Random stock within capacity
    fill_percentage = (current_stock / max_capacity) * 100  # Compute fill %
    return current_stock, round(fill_percentage, 2)

# List of stores (example)
store_list = [
    ["O BONHEUR DES SAVEURS", 50.948596, 1.853902, "33 Boulevard Jacquard, 62100 Calais", "Point Relais"],
    ["HEXOS MINIATURES", 50.947532, 1.854942, "13 Boulevard Lafayette, 62100 Calais", "Point Relais"],
    ["ICE MARKET CALAIS", 50.957499, 1.872397, "83 Rue Mollien, 62100 Calais", "Point Relais"],
    ["LA PASSION DE BENE", 50.926440, 1.868060, "5 Chemin des Regniers, 62137 Coulogne", "Point Relais"],
    ["COCCIMARKET MARCK", 50.954360, 1.927020, "319 Rue des Tourterelles, 62730 Marck", "Supermarket"],
    ["LE CONCORDE MARCK", 50.947440, 1.953660, "172 Avenue François Mitterrand, 62730 Marck", "Point Relais"],
    ["CREADELENA MARCK", 50.946523, 1.959415, "592 Avenue François Mitterrand, 62730 Marck", "Point Relais"],
    ["LE COLVERT", 50.981936, 1.966545, "670 Rue Robelin, 62730 Marck", "Point Relais"],
    ["Calais Vins", 50.937618, 1.863780, "Rue Gutenberg, 62100 Calais", "Caviste"],
    ["La Poste COULOGNE", 50.926590, 1.876040, "4 Rue Gelle Way, 62137 Coulogne", "Bureau de Poste"],
    ["La Poste Relais COULOGNE CARREFOUR EXPRESS", 50.924807, 1.887034, "Place de l'Église, 62137 Coulogne", "Bureau de Poste"],
    ["Relais Pickup FULLSTOCK", 50.950786, 1.902359, "77 Rue Henri Guillaumet, 62100 Calais", "Point Relais"],
]

data = []
for store in store_list:
    store_name, lat, lon, address, store_type = store
    max_capacity = get_max_capacity(store_name)  # User selects box size (in grams)
    current_stock, fill_percentage = generate_stock_values(max_capacity)  # Generate random stock values
    data.append([store_name, lat, lon, address, store_type, max_capacity, current_stock, fill_percentage,
                 None, None, None, None, None])

# Create main dataset DataFrame and save to CSV
df = pd.DataFrame(data, columns=columns)
df.to_csv(collection_csv, index=False)
print(f"\n✅ Main CSV file '{collection_csv}' created successfully with user-defined max capacities!")

# Create an empty history DataFrame if not exists
history_columns = ["Date", "Store_Name", "Max_Capacity", "Current_Stock", "Fill_Percentage"]
if not os.path.exists(history_csv):
    history_df = pd.DataFrame(columns=history_columns)
    history_df.to_csv(history_csv, index=False)
    print(f"✅ History CSV file '{history_csv}' created successfully!")
else:
    print(f"✅ History CSV file '{history_csv}' already exists!")
