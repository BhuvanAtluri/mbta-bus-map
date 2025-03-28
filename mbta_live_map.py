import streamlit as st
import requests
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="MBTA Live Bus Tracker", layout="wide")

st.title("🚍 MBTA Live Bus Tracker")
st.markdown("Real-time MBTA bus locations with route filters and live tracking.")

# --- MBTA API ---
API_KEY = "e83ca4904d974faa97355cfcedb2afae"
BASE_URL = "https://api-v3.mbta.com"

def fetch_mbta(endpoint, params=None):
    if params is None:
        params = {}
    params["api_key"] = API_KEY
    url = f"{BASE_URL}{endpoint}"
    return requests.get(url, params=params)

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
def get_route_colors():
    r = fetch_mbta("/routes", params={"filter[type]": 3})
    return {
        route["id"]: f'#{route["attributes"]["color"]}' for route in r.json()["data"]
    }

@st.cache_data(ttl=3600)
def get_stop_name(stop_id):
    if not stop_id:
        return "Unknown"
    try:
        r = fetch_mbta(f"/stops/{stop_id}")
        data = r.json().get("data", {})
        return data.get("attributes", {}).get("name", "Unknown")
    except Exception:
        return "Unknown"

def get_next_stop(vehicle_id):
    try:
        r = fetch_mbta("/predictions", params={"filter[vehicle]": vehicle_id, "include": "stop"})
        data = r.json()
        if data.get("data"):
            stop = data["data"][0]["relationships"]["stop"]["data"]
            stop_id = stop.get("id") if stop else None
            return stop_id, get_stop_name(stop_id)
    except Exception:
        pass
    return None, "Unknown"

@st.cache_data(ttl=3600)
def get_prediction(vehicle_id):
    try:
        r = fetch_mbta("/predictions", params={"filter[vehicle]": vehicle_id})
        if r.status_code == 200 and r.json()["data"]:
            return r.json()["data"][0]["attributes"]["arrival_time"]
    except Exception:
        pass
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
    except Exception:
        return []

@st.cache_data(ttl=3600)
def get_route_stops(route_id):
    try:
        r = fetch_mbta("/stops", params={"filter[route]": route_id})
        return [
            (s["attributes"]["latitude"], s["attributes"]["longitude"], s["attributes"]["name"])
            for s in r.json()["data"]
        ]
    except Exception:
        return []

# --- Sidebar UI ---
st.sidebar.header("🔍 Filter Options")
refresh_interval = st.sidebar.slider("Refresh every (seconds):", 10, 60, 30)

@st.cache_data(ttl=refresh_interval)
def get_bus_data():
    r = fetch_mbta("/vehicles", params={"filter[route_type]": 3})
    return r.json()

bus_data = get_bus_data()
route_colors = get_route_colors()

# Build list of available route/status options
all_routes = sorted({v.get("relationships", {}).get("route", {}).get("data", {}).get("id") for v in bus_data["data"] if v.get("relationships", {}).get("route", {}).get("data")})
all_statuses = sorted({v["attributes"]["current_status"] for v in bus_data["data"]})

selected_routes = st.sidebar.multiselect("Select Routes", all_routes, default=all_routes)
selected_statuses = st.sidebar.multiselect("Select Statuses", all_statuses, default=all_statuses)

# ✅ Safe bus selection (no KeyErrors)
bus_choices = {}
for v in bus_data["data"]:
    route_data = v.get("relationships", {}).get("route", {}).get("data")
    route_id = route_data.get("id") if route_data else None
    if route_id and route_id in selected_routes:
        label = v["attributes"].get("label", "?")
        bus_choices[f'Bus {label} (Route {route_id})'] = v["id"]

selected_bus_label = st.sidebar.selectbox("📍 Track a Bus", ["None"] + list(bus_choices.keys()))

# --- Create Map ---
m = folium.Map(location=[42.3601, -71.0589], zoom_start=13)

# --- Add Markers (no slow lookups here!) ---
for vehicle in bus_data["data"]:
    attr = vehicle["attributes"]
    route_data = vehicle.get("relationships", {}).get("route", {}).get("data")
    route_id = route_data.get("id") if route_data else None
    status = attr["current_status"]

    if not route_id or route_id not in selected_routes or status not in selected_statuses:
        continue

    arrow = bearing_to_arrow(attr.get("bearing"))
    label = route_id
    tooltip = f"Route {route_id} | Bus {attr.get('label') or '?'} | {status}"

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

# --- If a bus is selected, show route + stops ---
if selected_bus_label != "None":
    bus_id = bus_choices[selected_bus_label]
    bus = next((v for v in bus_data["data"] if v["id"] == bus_id), None)

    if bus:
        attr = bus["attributes"]
        route_data = bus["relationships"]["route"]["data"]
        route_id = route_data.get("id") if route_data else None
        stop_id, stop_name = get_next_stop(bus_id)
        prediction_time = get_prediction(bus_id)

        shape_coords = get_route_shape(route_id)
        if shape_coords:
            folium.PolyLine(shape_coords, color="blue", weight=4, opacity=0.7).add_to(m)
        else:
            st.warning(f"No shape data for route {route_id}")

        for lat, lon, name in get_route_stops(route_id):
            folium.CircleMarker(
                location=[lat, lon],
                radius=3,
                color="gray",
                fill=True,
                fill_opacity=0.7,
                tooltip=name
            ).add_to(m)

        # Sidebar details
        st.sidebar.markdown("### 🛰️ Bus Details")
        st.sidebar.write(f"**Bus ID:** {bus['id']}")
        st.sidebar.write(f"**Route:** {route_id}")
        st.sidebar.write(f"**Current Status:** {attr['current_status']}")
        st.sidebar.write(f"**Next Stop:** {stop_name}")
        st.sidebar.write(f"**Arrival Time:** {prediction_time if prediction_time else 'N/A'}")

# --- Show the map ---
st_folium(m, width="100%", height=800)
