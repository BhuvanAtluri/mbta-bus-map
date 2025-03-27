import streamlit as st
import requests
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="MBTA Live Bus Tracker", layout="wide")

st.title("🚍 MBTA Live Bus Tracker")
st.markdown("Real-time MBTA bus locations with route filtering and live tracking.")

# Sidebar: refresh and filters
refresh_interval = st.sidebar.slider("Refresh every (seconds):", 10, 60, 30)
st.sidebar.header("🔍 Filter Options")

# --- API Fetching Functions ---
@st.cache_data(ttl=refresh_interval)
def get_bus_data():
    url = "https://api-v3.mbta.com/vehicles?filter[route_type]=3"
    return requests.get(url).json()

@st.cache_data(ttl=3600)
def get_route_colors():
    url = "https://api-v3.mbta.com/routes?filter[type]=3"
    routes = requests.get(url).json()
    return {
        route["id"]: f'#{route["attributes"]["color"]}' for route in routes["data"]
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

# --- Get Data ---
bus_data = get_bus_data()
route_colors = get_route_colors()

# --- Filters ---
all_routes = sorted({v["relationships"]["route"]["data"]["id"] for v in bus_data["data"]})
all_statuses = sorted({v["attributes"]["current_status"] for v in bus_data["data"]})

selected_routes = st.sidebar.multiselect("Select Routes", all_routes,
