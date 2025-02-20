import pandas as pd
import networkx as nx
from haversine import haversine
from datetime import datetime

# File paths
collection_csv = "data/collection_points.csv"
history_csv = "data/collection_history.csv"

# Load main dataset
df = pd.read_csv(collection_csv)

# Define the correct Croix-Rouge location DataFrame
croix_rouge_data = pd.DataFrame([{
    "Store_Name": "Croix-Rouge Calais",
    "Latitude": 50.946834,
    "Longitude": 1.859344,
    "Address": "57 Rue Magenta, 62100 Calais, France",
    "Type": "Central Unit",
    "Max_Capacity": None,
    "Current_Stock": None,
    "Fill_Percentage": None,
    "Distance_to_CroixRouge": 0,
    "Estimated_Pickup_Time": None,
    "Priority_Level": None,
    "Connected_Stores": None,
    "Distance_to_Next": None
}])

# Add Croix-Rouge to the dataset if it's not already present
if "Croix-Rouge Calais" not in df["Store_Name"].values:
    df = pd.concat([df, croix_rouge_data], ignore_index=True)

# Ask user for an update date; use current date if left empty
date_input = input("Enter the update date (YYYY-MM-DD) [Leave empty for current date]: ").strip()
if date_input == "":
    update_date = datetime.now().strftime("%Y-%m-%d")
else:
    update_date = date_input

# Update Current_Stock for each store (except Croix-Rouge) and allow Enter to keep existing value
for index, row in df.iterrows():
    if pd.notna(row["Max_Capacity"]) and row["Store_Name"] != "Croix-Rouge Calais":
        current_value = row["Current_Stock"] if pd.notna(row["Current_Stock"]) else "None"
        prompt = f"Enter current stock for {row['Store_Name']} (Max: {int(row['Max_Capacity'])}) [Current: {current_value}]: "
        user_input = input(prompt).strip()
        if user_input != "":
            try:
                stock_value = int(user_input)
                if 0 <= stock_value <= row["Max_Capacity"]:
                    df.at[index, "Current_Stock"] = stock_value
                else:
                    print(f"⚠ Value must be between 0 and {int(row['Max_Capacity'])}. Keeping current value.")
            except ValueError:
                print("⚠ Invalid input. Keeping current value.")

# Function to calculate Fill_Percentage
def calculate_fill_percentage(row):
    if pd.notna(row["Max_Capacity"]) and row["Max_Capacity"] > 0 and pd.notna(row["Current_Stock"]):
        return (row["Current_Stock"] / row["Max_Capacity"]) * 100
    return None

# Update calculated columns
df["Fill_Percentage"] = df.apply(calculate_fill_percentage, axis=1)

# Calculate Distance_to_CroixRouge using haversine
df["Distance_to_CroixRouge"] = df.apply(
    lambda row: haversine(
        (row["Latitude"], row["Longitude"]),
        (croix_rouge_data.iloc[0]["Latitude"], croix_rouge_data.iloc[0]["Longitude"])
    ) if pd.notna(row["Latitude"]) and pd.notna(row["Longitude"]) else None,
    axis=1
)

# (Optionally, update other computed fields here, e.g., Estimated_Pickup_Time, Priority_Level, etc.)
def estimate_pickup_time(fill_percentage):
    if fill_percentage is None:
        return None
    if fill_percentage >= 90:
        return 5
    elif fill_percentage >= 80:
        return 10
    elif fill_percentage >= 60:
        return 20
    else:
        return 30

def assign_priority(fill_percentage):
    if fill_percentage is None:
        return None
    if fill_percentage >= 80:
        return "High"
    elif fill_percentage >= 60:
        return "Medium"
    else:
        return "Low"

df["Estimated_Pickup_Time"] = df["Fill_Percentage"].apply(estimate_pickup_time)
df["Priority_Level"] = df["Fill_Percentage"].apply(assign_priority)

# (Recompute Connected_Stores and Distance_to_Next as before)
connected_stores = []
distances_next = []

def calculate_distance(lat1, lon1, lat2, lon2):
    return haversine((lat1, lon1), (lat2, lon2))

for _, row1 in df.iterrows():
    temp_stores = []
    temp_distances = []
    for _, row2 in df.iterrows():
        if row1["Store_Name"] != row2["Store_Name"] and pd.notna(row1["Latitude"]) and pd.notna(row2["Latitude"]):
            dist = calculate_distance(row1["Latitude"], row1["Longitude"], row2["Latitude"], row2["Longitude"])
            if dist <= 3:
                temp_stores.append(row2["Store_Name"])
                temp_distances.append(str(round(dist, 2)))
                # Add edge to graph if needed (not used later here)
    connected_stores.append(";".join(temp_stores) if temp_stores else None)
    distances_next.append(";".join(temp_distances) if temp_distances else None)

df["Connected_Stores"] = connected_stores
df["Distance_to_Next"] = distances_next

# Save updated main dataset
df.to_csv(collection_csv, index=False)
print("✅ Main dataset updated successfully!")

# --- Update the history table ---
# Create a DataFrame with the update date and relevant columns
history_columns = ["Date", "Store_Name", "Max_Capacity", "Current_Stock", "Fill_Percentage"]
history_records = df[["Store_Name", "Max_Capacity", "Current_Stock", "Fill_Percentage"]].copy()
history_records.insert(0, "Date", update_date)

# Load existing history data if available, otherwise create a new DataFrame
try:
    history_df = pd.read_csv(history_csv)
except FileNotFoundError:
    history_df = pd.DataFrame(columns=history_columns)

# Append today's records to the history table and save
history_df = pd.concat([history_df, history_records], ignore_index=True)
history_df.to_csv(history_csv, index=False)

print(f"✅ History updated for {update_date} and saved in '{history_csv}'!")
