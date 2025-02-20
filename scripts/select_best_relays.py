import os
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# Fix Joblib CPU warning by limiting CPU cores
os.environ["LOKY_MAX_CPU_COUNT"] = "1"

# Load dataset
csv_file_path = "data/collection_points.csv"
df = pd.read_csv(csv_file_path)

# Filter rows where Latitude and Longitude are not available
df = df.dropna(subset=["Latitude", "Longitude"])

# Convert lat/lon to numeric
df["Latitude"] = pd.to_numeric(df["Latitude"])
df["Longitude"] = pd.to_numeric(df["Longitude"])

# Ask user how many relay points they want to select
while True:
    try:
        num_clusters = int(input("\n🔹 Enter the number of relay points you want to select (1-10): ").strip())
        if 1 <= num_clusters <= 10:
            break
        else:
            print("⚠ Please enter a number between 1 and 10.")
    except ValueError:
        print("⚠ Invalid input! Please enter a valid number.")

# Normalize coordinates for clustering
scaler = StandardScaler()
df[["Latitude_scaled", "Longitude_scaled"]] = scaler.fit_transform(df[["Latitude", "Longitude"]])

# Apply K-Means clustering to distribute relay points evenly
kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
df["Cluster"] = kmeans.fit_predict(df[["Latitude_scaled", "Longitude_scaled"]])

# Function to choose the best point per cluster
def select_best_point(cluster_df):
    # Prioritize supermarkets, post offices, or high-traffic points
    priority_types = ["Supermarket", "Bureau de Poste", "Point Relais"]
    cluster_df = cluster_df.sort_values(by="Type", key=lambda x: x.isin(priority_types), ascending=False)
    return cluster_df.iloc[0]  # Select the best priority location in each cluster

# Select the best relay points from each cluster (Fix Pandas DeprecationWarning)
best_points = df.groupby("Cluster", group_keys=False, as_index=False, sort=False).apply(
    select_best_point, include_groups=False
).reset_index(drop=True)

# Keep only the user-defined number of points
best_points = best_points.head(num_clusters)

# Save the selected points to a new CSV
best_points.to_csv("data/selected_relay_points.csv", index=False)

# Print selected points
print("\n✅ The best relay points have been selected based on your choice!")
print("📌 Selected Relay Points:")
print(best_points[["Store_Name", "Address", "Type"]].to_string(index=False))

print(f"\n✅ The selected relay points have been saved in 'data/selected_relay_points.csv'.")
