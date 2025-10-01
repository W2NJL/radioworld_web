import pandas as pd
import folium
from folium import plugins
import numpy as np

print("Creating comprehensive HD Radio map with all requested features...")
df = pd.read_csv('fm_db_0815.csv', low_memory=False)

# Expand to include ALL HD stations in US and Canada (not just full-power)
base_df = df[
    (df['country'].isin(['USA', 'CAN']))  # Include Canada
    # Remove the service_code filtering to include ALL station types
].copy()

print(f"Total stations in US/Canada: {len(base_df):,}")

# HD detection
hd_mask = (
    (base_df['mode'] == 'HD') |
    (base_df['HD_Notes'].fillna('').str.contains('suspected', case=False, na=False))
)

hd_stations = base_df[hd_mask].copy()
print(f"Total HD stations (all types): {len(hd_stations):,}")

# Fix coordinates with special handling for Guam
def fix_longitude(row):
    lon = row['lon']
    state = row.get('sp', '')

    if state == 'GU':
        return lon  # Guam stays positive
    else:
        return -lon if lon > 0 else lon

hd_stations['lon_fixed'] = hd_stations.apply(fix_longitude, axis=1)

# Filter for mappable stations
mappable_hd = hd_stations[
    (hd_stations['lat'].notna()) &
    (hd_stations['lon_fixed'].notna()) &
    (hd_stations['lat'] != 0) &
    (hd_stations['lon_fixed'] != 0)
].copy()

print(f"Mappable HD stations: {len(mappable_hd):,}")

# Analyze station classes
class_counts = mappable_hd['class'].value_counts()
print(f"\nStation classes found:")
for cls, count in class_counts.head(10).items():
    print(f"  {cls}: {count:,} stations")

# Analyze service codes
service_counts = mappable_hd['service_code'].value_counts()
print(f"\nService codes found:")
for svc, count in service_counts.head(10).items():
    print(f"  {svc}: {count:,} stations")

# Create Nielsen market tier mapping (simplified)
def get_nielsen_tier(rank):
    if pd.isna(rank):
        return 'Unknown'
    try:
        rank_num = float(rank)
        if rank_num <= 10:
            return 'Top 10'
        elif rank_num <= 25:
            return 'Top 11-25'
        elif rank_num <= 50:
            return 'Top 26-50'
        elif rank_num <= 100:
            return 'Markets 51-100'
        elif rank_num <= 200:
            return 'Markets 101-200'
        else:
            return 'Smaller Markets'
    except:
        return 'Unknown'

mappable_hd['nielsen_tier'] = mappable_hd['rank'].apply(get_nielsen_tier)

# Analyze Nielsen tiers
nielsen_counts = mappable_hd['nielsen_tier'].value_counts()
print(f"\nNielsen market tiers:")
for tier, count in nielsen_counts.items():
    print(f"  {tier}: {count:,} stations")

# Create the comprehensive map with ONLY OpenStreetMap (no alternative tiles initially)
m = folium.Map(
    location=[45.0, -100.0],  # Adjusted to better center US/Canada
    zoom_start=4,
    tiles='OpenStreetMap'
)

# Note: Removed alternative tile layers to ensure OpenStreetMap remains default
# Users can access different themes through other maps if needed

# Create heat map
heat_data = [[row['lat'], row['lon_fixed']] for idx, row in mappable_hd.iterrows()]

plugins.HeatMap(
    heat_data,
    name='HD Radio Heat Map',
    radius=12,
    blur=8,
    max_zoom=1,
    gradient={
        0.1: '#000080',
        0.3: '#0000FF',
        0.5: '#00FFFF',
        0.7: '#00FF00',
        0.9: '#FFFF00',
        1.0: '#FF0000'
    }
).add_to(m)

# Define colors for station classes
class_colors = {
    'A': '#FF0000',      # Red - Full power
    'B': '#FF8C00',      # Dark orange
    'B1': '#FFA500',     # Orange
    'C': '#32CD32',      # Lime green
    'C0': '#228B22',     # Forest green
    'C1': '#00FF00',     # Green
    'C2': '#ADFF2F',     # Green yellow
    'C3': '#9AFF9A',     # Light green
    'D': '#8A2BE2',      # Blue violet - Translators
    'LP100': '#FF69B4',  # Hot pink - LPFM
    'LP10': '#FF1493',   # Deep pink - LPFM
}

# Define colors for Nielsen market tiers
nielsen_colors = {
    'Top 10': '#8B0000',         # Dark red
    'Top 11-25': '#DC143C',      # Crimson
    'Top 26-50': '#FF4500',      # Orange red
    'Markets 51-100': '#FF8C00', # Dark orange
    'Markets 101-200': '#FFA500', # Orange
    'Smaller Markets': '#FFD700', # Gold
    'Unknown': '#D3D3D3'         # Light gray
}

# Create feature groups with marker clustering for each station class
class_groups = {}
major_classes = ['A', 'B', 'B1', 'C', 'C0', 'C1', 'C2', 'C3', 'D', 'LP100', 'LP10']

