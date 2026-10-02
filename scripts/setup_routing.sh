#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
data_dir="$repo_dir/routing-data"
pbf_name="nord-pas-de-calais-latest.osm.pbf"
osrm_image="ghcr.io/project-osrm/osrm-backend:latest"
pbf_url="${OSM_PBF_URL:-https://download.geofabrik.de/europe/france/nord-pas-de-calais-latest.osm.pbf}"

mkdir -p "$data_dir"
if [[ ! -f "$data_dir/$pbf_name.complete" ]]; then
  echo "Downloading the Nord-Pas-de-Calais OpenStreetMap extract..."
  curl --fail --location --retry 5 --retry-all-errors --connect-timeout 30 --speed-time 90 --speed-limit 1024 -C - "$pbf_url" --output "$data_dir/$pbf_name"
  touch "$data_dir/$pbf_name.complete"
fi

docker pull "$osrm_image"
docker run --rm -t -v "$data_dir:/data" "$osrm_image" \
  osrm-extract -p /opt/car.lua "/data/$pbf_name"
docker run --rm -t -v "$data_dir:/data" "$osrm_image" \
  osrm-partition "/data/nord-pas-de-calais-latest.osrm"
docker run --rm -t -v "$data_dir:/data" "$osrm_image" \
  osrm-customize "/data/nord-pas-de-calais-latest.osrm"

echo "OSRM data prepared in $data_dir. Start it with: docker compose up -d routing"
