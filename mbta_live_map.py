import streamlit as st
import requests
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Live MBTA Bus Tracker", layout="wide")

st.title("🚍 Live MBTA Bus Tracker")
st.markdown("Real-time MBTA bus map with route filters and color-coded markers.")

# Sidebar: refresh + filters
refresh_interval = st.sidebar.slider("Refresh every (seconds):", 10, 60, 30)
st.sidebar.header("🔍 Filter Options")

# --- Data Fetching ---
@st.cache_data(ttl=refresh_interval)
def get_bus_data():
    url = "https://api-v3.mbta.com/vehicles?filter[route_type]=3"
    return requests.get(url).json()

@st.cache_data(ttl=3600)
def get_route_colors():
    url = "https://api-v3.mbta.com/routes?filter[type]=3"
    routes_data = requests.get(url).json()
    return {
        route["id"]: f'#{route["attributes"]["color"]}'
        for route in routes_data["data"]
    }

bus_data = get_bus_data()
route_colors = get_route_colors()

# Extract route list and statuses from live bus data
all_routes = sorted({v["relationships"]["route"]["data"]["id"] for v in bus_data["data"]})
all_statuses = sorted({v["attributes"]["current_status"] for v in bus_data["data"]})

# Filters
selected_routes = st.sidebar.multiselect("Select Routes", all_routes, default=all_routes)
selected_statuses = st.sidebar.multiselect("Select Statuses", all_statuses, default=all_statuses)

# --- Map Setup ---
m = folium.Map(location=[42.3601, -71.0589], zoom_start=13)

# --- Add Buses ---
for vehicle in bus_data["data"]:
    attr = vehicle["attributes"]
    route_id = vehicle["relationships"]["route"]["data"]["id"]
    status = attr["current_status"]

    if route_id not in selected_routes or status not in selected_statuses:
        continue

    color = route_colors.get(route_id, "#0000FF")  # fallback to blue
    label = f"Route {route_id} | Bus {attr['label']} | {status}"

    folium.CircleMarker(
        location=[attr["latitude"], attr["longitude"]],
        radius=7,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.8,
        popup=label,
        tooltip=label
    ).add_to(m)

# Display map
st_folium(m, width=1000, height=600)

# Refresh page
st.rerun()

