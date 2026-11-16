"""Build per-station walks files from an OpenStreetMap extract (England).

1. Download the England extract (Geofabrik).
2. osmium tags-filter keeps hiking route relations plus the ways and nodes they reference.
3. pyosmium reads that small file, and for each hiking route works out a centre point.
4. For each station with a map position, keep the 6 nearest routes within 6 km.
5. Write data/walks/<CRS>.json.
The walking-time filter (OpenRouteService) is added later.
"""
import json, math, pathlib, subprocess, sys, datetime, urllib.request
import osmium

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXTRACT_URL = "https://download.geofabrik.de/europe/united-kingdom/england-latest.osm.pbf"
WORK = ROOT / "work"
OUT = ROOT / "data" / "walks"
RADIUS_KM = 6.0
WIDE_RADIUS_KM = 12.0   # used only where fewer than MIN_TRAILS routes are within RADIUS_KM
MIN_TRAILS = 3
MAX_TRAILS = 6


class HikingHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.routes = {}   # relation id -> (name, ref, [points])
        self.ways = {}     # way id -> [(lon, lat)]
        self.members = {}  # relation id -> [way ids]

    def relation(self, r):
        if r.tags.get("route") == "hiking" and r.tags.get("name"):
            self.members[r.id] = [m.ref for m in r.members if m.type == "w"]
            self.routes[r.id] = (r.tags.get("name"), r.tags.get("ref", ""))

    def way(self, w):
        if w.id in self.ways or not w.nodes:
            return
        pts = [(n.lon, n.lat) for n in w.nodes if n.location.valid()]
        if pts:
            self.ways[w.id] = pts


def haversine_km(lon1, lat1, lon2, lat2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def main():
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    pbf = WORK / "england.osm.pbf"
    if not pbf.exists():
        print("Downloading England extract...", flush=True)
        urllib.request.urlretrieve(EXTRACT_URL, pbf)
    hiking = WORK / "hiking.osm.pbf"
    subprocess.run(["osmium", "tags-filter", str(pbf), "r/route=hiking", "-o", str(hiking), "--overwrite"], check=True)

    h = HikingHandler()
    h.apply_file(str(hiking), locations=True)
    print(f"{len(h.routes)} named hiking routes", flush=True)

    # Centre point per route: average of all its way points.
    centres = {}
    for rid, wids in h.members.items():
        pts = [p for wid in wids for p in h.ways.get(wid, [])]
        if not pts:
            continue
        lon = sum(p[0] for p in pts) / len(pts)
        lat = sum(p[1] for p in pts) / len(pts)
        name, ref = h.routes[rid]
        centres[rid] = (lon, lat, name, ref, len(pts))

    stations = json.loads((ROOT / "data" / "destinations.json").read_text())["stations"]
    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = 0
    for s in stations:
        if s.get("lat") is None or s.get("lon") is None:
            continue
        def find(radius, box_lat, box_lon):
            found = []
            for rid, (lon, lat, name, ref, npts) in centres.items():
                if abs(lat - s["lat"]) > box_lat or abs(lon - s["lon"]) > box_lon:
                    continue  # quick box check before the distance
                d = haversine_km(s["lon"], s["lat"], lon, lat)
                if d <= radius:
                    found.append({"name": name, "ref": ref, "km_from_station": round(d, 1)})
            found.sort(key=lambda x: x["km_from_station"])
            return found
        near = find(RADIUS_KM, 0.06, 0.1)
        radius_used = RADIUS_KM
        if len(near) < MIN_TRAILS:
            near = find(WIDE_RADIUS_KM, 0.13, 0.22)
            radius_used = WIDE_RADIUS_KM
        trails = near[:MAX_TRAILS]
        total += len(trails)
        out = {"station": s["name"], "crs": s["crs"], "generatedAt": generated,
               "note": f"Hiking routes from OpenStreetMap contributors (ODbL). Nearest routes within {radius_used:g} km; walking time not yet applied.",
               "trails": trails}
        (OUT / f"{s['crs']}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"Written {OUT}; {total} trails in total", flush=True)


if __name__ == "__main__":
    sys.exit(main())
