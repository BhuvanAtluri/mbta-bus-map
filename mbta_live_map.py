import streamlit as st
import requests
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="MBTA Live Tracker", layout="wide")

st.title("🚦 MBTA Live Tracker")
st.markdown("Track buses and trains in real-time.")

# --- MBTA API ---
API_KEY = "e83ca4904d974faa97355cfcedb2afae"
BASE_URL = "https://api-v3.mbta.com"

def fetch_mbta(endpoint, params=None):
    if params is None:
        params = {}
    params["api_key"] = API_KEY
    url = f"{BASE_URL}{endpoint}"
    return requests.get(url, params=params)

# --- Helpers ---
def bearing_to_arrow(bearing):
    if bearing is None:
        return "•"
    directions = [
        (22.5, "↑"), (67.5, "↗"), (112.5, "→"), (157.5, "↘"),
        (202.5, "↓"), (247.5, "↙"), (292.5, "←"), (337.5, "↖"), (360, "↑")
    ]
    for angle, arrow in directions:
        if bearing <= angle:
            return arrow
    return "↑"

@st.cache_data(ttl=3600)
def get_stop_name(stop_id):
    if not stop_id:
        return "Unknown"
    try:
        r = fetch_mbta(f"/stops/{stop_id}")
        return r.json()["data"]["attributes"]["name"]
    except:
        return "Unknown"

def get_next_stop(vehicle_id):
    try:
        r = fetch_mbta("/predictions", params={
            "filter[vehicle]": vehicle_id,
            "include": "stop",
            "sort": "arrival_time"
        })
        data = r.json().get("data", [])
        for prediction in data:
            stop_rel = prediction.get("relationships", {}).get("stop", {}).get("data", {})
            stop_id = stop_rel.get("id")
            if stop_id:
                stop_name = get_stop_name(stop_id)
                return stop_id, stop_name
    except Exception as e:
        st.warning(f"Prediction error for {vehicle_id}: {e}")
    return None, "Unknown"

def get_prediction(vehicle_id):
    try:
        r = fetch_mbta("/predictions", params={
            "filter[vehicle]": vehicle_id,
            "sort": "arrival_time"
        })
        data = r.json().get("data", [])
        for pred in data:
            arrival = pred["attributes"].get("arrival_time")
            if arrival:
                return arrival
    except Exception as e:
        st.warning(f"Arrival time error for {vehicle_id}: {e}")
    return None

@st.cache_data(ttl=3600)
def get_route_shape(route_id):
    try:
        r = fetch_mbta("/shapes", params={"filter[route]": route_id, "page[limit]": 1000})
        return [
            (s["attributes"]["shape_pt_lat"], s["attributes"]["shape_pt_lon"])
            for s in r.json()["data"]
            if s["attributes"].get("shape_pt_lat") and s["attributes"].get("shape_pt_lon")
        ]
    except:
        return []

@st.cache_data(ttl=3600)
def get_route_stops(route_id):
    try:
        r = fetch_mbta("/stops", params={"filter[route]": route_id})
        return [
            (s["attributes"]["latitude"], s["attributes"]["longitude"], s["attributes"]["name"])
            for s in r.json()["data"]
        ]
    except:
        return []

# --- Sidebar UI ---
st.sidebar.header("🎛️ Filters")
mode = st.sidebar.selectbox("Transit Mode", ["Bus", "Rail"])
route_type = 3 if mode == "Bus" else 1

bus_routes = [str(i) for i in range(1, 21)]
rail_routes = ["Red", "Orange", "Blue", "Green-B", "Green-C", "Green-D", "Green-E"]
included_routes = bus_routes if mode == "Bus" else rail_routes

refresh_interval = st.sidebar.slider("Refresh every (seconds):", 10, 60, 30)

@st.cache_data(ttl=refresh_interval)
def get_vehicle_data(route_type):
    r = fetch_mbta("/vehicles", params={"filter[route_type]": route_type})
    return r.json()

vehicle_data = get_vehicle_data(route_type)

vehicles = [
    v for v in vehicle_data["data"]
    if (v.get("relationships", {}).get("route", {}).get("data") or {}).get("id") in included_routes
]

available_routes = sorted(set(
    (v.get("relationships", {}).get("route", {}).get("data", {}) or {}).get("id")
    for v in vehicles
))
available_statuses = sorted(set(v["attributes"]["current_status"] for v in vehicles))

selected_routes = st.sidebar.multiselect("Routes", available_routes, default=available_routes)
selected_statuses = st.sidebar.multiselect("Statuses", available_statuses, default=available_statuses)

vehicle_choices = {}
for v in vehicles:
    route_id = (v.get("relationships", {}).get("route", {}).get("data", {}) or {}).get("id")
    if route_id in selected_routes:
        label = v["attributes"].get("label", "?")
        vehicle_choices[f"{label} (Route {route_id})"] = v["id"]

selected_vehicle_label = st.sidebar.selectbox("📍 Track a Vehicle", ["None"] + list(vehicle_choices.keys()))

# --- Map ---
m = folium.Map(location=[42.3601, -71.0589], zoom_start=13)

# --- Add vehicle markers ---
for v in vehicles:
    attr = v["attributes"]
    route_id = (v.get("relationships", {}).get("route", {}).get("data", {}) or {}).get("id")
    if route_id not in selected_routes or attr["current_status"] not in selected_statuses:
        continue

    arrow = bearing_to_arrow(attr.get("bearing"))
    label = route_id
    tooltip = f"Route {route_id} | Vehicle {attr.get('label')} | {attr['current_status']}"

    html = f"""
    <div style="
        background-color: orange;
        color: black;
        border-radius: 12px;
        padding: 2px 6px;
        font-size: 11px;
        font-weight: bold;
        text-align: center;
        white-space: nowrap;
        box-shadow: 0 0 2px #333;
    ">
        {arrow} {label}
    </div>
    """

    folium.Marker(
        [attr["latitude"], attr["longitude"]],
        icon=folium.DivIcon(html=html),
        tooltip=tooltip
    ).add_to(m)

# --- Highlight selected vehicle route ---
if selected_vehicle_label != "None":
    vehicle_id = vehicle_choices[selected_vehicle_label]
    vehicle = next((v for v in vehicles if v["id"] == vehicle_id), None)

    if vehicle:
        attr = vehicle["attributes"]
        route_id = (vehicle["relationships"]["route"]["data"] or {}).get("id")
        stop_id, stop_name = get_next_stop(vehicle_id)
        prediction = get_prediction(vehicle_id)

        shape = get_route_shape(route_id)
        if shape:
            folium.PolyLine(shape, color="blue", weight=4, opacity=0.7).add_to(m)

        for lat, lon, name in get_route_stops(route_id):
            folium.CircleMarker(
                location=[lat, lon],
                radius=3,
                color="gray",
                fill=True,
                fill_opacity=0.7,
                tooltip=name
            ).add_to(m)

        st.sidebar.markdown("### 🛰 Vehicle Info")
        st.sidebar.write(f"**Vehicle ID:** {vehicle_id}")
        st.sidebar.write(f"**Route:** {route_id}")
        st.sidebar.write(f"**Current Status:** {attr['current_status']}")
        st.sidebar.write(f"**Next Stop:** {stop_name}")
        st.sidebar.write(f"**Arrival Time:** {prediction or 'N/A'}")

# --- Show Map ---
st_folium(m, width="100%", height=800)
