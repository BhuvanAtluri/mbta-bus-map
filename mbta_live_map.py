import streamlit as st
import requests
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="MBTA Live Bus Tracker", layout="wide")

st.title("🚍 MBTA Live Bus Tracker")
st.markdown("Real-time MBTA bus locations with route filters, directions, and next stop tracking.")

# Sidebar: refresh + filters
refresh_interval = st.sidebar.slider("Refresh every (seconds):", 10, 60, 30)
st.sidebar.header("🔍 Filter Options")

# --- Helper: Convert bearing to arrow symbol ---
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

# --- API functions ---
@st.cache_data(ttl=refresh_interval)
def get_bus_data():
    url = "https://api-v3.mbta.com/vehicles?filter[route_type]=3"
    return requests.get(url).json()

@st.cache_data(ttl=3600)
def get_route_colors():
    url = "https://api-v3.mbta.com/routes?filter[type]=3"
    data = requests.get(url).json()
    return {
        route["id"]: f'#{route["attributes"]["color"]}' for route in data["data"]
    }

@st.cache_data(ttl=3600)
def get_stop_name(stop_id):
    if not stop_id:
        return "Unknown"
    url = f"https://api-v3.mbta.com/stops/{stop_id}"
    r = requests.get(url)
    if r.status_code == 200:
        return r.json()["data"]["attributes"]["name"]
    return "Unknown"

def get_prediction(vehicle_id):
    url = f"https://api-v3.mbta.com/predictions?filter[vehicle]={vehicle_id}"
    r = requests.get(url)
    if r.status_code == 200 and r.json()["data"]:
        pred = r.json()["data"][0]["attributes"]
        return pred["arrival_time"]
    return None

# --- Load data ---
bus_data = get_bus_data()
route_colors = get_route_colors()

# --- Sidebar filters ---
all_routes = sorted({v["relationships"]["route"]["data"]["id"] for v in bus_data["data"]})
all_statuses = sorted({v["attributes"]["current_status"] for v in bus_data["data"]})

selected_routes = st.sidebar.multiselect("Select Routes", all_routes, default=all_routes)
selected_statuses = st.sidebar.multiselect("Select Statuses", all_statuses, default=all_statuses)

# --- Bus tracking dropdown ---
bus_choices = {
    f'Bus {v["attributes"]["label"]} (Route {v["relationships"]["route"]["data"]["id"]})': v["id"]
    for v in bus_data["data"]
    if v["relationships"]["route"]["data"]["id"] in selected_routes
}
selected_bus_label = st.sidebar.selectbox("📍 Track a Bus", ["None"] + list(bus_choices.keys()))

# --- Create map ---
m = folium.Map(location=[42.3601, -71.0589], zoom_start=13)

# --- Add bus markers with number + direction ---
for vehicle in bus_data["data"]:
    attr = vehicle["attributes"]
    route_id = vehicle["relationships"]["route"]["data"]["id"]
    status = attr["current_status"]

    if route_id not in selected_routes or status not in selected_statuses:
        continue

    color = route_colors.get(route_id, "#0000FF")
    label = attr["label"] or "?"
    arrow = bearing_to_arrow(attr.get("bearing"))

    folium.Marker(
        [attr["latitude"], attr["longitude"]],
        icon=folium.DivIcon(html=f"""
            <div style="font-size: 11px; font-weight: bold;
                        color: {color}; text-align: center;">
                {arrow} {label}
            </div>
        """),
        tooltip=f"Route {route_id} | Bus {label} | {status}"
    ).add_to(m)

# --- Show map ---
st_folium(m, width=1000, height=600)

# --- Show selected bus info ---
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
