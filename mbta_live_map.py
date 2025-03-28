import streamlit as st
import requests
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="MBTA Live Bus Tracker", layout="wide")

st.title("🚍 MBTA Live Bus Tracker")
st.markdown("Real-time MBTA bus locations with route filters, directions, and next stop tracking.")

# --- MBTA API Key ---
API_KEY = "e83ca4904d974faa97355cfcedb2afae"
BASE_URL = "https://api-v3.mbta.com"

# --- API Helper ---
def fetch_mbta(endpoint, params=None):
    if params is None:
        params = {}
    params["api_key"] = API_KEY
    url = f"{BASE_URL}{endpoint}"
    return requests.get(url, params=params)

# --- Bearing to Arrow ---
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

# --- Refresh & Filters ---
refresh_interval = st.sidebar.slider("Refresh every (seconds):", 10, 60, 30)
st.sidebar.header("🔍 Filter Options")

@st.cache_data(ttl=refresh_interval)
def get_bus_data():
    r = fetch_mbta("/vehicles", params={"filter[route_type]": 3})
    return r.json()

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
    r = fetch_mbta(f"/stops/{stop_id}")
    if r.status_code == 200:
        return r.json()["data"]["attributes"]["name"]
    return "Unknown"

def get_prediction(vehicle_id):
    r = fetch_mbta("/predictions", params={"filter[vehicle]": vehicle_id})
    if r.status_code == 200 and r.json()["data"]:
        return r.json()["data"][0]["attributes"]["arrival_time"]
    return None

# --- Load Data ---
bus_data = get_bus_data()
route_colors = get_route_colors()

# --- Filters ---
all_routes = sorted({v["relationships"]["route"]["data"]["id"] for v in bus_data["data"]})
all_statuses = sorted({v["attributes"]["current_status"] for v in bus_data["data"]})

selected_routes = st.sidebar.multiselect("Select Routes", all_routes, default=all_routes)
selected_statuses = st.sidebar.multiselect("Select Statuses", all_statuses, default=all_statuses)

# --- Track Specific Bus ---
bus_choices = {
    f'Bus {v["attributes"]["label"]} (Route {v["relationships"]["route"]["data"]["id"]})': v["id"]
    for v in bus_data["data"]
    if v["relationships"]["route"]["data"]["id"] in selected_routes
}
selected_bus_label = st.sidebar.selectbox("📍 Track a Bus", ["None"] + list(bus_choices.keys()))

# --- Create Map ---
m = folium.Map(location=[42.3601, -71.0589], zoom_start=13)

# --- Add Buses with Orange Dot + Arrow + Route Number ---
for vehicle in bus_data["data"]:
    attr = vehicle["attributes"]
    route_id = vehicle["relationships"]["route"]["data"]["id"]
    status = attr["current_status"]

    if route_id not in selected_routes or status not in selected_statuses:
        continue

    label = route_id
    arrow = bearing_to_arrow(attr.get("bearing"))

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
        tooltip=f"Route {route_id} | Bus {attr['label'] or '?'} | {status}"
    ).add_to(m)

# --- Show Map ---
st_folium(m, width=1400, height=1000)

# --- Show Bus Info in Sidebar ---
if selected_bus_label != "None":
    bus_id = bus_choices[selected_bus_label]
    bus = next((v for v in bus_data["data"] if v["id"] == bus_id), None)

    if bus:
        attr = bus["attributes"]
        route_id = bus["relationships"]["route"]["data"]["id"]
        stop_id = attr.get("stop_id")
        stop_name = get_stop_name(stop_id)
        prediction_time = get_prediction(bus_id)

        st.sidebar.markdown("### 🛰️ Bus Details")
        st.sidebar.write(f"**Bus ID:** {bus['id']}")
        st.sidebar.write(f"**Route:** {route_id}")
        st.sidebar.write(f"**Current Status:** {attr['current_status']}")
        st.sidebar.write(f"**Next Stop:** {stop_name}")
        st.sidebar.write(f"**Arrival Time:** {prediction_time if prediction_time else 'N/A'}")