for cls in major_classes:
    if cls in class_counts.index:
        # Use MarkerCluster for each class to handle co-located stations
        class_groups[cls] = plugins.MarkerCluster(
            name=f'Class {cls} ({class_counts[cls]:,} stations)',
            show=True,  # All visible by default
            options={
                'spiderfyOnMaxZoom': True,
                'showCoverageOnHover': False,
                'zoomToBoundsOnClick': True,
                'maxClusterRadius': 40,  # Stations within 40px will cluster
                'spiderfyDistanceMultiplier': 2,  # Spread markers further apart
                'spiderLegPolylineOptions': {'weight': 1.5, 'color': '#222', 'opacity': 0.5}
            }
        )

# Create feature groups with marker clustering for Nielsen market tiers
nielsen_groups = {}
for tier in nielsen_colors.keys():
    if tier in nielsen_counts.index:
        # Use MarkerCluster for Nielsen tiers as well
        nielsen_groups[tier] = plugins.MarkerCluster(
            name=f'Nielsen: {tier} ({nielsen_counts[tier]:,})',
            show=False,  # Start hidden, can be toggled
            options={
                'spiderfyOnMaxZoom': True,
                'showCoverageOnHover': False,
                'zoomToBoundsOnClick': True,
                'maxClusterRadius': 40,
                'spiderfyDistanceMultiplier': 2,
                'spiderLegPolylineOptions': {'weight': 1.5, 'color': '#222', 'opacity': 0.5}
            }
        )

print("Adding station markers by class and Nielsen tier...")

for idx, station in mappable_hd.iterrows():
    # Clean data
    callsign = str(station.get('callsign', 'Unknown'))
    frequency = station.get('frequency', 'Unknown')
    city = str(station.get('city', 'Unknown'))
    state = str(station.get('sp', 'Unknown'))
    country = str(station.get('country', 'Unknown'))
    format_type = str(station.get('format', 'Unknown'))
    owner = str(station.get('owner', 'Unknown'))[:35]
    erp = station.get('erp', 'Unknown')
    station_class = str(station.get('class', 'Unknown'))
    service_code = str(station.get('service_code', 'Unknown'))
    # Handle Canadian stations that may have nan service codes
    if service_code == 'nan' or service_code == 'Unknown':
        service_code = 'FM' if country == 'CAN' else 'Unknown'
    market = str(station.get('market', 'Unknown'))
    nielsen_rank = station.get('rank', 'Unknown')
    nielsen_tier = station.get('nielsen_tier', 'Unknown')
    lat = station['lat']
    lon = station['lon_fixed']

    # Create detailed popup with conditional Nielsen info
    popup_rows = [
        f"<tr><td><b>Frequency:</b></td><td>{frequency} MHz</td></tr>",
        f"<tr><td><b>Location:</b></td><td>{city}, {state}, {country}</td></tr>",
        f"<tr><td><b>Format:</b></td><td>{format_type}</td></tr>",
        f"<tr><td><b>Owner:</b></td><td>{owner}...</td></tr>",
        f"<tr><td><b>ERP:</b></td><td>{erp} kW</td></tr>",
        f"<tr><td><b>Class:</b></td><td>{station_class}</td></tr>",
        f"<tr><td><b>Service:</b></td><td>{service_code}</td></tr>",
    ]

    # Only add Nielsen info if it exists
    if market != 'nan' and market != 'Unknown' and str(market) != 'nan':
        popup_rows.append(f"<tr><td><b>Market:</b></td><td>{market}</td></tr>")

    if nielsen_rank != 'Unknown' and str(nielsen_rank) != 'nan' and nielsen_rank != 'nan':
        try:
            rank_int = int(float(nielsen_rank))
            popup_rows.append(f"<tr><td><b>Nielsen Rank:</b></td><td>#{rank_int}</td></tr>")
        except:
            popup_rows.append(f"<tr><td><b>Nielsen Rank:</b></td><td>{nielsen_rank}</td></tr>")

    if nielsen_tier != 'Unknown':
        popup_rows.append(f"<tr><td><b>Nielsen Tier:</b></td><td>{nielsen_tier}</td></tr>")

    popup_rows.append(f"<tr><td><b>Coordinates:</b></td><td>{lat:.4f}, {lon:.4f}</td></tr>")

    popup_text = f"""
    <div style="font-family: Arial; width: 280px; max-height: 400px; overflow-y: auto;">
        <h4 style="color: #1f77b4; margin: 0 0 8px 0;">{callsign} - HD Radio</h4>
        <table style="width: 100%; font-size: 12px; border-collapse: collapse;">
            {''.join(popup_rows)}
        </table>
        <hr style="margin: 8px 0;">
        <div style="color: green; font-weight: bold; text-align: center;">
            ✓ HD Radio Enabled
        </div>
    </div>
    """

    tooltip_text = f"{callsign} - {frequency} MHz - {city}, {state} - Class {station_class}"

    # Get colors for class and Nielsen tier
    class_color = class_colors.get(station_class, '#808080')  # Gray default
    nielsen_color = nielsen_colors.get(nielsen_tier, '#D3D3D3')  # Light gray default

    # Marker size based on class (full power = larger)
    if station_class in ['A', 'B', 'B1']:
        radius = 6
    elif station_class in ['C', 'C0', 'C1', 'C2', 'C3']:
        radius = 5
    else:  # D, LP100, LP10
        radius = 3

    # Add to class group
    if station_class in class_groups:
        folium.CircleMarker(
            location=[lat, lon],
            radius=radius,
            popup=folium.Popup(popup_text, max_width=300),
            tooltip=tooltip_text,
            color='white',
            weight=1,
            fillColor=class_color,
            fillOpacity=0.8
        ).add_to(class_groups[station_class])

    # Add to Nielsen group
    if nielsen_tier in nielsen_groups:
        folium.CircleMarker(
            location=[lat, lon],
            radius=radius,
            popup=folium.Popup(popup_text, max_width=300),
            tooltip=f"{callsign} - Nielsen: {nielsen_tier}",
            color='white',
            weight=1,
            fillColor=nielsen_color,
            fillOpacity=0.8
        ).add_to(nielsen_groups[nielsen_tier])

