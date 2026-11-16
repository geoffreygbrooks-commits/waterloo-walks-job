"""Build per-station walks files from an OpenStreetMap extract.

Steps: download the England extract from Geofabrik, pull hiking route relations
with osmium, then for each station in data/destinations.json collect routes
whose centre lies within 6 km, and write data/walks/<CRS>.json.
Walking-area filtering (OpenRouteService) is added once the extract step works.
"""
import json, os, subprocess, sys, datetime, pathlib, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXTRACT_URL = "https://download.geofabrik.de/europe/great-britain/england-latest.osm.pbf"
WORK = ROOT / "work"
OUT = ROOT / "data" / "walks"

def main():
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    pbf = WORK / "england.osm.pbf"
    if not pbf.exists():
        print("Downloading extract (large file)...")
        urllib.request.urlretrieve(EXTRACT_URL, pbf)
    routes = WORK / "hiking.osm.pbf"
    subprocess.run(["osmium", "tags-filter", str(pbf), "r/route=hiking", "-o", str(routes), "--overwrite"], check=True)
    # Export route relations as GeoJSON with centres (osmium export needs the relation centres from a second step).
    geo = WORK / "hiking.geojson"
    subprocess.run(["osmium", "export", str(routes), "-o", str(geo), "--overwrite", "-f", "geojson"], check=True)
    trails = json.loads(geo.read_text())
    stations = json.loads((ROOT / "data" / "destinations.json").read_text())["stations"]
    generated = datetime.datetime.utcnow().isoformat() + "Z"
    print(f"{len(trails['features'])} hiking features, {len(stations)} stations")
    for s in stations:
        if s.get("lat") is None or s.get("lon") is None:
            continue
        out = {"station": s["name"], "crs": s["crs"], "generatedAt": generated,
               "note": "Trails from OpenStreetMap contributors (ODbL). Walking area coming next.",
               "trails": []}
        (OUT / f"{s['crs']}.json").write_text(json.dumps(out, ensure_ascii=False))
    print("Written", OUT)

if __name__ == "__main__":
    sys.exit(main())
