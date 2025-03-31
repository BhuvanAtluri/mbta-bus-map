import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from geopy.distance import geodesic

st.set_page_config(page_title="MBTA Live Transit Tracker", layout="wide")

st.title("MBTA Live Tracker")
st.markdown("Track MBTA buses and trains in real-time. Select a vehicle from the dropdown on the left to highlight its route and stops.")

API_KEY = "e83ca4904d974faa97355cfcedb2afae"
BASE_URL = "https://api-v3.mbta.com"

def fetch_mbta(endpoint, params=None):
    if params is None:
        params = {}
    params["api_key"] = API_KEY
    return requests.get(f"{BASE_URL}{endpoint}", params=params)

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

def estimate_stop_and_destination(vehicle_latlon, route_id):
    try:
        stops = get_route_stops(route_id)
        if not stops:
            return "Unknown", "Unknown"

        # Sort by distance
        sorted_stops = sorted(
            stops,
            key=lambda stop: geodesic(vehicle_latlon, (stop[0], stop[1])).meters
        )

        next_stop = sorted_stops[0][2]
        destination = sorted_stops[-1][2]
        return next_stop, destination
    except:
        return "Unknown", "Unknown"

def bearing_to_arrow(bearing):
    if bearing is None:
        return "•"
    directions = [(22.5, "↑"), (67.5, "↗"), (112.5, "→"), (157.5, "↘"),
                  (202.5, "↓"), (247.5, "↙"), (292.5, "←"), (337.5, "↖"), (360, "↑")]
    for angle, arrow in directions:
        if bearing <= angle:
            return arrow
    return "↑"

# --- Sidebar Filters ---
st.sidebar.header("🎛️ Filters")
mode = st.sidebar.selectbox("Transit Mode", ["Bus", "Rail"])
route_type = 3 if mode == "Bus" else 1

bus_routes = [str(i) for i in range(1, 71)]
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

selected_vehicle_label = st.sidebar.selectbox("Track a Vehicle (highlighted via a red dot)", ["None"] + list(vehicle_choices.keys()))

# --- Map ---
m = folium.Map(location=[42.3601, -71.0589], zoom_start=13)

# --- Add Vehicle Markers ---
for v in vehicles:
    attr = v["attributes"]
    vehicle_id = v["id"]
    route_id = (v.get("relationships", {}).get("route", {}).get("data", {}) or {}).get("id")

    if route_id not in selected_routes or attr["current_status"] not in selected_statuses:
        continue

    is_selected = (vehicle_id == vehicle_choices.get(selected_vehicle_label))
    color = "red" if is_selected else "orange"
    arrow = bearing_to_arrow(attr.get("bearing"))
    label = route_id

    vehicle_latlon = (attr["latitude"], attr["longitude"])
    stop_name, _ = estimate_stop_and_destination(vehicle_latlon, route_id)

    tooltip = f"Route {route_id} | Vehicle {attr.get('label')} | {attr['current_status']} | {stop_name}"

    html = f"""
    <div style="
        background-color: {color};
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

# --- Highlight Route + Stops for Selected Vehicle ---
if selected_vehicle_label != "None":
    selected_id = vehicle_choices[selected_vehicle_label]
    vehicle = next((v for v in vehicles if v["id"] == selected_id), None)

    if vehicle:
        attr = vehicle["attributes"]
        route_id = (vehicle["relationships"]["route"]["data"] or {}).get("id")
        vehicle_latlon = (attr["latitude"], attr["longitude"])
        next_stop, destination = estimate_stop_and_destination(vehicle_latlon, route_id)

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
        st.sidebar.write(f"**Vehicle ID:** {selected_id}")
        st.sidebar.write(f"**Route:** {route_id}")
        st.sidebar.write(f"**Current Status:** {attr['current_status']}")
        st.sidebar.write(f"**Next Stop:** {next_stop}")
        st.sidebar.write(f"**Destination:** {destination}")

# --- Show Map ---
st_folium(m, width="100%", height=800)