# Add all groups to map
for group in class_groups.values():
    group.add_to(m)

for group in nielsen_groups.values():
    group.add_to(m)

# Add layer control
folium.LayerControl().add_to(m)

# Comprehensive legend
legend_html = f'''
<div style="position: fixed;
            bottom: 20px; left: 20px; width: 350px; height: 300px;
            background-color: white; border: 2px solid #333; z-index: 9999;
            font-size: 12px; padding: 15px; border-radius: 10px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.2); overflow-y: auto;">
<h4 style="margin: 0 0 10px 0; color: #333;">📊 HD Radio Analysis Map</h4>

<div style="margin: 8px 0;">
    <span style="background: linear-gradient(to right, #000080, #0000FF, #00FFFF, #00FF00, #FFFF00, #FF0000);
                 width: 120px; height: 12px; display: inline-block; border-radius: 3px;"></span>
    <br><small>Heat Map: Station Concentration</small>
</div>

<hr style="margin: 8px 0;">
<b>Station Classes:</b><br>
<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 2px; font-size: 11px;">
    <div><span style="color: {class_colors.get('A', '#808080')};">●</span> Class A (Full Power)</div>
    <div><span style="color: {class_colors.get('B', '#808080')};">●</span> Class B</div>
    <div><span style="color: {class_colors.get('C', '#808080')};">●</span> Class C</div>
    <div><span style="color: {class_colors.get('D', '#808080')};">●</span> Class D (Translator)</div>
    <div><span style="color: {class_colors.get('LP100', '#808080')};">●</span> LPFM</div>
    <div><span style="color: {class_colors.get('LP10', '#808080')};">●</span> LP10</div>
</div>

<hr style="margin: 8px 0;">
<b>Nielsen Market Tiers:</b><br>
<div style="font-size: 11px;">
    <div><span style="color: {nielsen_colors['Top 10']};">●</span> Top 10 Markets</div>
    <div><span style="color: {nielsen_colors['Top 11-25']};">●</span> Top 11-25 Markets</div>
    <div><span style="color: {nielsen_colors['Top 26-50']};">●</span> Top 26-50 Markets</div>
    <div><span style="color: {nielsen_colors['Markets 51-100']};">●</span> Markets 51-100</div>
    <div><span style="color: {nielsen_colors['Markets 101-200']};">●</span> Markets 101-200</div>
    <div><span style="color: {nielsen_colors['Smaller Markets']};">●</span> Smaller Markets (200+)</div>
</div>

<hr style="margin: 8px 0;">
<small><b>💡 Features:</b><br>
• All station classes visible by default<br>
• Toggle Nielsen tiers for market analysis<br>
• Includes US + Canada, all station types<br>
• Click any station for detailed info<br>
<br>
<b>Created for Radio World</b><br>
<b>Data:</b> RadioLand Database</small>
</div>
'''

m.get_root().html.add_child(folium.Element(legend_html))

# Save the map
m.save('comprehensive_hd_radio_map.html')

print(f"\n🎯 COMPREHENSIVE HD RADIO MAP CREATED!")
print(f"📂 File: comprehensive_hd_radio_map.html")
print(f"✅ Features implemented:")
print(f"   1. ✅ All station icons visible by default")
print(f"   2. ✅ Includes ALL HD stations in US + Canada (not just full-power)")
print(f"   3. ✅ Toggle by station class (A, B, C, D, LPFM, etc.)")
print(f"   4. ✅ Nielsen market color coding with toggle layers")
print(f"\n📊 Data summary:")
print(f"   • Total mappable HD stations: {len(mappable_hd):,}")
print(f"   • US + Canada coverage")
print(f"   • All station types included")
print(f"   • {len(class_groups)} station class groups")
print(f"   • {len(nielsen_groups)} Nielsen market tier groups")
print(f"\n🎮 How to use:")
print(f"   • All station classes are visible by default")
print(f"   • Use layer control to toggle specific classes or Nielsen tiers")
print(f"   • Click any station for complete details")
print(f"   • Heat map shows overall concentration patterns")