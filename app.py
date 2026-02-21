from flask import Flask, render_template, jsonify
import requests
import time

app = Flask(__name__)

# ── Site Configuration ────────────────────────────────────────────────────────
SITE_CONFIG = {
    "03333050": {"temp_sites": ["05524500", "03327000"], "lat": 40.514051, "lng": -86.804322},
    "03351201": {"temp_sites": ["03353611", "03353000"], "lat": 39.825313, "lng": -86.188908},
    "03353200": {"temp_sites": ["03353200"],             "lat": 39.886527, "lng": -86.307937},
    "03353451": {"temp_sites": ["03353200"],             "lat": 39.801197, "lng": -86.281049},
    "03339500": {"temp_sites": ["03353200", "03340900"], "lat": 40.083484, "lng": -86.871184},
    "03339305": {"temp_sites": ["03353200", "03340900"], "lat": 40.141979, "lng": -86.628439},
    "03351710": {"temp_sites": ["03353200", "03353000", "03354000"], "lat": 39.872646, "lng": -86.018977},
    "03363000": {"temp_sites": ["03276000", "03354000", "03372500"], "lat": 39.349119, "lng": -85.980852},
    "03353910": {"temp_sites": ["03353200", "03354000", "03340900"], "lat": 39.702303, "lng": -86.408420},
    "03353000": {"temp_sites": ["03353000"],             "lat": 39.803721, "lng": -86.197487},
    "03359000": {"temp_sites": ["03359000"],             "lat": 39.434033, "lng": -86.814019},
}

USGS_BASE_URL = "https://waterservices.usgs.gov/nwis/iv/"

_cache = {"data": None, "timestamp": 0}
CACHE_TTL = 300


def get_all_site_ids():
    all_ids = set(SITE_CONFIG.keys())
    for config in SITE_CONFIG.values():
        all_ids.update(config["temp_sites"])
    return list(all_ids)


def fetch_usgs_data():
    params = {
        "sites": ",".join(get_all_site_ids()),
        "parameterCd": "00010,00065",
        "format": "json",
    }
    response = requests.get(USGS_BASE_URL, params=params, timeout=15)
    response.raise_for_status()
    raw = response.json()

    readings = {}
    for series in raw["value"]["timeSeries"]:
        site_no   = series["sourceInfo"]["siteCode"][0]["value"]
        site_name = series["sourceInfo"]["siteName"]
        param     = series["variable"]["variableCode"][0]["value"]
        values    = series["values"][0]["value"]

        latest_value = None
        latest_time  = None
        for v in reversed(values):
            if v["value"] not in (None, "", "-999999"):
                try:
                    latest_value = float(v["value"])
                    latest_time  = v["dateTime"]
                    break
                except ValueError:
                    continue

        if site_no not in readings:
            readings[site_no] = {
                "name": site_name, "gage_height": None,
                "gage_time": None, "water_temp": None, "temp_time": None,
            }

        if param == "00065":
            readings[site_no]["gage_height"] = latest_value
            readings[site_no]["gage_time"]   = latest_time
        elif param == "00010":
            readings[site_no]["water_temp"]  = latest_value
            readings[site_no]["temp_time"]   = latest_time

    return readings


def build_results(readings):
    results = []
    for main_site, config in SITE_CONFIG.items():
        main_data = readings.get(main_site, {})

        gage_height = main_data.get("gage_height")
        gage_time   = main_data.get("gage_time")

        temp_values = []
        for temp_site in config["temp_sites"]:
            val = readings.get(temp_site, {}).get("water_temp")
            if val is not None:
                temp_values.append(val)

        if temp_values:
            avg_temp_c = round(sum(temp_values) / len(temp_values), 2)
            avg_temp_f = round(avg_temp_c * 9 / 5 + 32, 1)
        else:
            avg_temp_c = None
            avg_temp_f = None

        results.append({
            "site_no":        main_site,
            "name":           main_data.get("name", f"Site {main_site}"),
            "gage_height_ft": gage_height,
            "gage_time":      gage_time,
            "avg_temp_c":     avg_temp_c,
            "avg_temp_f":     avg_temp_f,
            "lat":            config["lat"],
            "lng":            config["lng"],
        })
    return results


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def api_data():
    now = time.time()
    if _cache["data"] is not None and (now - _cache["timestamp"]) < CACHE_TTL:
        return jsonify(_cache["data"])
    try:
        readings = fetch_usgs_data()
        results  = build_results(readings)
        _cache["data"]      = results
        _cache["timestamp"] = now
        return jsonify(results)
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to fetch USGS data: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": f"Internal error: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True)