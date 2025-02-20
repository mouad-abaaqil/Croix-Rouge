import pandas as pd
import networkx as nx
from haversine import haversine
import os

# File to store the threshold
threshold_file = "data/threshold.txt"

# Load dataset
csv_file_path = "data/collection_points.csv"
df = pd.read_csv(csv_file_path)

# Define Croix-Rouge location name (we assume its row is already in the file)
croix_rouge_name = "Croix-Rouge Calais"

# Ask the user for the fill percentage threshold
try:
    min_fill_percentage = float(input("Enter the minimum fill percentage for collection (e.g., 80 for 80%): "))
    if not (0 <= min_fill_percentage <= 100):
        raise ValueError("Percentage must be between 0 and 100.")
except ValueError as e:
    print(f"⚠ Invalid input: {e}. Defaulting to 80%.")
    min_fill_percentage = 80.0

# Write the threshold to file so that other scripts can reuse it.
with open(threshold_file, "w") as f:
    f.write(str(min_fill_percentage))
print(f"✅ Threshold of {min_fill_percentage}% saved to '{threshold_file}'.")

# Convert Fill_Percentage to numeric
df["Fill_Percentage"] = pd.to_numeric(df["Fill_Percentage"], errors='coerce')

# Filter stores with Fill_Percentage ≥ user-defined threshold
high_priority_stores = df[df["Fill_Percentage"] >= min_fill_percentage].copy()

# Add Croix-Rouge to the dataset if it's not already present
if croix_rouge_name not in high_priority_stores["Store_Name"].values:
    croix_rouge_location = df[df["Store_Name"] == croix_rouge_name]
    high_priority_stores = pd.concat([high_priority_stores, croix_rouge_location])

# Create a graph
G = nx.Graph()

# Add nodes (stores)
for _, row in high_priority_stores.iterrows():
    G.add_node(row["Store_Name"], pos=(row["Latitude"], row["Longitude"]))

# Add weighted edges (distances)
for _, row in high_priority_stores.iterrows():
    if pd.notna(row["Connected_Stores"]) and pd.notna(row["Distance_to_Next"]):
        connected_stores = row["Connected_Stores"].split(";")
        distances = list(map(float, row["Distance_to_Next"].split(";")))
        for store, distance in zip(connected_stores, distances):
            if store in high_priority_stores["Store_Name"].values:
                G.add_edge(row["Store_Name"], store, weight=distance)

# Define the itinerary structure with column names
itinerary_columns = [
    "Step", "Start_Point", "End_Point",
    "Latitude_Start", "Longitude_Start", "Latitude_End", "Longitude_End", "Distance_km"
]
itinerary_df = pd.DataFrame(columns=itinerary_columns)

# Run Dijkstra's Algorithm to find the best collection route
if croix_rouge_name in G and len(G.nodes) > 1:
    shortest_routes = nx.single_source_dijkstra_path(G, croix_rouge_name)
    shortest_distances = nx.single_source_dijkstra_path_length(G, croix_rouge_name)

    # Sort stores by shortest distance from Croix-Rouge
    sorted_stores = sorted(shortest_distances.items(), key=lambda x: x[1])

    # Create an itinerary list and build the route string with emojis
    itinerary = []
    route_list = []

    for i, (dest, distance) in enumerate(sorted_stores, start=1):
        if dest != croix_rouge_name:  # Skip the starting point for now
            route = shortest_routes[dest]
            for j in range(len(route) - 1):
                itinerary.append({
                    "Step": i,
                    "Start_Point": route[j],
                    "End_Point": route[j+1],
                    "Latitude_Start": df.loc[df["Store_Name"] == route[j], "Latitude"].values[0],
                    "Longitude_Start": df.loc[df["Store_Name"] == route[j], "Longitude"].values[0],
                    "Latitude_End": df.loc[df["Store_Name"] == route[j+1], "Latitude"].values[0],
                    "Longitude_End": df.loc[df["Store_Name"] == route[j+1], "Longitude"].values[0],
                    "Distance_km": round(haversine(
                        (df.loc[df["Store_Name"] == route[j], "Latitude"].values[0],
                         df.loc[df["Store_Name"] == route[j], "Longitude"].values[0]),
                        (df.loc[df["Store_Name"] == route[j+1], "Latitude"].values[0],
                         df.loc[df["Store_Name"] == route[j+1], "Longitude"].values[0])
                    ), 2)
                })
            route_list.append(dest)

    # Add the return to Croix-Rouge
    if route_list:
        last_stop = route_list[-1]
        itinerary.append({
            "Step": len(route_list) + 1,
            "Start_Point": last_stop,
            "End_Point": croix_rouge_name,
            "Latitude_Start": df.loc[df["Store_Name"] == last_stop, "Latitude"].values[0],
            "Longitude_Start": df.loc[df["Store_Name"] == last_stop, "Longitude"].values[0],
            "Latitude_End": df.loc[df["Store_Name"] == croix_rouge_name, "Latitude"].values[0],
            "Longitude_End": df.loc[df["Store_Name"] == croix_rouge_name, "Longitude"].values[0],
            "Distance_km": round(haversine(
                (df.loc[df["Store_Name"] == last_stop, "Latitude"].values[0],
                 df.loc[df["Store_Name"] == last_stop, "Longitude"].values[0]),
                (df.loc[df["Store_Name"] == croix_rouge_name, "Latitude"].values[0],
                 df.loc[df["Store_Name"] == croix_rouge_name, "Longitude"].values[0])
            ), 2)
        })
        route_list.append(croix_rouge_name)

    # Convert itinerary list to a DataFrame
    itinerary_df = pd.DataFrame(itinerary)

    # Build the route summary string with emojis:
    # Use 🚩 for departure, ➡️ for intermediate points, and 🏁 for arrival.
    if route_list:
        route_with_emojis = "🚩 " + croix_rouge_name
        for idx, point in enumerate(route_list, start=1):
            # If last point equals Croix-Rouge, mark as finish.
            if point == croix_rouge_name and idx == len(route_list):
                route_with_emojis += " 🏁 " + point
            else:
                route_with_emojis += " ➡️ " + point
        print(f"\n✅ Optimized Collection Itinerary (Threshold: {min_fill_percentage}%):")
        print(route_with_emojis)
    else:
        print("\n⚠ No valid route found! Check your data and try again.")

# Save itinerary to CSV with proper column names, even if it's empty
itinerary_csv_path = "data/itinerary.csv"
itinerary_df.to_csv(itinerary_csv_path, index=False)

if not itinerary_df.empty:
    print(f"\n✅ The optimized collection itinerary has been saved to '{itinerary_csv_path}'.")
else:
    print("\n⚠ No collection points met the criteria. An empty itinerary file has been created.")
