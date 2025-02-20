import pandas as pd

# File paths
itinerary_csv = "data/itinerary.csv"
output_link_file = "data/maps_link.txt"

# Read the itinerary CSV file
try:
    df = pd.read_csv(itinerary_csv)
except FileNotFoundError:
    print(f"❌ Le fichier {itinerary_csv} n'a pas été trouvé!")
    exit()

if df.empty:
    print("❌ Aucun itinéraire n'a été trouvé dans le fichier.")
    exit()

# Get origin from the first row's start coordinates
origin_lat = df.iloc[0]["Latitude_Start"]
origin_lng = df.iloc[0]["Longitude_Start"]
origin = f"{origin_lat},{origin_lng}"

# Get destination from the last row's end coordinates
destination_lat = df.iloc[-1]["Latitude_End"]
destination_lng = df.iloc[-1]["Longitude_End"]
destination = f"{destination_lat},{destination_lng}"

# Build waypoints from each row's end coordinates, excluding the last row if it equals destination
waypoints_list = []
for index, row in df.iterrows():
    lat = row["Latitude_End"]
    lng = row["Longitude_End"]
    coord = f"{lat},{lng}"
    # Skip if this coordinate is equal to destination (especially for the last row)
    if coord == destination:
        continue
    waypoints_list.append(coord)

# Join waypoints with a pipe separator
waypoints = "|".join(waypoints_list)

# Build the final Google Maps URL
maps_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}&waypoints={waypoints}"

# Save the URL to output file
with open(output_link_file, "w") as f:
    f.write(maps_url)

print(f"✅ Le lien Google Maps a été généré et sauvegardé dans '{output_link_file}':")
print(maps_url)
