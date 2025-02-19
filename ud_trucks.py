import openai
import pandas as pd
import numpy as np
import dash
from dash import dcc, html, dash_table, Input, Output, State
import plotly.express as px
import plotly.graph_objs as go
import base64
import re
from io import BytesIO
from plotly.subplots import make_subplots
from dash import html, Input, Output, State
from dash_dangerously_set_inner_html import DangerouslySetInnerHTML
import json
import copy

# Initialize the Dash app
app = dash.Dash(__name__)

# Function to detect report type based on the uploaded file
def detect_report_type(contents, filename):
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    
    # Read the sheet names of the Excel file to identify the report type
    xls = pd.ExcelFile(decoded)

    if 'Driving Behavior' in xls.sheet_names:
        return 'Driving Behavior'
    elif 'Fleet Overview' in xls.sheet_names:
        return 'Fleet Overview'
    elif 'Fuel Utilization' in xls.sheet_names:
        return 'Fuel Utilization'
    else:
        return None

# Helper function to merge datasets by Chassis ID
def merge_datasets(df_fo, df_fu):
    # Merge the two datasets on 'Chassis ID'
    merged_df = pd.merge(df_fo, df_fu, on='Chassis ID', how='inner')
    return merged_df

# Function to match dates and fleet name in both reports
def check_report_metadata(fo_contents, fu_contents):
    # Decode the content of both files
    fo_decoded = base64.b64decode(fo_contents.split(',')[1])
    fu_decoded = base64.b64decode(fu_contents.split(',')[1])
    
    # Read both files into DataFrames
    fo_df = pd.read_excel(BytesIO(fo_decoded), sheet_name=0, engine='openpyxl')
    fu_df = pd.read_excel(BytesIO(fu_decoded), sheet_name=0, engine='openpyxl')

    # Extract values from specific cells
    fo_start_time = fo_df.iloc[2, 2]  # C4
    fo_end_time = fo_df.iloc[2, 4]    # E4
    fo_fleet_name = fo_df.iloc[3, 4]  # E5

    fu_start_time = fu_df.iloc[2, 2]  # C4
    fu_end_time = fu_df.iloc[2, 4]    # E4
    fu_fleet_name = fu_df.iloc[3, 4]  # E5

    # Check if the start time, end time, and fleet name match
    if (fo_start_time == fu_start_time) and (fo_end_time == fu_end_time) and (fo_fleet_name == fu_fleet_name):
        return True  # The metadata matches
    else:
        return False  # The metadata doesn't match

# Function to process driving behavior report
def process_driving_behavior(contents, filename):
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    
    # Reading the Driving Behavior sheet into a pandas DataFrame
    df = pd.read_excel(decoded, sheet_name='Driving Behavior', skiprows=8, usecols='B:U', engine='openpyxl')

    df.rename(columns={
        'Unnamed: 1': 'Chassis ID',
        'Unnamed: 2': 'Reg. No.',
        'Unnamed: 3': 'Truck ID',
        'Unnamed: 4': 'Vehicle Specification',
    }, inplace=True)

    df['Vehicle Specification'] = df['Vehicle Specification'].replace(
        "UD, LOW CAB (STRAIGHT), 4*2, RIGID, 12 Ton", "Croner, 4*2, RIGID")

    df['Maximum Speed (km/h)'] = pd.to_numeric(df['Maximum Speed (km/h)'].replace('-', np.nan), errors='coerce')
    df['Maximum Speed (km/h)'].fillna(0, inplace=True)

    df[['Model', 'Axle Configuration', 'Truck Type']] = df['Vehicle Specification'].str.split(r'\s+', n=2, expand=True)
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

    for col in ['Distance (km)', 'Fuel Consumed (L)', 'Average Speed (while driving) (km/h)', 'Brake Count',
                'Stop Count', 'Harsh Brake Count', 'Harsh Acceleration Count', 'Over Speeding Count',
                'Engine Overrev Count', 'Excessive Idling Count', 'Idling Time %', 'Coasting (%)',
                'Top gear (%)', 'Sweetspot (%)']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df['Fuel Efficiency (km/L)'] = df['Distance (km)'] / df['Fuel Consumed (L)']
    df['Brakes per km'] = df['Brake Count'] / df['Distance (km)']
    df[['Engine Hours', 'Engine Minutes']] = df['Engine hours (hh:mm)'].str.split(':', expand=True).astype(float)
    df['Total Engine Hours'] = df['Engine Hours'] + df['Engine Minutes'] / 60
    df['Idling Time (hours)'] = df['Idling Time %'] / 100 * df['Total Engine Hours']
    df['Sweetspot Hours'] = df['Sweetspot (%)'] / 100 * df['Total Engine Hours']

    return df

# Function to process fleet overview report
def process_fleet_overview(contents, filename):
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    
    # Reading the Driving Behavior sheet into a pandas DataFrame
    df = pd.read_excel(decoded, sheet_name='Fleet Overview', skiprows=7, usecols='B:T', engine='openpyxl')

    df['Vehicle Specification'] = df['Vehicle Specification'].replace(
        "UD, LOW CAB (STRAIGHT), 4*2, RIGID, 12 Ton", "Croner, 4*2, RIGID")

    df['Maximum Speed (km/h)'] = pd.to_numeric(df['Maximum Speed (km/h)'].replace('-', np.nan), errors='coerce')
    df['Maximum Speed (km/h)'].fillna(0, inplace=True)

    df[['Model', 'Axle Configuration', 'Truck Type']] = df['Vehicle Specification'].str.split(r'\s+', n=2, expand=True)
    # Remove any trailing commas in 'Model', 'Axle Configuration', and 'Truck Type'
    df['Model'] = df['Model'].str.rstrip(',')
    df['Axle Configuration'] = df['Axle Configuration'].str.rstrip(',')
    df['Truck Type'] = df['Truck Type'].str.rstrip(',')

    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

    # Remove the first record (row) from the DataFrame
    df = df.iloc[1:]

    for col in ['Maximum Speed (km/h)', 'Distance (km)', 'Fuel Consumed (L)', 'Fuel consumed during overspeed (L)', 
                'Engine overrev (L)', 'Excessive Idling (L)', 'Harsh Brakings', 'Harsh Accelerations', 'Over Speeding',
                'Over Revving', 'Excessive Idling']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df['Fuel Efficiency (km/L)'] = df['Distance (km)'] / df['Fuel Consumed (L)']
    df[['Engine Hours', 'Engine Minutes']] = df['Engine hours (hh:mm)'].str.split(':', expand=True).astype(float)
    df['Total Engine Hours'] = df['Engine Hours'] + df['Engine Minutes'] / 60

    # Calculate wasted engine hours
    df[['Overspeed Hours', 'Overspeed Minutes']] = df['Overspeed (hh:mm)'].str.split(':', expand=True).astype(float)
    df['Total Overspeed Hours'] = df['Overspeed Hours'] + df['Overspeed Minutes'] / 60

    df[['Excessive Idling Hours', 'Excessive Idling Minutes']] = df['Excessive idling (hh:mm)'].str.split(':', expand=True).astype(float)
    df['Total Excessive Idling Hours'] = df['Excessive Idling Hours'] + df['Excessive Idling Minutes'] / 60

    df[['Engine Overrev Hours', 'Engine Overrev Minutes']] = df['Engine overrev (hh:mm)'].str.split(':', expand=True).astype(float)
    df['Total Engine Overrev Hours'] = df['Engine Overrev Hours'] + df['Engine Overrev Minutes'] / 60

    return df

def process_fuel_utilization(contents, filename):
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    
    # Reading the Fuel Utilization sheet into a pandas DataFrame
    df = pd.read_excel(decoded, sheet_name='Fuel Utilization', skiprows=8, usecols='B:AO', engine='openpyxl')

    df.rename(columns={
        'Unnamed: 1': 'Chassis ID',
        'Unnamed: 2': 'Reg. No.',
        'Unnamed: 3': 'Truck ID',
        'Unnamed: 4': 'Vehicle Specification',
    }, inplace=True)

    df['Vehicle Specification'] = df['Vehicle Specification'].replace(
        "UD, LOW CAB (STRAIGHT), 4*2, RIGID, 12 Ton", "Croner, 4*2, RIGID")

    df[['Model', 'Axle Configuration', 'Truck Type']] = df['Vehicle Specification'].str.split(r'\s+', n=2, expand=True)
    # Remove any trailing commas in 'Model', 'Axle Configuration', and 'Truck Type'
    df['Model'] = df['Model'].str.rstrip(',')
    df['Axle Configuration'] = df['Axle Configuration'].str.rstrip(',')
    df['Truck Type'] = df['Truck Type'].str.rstrip(',')
    
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

    df.replace('-', 0, inplace=True)

    for col in ['Distance (km)', 'Fuel Consumed (L)', 'Adblue Consumed (L)', 'PTO (L)', 'Idling (L)', 'Cruise Control (L)', 'Sweetspot (L)',
                'Top gear (L)', 'Driving (L)', 'Total Fuel Efficiency (km/L)', 'Total Fuel Efficiency (L/h)']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df[['Engine Hours', 'Engine Minutes']] = df['Total Engine Hours (hh:mm)'].str.split(':', expand=True).astype(float)
    df['Total Engine Hours'] = df['Engine Hours'] + df['Engine Minutes'] / 60

    df[['Driving Hours', 'Driving Minutes']] = df['Driving Time (hh:mm)'].str.split(':', expand=True).astype(float)
    df['Total Driving Hours'] = df['Driving Hours'] + df['Driving Minutes'] / 60

    df[['PTO Hours', 'PTO Minutes']] = df['PTO Time (hh:mm)'].str.split(':', expand=True).astype(float)
    df['Total PTO Hours'] = df['PTO Hours'] + df['PTO Minutes'] / 60

    df[['Idling Hours', 'Idling Minutes']] = df['Idling Time (hh:mm)'].str.split(':', expand=True).astype(float)
    df['Total Idling Hours'] = df['Idling Hours'] + df['Idling Minutes'] / 60

    df[['Cruise Control Hours', 'Cruise Control Minutes']] = df['Cruise Control Time (hh:mm)'].str.split(':', expand=True).astype(float)
    df['Total Cruise Control Hours'] = df['Cruise Control Hours'] + df['Cruise Control Minutes'] / 60

    df[['Sweetspot Hours', 'Sweetspot Minutes']] = df['Sweetspot Time (hh:mm)'].str.split(':', expand=True).astype(float)
    df['Total Sweetspot Hours'] = df['Sweetspot Hours'] + df['Sweetspot Minutes'] / 60

    df[['Top Gear Hours', 'Top Gear Minutes']] = df['Top Gear Time (hh:mm)'].str.split(':', expand=True).astype(float)
    df['Total Top Gear Hours'] = df['Top Gear Hours'] + df['Top Gear Minutes'] / 60

    df[['Coasting Hours', 'Coasting Minutes']] = df['Coasting Time (hh:mm)'].str.split(':', expand=True).astype(float)
    df['Total Coasting Hours'] = df['Coasting Hours'] + df['Coasting Minutes'] / 60

    df['Fuel Efficiency (km/L)'] = df['Distance (km)'] / df['Fuel Consumed (L)']
    df['Idling Time (hours)'] = df['Idling (L)'] / df['Fuel Efficiency (km/L)'] 
    
    return df

# Function to process the combined datasets of Fleet Overview and Fuel Utilization
def process_combined_dataset(df_fo, df_fu):
    # Remove the specified fields from the Fleet Overview DataFrame
    df_fo_cleaned = df_fo.drop(columns=['Reg. No.', 'Truck ID', 'Vehicle Specification', 'Distance (km)', 'Fuel Consumed (L)', 'Fuel Efficiency (km/L)', 'Total Engine Hours', 'Model', 'Axle Configuration', 'Truck Type'])
    
    # Merge Fleet Overview (FO) and Fuel Utilization (FU) DataFrames on 'Chassis ID'
    df_combined = merge_datasets(df_fu, df_fo_cleaned)
    
    return df_combined

# Function to generate visualizations
def generate_visuals(df, report_type):
    if report_type == 'Driving Behavior':
        # Box plot for Fuel Efficiency by truck type, model, and axle configuration
        fig_box = px.box(df, x='Model', y='Fuel Efficiency (km/L)', color='Truck Type',
                         labels={'Fuel Efficiency (km/L)': 'Fuel Efficiency (km/L)'}, title="Fuel Efficiency by Truck Model and Type")

        # Scatter plot for Idling Time vs Fuel Efficiency
        fig_scatter = px.scatter(df, x='Idling Time (hours)', y='Fuel Efficiency (km/L)', color='Truck Type',
                                 labels={'Fuel Efficiency (km/L)': 'Fuel Efficiency (km/L)', 'Idling Time (hours)': 'Idling Time (hours)'},
                                 title="Idling Time vs Fuel Efficiency")

        # Pie charts for Good and Inefficient Driving Behavior
        good_behavior = {
            'Top Gear (%)': df['Top gear (%)'].mean(),
            'Sweetspot (%)': df['Sweetspot (%)'].mean(),
            'Coasting (%)': df['Coasting (%)'].mean()
        }
        bad_behavior = {
            'Excessive Idling Count': df['Excessive Idling Count'].mean(),
            'Harsh Acceleration Count': df['Harsh Acceleration Count'].mean(),
            'Harsh Brake Count': df['Harsh Brake Count'].mean(),
            'Engine Overrev Count': df['Engine Overrev Count'].mean()
        }

        # Pie charts
        fig_good_behavior = go.Figure(data=[go.Pie(labels=list(good_behavior.keys()), values=list(good_behavior.values()), hole=.3)])
        fig_good_behavior.update_layout(title_text="Good Driving Behavior Breakdown", height=400)

        fig_bad_behavior = go.Figure(data=[go.Pie(labels=list(bad_behavior.keys()), values=list(bad_behavior.values()), hole=.3)])
        fig_bad_behavior.update_layout(title_text="Inefficient Driving Behavior Breakdown", height=400)

        # Stacked Bar for Idling Time vs Engine Hours
        fig5 = go.Figure()
        fig5.add_trace(go.Bar(x=df['Chassis ID'], y=df['Idling Time (hours)'], name='Idling Time', marker_color='indianred'))
        fig5.add_trace(go.Bar(x=df['Chassis ID'], y=df['Total Engine Hours'] - df['Idling Time (hours)'],
                              name='Engine Hours (Non-Idling)', marker_color='lightsalmon'))
        fig5.update_layout(barmode='stack', title='Idling Time vs Engine Hours', xaxis_title='Idling vs Engine Hours', yaxis_title='Hours')

        return [fig_box, fig_scatter, fig_good_behavior, fig_bad_behavior, fig5]
    
    if report_type == 'Fleet Overview':
        # COMBINED GRAPHS FOR THE STATS
        # Prepare Distance Traveled data
        sorted_distance_data = df.sort_values(by='Distance (km)', ascending=False)
        chassis_ids_sorted = sorted_distance_data['Chassis ID']
        total_distance_traveled_sorted = sorted_distance_data['Distance (km)']

        # Prepare Engine Hours data
        df_sorted_e = df.sort_values(by='Total Engine Hours', ascending=False)
        chassis_ids_engine = df_sorted_e['Chassis ID']
        total_engine_hours = df_sorted_e['Total Engine Hours']

        # Prepare data for Fuel Consumed
        sorted_fuel = df.sort_values(by='Fuel Consumed (L)', ascending=False)
        chassis_ids_fuel = sorted_fuel['Chassis ID']
        total_fuel_consumed = sorted_fuel['Fuel Consumed (L)']

        # Create the Distance Traveled bar chart
        fig_distance_traveled = go.Bar(
            x=chassis_ids_sorted,
            y=total_distance_traveled_sorted,
            marker=dict(color=total_distance_traveled_sorted, colorscale='Viridis'),
            text=[f"{val:.0f}" for val in total_distance_traveled_sorted],
            textposition='outside',
            name='Distance Traveled'
        )

        # Create the Engine Hours bar chart
        fig_engine_hours = go.Bar(
            x=chassis_ids_engine,
            y=total_engine_hours,
            marker=dict(color=total_engine_hours, colorscale=[[0, 'goldenrod'], [0.5, 'gold'], [1, 'khaki']]),
            text=[f"{val:.0f}" for val in total_engine_hours],
            textposition='outside',
            name='Total Engine Hours'
        )

        # Create the Fuel Consumed bar chart
        fig_fuel_consumed = go.Bar(
            x=chassis_ids_fuel,
            y=total_fuel_consumed,
            marker=dict(color=total_fuel_consumed, colorscale=[[0, 'darkred'], [0.5, 'red'], [1, 'lightsalmon']]),
            text=[f"{val:.0f}" for val in total_fuel_consumed],
            textposition='outside',
            name='Fuel Consumed (L)'
        )

        # Set up the figure and add traces
        fig_histogram = make_subplots()
        fig_histogram.add_trace(fig_distance_traveled)
        fig_histogram.add_trace(fig_engine_hours)
        fig_histogram.add_trace(fig_fuel_consumed)

        # Initially hide the Engine Hours chart
        fig_histogram['data'][1].visible = False
        fig_histogram['data'][2].visible = False

        # Dynamically set y-axis range based on maximum values in the dataset
        max_distance = total_distance_traveled_sorted.max()
        max_engine_hours = total_engine_hours.max()
        max_fuel_consumed = total_fuel_consumed.max()

        # Configure layout and updatemenu buttons for toggling
        fig_histogram.update_layout(
            title=dict(
                text="Fleet Utilization (KM / Hours / Fuel)",
                x=0.28,  # Center the title
                y=0.95,  # Keep the title at the top
                xanchor="center",
                yanchor="top",
                font=dict(size=16)
            ),
            xaxis_title="Chassis ID",
            yaxis_title="Value",
            template='simple_white',
            xaxis=dict(
                rangeslider=dict(visible=True,thickness=0.02,borderwidth=3,bordercolor="gray"),  # Add a range slider for scrolling
                tickangle=-45,  # Tilt the x-axis labels for better visibility
                automargin=True,  # Ensure margins adjust dynamically
            ),
            updatemenus=[
                dict(
                    type="buttons",
                    direction="left",
                    buttons=[
                        dict(label="Distance Traveled",
                            method="update",
                            args=[{"visible": [True, False, False]},
                                {"yaxis": {"title": "Total Distance Traveled (km)", "range": [0, max_distance * 1.3]}}]),
                        dict(label="Engine Hours",
                            method="update",
                            args=[{"visible": [False, True, False]},
                                {"yaxis": {"title": "Total Engine Hours", "range": [0, max_engine_hours * 1.3]}}]),
                        dict(label="Fuel Consumed",
                            method="update",
                            args=[{"visible": [False, False, True]},
                                {"yaxis": {"title": "Fuel Consumed (L)", "range": [0, max_fuel_consumed * 1.3]}}])
                    ],
                    showactive=True,
                    x=0.5,
                    y=1.2,
                    xanchor="center",
                    yanchor="bottom"
                )
            ],
            margin=dict(t=120)
        )

        # Group by Truck Model, Axle Configuration, and Truck Type to count occurrences
        count_df = df.groupby(['Model', 'Truck Type', 'Axle Configuration']).size().reset_index(name='Count')

        fig_sunburst = px.sunburst(
            count_df, 
            path=['Model', 'Truck Type', 'Axle Configuration'], 
            values='Count',  # Assuming there's a column for count, else use 'count' method on grouped data
            title="Truck Models",
            color='Model',  # Color based on Model
            color_discrete_map={'Quester': 'darkblue', 'Croner': 'yellow'}
        )
        fig_sunburst.update_traces(
            textinfo="label+value",  # Display both label and value (count) on the slices
            insidetextorientation='auto'  # Automatically adjust text orientation for readability
        )

        # a. Total Number of Vehicles
        total_vehicles = df['Chassis ID'].nunique()
        fig_total_vehicles = go.Figure(go.Indicator(
            mode="number",
            value=total_vehicles,
            title={"text": "Total Number of Vehicles"},
            number={"font": {"size": 50, "color": "darkblue"}},
            domain={'x': [0, 1], 'y': [0, 1]}
        ))

        # Average maximum speed
        avg_speed = df['Distance (km)'].mean()/df['Total Engine Hours'].mean()
        # Create the visual for average maximum speed
        fig_avg_speed = go.Figure(go.Indicator(
            mode="number",
            value=avg_speed,
            title={"text": "Average Speed (km/h)"},
            number={"font": {"size": 50, "color": "green"}},
            domain={'x': [0, 1], 'y': [0, 1]}
        ))

        # Total engine hours
        total_engine_hours = df['Total Engine Hours'].sum()
        # Create the visual for total engine hours
        fig_total_engine_hours = go.Figure(go.Indicator(
            mode="number",
            value=total_engine_hours,
            title={"text": "Total Engine Hours"},
            number={"font": {"size": 50, "color": "orange"}},
            domain={'x': [0, 1], 'y': [0, 1]}
        ))

        # Total distance travelled
        total_distance = df['Distance (km)'].sum()
        # Create the visual for total distance travelled
        fig_total_distance = go.Figure(go.Indicator(
            mode="number",
            value=total_distance,
            title={"text": "Total Distance (km)"},
            number={"font": {"size": 50, "color": "purple"}},
            domain={'x': [0, 1], 'y': [0, 1]}
        ))

        # Total fuel consumed
        total_fuel_consumed = df['Fuel Consumed (L)'].sum()
        # Create the visual for total fuel consumed
        fig_total_fuel_consumed = go.Figure(go.Indicator(
            mode="number",
            value=total_fuel_consumed,
            title={"text": "Total Fuel Consumed (L)"},
            number={"font": {"size": 50, "color": "red"}},
            domain={'x': [0, 1], 'y': [0, 1]}
        ))
        # Add calculation for potential fuel saving
        total_fuel_wasted = df['Fuel consumed during overspeed (L)'].sum() + df['Engine overrev (L)'].sum() + df['Excessive Idling (L)'].sum()
        # Create a text indicator for the potential fuel saving
        fig_fuel_saving = go.Figure(go.Indicator(
            mode="number",
            value=total_fuel_wasted,
            title={"text": "Potential Fuel Saving (L)"},
            number={"font": {"size": 50, "color": "gray"}},  # Styling the number
            domain={'x': [0, 1], 'y': [0, 1]}
        ))

        # b. Pie charts 
        # For wasted engine hours
        # Calculate total engine hours and remaining engine hours
        total_engine_hours = df['Total Engine Hours'].sum()
        total_wasted_hours = df[['Total Overspeed Hours', 'Total Excessive Idling Hours', 'Total Engine Overrev Hours']].sum()
        remaining_engine_hours = total_engine_hours - total_wasted_hours.sum()
        fig_wasted_hours = px.pie(values=[total_wasted_hours[0], total_wasted_hours[1], total_wasted_hours[2], remaining_engine_hours], 
                                names=['Overspeed', 'Excessive Idling', 'Engine Overrev', 'Remaining Engine Hours'], 
                                title="Engine Hours for Inefficient Driving Behaviour - Summary <br><sub>Note: Remaining Engine Hours = Hours utilised for Driving + Idling + PTO</sub>",
                                color=['Overspeed', 'Excessive Idling', 'Engine Overrev', 'Remaining Engine Hours'],
                                color_discrete_map={ 'Overspeed': 'darkred', 'Excessive Idling': 'red', 'Engine Overrev': 'lightsalmon', 'Remaining Engine Hours': 'lightgreen'})
        
        # Adjust the layout to add spacing after the title
        fig_wasted_hours.update_layout(
            title=dict(
                y=0.9,  # Position the title slightly higher
                x=0.1,
                font=dict(size=16)
            ),
            margin=dict(t=105)  # Add more space at the top to avoid crowding the title area
        )

        # Add annotation for total engine hours
        fig_wasted_hours.add_annotation(
            text=f"Total Engine Hours: {total_engine_hours:.2f} Hours",
            x=0.5, y=-0.2,
            showarrow=False,
            font=dict(size=12)
        )

        # For wasted fuel
        # Calculate total fuel consumed and remaining fuel
        total_fuel_consumed = df['Fuel Consumed (L)'].sum()
        total_fuel_wasted = df[['Fuel consumed during overspeed (L)', 'Excessive Idling (L)', 'Engine overrev (L)']].sum()
        remaining_fuel_consumed = total_fuel_consumed - total_fuel_wasted.sum()
        fig_fuel_wasted = px.pie( values=[total_fuel_wasted[0], total_fuel_wasted[1], total_fuel_wasted[2], remaining_fuel_consumed],
                            names=['Overspeed', 'Excessive Idling', 'Engine Overrev', 'Remaining Fuel Consumed'], 
                            title="Fuel Utilised for Inefficient Driving Behaviour - Summary <br><sub>Note: Remaining Fuel Consumed = Fuel utilised for Driving + Idling + PTO</sub>",
                            color=['Overspeed', 'Excessive Idling', 'Engine Overrev', 'Remaining Fuel Consumed'],
                            color_discrete_map={ 'Overspeed': 'darkred', 'Excessive Idling': 'red', 'Engine Overrev': 'lightsalmon', 'Remaining Fuel Consumed': 'lightgreen'})

        # Adjust the layout to add spacing after the title
        fig_fuel_wasted.update_layout(
            title=dict(
                y=0.9,  # Position the title slightly higher
                x=0.1,
                font=dict(size=16)
            ),
            margin=dict(t=120)  # Add more space at the top to avoid crowding the title area
        )

        # Add annotation for total fuel consumed
        fig_fuel_wasted.add_annotation(
            text=f"Total Fuel Consumed: {total_fuel_consumed:.2f} L",
            x=0.5, y=-0.2,
            showarrow=False,
            font=dict(size=12)
        )

        # d. Scatter plot for correlation
        # fig_fuel_efficiency_vs_idling = px.scatter(df, 
        #                                         x='Total Excessive Idling Hours', 
        #                                         y='Fuel Efficiency (km/L)', 
        #                                         title="Correlation between Fuel Efficiency and Excessive Idling",
        #                                         labels={'x': 'Excessive Idling Hours', 'y': 'Fuel Efficiency (km/L)'})

        # e. Stacked bar chart for fuel consumption by Inefficient Driving behaviors
        # Calculate the percentage of fuel used by Inefficient Driving behaviors
        df['Inefficient Driving Behavior %'] = ((df['Fuel consumed during overspeed (L)'] + 
                                        df['Engine overrev (L)'] + 
                                        df['Excessive Idling (L)']) / df['Fuel Consumed (L)']) * 100

        # Sort the dataframe by the percentage in descending order
        df_sorted_f = df.copy()
        df_sorted_f = df_sorted_f.sort_values(by=['Total Engine Hours', 'Inefficient Driving Behavior %'], ascending=[False, False])

        # Calculate the percentage of fuel used by each behavior relative to total fuel for each vehicle
        df_sorted_f['Fuel Overspeed %'] = (df_sorted_f['Fuel consumed during overspeed (L)'] / df_sorted_f['Fuel Consumed (L)']) * 100
        df_sorted_f['Fuel Engine Overrev %'] = (df_sorted_f['Engine overrev (L)'] / df_sorted_f['Fuel Consumed (L)']) * 100
        df_sorted_f['Fuel Excessive Idling %'] = (df_sorted_f['Excessive Idling (L)'] / df_sorted_f['Fuel Consumed (L)']) * 100
        df_sorted_f['Remaining Fuel %'] = 100 - (df_sorted_f['Fuel Overspeed %'] + df_sorted_f['Fuel Engine Overrev %'] + df_sorted_f['Fuel Excessive Idling %'])

        # Prepare the sorted data
        chassis_ids_sorted_f = df_sorted_f['Chassis ID']
        fuel_overspeed_sorted_f = df_sorted_f['Fuel Overspeed %']
        fuel_engine_overrev_sorted_f = df_sorted_f['Fuel Engine Overrev %']
        fuel_excessive_idling_sorted_f = df_sorted_f['Fuel Excessive Idling %']
        remaining_fuel_sorted_f = df_sorted_f['Remaining Fuel %']

        # Create the 100% stacked bar chart
        fig_fuel_consumption = go.Figure()
        fig_fuel_consumption.add_trace(go.Bar(x=chassis_ids_sorted_f, y=fuel_overspeed_sorted_f, name='Fuel used by Overspeed', marker_color='darkred'))
        fig_fuel_consumption.add_trace(go.Bar(x=chassis_ids_sorted_f, y=fuel_engine_overrev_sorted_f, name='Fuel used by Engine Overrev', marker_color='lightsalmon'))
        fig_fuel_consumption.add_trace(go.Bar(x=chassis_ids_sorted_f, y=fuel_excessive_idling_sorted_f, name='Fuel used by Excessive Idling', marker_color='red'))
        fig_fuel_consumption.add_trace(go.Bar(x=chassis_ids_sorted_f, y=remaining_fuel_sorted_f, name='Remaining Fuel Consumed', marker_color='lightgreen'))

        # Update layout
        fig_fuel_consumption.update_layout(
            barmode='stack',
            title="Fuel Utilised for Inefficient Driving Behavior - Per unit <br><sub>Note: 100% Stacked graph with Total % Fuel Consumed in Inefficient Driving labelled at the top</sub>",
            xaxis=dict(
                rangeslider=dict(visible=True,thickness=0.02,borderwidth=3,bordercolor="gray"),  # Add a range slider for scrolling
                tickangle=-45,  # Tilt the x-axis labels for better visibility
                automargin=True,  # Dynamically adjust margins
            ),
            xaxis_title="Chassis ID",
            yaxis_title="Percentage of Fuel Consumed (%)",
            legend_title=None,
            legend=dict(orientation="h", yanchor="top", y=-0.8, xanchor="center", x=0.5),
            height=600
        )

        # Add annotations for total engine hours at the top of each bar
        for i, chassis_id in enumerate(chassis_ids_sorted_f):
            fig_fuel_consumption.add_annotation(
                x=chassis_id,
                y=100,  # Place annotation at the top of the 100% stacked bar
                text=f"{df_sorted_f['Inefficient Driving Behavior %'].iloc[i]:.0f}%",
                showarrow=False,
                font=dict(size=13),
                yshift=20,  # Add a slight offset for better readability
                textangle=90
            )

        # f. Stacked bar chart for engine hours by Inefficient Driving behaviors
        # Calculate the percentage of engine hours used by Inefficient Driving behaviors
        df['Inefficient Driving Behavior Hours %'] = ((df['Total Overspeed Hours'] + 
                                            df['Total Engine Overrev Hours'] + 
                                            df['Total Excessive Idling Hours']) / df['Total Engine Hours']) * 100

        # Sort the dataframe by the percentage in descending order
        df_sorted_h = df.copy()
        df_sorted_h = df_sorted_h.sort_values(by=['Total Engine Hours', 'Inefficient Driving Behavior Hours %'], ascending=[False, False])

        # Calculate the percentage of engine hours used by each behavior relative to total engine hours for each vehicle
        df_sorted_h['Overspeed Hours %'] = (df_sorted_h['Total Overspeed Hours'] / df_sorted_h['Total Engine Hours']) * 100
        df_sorted_h['Engine Overrev Hours %'] = (df_sorted_h['Total Engine Overrev Hours'] / df_sorted_h['Total Engine Hours']) * 100
        df_sorted_h['Excessive Idling Hours %'] = (df_sorted_h['Total Excessive Idling Hours'] / df_sorted_h['Total Engine Hours']) * 100
        df_sorted_h['Remaining Engine Hours %'] = 100 - (df_sorted_h['Overspeed Hours %'] + df_sorted_h['Engine Overrev Hours %'] + df_sorted_h['Excessive Idling Hours %'])

        # Prepare the sorted data
        chassis_ids_sorted_h = df_sorted_h['Chassis ID']
        overspeed_hours_sorted = df_sorted_h['Overspeed Hours %']
        engine_overrev_hours_sorted = df_sorted_h['Engine Overrev Hours %']
        excessive_idling_hours_sorted = df_sorted_h['Excessive Idling Hours %']
        remaining_engine_hours_sorted = df_sorted_h['Remaining Engine Hours %']

        # Create the 100% stacked bar chart
        fig_engine_hours_consumption = go.Figure()
        fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids_sorted_h, y=overspeed_hours_sorted, name='Overspeed Hours', marker_color='darkred'))
        fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids_sorted_h, y=engine_overrev_hours_sorted, name='Engine Overrev Hours', marker_color='lightsalmon'))
        fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids_sorted_h, y=excessive_idling_hours_sorted, name='Excessive Idling Hours', marker_color='red'))
        fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids_sorted_h, y=remaining_engine_hours_sorted, name='Remaining Engine Hours', marker_color='lightgreen'))

        # Update layout
        fig_engine_hours_consumption.update_layout(
            barmode='stack',
            title="Engine Hours for Inefficient Driving Behavior - Per unit <br><sub>Note: 100% Stacked graph with Total % Engine Hours used in Inefficient Driving labelled at the top</sub>",
            xaxis=dict(
                rangeslider=dict(visible=True,thickness=0.02,borderwidth=3,bordercolor="gray"),  # Add a range slider for scrolling
                tickangle=-45,  # Tilt the x-axis labels for better visibility
                automargin=True,  # Dynamically adjust margins
            ),
            xaxis_title="Chassis ID",
            yaxis_title="Percentage of Engine Hours (%)",
            legend_title=None,
            legend=dict(orientation="h", yanchor="top", y=-0.8, xanchor="center", x=0.5),
            height=600
        )

        # Add annotations for total engine hours at the top of each bar
        for i, chassis_id in enumerate(chassis_ids_sorted_h):
            fig_engine_hours_consumption.add_annotation(
                x=chassis_id,
                y=100,  # Place annotation at the top of the 100% stacked bar
                text=f"{df_sorted_h['Inefficient Driving Behavior Hours %'].iloc[i]:.0f}%",
                showarrow=False,
                font=dict(size=13),
                yshift=20,  # Add a slight offset for better readability
                textangle=90
            )

        # g. Stacked bar chart of Inefficient Driving Counts
        # Calculate the total Inefficient Driving behaviors for each vehicle
        df['Total Inefficient Driving Behaviors'] = df['Harsh Accelerations'] + df['Over Speeding'] + df['Over Revving'] + df['Excessive Idling']

        # Calculate Inefficient Driving behavior rate per kilometer
        df['Bad Behavior Rate per 100 km (%)'] = (df['Total Inefficient Driving Behaviors'] / df['Distance (km)']) * 100
        df['Harsh Acceleration per 100 km'] = (df['Harsh Accelerations'] / df['Distance (km)']) * 100
        df['Over Speeding per 100 km'] = (df['Over Speeding'] / df['Distance (km)']) * 100
        df['Over Revving per 100 km'] = (df['Over Revving'] / df['Distance (km)']) * 100
        df['Excessive Idling per 100 km'] = (df['Excessive Idling'] / df['Distance (km)']) * 100

        # Sort the dataframe by the bad behavior rate per km in descending order
        df_sorted_c = df.copy()
        df_sorted_c = df_sorted_c.sort_values(by=['Total Engine Hours', 'Bad Behavior Rate per 100 km (%)'], ascending=[False, False])

        # Create the stacked bar chart
        fig_bad_behavior_counts = px.bar(
            df_sorted_c,
            x='Chassis ID',
            y=['Harsh Acceleration per 100 km', 'Over Speeding per 100 km', 'Over Revving per 100 km', 'Excessive Idling per 100 km'],
            title="Inefficient Driving Behavior - Event Counts per 100 km<br><sub>Note: Worst to Best based on count</sub>",
            labels={'x': 'Chassis ID', 'value': 'Count'},
            barmode='stack',
            color_discrete_sequence=['#FFA07A', '#FF8C00', '#FF4500', '#8B0000']
        )

        # Get the number of vehicles
        num_vehicles = len(df_sorted_c['Chassis ID'])
        # Determine the width dynamically based on the number of vehicles
        if num_vehicles < 8:
            bar_width = 0.4  # Smaller width for fewer vehicles
        else:
            bar_width = None  # Default width for larger datasets

        # Update traces with the determined bar width
        fig_bad_behavior_counts.update_traces(width=bar_width)

        # Update layout for better visualization
        fig_bad_behavior_counts.update_layout(
            xaxis=dict(
                rangeslider=dict(visible=True,thickness=0.02,borderwidth=3,bordercolor="gray"),  # Add a range slider for scrolling
                tickangle=-45,  # Tilt the x-axis labels for better visibility
                automargin=True,  # Dynamically adjust margins
            ),
            xaxis_title="Chassis ID",
            yaxis_title="Behavior Count",
            legend_title=None,
            legend=dict(orientation="h", yanchor="top", y=-0.8, xanchor="center", x=0.5),
            height=600
        )

        return [fig_total_fuel_consumed, fig_total_engine_hours, fig_total_vehicles, fig_avg_speed, fig_total_distance, fig_histogram, fig_sunburst, fig_wasted_hours, fig_fuel_wasted, fig_fuel_consumption, fig_engine_hours_consumption, fig_bad_behavior_counts, fig_fuel_saving]
    
    if report_type == 'Fuel Utilization':
        # a. Total Number of Vehicles
        total_vehicles = df['Chassis ID'].nunique()
        fig_total_vehicles = go.Figure(go.Indicator(
            mode="number",
            value=total_vehicles,
            title={"text": "Total Number of Vehicles"},
            number={"font": {"size": 50, "color": "darkblue"}},
            domain={'x': [0, 1], 'y': [0, 1]}
        ))
        # Average speed
        avg_speed = df['Distance (km)'].mean()/df['Total Engine Hours'].mean()
        # Create the visual for average speed
        fig_avg_speed = go.Figure(go.Indicator(
            mode="number",
            value=avg_speed,
            title={"text": "Average Speed (km/h)"},
            number={"font": {"size": 50, "color": "green"}},
            domain={'x': [0, 1], 'y': [0, 1]}
        ))
        # Total engine hours
        total_engine_hours = df['Total Engine Hours'].sum()
        # Create the visual for total engine hours
        fig_total_engine_hours = go.Figure(go.Indicator(
            mode="number",
            value=total_engine_hours,
            title={"text": "Total Engine Hours"},
            number={"font": {"size": 50, "color": "orange"}},
            domain={'x': [0, 1], 'y': [0, 1]}
        ))
        # Total distance travelled
        total_distance = df['Distance (km)'].sum()
        # Create the visual for total distance travelled
        fig_total_distance = go.Figure(go.Indicator(
            mode="number",
            value=total_distance,
            title={"text": "Total Distance (km)"},
            number={"font": {"size": 50, "color": "purple"}},
            domain={'x': [0, 1], 'y': [0, 1]}
        ))
        # Total fuel consumed
        total_fuel_consumed = df['Fuel Consumed (L)'].sum()
        # Create the visual for total fuel consumed
        fig_total_fuel_consumed = go.Figure(go.Indicator(
            mode="number",
            value=total_fuel_consumed,
            title={"text": "Total Fuel Consumed (L)"},
            number={"font": {"size": 50, "color": "red"}},
            domain={'x': [0, 1], 'y': [0, 1]}
        ))

        # Group by Truck Model, Axle Configuration, and Truck Type to count occurrences
        count_df = df.groupby(['Model', 'Truck Type', 'Axle Configuration']).size().reset_index(name='Count')

        fig_sunburst = px.sunburst(
            count_df, 
            path=['Model', 'Truck Type', 'Axle Configuration'], 
            values='Count',  # Assuming there's a column for count, else use 'count' method on grouped data
            title="Truck Models",
            color='Model',  # Color based on Model
            color_discrete_map={'Quester': 'darkblue', 'Croner': 'yellow'}
        )
        fig_sunburst.update_traces(
            textinfo="label+value",  # Display both label and value (count) on the slices
            insidetextorientation='auto'  # Automatically adjust text orientation for readability
        )

        # COMBINED GRAPHS FOR THE STATS
        # Prepare Distance Traveled data
        sorted_distance_data = df.copy()
        sorted_distance_data = sorted_distance_data.sort_values(by='Distance (km)', ascending=False)
        chassis_ids_sorted = sorted_distance_data['Chassis ID']
        total_distance_traveled_sorted = sorted_distance_data['Distance (km)']

        # Prepare Engine Hours data
        df_sorted_e= df.copy()
        df_sorted_e = df_sorted_e.sort_values(by='Total Engine Hours', ascending=False)
        chassis_ids_engine = df_sorted_e['Chassis ID']
        total_engine_hours = df_sorted_e['Total Engine Hours']

        # Prepare data for Fuel Consumed
        sorted_fuel = df.copy()
        sorted_fuel = sorted_fuel.sort_values(by='Fuel Consumed (L)', ascending=False)
        chassis_ids_fuel = sorted_fuel['Chassis ID']
        total_fuel_consumed = sorted_fuel['Fuel Consumed (L)']

        # Create the Distance Traveled bar chart
        fig_distance_traveled = go.Bar(
            x=chassis_ids_sorted,
            y=total_distance_traveled_sorted,
            marker=dict(color=total_distance_traveled_sorted, colorscale='Viridis'),
            text=[f"{val:.0f}" for val in total_distance_traveled_sorted],
            textposition='outside',
            name='Distance Traveled'
        )

        # Create the Engine Hours bar chart
        fig_engine_hours = go.Bar(
            x=chassis_ids_engine,
            y=total_engine_hours,
            marker=dict(color=total_engine_hours, colorscale=[[0, 'goldenrod'], [0.5, 'gold'], [1, 'khaki']]),
            text=[f"{val:.0f}" for val in total_engine_hours],
            textposition='outside',
            name='Total Engine Hours'
        )

        # Create the Fuel Consumed bar chart
        fig_fuel_consumed = go.Bar(
            x=chassis_ids_fuel,
            y=total_fuel_consumed,
            marker=dict(color=total_fuel_consumed, colorscale=[[0, 'darkred'], [0.5, 'red'], [1, 'lightsalmon']]),
            text=[f"{val:.0f}" for val in total_fuel_consumed],
            textposition='outside',
            name='Fuel Consumed (L)'
        )

        # Set up the figure and add traces
        fig_combined = make_subplots()
        fig_combined.add_trace(fig_distance_traveled)
        fig_combined.add_trace(fig_engine_hours)
        fig_combined.add_trace(fig_fuel_consumed)

        # Initially hide the Engine Hours chart
        fig_combined['data'][1].visible = False
        fig_combined['data'][2].visible = False

        # Dynamically set y-axis range based on maximum values in the dataset
        max_distance = total_distance_traveled_sorted.max()
        max_engine_hours = total_engine_hours.max()
        max_fuel_consumed = total_fuel_consumed.max()

        # Configure layout and updatemenu buttons for toggling
        fig_combined.update_layout(
            title=dict(
                text="Fleet Utilization (KM / Hours / Fuel)",
                x=0.28,  # Center the title
                y=0.95,  # Keep the title at the top
                xanchor="center",
                yanchor="top",
                font=dict(size=16)
            ),
            xaxis_title="Chassis ID",
            yaxis_title="Value",
            template='simple_white',
            xaxis=dict(
                rangeslider=dict(visible=True,thickness=0.02,borderwidth=3,bordercolor="gray"),  # Add a range slider for scrolling
                tickangle=-45,  # Tilt the x-axis labels for better visibility
                automargin=True,  # Ensure margins adjust dynamically
            ),
            updatemenus=[
                dict(
                    type="buttons",
                    direction="left",
                    buttons=[
                        dict(label="Distance Traveled",
                            method="update",
                            args=[{"visible": [True, False, False]},
                                {"yaxis": {"title": "Total Distance Traveled (km)", "range": [0, max_distance * 1.3]}}]),
                        dict(label="Engine Hours",
                            method="update",
                            args=[{"visible": [False, True, False]},
                                {"yaxis": {"title": "Total Engine Hours", "range": [0, max_engine_hours * 1.3]}}]),
                        dict(label="Fuel Consumed",
                            method="update",
                            args=[{"visible": [False, False, True]},
                                {"yaxis": {"title": "Fuel Consumed (L)", "range": [0, max_fuel_consumed * 1.3]}}])
                    ],
                    showactive=True,
                    x=0.5,
                    y=1.2,
                    xanchor="center",
                    yanchor="bottom"
                )
            ],
            margin=dict(t=120)
        )

        # Total fuel consumed and engine hours for reference
        total_fuel_consumed = df['Fuel Consumed (L)'].sum()
        total_engine_hours = df['Total Engine Hours'].sum()

        # Calculate average utilizations
        utilized_fuel = df[['Driving (L)', 'PTO (L)', 'Idling (L)']].sum()
        fig_fuel_utilization = px.pie(
            values=[utilized_fuel[0], utilized_fuel[1], utilized_fuel[2]],
            names=['Driving (L)', 'PTO (L)', 'Idling (L)'],
            title="Fleet Fuel Utilization Breakdown - Summary",
            color=['Driving (L)', 'PTO (L)', 'Idling (L)'],
            color_discrete_map={'Driving (L)': 'limegreen','PTO (L)': 'goldenrod','Idling (L)': 'indianred'}
        )

        # Add annotation for total fuel consumed
        fig_fuel_utilization.add_annotation(
            text=f"Total Fuel Consumed: {total_fuel_consumed:.2f} L",
            x=0.5, y=-0.2,
            showarrow=False,
            font=dict(size=12)
        )

        # Engine Hours Breakdown (Pie Chart) with custom colors
        engine_hours_data = df[['Total Driving Hours', 'Total PTO Hours', 'Total Idling Hours']].sum()
        fig_engine_hours = px.pie(
            values=[engine_hours_data[0], engine_hours_data[1], engine_hours_data[2]],
            names=['Driving Hours', 'PTO Hours', 'Idling Hours'],
            title="Fleet Engine Hours Utilisation Breakdown - Summary",
            color=['Driving Hours', 'PTO Hours', 'Idling Hours'],
            color_discrete_map={'Driving Hours': 'limegreen','PTO Hours': 'goldenrod','Idling Hours': 'indianred'}
        )

        # Add annotation for total engine hours
        fig_engine_hours.add_annotation(
            text=f"Total Engine Hours: {total_engine_hours:.2f} Hours",
            x=0.5, y=-0.2,
            showarrow=False,
            font=dict(size=12)
        )

        # Fuel Utilization Breakdown by Chassis ID
        # Sort data by total fuel consumed in descending order
        sorted_fuel_data = df.copy()
        sorted_fuel_data = sorted_fuel_data.sort_values(by='Total Engine Hours', ascending=False)
        chassis_ids_sorted_fuel = sorted_fuel_data['Chassis ID']

        # Create stacked bar chart
        fuel_utilization_breakdown = go.Figure()
        fuel_utilization_breakdown.add_trace(go.Bar(
            x=chassis_ids_sorted_fuel, y=sorted_fuel_data['Driving (L)'], name='Driving (L)', marker_color='limegreen',
            text=sorted_fuel_data['Driving (L)'], textposition='outside', texttemplate='%{text:.0f}'
        ))
        fuel_utilization_breakdown.add_trace(go.Bar(
            x=chassis_ids_sorted_fuel, y=sorted_fuel_data['PTO (L)'], name='PTO (L)', marker_color='goldenrod',
            text=sorted_fuel_data['PTO (L)'], textposition='outside', texttemplate='%{text:.0f}'
        ))
        fuel_utilization_breakdown.add_trace(go.Bar(
            x=chassis_ids_sorted_fuel, y=sorted_fuel_data['Idling (L)'], name='Idling (L)', marker_color='indianred',
            text=sorted_fuel_data['Idling (L)'], textposition='outside', texttemplate='%{text:.0f}'
        ))
        
        max_fuel_utilization = df['Fuel Consumed (L)'].max()

        fuel_utilization_breakdown.update_layout(
            title="Fuel Utilization Breakdown - Per unit",
            xaxis=dict(
                rangeslider=dict(visible=True,thickness=0.02,borderwidth=3,bordercolor="gray"),  # Add a range slider for scrolling
                tickangle=-45,  # Tilt the x-axis labels for better visibility
                automargin=True,  # Dynamically adjust margins
                title_standoff=20
            ),
            xaxis_title="Chassis ID",
            yaxis_title="Fuel Consumed (L)",
            barmode='stack',
            margin=dict(b=100, t=120),
            yaxis=dict(automargin=True, range=[0, max_fuel_utilization * 1.3]), 
            legend=dict(x=0.5, y=-1.5, orientation='h', xanchor='center', yanchor='top'),
            template='plotly_white'
        )

        # Engine Hours Breakdown by Chassis ID
        # Sort data by total engine hours in descending order
        sorted_engine_hours_data = df.copy()
        sorted_engine_hours_data = sorted_engine_hours_data.sort_values(by='Total Engine Hours', ascending=False)
        chassis_ids_sorted_engine = sorted_engine_hours_data['Chassis ID']

        # Create stacked bar chart
        engine_hours_breakdown = go.Figure()
        engine_hours_breakdown.add_trace(go.Bar(
            x=chassis_ids_sorted_engine, y=sorted_engine_hours_data['Total Driving Hours'], name='Total Driving Hours', marker_color='limegreen',
             text=sorted_engine_hours_data['Total Driving Hours'], textposition='outside', texttemplate='%{text:.0f}'
        ))
        engine_hours_breakdown.add_trace(go.Bar(
            x=chassis_ids_sorted_engine, y=sorted_engine_hours_data['Total PTO Hours'], name='Total PTO Hours', marker_color='goldenrod',
            text=sorted_engine_hours_data['Total PTO Hours'], textposition='outside', texttemplate='%{text:.0f}'
        ))
        engine_hours_breakdown.add_trace(go.Bar(
            x=chassis_ids_sorted_engine, y=sorted_engine_hours_data['Total Idling Hours'], name='Total Idling Hours', marker_color='indianred',
            text=sorted_engine_hours_data['Total Idling Hours'], textposition='outside', texttemplate='%{text:.0f}'
        ))

        max_engine_hours = df['Total Engine Hours'].max()

        engine_hours_breakdown.update_layout(
            title="Engine Hours Breakdown - Per unit",
            xaxis=dict(
                rangeslider=dict(visible=True,thickness=0.02,borderwidth=3,bordercolor="gray"),  # Add a range slider for scrolling
                tickangle=-45,  # Tilt the x-axis labels for better visibility
                automargin=True,  # Dynamically adjust margins
                title_standoff=20
            ),
            xaxis_title="Chassis ID",
            yaxis_title="Engine Hours",
            barmode='stack',
            margin=dict(b=100, t=120),
            yaxis=dict(automargin=True, range=[0, max_engine_hours * 1.3]),
            legend=dict(x=0.5, y=-1.5, orientation='h', xanchor='center', yanchor='top'),
            template='plotly_white'
        )

        # Good Driving Behavior Hour Breakdown by Chassis ID (Ordered by Driving Efficiency %)
        # Create a copy of the dataframe
        df_sorted_hh = df.copy()
        # Calculate the custom percentage for ordering
        df_sorted_hh['Driving Efficiency %'] = ((df_sorted_hh['Total Engine Hours'] - 
                                    (df_sorted_hh['Total Cruise Control Hours'] + df_sorted_hh['Total Sweetspot Hours'] + 
                                    df_sorted_hh['Total Top Gear Hours'] + df_sorted_hh['Total Coasting Hours'])) * 100) / df_sorted_hh['Total Engine Hours']

        # Sort the DataFrame by the calculated percentage in ascending order and sort by Total Engine Hours (descending)
        df_sorted_hh = df_sorted_hh.sort_values(by=['Total Engine Hours','Driving Efficiency %'], ascending=[False,True])

        # Extract sorted data for plotting
        df_sorted_hh['Cruise Control Hours %'] = (df_sorted_hh['Total Cruise Control Hours'] / df_sorted_hh['Total Engine Hours']) * 100
        df_sorted_hh['Sweetspot Hours %'] = (df_sorted_hh['Total Sweetspot Hours'] / df_sorted_hh['Total Engine Hours']) * 100
        df_sorted_hh['Top Gear Hours %'] = (df_sorted_hh['Total Top Gear Hours'] / df_sorted_hh['Total Engine Hours']) * 100
        df_sorted_hh['Coasting Hours %'] = (df_sorted_hh['Total Coasting Hours'] / df_sorted_hh['Total Engine Hours']) * 100
        df_sorted_hh['PTO Hours %'] = (df_sorted_hh['Total PTO Hours'] / df_sorted_hh['Total Engine Hours']) * 100
        df_sorted_hh['Idling Hours %'] = (df_sorted_hh['Total Idling Hours'] / df_sorted_hh['Total Engine Hours']) * 100
        df_sorted_hh['Driving Hours %'] = (df_sorted_hh['Total Driving Hours'] / df_sorted_hh['Total Engine Hours']) * 100

        good_behavior_hours = df_sorted_hh['Total Cruise Control Hours'] + df_sorted_hh['Total Sweetspot Hours'] + df_sorted_hh['Total Top Gear Hours'] + df_sorted_hh['Total Coasting Hours']
        df_sorted_hh['Remaining Driving Hours %'] = ((df_sorted_hh['Total Driving Hours'] - good_behavior_hours) / df_sorted_hh['Total Engine Hours']) * 100

        # Prepare the sorted data
        chassis_ids = df_sorted_hh['Chassis ID']
        cruise_control_hours_perc = df_sorted_hh['Cruise Control Hours %']
        sweetspot_hours_perc = df_sorted_hh['Sweetspot Hours %']
        top_gear_hours_perc = df_sorted_hh['Top Gear Hours %']
        coasting_hours_perc = df_sorted_hh['Coasting Hours %']
        remaining_driving_hours_perc = df_sorted_hh['Remaining Driving Hours %']
        pto_hours_perc = df_sorted_hh['PTO Hours %']
        idling_hours_perc = df_sorted_hh['Idling Hours %']

        # Create stacked bar chart with sorted data
        fig_good_driving = go.Figure()
        fig_good_driving.add_trace(go.Bar(x=chassis_ids, y=cruise_control_hours_perc, name='Cruise Control  %', marker_color='darkgreen'))
        fig_good_driving.add_trace(go.Bar(x=chassis_ids, y=sweetspot_hours_perc, name='Sweetspot Hours %', marker_color='lightgreen'))
        fig_good_driving.add_trace(go.Bar(x=chassis_ids, y=top_gear_hours_perc, name='Top Gear Hours %', marker_color='forestgreen'))
        fig_good_driving.add_trace(go.Bar(x=chassis_ids, y=coasting_hours_perc, name='Coasting Hours %', marker_color='limegreen'))

        # Add adjusted driving hours on top of good driving behaviors
        fig_good_driving.add_trace(go.Bar(x=chassis_ids, y=remaining_driving_hours_perc, name='Remaining Driving Hours %', marker_color='cornflowerblue'))

        # Add remaining engine hours as the top layer
        fig_good_driving.add_trace(go.Bar(x=chassis_ids, y=pto_hours_perc, name='PTO Hours %', marker_color='goldenrod'))
        fig_good_driving.add_trace(go.Bar(x=chassis_ids, y=idling_hours_perc, name='Idling Hours %', marker_color='indianred'))

        # Update layout for stacked bar
        fig_good_driving.update_layout(
            title="Summary of Good Driving Behavior - Engine Hours Per Unit<br><sub>Note: Ordered from Best to worst Hours. ESCOT Transmission vehicles do not show Sweetspot %</sub><br>",
            xaxis=dict(
                rangeslider=dict(visible=True,thickness=0.02,borderwidth=3,bordercolor="gray"),  # Add a range slider for scrolling
                tickangle=-45,  # Tilt the x-axis labels for better visibility
                automargin=True,  # Dynamically adjust margins
            ),
            xaxis_title="Chassis ID",
            yaxis_title="Engine Hours %",
            barmode='stack',
            legend=dict(x=0.5, y=-1.5, orientation='h', xanchor='center', yanchor='top', font=dict(size=10)),
            template='plotly_white'
        )

        # Good Driving Behavior Fuel Breakdown by Chassis ID (Ordered by Driving Efficiency %)
        # Create a copy of the dataframe
        df_sorted_fuel = df.copy()
        # Calculate custom percentage for ordering (fuel efficiency instead of hours)
        df_sorted_fuel['Fuel Efficiency %'] = ((df_sorted_fuel['Fuel Consumed (L)'] - 
                                (df_sorted_fuel['Cruise Control (L)'] + df_sorted_fuel['Sweetspot (L)'] + 
                                    df_sorted_fuel['Top gear (L)'])) * 100) / df_sorted_fuel['Fuel Consumed (L)']

        # Sort the DataFrame by the calculated fuel efficiency percentage in ascending order
        df_sorted_fuel = df_sorted_fuel.sort_values(by=['Total Engine Hours','Fuel Efficiency %'], ascending=[False,True])

        # Extract sorted data for plotting
        chassis_ids = df_sorted_fuel['Chassis ID']
        total_fuel_consumed = df_sorted_fuel['Fuel Consumed (L)']
        cruise_control_fuel = df_sorted_fuel['Cruise Control (L)']
        sweetspot_fuel = df_sorted_fuel['Sweetspot (L)']
        top_gear_fuel = df_sorted_fuel['Top gear (L)']
        total_pto_fl = df_sorted_fuel['PTO (L)']
        total_idling_fl = df_sorted_fuel['Idling (L)']
        good_behavior_fuel = cruise_control_fuel + sweetspot_fuel + top_gear_fuel

        # Calculate adjusted total fuel by removing good behavior fuel usage
        adjusted_fuel_consumed = 100 - (cruise_control_fuel + sweetspot_fuel + top_gear_fuel + total_pto_fl + total_idling_fl)

        # Calculate percentages for each fuel type
        df_sorted_fuel['Cruise Control L%'] = (df_sorted_fuel['Cruise Control (L)'] / df_sorted_fuel['Fuel Consumed (L)']) * 100
        df_sorted_fuel['Sweetspot L%'] = (df_sorted_fuel['Sweetspot (L)'] / df_sorted_fuel['Fuel Consumed (L)']) * 100
        df_sorted_fuel['Top Gear L%'] = (df_sorted_fuel['Top gear (L)'] / df_sorted_fuel['Fuel Consumed (L)']) * 100
        df_sorted_fuel['Remaining Driving Fuel L%'] = (
            (df_sorted_fuel['Driving (L)'] - 
            (df_sorted_fuel['Cruise Control (L)'] + df_sorted_fuel['Sweetspot (L)'] + df_sorted_fuel['Top gear (L)']))
            / df_sorted_fuel['Fuel Consumed (L)']
        ) * 100
        df_sorted_fuel['PTO Fuel L%'] = (df_sorted_fuel['PTO (L)'] / df_sorted_fuel['Fuel Consumed (L)']) * 100
        df_sorted_fuel['Idling Fuel L%'] = (df_sorted_fuel['Idling (L)'] / df_sorted_fuel['Fuel Consumed (L)']) * 100

        cruise_control_fuel = df_sorted_fuel['Cruise Control L%']
        sweetspot_fuel = df_sorted_fuel['Sweetspot L%']
        top_gear_fuel = df_sorted_fuel['Top Gear L%']
        total_pto_fl = df_sorted_fuel['PTO Fuel L%']
        total_idling_fl = df_sorted_fuel['Idling Fuel L%']
        rmng_fuel_consumed = df_sorted_fuel['Remaining Driving Fuel L%']

        # Create stacked bar chart with sorted data
        fig_fuel_good = go.Figure()
        fig_fuel_good.add_trace(go.Bar(x=chassis_ids, y=cruise_control_fuel, name='Cruise Control Fuel', marker_color='darkgreen'))
        fig_fuel_good.add_trace(go.Bar(x=chassis_ids, y=sweetspot_fuel, name='Sweetspot Fuel', marker_color='lightgreen'))
        fig_fuel_good.add_trace(go.Bar(x=chassis_ids, y=top_gear_fuel, name='Top Gear Fuel', marker_color='forestgreen'))

        # Add adjusted fuel used for other purposes on top of good driving behaviors
        fig_fuel_good.add_trace(go.Bar(x=chassis_ids, y=rmng_fuel_consumed, name='Remaining Driving Fuel', marker_color='cornflowerblue'))

        # Add remaining fuel as the top layer
        fig_fuel_good.add_trace(go.Bar(x=chassis_ids, y=total_pto_fl, name='PTO Fuel', marker_color='goldenrod'))
        fig_fuel_good.add_trace(go.Bar(x=chassis_ids, y=total_idling_fl, name='Idling Fuel', marker_color='indianred'))

        # Get the number of vehicles
        num_vehicles = len(df['Chassis ID'])
        # Determine the width dynamically based on the number of vehicles
        if num_vehicles < 8:
            bar_width = 0.4  # Smaller width for fewer vehicles
        else:
            bar_width = None  # Default width for larger datasets

        # Update traces with the determined bar width
        fig_fuel_good.update_traces(width=bar_width)

        # Update layout for stacked bar
        fig_fuel_good.update_layout(
            title="Summary of Good Driving Behavior - Fuel Consumed Per Unit<br><sub>Note: Ordered from Best to worst Fuel Consumption. ESCOT Transmission vehicles do not show Sweetspot %</sub><br>",
            xaxis=dict(
                rangeslider=dict(visible=True,thickness=0.02,borderwidth=3,bordercolor="gray"),  # Add a range slider for scrolling
                tickangle=-45,  # Tilt the x-axis labels for better visibility
                automargin=True,  # Dynamically adjust margins
                title_standoff=2
            ),
            xaxis_title="Chassis ID",
            yaxis_title="Fuel Consumed (L)%",
            barmode='stack',
            legend=dict(x=0.5, y=-1.5, orientation='h', xanchor='center', yanchor='top', font=dict(size=10)),
            template='plotly_white'
        )

        df_sorted_efficiency = df.copy()
        df_sorted_efficiency = df_sorted_efficiency.sort_values(by='Total Engine Hours', ascending=False)

        # Extract sorted data
        chassis_ids = df_sorted_efficiency['Chassis ID'].tolist()
        fuel_efficiency_km_per_l = df_sorted_efficiency['Total Fuel Efficiency (km/L)'].tolist()
        fuel_efficiency_l_per_h = df_sorted_efficiency['Total Fuel Efficiency (L/h)'].tolist()

        # Create the figure
        fig_fuel_efficiency = go.Figure()

        # Line chart for "Total Fuel Efficiency (km/L)"
        fig_fuel_efficiency.add_trace(go.Scatter(
            x=chassis_ids, 
            y=fuel_efficiency_km_per_l, 
            mode='lines+markers+text',  
            name='Fuel Efficiency (km/L)', 
            marker_color='cornflowerblue',
            text=[f"{eff:.2f} km/L" for eff in fuel_efficiency_km_per_l],  
            textposition="top center"  
        ))

        # Line chart for "Total Fuel Efficiency (L/h)"
        fig_fuel_efficiency.add_trace(go.Scatter(
            x=chassis_ids, 
            y=fuel_efficiency_l_per_h, 
            mode='lines+markers+text',  
            name='Fuel Efficiency (L/h)', 
            marker_color='darkorange',
            text=[f"{eff:.2f} L/h" for eff in fuel_efficiency_l_per_h],  
            textposition="bottom center"  
        ))

        # Update layout with a single y-axis and toggling buttons
        fig_fuel_efficiency.update_layout(
            title='Fuel Efficiency Comparison (Km/L vs. L/h) - Sorted by Engine Hours',
            xaxis=dict(
                rangeslider=dict(visible=True, thickness=0.02, borderwidth=3, bordercolor="gray"),  
                tickangle=-45,  
                automargin=True,  
            ),
            xaxis_title='Chassis ID',
            yaxis_title='Fuel Efficiency',
            legend=dict(x=0.5, y=-0.8, orientation="h", xanchor="center", yanchor="top", font=dict(size=10)),
            template='plotly_white',
            updatemenus=[{
                'buttons': [
                    {'method': 'update', 'label': 'Show Both', 'args': [{'visible': [True, True]}]},
                    {'method': 'update', 'label': 'Show km/L Only', 'args': [{'visible': [True, False]}]},
                    {'method': 'update', 'label': 'Show L/h Only', 'args': [{'visible': [False, True]}]},
                ],
                'direction': 'down',
                'showactive': True,
                'x': 0.5,
                'y': 1.15,
                'xanchor': 'center',
                'yanchor': 'top'
            }]
        )

        # e. Fuel Consumed vs AdBlue Consumed (Bar and Line Graph)
        # Group and sort the data by Fuel Consumed in descending order
        fuel_consumed_data = df.groupby('Chassis ID')['Fuel Consumed (L)'].sum().sort_values(ascending=False)
        adblue_consumed_data = df.groupby('Chassis ID')['Adblue Consumed (L)'].sum().reindex(fuel_consumed_data.index)

        # Create the figure
        fig_fuel_adblue_consumption = go.Figure()

        # Bar for Fuel Consumed
        fig_fuel_adblue_consumption.add_trace(go.Bar(
            x=fuel_consumed_data.index, 
            y=fuel_consumed_data.values, 
            name='Fuel Consumed (L)', 
            marker_color='steelblue',  # Updated to a more contextually appropriate color
            text=fuel_consumed_data.values,  # Display values as text
            texttemplate='%{text:.0f}',      # Display as whole numbers
            textposition='outside',          # Position text outside the bar
            yaxis='y1'
        ))

        # Line for AdBlue Consumed
        fig_fuel_adblue_consumption.add_trace(go.Scatter(
            x=adblue_consumed_data.index, 
            y=adblue_consumed_data.values, 
            mode='lines+markers', 
            name='Adblue Consumed (L)', 
            marker_color='darkgoldenrod',  # Updated to a more suitable contrasting color
            yaxis='y2'
        ))

        # Calculate the maximum values for dynamic adjustment
        fmax = df['Fuel Consumed (L)'].max()
        amax = df['Adblue Consumed (L)'].max()

        # Get the number of vehicles
        num_vehicles = len(df['Chassis ID'])
        # Determine the width dynamically based on the number of vehicles
        if num_vehicles < 8:
            bar_width = 0.4  # Smaller width for fewer vehicles
        else:
            bar_width = None  # Default width for larger datasets

        # Update traces with the determined bar width
        for trace in fig_fuel_adblue_consumption.data:
            if isinstance(trace, go.Bar):  # Apply width only to bar traces
                trace.width = bar_width
        
        # Update layout for dual y-axes and add a note under the title
        fig_fuel_adblue_consumption.update_layout(
            title='Fuel vs AdBlue Consumed - Per unit<br><sub>Note: Ideal AdBlue consumption should be up to 5-6% of Fuel Consumed and is applicable for Euro4 vehicles onwards</sub>',
            xaxis=dict(
                rangeslider=dict(visible=True,thickness=0.02,borderwidth=3,bordercolor="gray"),  # Add a range slider for scrolling
                tickangle=-45,  # Tilt the x-axis labels for better visibility
                automargin=True,  # Dynamically adjust margins
            ),
            xaxis_title='Chassis ID',
            yaxis=dict(
                title='Fuel Consumed (L)',
                titlefont=dict(color='steelblue'),
                tickfont=dict(color='steelblue'),
                range=[0, fmax * 1.3]
            ),
            yaxis2=dict(
                title='AdBlue Consumed (L)',
                titlefont=dict(color='darkgoldenrod'),
                tickfont=dict(color='darkgoldenrod'),
                overlaying='y',  # Overlay on the same plot
                side='right',     # Position this axis on the right side
                rangemode="tozero",
            ),
            legend=dict(x=0.5, y=-1.1, orientation='h', xanchor='center', yanchor='top', font=dict(size=10)),
            template='plotly_white'
        )

        return [fig_fuel_utilization, fig_engine_hours, fig_good_driving, fig_fuel_efficiency, fig_fuel_adblue_consumption, fig_total_vehicles, fig_total_distance, fig_total_engine_hours, fig_total_fuel_consumed, fig_avg_speed, fig_sunburst, fig_combined, fuel_utilization_breakdown, engine_hours_breakdown, fig_fuel_good]

def generate_combined_visuals(df_combined):
    # a. Total Number of Vehicles
    total_vehicles = df_combined['Chassis ID'].nunique()
    fig_total_vehicles = go.Figure(go.Indicator(
        mode="number",
        value=total_vehicles,
        title={"text": "Total Number of Vehicles"},
        number={"font": {"size": 50, "color": "darkblue"}},
        domain={'x': [0, 1], 'y': [0, 1]}
    ))
    # Average maximum speed
    avg_speed = df_combined['Distance (km)'].mean()/df_combined['Total Engine Hours'].mean()
    # Create the visual for average maximum speed
    fig_avg_speed = go.Figure(go.Indicator(
        mode="number",
        value=avg_speed,
        title={"text": "Average Speed (km/h)"},
        number={"font": {"size": 50, "color": "green"}},
        domain={'x': [0, 1], 'y': [0, 1]}
    ))
    # Total engine hours
    total_engine_hours = df_combined['Total Engine Hours'].sum()
    # Create the visual for total engine hours
    fig_total_engine_hours = go.Figure(go.Indicator(
        mode="number",
        value=total_engine_hours,
        title={"text": "Total Engine Hours"},
        number={"font": {"size": 50, "color": "orange"}},
        domain={'x': [0, 1], 'y': [0, 1]}
    ))
    # Total distance travelled
    total_distance = df_combined['Distance (km)'].sum()
    # Create the visual for total distance travelled
    fig_total_distance = go.Figure(go.Indicator(
        mode="number",
        value=total_distance,
        title={"text": "Total Distance (km)"},
        number={"font": {"size": 50, "color": "purple"}},
        domain={'x': [0, 1], 'y': [0, 1]}
    ))
    # Total fuel consumed
    total_fuel_consumed = df_combined['Fuel Consumed (L)'].sum()
    # Create the visual for total fuel consumed
    fig_total_fuel_consumed = go.Figure(go.Indicator(
        mode="number",
        value=total_fuel_consumed,
        title={"text": "Total Fuel Consumed (L)"},
        number={"font": {"size": 50, "color": "red"}},
        domain={'x': [0, 1], 'y': [0, 1]}
    ))
    # Add calculation for potential fuel saving
    total_fuel_wasted = df_combined['Fuel consumed during overspeed (L)'].sum() + df_combined['Engine overrev (L)'].sum() + df_combined['Excessive Idling (L)'].sum()
    # Create a text indicator for the potential fuel saving
    fig_fuel_saving = go.Figure(go.Indicator(
        mode="number",
        value=total_fuel_wasted,
        title={"text": "Potential Fuel Saving (L)"},
        number={
            "font": {"size": 50, "color": "gray"},
            "valueformat": ".0f"  # Format to show zero decimal places
        },
        domain={'x': [0, 1], 'y': [0, 1]}
    ))
    
    global potential_fuel_saving_liters
    potential_fuel_saving_liters = total_fuel_wasted

    # COMBINED GRAPHS FOR THE STATS
    filters=None
    if filters:
        selected_models = filters.get('Model', None)
        selected_axles = filters.get('Axle Configuration', None)
        selected_truck_types = filters.get('Truck Type', None)

        if selected_models:
            df_combined = df_combined[df_combined['Model'].isin(selected_models)]
        if selected_axles:
            df_combined = df_combined[df_combined['Axle Configuration'].isin(selected_axles)]
        if selected_truck_types:
            df_combined = df_combined[df_combined['Truck Type'].isin(selected_truck_types)]
    # Prepare Distance Traveled data
    sorted_distance_data = df_combined.sort_values(by='Distance (km)', ascending=False)
    chassis_ids_sorted = sorted_distance_data['Chassis ID']
    total_distance_traveled_sorted = sorted_distance_data['Distance (km)']
    # Prepare Engine Hours data
    df_sorted_e = df_combined.sort_values(by='Total Engine Hours', ascending=False)
    chassis_ids_engine = df_sorted_e['Chassis ID']
    total_engine_hours = df_sorted_e['Total Engine Hours']
    # Prepare data for Fuel Consumed
    sorted_fuel = df_combined.sort_values(by='Fuel Consumed (L)', ascending=False)
    chassis_ids_fuel = sorted_fuel['Chassis ID']
    total_fuel_consumed = sorted_fuel['Fuel Consumed (L)']
    # Create the Distance Traveled bar chart
    fig_distance_traveled = go.Bar(
        x=chassis_ids_sorted,
        y=total_distance_traveled_sorted,
        marker=dict(color=total_distance_traveled_sorted, colorscale='Viridis'),
        text=[f"{val:.0f}" for val in total_distance_traveled_sorted],
        textposition='outside',
        name='Distance Traveled'
    )
    # Create the Engine Hours bar chart
    fig_engine_hours = go.Bar(
        x=chassis_ids_engine,
        y=total_engine_hours,
        marker=dict(color=total_engine_hours, colorscale=[[0, 'goldenrod'], [0.5, 'gold'], [1, 'khaki']]),
        text=[f"{val:.0f}" for val in total_engine_hours],
        textposition='outside',
        name='Total Engine Hours'
    )
    # Create the Fuel Consumed bar chart
    fig_fuel_consumed = go.Bar(
        x=chassis_ids_fuel,
        y=total_fuel_consumed,
        marker=dict(color=total_fuel_consumed, colorscale=[[0, 'darkred'], [0.5, 'red'], [1, 'lightsalmon']]),
        text=[f"{val:.0f}" for val in total_fuel_consumed],
        textposition='outside',
        name='Fuel Consumed (L)'
    )
    # Set up the figure and add traces
    fig_histogram = make_subplots()
    fig_histogram.add_trace(fig_distance_traveled)
    fig_histogram.add_trace(fig_engine_hours)
    fig_histogram.add_trace(fig_fuel_consumed)
    # Initially hide the Engine Hours chart
    fig_histogram['data'][1].visible = False
    fig_histogram['data'][2].visible = False
    # Dynamically set y-axis range based on maximum values in the dataset
    max_distance = total_distance_traveled_sorted.max()
    max_engine_hours = total_engine_hours.max()
    max_fuel_consumed = total_fuel_consumed.max()
    # Configure layout and updatemenu buttons for toggling
    fig_histogram.update_layout(
        title=dict(
            text="Fleet Utilization (KM / Hours / Fuel)",
            x=0.28,  # Center the title
            y=0.95,  # Keep the title at the top
            xanchor="center",
            yanchor="top",
            font=dict(size=16)
        ),
        xaxis_title="Chassis ID",
        yaxis_title="Value",
        template='simple_white',
        xaxis=dict(
            rangeslider=dict(visible=True,thickness=0.02,borderwidth=3,bordercolor="gray"),  # Add a range slider for scrolling
            tickangle=-45,  # Tilt the x-axis labels for better visibility
            automargin=True,  # Ensure margins adjust dynamically
        ),
        updatemenus=[
            dict(
                type="buttons",
                direction="left",
                buttons=[
                    dict(label="Distance Traveled",
                        method="update",
                        args=[{"visible": [True, False, False]},
                            {"yaxis": {"title": "Total Distance Traveled (km)", "range": [0, max_distance * 1.3]}}]),
                    dict(label="Engine Hours",
                        method="update",
                        args=[{"visible": [False, True, False]},
                            {"yaxis": {"title": "Total Engine Hours", "range": [0, max_engine_hours * 1.3]}}]),
                    dict(label="Fuel Consumed",
                        method="update",
                        args=[{"visible": [False, False, True]},
                            {"yaxis": {"title": "Fuel Consumed (L)", "range": [0, max_fuel_consumed * 1.3]}}])
                ],
                showactive=True,
                x=0.5,
                y=1.2,
                xanchor="center",
                yanchor="bottom"
            )
        ],
        margin=dict(t=120)
    )

    ##########################################################################################################################

    # Stacked bar chart for engine hours by Inefficient Driving behaviors
    # Prepare the data
    chassis_ids = df_combined['Chassis ID']
    total_engine_hours = df_combined['Total Engine Hours']
    overspeed_hours = df_combined['Total Overspeed Hours']
    engine_overrev_hours = df_combined['Total Engine Overrev Hours']
    excessive_idling_hours = df_combined['Total Excessive Idling Hours']

    # Driving Behavior (Updated Stacked Bar Chart)
    # Calculate additional fields for sorting criteria
    df_combined['Good Behavior Remaining Hours'] = df_combined['Total Engine Hours'] - (
        df_combined['Total Cruise Control Hours'] + df_combined['Total Sweetspot Hours'] + 
        df_combined['Total Top Gear Hours'] + df_combined['Total Coasting Hours']
    )
    df_combined['Bad Behavior Remaining Hours'] = df_combined['Total Engine Hours'] - (
        df_combined['Total Overspeed Hours'] + df_combined['Total Engine Overrev Hours'] + 
        df_combined['Total Excessive Idling Hours']
    )

    # Sort by good driving hours (ascending) and Inefficient Driving hours (descending)
    df_sorted_gb_bare = df_combined.copy()
    df_sorted_gb_bare = df_sorted_gb_bare.sort_values(by=['Total Engine Hours', 'Good Behavior Remaining Hours', 'Bad Behavior Remaining Hours'], ascending=[False, True, False])

    # Define data for the stacked bar chart
    chassis_ids = df_sorted_gb_bare['Chassis ID']
    total_driving_hours = df_sorted_gb_bare['Total Driving Hours']
    cruise_control_hours = df_sorted_gb_bare['Total Cruise Control Hours']
    sweetspot_hours = df_sorted_gb_bare['Total Sweetspot Hours']
    top_gear_hours = df_sorted_gb_bare['Total Top Gear Hours']
    coasting_hours = df_sorted_gb_bare['Total Coasting Hours']
    overspeed_hours = df_sorted_gb_bare['Total Overspeed Hours']
    engine_overrev_hours = df_sorted_gb_bare['Total Engine Overrev Hours']
    excessive_idling_hours = df_sorted_gb_bare['Total Excessive Idling Hours']
    fuel_efficiency_kmpl = df_sorted_gb_bare['Total Fuel Efficiency (km/L)']

    # Calculate other components
    normal_idling_hours = df_sorted_gb_bare['Total Idling Hours'] - excessive_idling_hours
    neutral_driving_hours = total_driving_hours - (cruise_control_hours + sweetspot_hours + top_gear_hours + coasting_hours + engine_overrev_hours + overspeed_hours)
    neutral_driving_hours = neutral_driving_hours.apply(lambda x: max(x, 0))  # Replace negative values with 0
    pto_hours = df_sorted_gb_bare['Total PTO Hours']
    remaining_engine_hours = df_sorted_gb_bare['Total Engine Hours'] - (
        overspeed_hours + engine_overrev_hours + excessive_idling_hours + 
        cruise_control_hours + sweetspot_hours + top_gear_hours + 
        coasting_hours + normal_idling_hours + neutral_driving_hours + pto_hours
    )
    remaining_engine_hours = remaining_engine_hours.apply(lambda x: max(x, 0))  # Replace negative values with 0

    # Create the stacked bar chart
    fig_engine_hours_consumption = go.Figure()

    # Add traces for each category
    fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids, y=overspeed_hours, name='Overspeed Hours', marker_color='darkred'))
    fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids, y=excessive_idling_hours, name='Excessive Idling Hours', marker_color='red'))
    fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids, y=engine_overrev_hours, name='Engine Overrev Hours', marker_color='lightsalmon'))
    fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids, y=cruise_control_hours, name='Cruise Control Hours', marker_color='darkgreen'))
    fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids, y=sweetspot_hours, name='Sweetspot Hours', marker_color='lightgreen'))
    fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids, y=top_gear_hours, name='Top Gear Hours', marker_color='forestgreen'))
    fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids, y=coasting_hours, name='Coasting Hours', marker_color='limegreen'))
    fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids, y=normal_idling_hours, name='Normal Idling Hours', marker_color='yellow'))
    fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids, y=neutral_driving_hours, name='Neutral Driving Hours', marker_color='cornflowerblue'))
    fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids, y=pto_hours, name='PTO Hours', marker_color='orange'))
    fig_engine_hours_consumption.add_trace(go.Bar(x=chassis_ids, y=remaining_engine_hours, name='Remaining Engine Hours', marker_color='gray'))

    engine_hours_annotations = []
    # Add fuel efficiency as text labels at the top of each stacked bar
    for idx, chassis in enumerate(chassis_ids):
        total_height = (total_driving_hours.iloc[idx] + cruise_control_hours.iloc[idx] + sweetspot_hours.iloc[idx] +
                    top_gear_hours.iloc[idx] + coasting_hours.iloc[idx] + normal_idling_hours.iloc[idx] + 
                    neutral_driving_hours.iloc[idx] + pto_hours.iloc[idx] + remaining_engine_hours.iloc[idx] +
                    overspeed_hours.iloc[idx] + engine_overrev_hours.iloc[idx] + excessive_idling_hours.iloc[idx])

        # Total Engine Hours label
        engine_hours_annotations.append(dict(
            x=chassis,
            y=total_height,
            text=f"{df_sorted_gb_bare['Total Engine Hours'].iloc[idx]:.0f} Hrs",
            showarrow=False,
            font=dict(size=10, color="gray"),
            yshift=30
        ))

        # Fuel Efficiency label
        engine_hours_annotations.append(dict(
            x=chassis,
            y=total_height,
            text=f"{fuel_efficiency_kmpl.iloc[idx]:.2f} km/L",
            showarrow=False,
            font=dict(size=10, color="black"),
            yshift=15
        ))
    
    # Get the number of vehicles
    num_vehicles = len(df_sorted_gb_bare['Chassis ID'])
    # Determine the width dynamically based on the number of vehicles
    if num_vehicles < 8:
        bar_width = 0.4  # Smaller width for fewer vehicles
    else:
        bar_width = None  # Default width for larger datasets

    # Update traces with the determined bar width
    fig_engine_hours_consumption.update_traces(width=bar_width)

    # Update layout for stacked bar
    fig_engine_hours_consumption.update_layout(
        title=dict(
            text="Comprehensive Fleet Summary - Engine Hours Utilisation Per Unit",
            y=0.95,  # Move title closer to the graph (default is usually around 1.0)
            x=0.5,
            xanchor="right",
            yanchor="top"
        ),
        xaxis=dict(
                rangeslider=dict(visible=True,thickness=0.01,borderwidth=3,bordercolor="gray"),  # Add a range slider for scrolling
                tickangle=-45,  # Tilt the x-axis labels for better visibility
                automargin=True,  # Ensure margins adjust dynamically
            ),
        xaxis_title="Chassis ID",
        yaxis_title="Engine Hours",
        barmode='stack',
        legend=dict(x=0.5, y=-0.7, orientation='h', xanchor='center', yanchor='top', font=dict(size=10)),
        template='plotly_white'
    )

    ##########################################################################################################

    # Stacked bar chart for fuel consumed by driving behaviors
    # Prepare the data
    chassis_ids_fuel = df_combined['Chassis ID']
    total_fuel = df_combined['Fuel Consumed (L)']
    overspeed_fuel = df_combined['Fuel consumed during overspeed (L)']
    engine_overrev_fuel = df_combined['Engine overrev (L)']
    excessive_idling_fuel = df_combined['Excessive Idling (L)']

    # Driving Behavior (Updated Stacked Bar Chart)
    # Calculate additional fields for sorting criteria
    df_combined['Good Behavior Remaining Fuel'] = df_combined['Fuel Consumed (L)'] - (
        df_combined['Cruise Control (L)'] + df_combined['Sweetspot (L)'] + 
        df_combined['Top gear (L)']
    )
    df_combined['Bad Behavior Remaining Fuel'] = df_combined['Fuel Consumed (L)'] - (
        df_combined['Fuel consumed during overspeed (L)'] + df_combined['Engine overrev (L)'] + 
        df_combined['Excessive Idling (L)']
    )

    # Sort by good driving hours (ascending) and Inefficient Driving hours (descending)
    df_sorted_gb_barf = df_combined.copy()
    df_sorted_gb_barf = df_sorted_gb_barf.sort_values(by=['Total Engine Hours', 'Good Behavior Remaining Hours', 'Bad Behavior Remaining Hours'], ascending=[False, True, False])

    # Define data for the stacked bar chart
    chassis_ids_fuel = df_sorted_gb_barf['Chassis ID']
    total_driving_fuel = df_sorted_gb_barf['Driving (L)']
    cruise_control_fuel = df_sorted_gb_barf['Cruise Control (L)']
    sweetspot_fuel = df_sorted_gb_barf['Sweetspot (L)']
    top_gear_fuel = df_sorted_gb_barf['Top gear (L)']
    overspeed_fuel = df_sorted_gb_barf['Fuel consumed during overspeed (L)']
    engine_overrev_fuel = df_sorted_gb_barf['Engine overrev (L)']

    # Calculate other components
    normal_idling_fuel = df_combined['Idling (L)'] - excessive_idling_fuel
    neutral_driving_fuel = total_driving_fuel - (cruise_control_fuel + sweetspot_fuel + top_gear_fuel + engine_overrev_fuel + overspeed_fuel)
    neutral_driving_fuel = neutral_driving_fuel.apply(lambda x: max(x, 0))  # Replace negative values with 0
    pto_fuel = df_sorted_gb_barf['PTO (L)']
    remaining_fuel = df_sorted_gb_barf['Fuel Consumed (L)'] - (
        overspeed_fuel + engine_overrev_fuel + excessive_idling_fuel + 
        cruise_control_fuel + sweetspot_fuel + top_gear_fuel + normal_idling_fuel + 
        neutral_driving_fuel + pto_fuel
    )
    remaining_fuel = remaining_fuel.apply(lambda x: max(x, 0))  # Replace negative values with 0

    # Create the stacked bar chart
    fig_fuel_consumption = go.Figure()

    # Add traces for each category
    fig_fuel_consumption.add_trace(go.Bar(x=chassis_ids_fuel, y=overspeed_fuel, name='Overspeed Fuel', marker_color='darkred'))
    fig_fuel_consumption.add_trace(go.Bar(x=chassis_ids_fuel, y=excessive_idling_fuel, name='Excessive Idling Fuel', marker_color='red'))
    fig_fuel_consumption.add_trace(go.Bar(x=chassis_ids_fuel, y=engine_overrev_fuel, name='Engine Overrev Fuel', marker_color='lightsalmon'))
    fig_fuel_consumption.add_trace(go.Bar(x=chassis_ids_fuel, y=cruise_control_fuel, name='Cruise Control Fuel', marker_color='darkgreen'))
    fig_fuel_consumption.add_trace(go.Bar(x=chassis_ids_fuel, y=sweetspot_fuel, name='Sweetspot Fuel', marker_color='lightgreen'))
    fig_fuel_consumption.add_trace(go.Bar(x=chassis_ids_fuel, y=top_gear_fuel, name='Top Gear Fuel', marker_color='forestgreen'))
    fig_fuel_consumption.add_trace(go.Bar(x=chassis_ids_fuel, y=normal_idling_fuel, name='Normal Idling Fuel', marker_color='yellow'))
    fig_fuel_consumption.add_trace(go.Bar(x=chassis_ids_fuel, y=neutral_driving_fuel, name='Neutral Driving Fuel', marker_color='cornflowerblue'))
    fig_fuel_consumption.add_trace(go.Bar(x=chassis_ids_fuel, y=pto_fuel, name='PTO Fuel', marker_color='orange'))
    fig_fuel_consumption.add_trace(go.Bar(x=chassis_ids_fuel, y=remaining_fuel, name='Remaining Fuel', marker_color='gray'))

    # Add fuel efficiency as text labels at the top of each stacked bar
    fuel_annotations = []
    for idx, chassis in enumerate(chassis_ids_fuel):
        total_height = (total_driving_fuel.iloc[idx] + cruise_control_fuel.iloc[idx] + sweetspot_fuel.iloc[idx] +
                        top_gear_fuel.iloc[idx] + normal_idling_fuel.iloc[idx] + 
                        neutral_driving_fuel.iloc[idx] + pto_fuel.iloc[idx] + remaining_fuel.iloc[idx] +
                        overspeed_fuel.iloc[idx] + engine_overrev_fuel.iloc[idx] + excessive_idling_fuel.iloc[idx])

        # Total Fuel label
        fuel_annotations.append(dict(
            x=chassis,
            y=total_height,
            text=f"{df_sorted_gb_barf['Fuel Consumed (L)'].iloc[idx]:.0f} L",
            showarrow=False,
            font=dict(size=10, color="gray"),
            yshift=30 if total_height > 500 else 30
        ))

        # Fuel Efficiency label
        fuel_annotations.append(dict(
            x=chassis,
            y=total_height,
            text=f"{fuel_efficiency_kmpl.iloc[idx]:.2f} km/L",
            showarrow=False,
            font=dict(size=10, color="black"),
            yshift=15
        ))
    
    # Get the number of vehicles
    num_vehicles = len(df_sorted_gb_barf['Chassis ID'])
    # Determine the width dynamically based on the number of vehicles
    if num_vehicles < 8:
        bar_width = 0.4  # Smaller width for fewer vehicles
    else:
        bar_width = None  # Default width for larger datasets

    # Update traces with the determined bar width
    fig_fuel_consumption.update_traces(width=bar_width)

    # Update layout for stacked bar
    fig_fuel_consumption.update_layout(
        title=dict(
            text="Comprehensive Fleet Summary - Fuel Utilisation Per Unit",
            y=0.95,  # Move title closer to the graph (default is usually around 1.0)
            x=0.15,
            xanchor="right",
            yanchor="top"
        ),
        xaxis=dict(
                rangeslider=dict(visible=True,thickness=0.01,borderwidth=3,bordercolor="gray"),  # Add a range slider for scrolling
                tickangle=-45,  # Tilt the x-axis labels for better visibility
                automargin=True,  # Ensure margins adjust dynamically
            ),
        xaxis_title="Chassis ID",
        yaxis_title="Fuel (L)",
        barmode='stack',
        legend=dict(x=0.5, y=-0.7, orientation='h', xanchor='center', yanchor='top', font=dict(size=10)),
        template='plotly_white'
    )

    #######################################################################################################################

    # Make a deep copy of the engine hours figure
    efbarcombined_fig = copy.deepcopy(fig_engine_hours_consumption)

    # Append the fuel consumption traces to the figure and set them invisible by default
    for trace in fig_fuel_consumption.data:
        trace.visible = False
        efbarcombined_fig.add_trace(trace)

    # Set default layout with Engine Hours Annotations at startup
    efbarcombined_fig.update_layout(
        title=dict(
            text="Comprehensive Fleet Summary - Engine Hours Utilisation Per Unit",
            y=0.95,
            x=0.5,
            xanchor="right",
            yanchor="top"
        ),
        yaxis=dict(title="Engine Hours"),
        annotations=engine_hours_annotations  # Set default annotations
    )

    # Define the update menus to toggle between trace sets
    efbarcombined_fig.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                direction="left",
                pad={"t": 10},
                buttons=[
                    dict(
                        label="Engine Hours Utilisation",
                        method="update",
                        args=[
                            {"visible": [True] * len(fig_engine_hours_consumption.data) + [False] * len(fig_fuel_consumption.data)},
                            {"title": dict(
                                text="Comprehensive Fleet Summary - Engine Hours Utilisation Per Unit",
                                y=0.95,
                                x=0.5,
                                xanchor="right",
                                yanchor="top"
                            ),
                            "yaxis": {"title": "Engine Hours"},
                            "annotations": engine_hours_annotations  # Apply engine hours annotations
                            }
                        ]
                    ),
                    dict(
                        label="Fuel Utilisation",
                        method="update",
                        args=[
                            {"visible": [False] * len(fig_engine_hours_consumption.data) + [True] * len(fig_fuel_consumption.data)},
                            {"title": dict(
                                text="Comprehensive Fleet Summary - Fuel Utilisation Per Unit",
                                y=0.95,
                                x=0.45,
                                xanchor="right",
                                yanchor="top"
                            ),
                            "yaxis": {"title": "Fuel (L)"},
                            "annotations": fuel_annotations  # Apply fuel annotations
                            }
                        ]
                    )
                ],
                showactive=True,
                x=0.5,
                y=1.2,
                xanchor="center",
                yanchor="top"
            )
        ]
    )

    #######################################################################################################################
    # % Breakdown of Engine Hours Utilised for Driving Behaviours
    total_engine_hours = df_combined['Total Engine Hours'].sum()
    normal_idling_time = df_combined['Total Idling Hours'].sum() - df_combined['Total Excessive Idling Hours'].sum()
    pto = df_combined['Total PTO Hours'].sum()
    total_distributed_hours = df_combined[['Total Overspeed Hours', 'Total Excessive Idling Hours', 'Total Engine Overrev Hours', 'Total Cruise Control Hours', 
                             'Total Sweetspot Hours', 'Total Top Gear Hours', 'Total Coasting Hours']].sum()
    # Calculate total distributed hours
    total_distributed_hours = df_combined[['Total Overspeed Hours', 'Total Excessive Idling Hours', 'Total Engine Overrev Hours',
                                        'Total Cruise Control Hours', 'Total Sweetspot Hours', 'Total Top Gear Hours',
                                        'Total Coasting Hours']].sum()

    # Calculate neutral driving for each record and replace negative values with 0
    df_combined['Neutral Driving'] = df_combined['Total Driving Hours'] - (df_combined[['Total Overspeed Hours', 'Total Excessive Idling Hours', 'Total Engine Overrev Hours', 'Total Cruise Control Hours', 'Total Sweetspot Hours', 'Total Top Gear Hours', 'Total Coasting Hours']].sum(axis=1))
    df_combined['Neutral Driving'] = df_combined['Neutral Driving'].apply(lambda x: max(x, 0))
    neutral_driving = df_combined['Neutral Driving'].sum()
    remaining_engine_hours = total_engine_hours - (total_distributed_hours.sum() + df_combined['Total Idling Hours'].sum() + neutral_driving + pto)
    fig_distributed_hours = px.pie(values=[total_distributed_hours[0], total_distributed_hours[1], total_distributed_hours[2], total_distributed_hours[3], total_distributed_hours[4], total_distributed_hours[5], total_distributed_hours[6], normal_idling_time, neutral_driving, pto], 
                            names=['Overspeed', 'Excessive Idling', 'Engine Overrev', 'Cruise Control', 'Sweetspot', 'Top Gear', 
                                   'Coasting', 'Normal Idling', 'Neutral Driving', 'PTO'], 
                            title="Comprehensive Fleet Summary - Engine Hours Utilisation<br><sub>Note: Some overlap between Good and Inefficient Driving on total driven hours</sub>",
                            color=['Overspeed', 'Excessive Idling', 'Engine Overrev', 'Cruise Control', 'Sweetspot', 'Top Gear', 
                                   'Coasting', 'Normal Idling', 'Neutral Driving', 'PTO'],
                            color_discrete_map={'Overspeed': 'darkred', 'Excessive Idling': 'red', 'Engine Overrev': 'lightsalmon', 
                                                'Cruise Control': 'darkgreen', 'Sweetspot': 'lightgreen', 'Top Gear': 'forestgreen', 'Coasting': 'limegreen', 
                                                'Normal Idling': 'Yellow', 'Neutral Driving': 'cornflowerblue', 'PTO': 'orange'})
    fig_distributed_hours.update_traces(hole=0.4)  # Make it a donut chart

    # % Breakdown of Fuel Utilised for Driving Behaviours
    total_fuel_used = df_combined['Fuel Consumed (L)'].sum()
    normal_idling_fuel = df_combined['Idling (L)'].sum() - df_combined['Excessive Idling (L)'].sum()
    pto_fuel = df_combined['PTO (L)'].sum()
    total_distributed_fuel = df_combined[['Fuel consumed during overspeed (L)', 'Excessive Idling (L)', 'Engine overrev (L)', 'Cruise Control (L)', 
                             'Sweetspot (L)', 'Top gear (L)']].sum()
    # Calculate neutral driving fuel for each record and replace negative values with 0
    df_combined['Neutral Driving Fuel'] = df_combined['Driving (L)'] - (df_combined[['Fuel consumed during overspeed (L)', 'Excessive Idling (L)', 'Engine overrev (L)', 'Cruise Control (L)', 'Sweetspot (L)', 'Top gear (L)']].sum(axis=1))
    df_combined['Neutral Driving Fuel'] = df_combined['Neutral Driving Fuel'].apply(lambda x: max(x, 0))  # Replace negative values with 0
    neutral_driving_fuel = df_combined['Neutral Driving Fuel'].sum() # Sum up neutral driving fuel after applying the condition
    remaining_engine_hours = total_fuel_used - (total_distributed_fuel.sum() + df_combined['Idling (L)'].sum() + neutral_driving_fuel + pto_fuel)
    fig_distributed_fuel = px.pie(values=[total_distributed_fuel[0], total_distributed_fuel[1], total_distributed_fuel[2], total_distributed_fuel[3], total_distributed_fuel[4], total_distributed_fuel[5], normal_idling_fuel, neutral_driving, pto_fuel], 
                            names=['Overspeed', 'Excessive Idling', 'Engine Overrev', 'Cruise Control', 'Sweetspot', 'Top Gear', 
                                   'Normal Idling', 'Neutral Driving', 'PTO'], 
                            title="Comprehensive Fleet Summary - Fuel Utilisation<br><sub>Note: Some overlap between Good and Inefficient Driving on total driven fuel</sub>",
                            color=['Overspeed', 'Excessive Idling', 'Engine Overrev', 'Cruise Control', 'Sweetspot', 'Top Gear', 
                                   'Normal Idling', 'Neutral Driving', 'PTO'],
                            color_discrete_map={'Overspeed': 'darkred', 'Excessive Idling': 'red', 'Engine Overrev': 'lightsalmon', 
                                                'Cruise Control': 'darkgreen', 'Sweetspot': 'lightgreen', 'Top Gear': 'forestgreen', 
                                                'Normal Idling': 'Yellow', 'Neutral Driving': 'cornflowerblue', 'PTO': 'orange'})
    fig_distributed_fuel.update_traces(hole=0.4)  # Make it a donut chart
    
    # Create a copy of the engine hours donut chart
    efdonutcombined_fig = copy.deepcopy(fig_distributed_hours)

    # Add the fuel utilisation donut chart as additional traces but make them initially invisible.
    for trace in fig_distributed_fuel.data:
        trace.visible = False
        efdonutcombined_fig.add_trace(trace)

    # Create update menus to toggle between the two sets of traces.
    efdonutcombined_fig.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                direction="left",
                buttons=[
                    dict(
                        label="Engine Hours Utilisation",
                        method="update",
                        args=[{"visible": [True]*len(fig_distributed_hours.data) + [False]*len(fig_distributed_fuel.data)},
                            {"title": "Comprehensive Fleet Summary - Engine Hours Utilisation<br><sub>Note: Some overlap between Good and Inefficient Driving on total driven hours</sub>"}]
                    ),
                    dict(
                        label="Fuel Utilisation",
                        method="update",
                        args=[{"visible": [False]*len(fig_distributed_hours.data) + [True]*len(fig_distributed_fuel.data)},
                            {"title": "Comprehensive Fleet Summary - Fuel Utilisation<br><sub>Note: Some overlap between Good and Inefficient Driving on total driven fuel</sub>"}]
                    )
                ],
                showactive=True,
                x=0.5,  # Adjust position to avoid overlap with the chart
                y=1.6,   # Move buttons higher up
                xanchor="center",
                yanchor="top"
            )
        ]
    )

    # Suburst grouped by Truck Model, Axle Configuration, and Truck Type to count occurrences
    count_df = df_combined.groupby(['Model', 'Truck Type', 'Axle Configuration']).size().reset_index(name='Count')
    fig_sunburst = px.sunburst(
        count_df, 
        path=['Model', 'Truck Type', 'Axle Configuration'], 
        values='Count',
        title="Truck Models",
        color='Model',  # Color based on Model
        color_discrete_map={'Quester': 'darkblue', 'Croner': 'yellow'}
    )
    fig_sunburst.update_traces(
        textinfo="label+value",  # Display both label and value (count) on the slices
        insidetextorientation='auto'  # Automatically adjust text orientation for readability
    )

    # Good vs Inefficient Driving Bar with Neutral Driving Correctly Added
    good_factors = ['Total Coasting Hours', 'Total Top Gear Hours', 'Total Cruise Control Hours', 'Total Sweetspot Hours']
    bad_factors = ['Total Engine Overrev Hours', 'Total Overspeed Hours', 'Total Excessive Idling Hours']
    df_combined['Total Normal Idling Hours'] = df_combined['Total Idling Hours'] - df_combined['Total Excessive Idling Hours']
    ntrl_factors = ['Total Driving Hours', 'Total Normal Idling Hours']

    # Calculate total good and Inefficient Driving hours across all vehicles
    total_good_hours = df_combined[good_factors].sum().sum()
    total_bad_hours = df_combined[bad_factors].sum().sum()
    total_engine_hours = df_combined['Total Engine Hours'].sum()

    # Calculate percentages for good and Inefficient Driving relative to Total Engine Hours
    good_percentage = (total_good_hours / (total_good_hours + total_bad_hours)) * 100
    bad_percentage = (total_bad_hours / (total_good_hours + total_bad_hours)) * 100

    # Calculate individual factor percentages for hover information
    good_factors_percentages = [(df_combined[fac].sum() / total_good_hours) * 100 for fac in good_factors]
    bad_factors_percentages = [(df_combined[fac].sum() / total_bad_hours) * 100 for fac in bad_factors]

    # Define hover text for good and Inefficient Driving segments
    good_hover_text = "<br>".join([f"{factor}: {percent:.2f}%" for factor, percent in zip(good_factors, good_factors_percentages)])
    bad_hover_text = "<br>".join([f"{factor}: {percent:.2f}%" for factor, percent in zip(bad_factors, bad_factors_percentages)])

    # Create the bar chart with two segments (Good Driving and Inefficient Driving)
    fig_good_bad = go.Figure(data=[
        go.Bar(
            y=["Driving Behavior"],
            x=[good_percentage],
            name="Good Driving",
            orientation='h',
            marker=dict(
                color="rgba(0, 128, 0, 0.8)",  # Green with transparency
                line=dict(color="rgba(0, 100, 0, 1)", width=2),  # Darker green border
            ),
            hoverinfo="text",
            hovertext=f"{good_hover_text}",  # Show breakdown only on hover
            text=f"<b>Good Driving</b>: {good_percentage:.2f}%",  # Display only the main percentage with label
            textposition='inside'  # Center the text inside the bar
        ),
        go.Bar(
            y=["Driving Behavior"],
            x=[bad_percentage],
            name="Inefficient Driving",
            orientation='h',
            marker=dict(
                color="rgba(255, 0, 0, 0.8)",  # Red with transparency
                line=dict(color="rgba(180, 0, 0, 1)", width=2),  # Darker red border
            ),
            hoverinfo="text",
            hovertext=f"{bad_hover_text}",  # Show breakdown only on hover
            text=f"<b>Inefficient Driving</b>: {bad_percentage:.2f}%",  # Display only the main percentage with label
            textposition='inside'  # Center the text inside the bar
        )
    ])

    # Update layout for aesthetics
    fig_good_bad.update_layout(
        title="Good vs. Inefficient Driving",
        barmode='stack',
        plot_bgcolor='white',
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, showline=False),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        showlegend=False,
        margin=dict(l=50, r=50, t=50, b=50),
    )

    # Update traces to adjust bar height and round corners
    fig_good_bad.update_traces(marker_line_width=0, width=0.4)  # Set bar height
    fig_good_bad.update_traces(marker=dict(line=dict(width=1.5)))  # Set border width for 3D effect

    # Make a sorted copy to ensure original dataframe remains unchanged
    df_sorted_good = df_combined.copy()
    df_sorted_good = df_sorted_good.sort_values(by='Total Engine Hours', ascending=True)

    # Good driving behaviors per Chassis ID stacked Bar
    good_factors = ['Total Coasting Hours', 'Total Top Gear Hours', 'Total Cruise Control Hours', 'Total Sweetspot Hours']

    # Calculate percentage AFTER sorting
    for factor in good_factors:
        df_sorted_good[f'{factor} %'] = (df_sorted_good[factor] / df_sorted_good['Total Driving Hours']) * 100

    # Create traces for each good driving behavior
    fig_good_f = go.Figure()
    fig_good_f.add_trace(go.Bar(y=df_sorted_good['Chassis ID'], x=df_sorted_good['Total Coasting Hours %'], name="Coasting Hours", orientation='h', marker=dict(color="rgba(0, 128, 0, 0.8)") ))
    fig_good_f.add_trace(go.Bar(y=df_sorted_good['Chassis ID'], x=df_sorted_good['Total Top Gear Hours %'], name="Top Gear Hours", orientation='h', marker=dict(color="rgba(34, 139, 34, 0.8)") ))
    fig_good_f.add_trace(go.Bar(y=df_sorted_good['Chassis ID'], x=df_sorted_good['Total Cruise Control Hours %'], name="Cruise Control Hours", orientation='h', marker=dict(color="rgba(50, 205, 50, 0.8)") ))
    fig_good_f.add_trace(go.Bar(y=df_sorted_good['Chassis ID'], x=df_sorted_good['Total Sweetspot Hours %'], name="Sweetspot Hours", orientation='h', marker=dict(color="rgba(144, 238, 144, 0.8)") ))

    # Update layout for better aesthetics
    fig_good_f.update_layout(
        title="Good Driving Behavior as % of Total Driving Hours per Vehicle",
        barmode='stack',
        plot_bgcolor='white',
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, showline=False),
        yaxis=dict(showgrid=False, zeroline=False),
        showlegend=True,
        margin=dict(l=100, r=50, t=50, b=50),  # Space for chassis ID labels on y-axis
    )

    # Make a sorted copy to ensure original dataframe remains unchanged
    df_sorted_bad = df_combined.copy()
    df_sorted_bad = df_sorted_bad.sort_values(by='Total Engine Hours', ascending=True)

    # Inefficient Driving behaviors
    bad_factors = ['Total Engine Overrev Hours', 'Total Overspeed Hours', 'Total Excessive Idling Hours']

    # Calculate the percentage of each Inefficient Driving factor relative to total driving hours for each chassis
    for factor in bad_factors:
        df_sorted_bad[f'{factor} %'] = (df_sorted_bad[factor] / df_sorted_bad['Total Driving Hours']) * 100

    # Create traces for each Inefficient Driving behavior with different shades of red
    fig_bad_f = go.Figure()
    fig_bad_f.add_trace(go.Bar(y=df_sorted_bad['Chassis ID'], x=df_sorted_bad['Total Engine Overrev Hours %'], name="Engine Overrev Hours", orientation='h', marker=dict(color="rgba(255, 99, 71, 0.8)") ))
    fig_bad_f.add_trace(go.Bar(y=df_sorted_bad['Chassis ID'], x=df_sorted_bad['Total Overspeed Hours %'], name="Overspeed Hours", orientation='h', marker=dict(color="rgba(220, 20, 60, 0.8)") ))
    fig_bad_f.add_trace(go.Bar(y=df_sorted_bad['Chassis ID'], x=df_sorted_bad['Total Excessive Idling Hours %'], name="Excessive Idling Hours", orientation='h', marker=dict(color="rgba(139, 0, 0, 0.8)") ))

    # Update layout for aesthetics and to flip the bar direction
    fig_bad_f.update_layout(
        title="Inefficient Driving Behavior as % of Total Driving Hours per Vehicle",
        barmode='stack',
        plot_bgcolor='white',
        xaxis=dict(
            showgrid=False,
            showticklabels=False,
            zeroline=False,
            showline=False,
            autorange='reversed'  # Flip the direction of the bars
        ),
        yaxis=dict(showgrid=False, zeroline=False, side='right'),
        showlegend=True,
        legend=dict(x=-0.2, y=1),  # Move legend to the right side
        margin=dict(l=50, r=150, t=50, b=50)  # Adjust margin for flipped layout
    )

    # Calculate Normal Idling Hours
    df_combined['Total Normal Idling Hours'] = df_combined['Total Idling Hours'] - df_combined['Total Excessive Idling Hours']
    # Calculate each idling time across all vehicles
    total_idling_hours = df_combined['Total Idling Hours'].sum()
    total_nidling_hours = df_combined['Total Normal Idling Hours'].sum()
    total_eidling_hours = df_combined['Total Excessive Idling Hours'].sum()
    # Calculate percentages of normal and excessive idling
    normal_percentage = (total_nidling_hours / total_idling_hours) * 100
    excessive_percentage = (total_eidling_hours / total_idling_hours) * 100

    # Calculate per-vehicle percentages
    df_combined['Total Normal Idling Hours %'] = (df_combined['Total Normal Idling Hours'] / df_combined['Total Idling Hours']) * 100
    df_combined['Total Excessive Idling Hours %'] = (df_combined['Total Excessive Idling Hours'] / df_combined['Total Idling Hours']) * 100

    # Define hover text for each chassis ID
    nidling_hover_text = "<br>".join([f"Chassis {row['Chassis ID']}: {row['Total Normal Idling Hours %']:.2f}%" for _, row in df_combined.iterrows()])
    eidling_hover_text = "<br>".join([f"Chassis {row['Chassis ID']}: {row['Total Excessive Idling Hours %']:.2f}%" for _, row in df_combined.iterrows()])

    # Create the bar chart with a 3D effect
    fig_normal_excessive = go.Figure(data=[
        go.Bar(
            y=["Idling Type"],
            x=[normal_percentage],
            name="Normal Idling",
            orientation='h',
            marker=dict(
                color="rgba(255, 225, 102, 0.8)",  # Yellow with transparency
                line=dict(color="rgba(255, 204, 0, 1)", width=2),  # Darker yellow border for 3D effect
            ),
            hoverinfo="text",
            hovertext=f"{nidling_hover_text}",  # Show breakdown only on hover
            text=f"<b>Normal Idling</b>: {normal_percentage:.2f}%",  # Display only the main percentage with label
            textposition='inside'  # Center the text inside the bar
        ),
        go.Bar(
            y=["Idling Type"],
            x=[excessive_percentage],
            name="Excessive Idling",
            orientation='h',
            marker=dict(
                color="rgba(218, 165, 32, 0.8)",  # Green with transparency
                line=dict(color="rgba(184, 134, 11, 1)", width=2),  # Darker yellow border for 3D effect
            ),
            hoverinfo="text",
            hovertext=f"{eidling_hover_text}",  # Show breakdown only on hover
            text=f"<b>Excessive Idling</b>: {excessive_percentage:.2f}%",  # Display only the main percentage with label
            textposition='inside'  # Center the text inside the bar
        ),
    ])

    # Update layout for aesthetics
    fig_normal_excessive.update_layout(
        title="Normal vs Excessive Idling as a Percentage of Total Idling Hours",
        barmode='stack',
        plot_bgcolor='white',
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, showline=False),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        showlegend=False,
        margin=dict(l=50, r=50, t=50, b=50),
    )

    # Update traces to adjust bar height and round corners
    fig_normal_excessive.update_traces(marker_line_width=0, width=0.3)  # Set bar height
    fig_normal_excessive.update_traces(marker=dict(line=dict(width=1.5)))  # Set border width for 3D effect

    df_sorted_i = df_combined.copy()
    df_sorted_i = df_sorted_i.sort_values(by='Total Engine Hours', ascending=True)

    # Calculate the percentage of each normal idling records relative to total idling hours for each chassis
    df_sorted_i['Total Normal Idling Hours %'] = (df_sorted_i['Total Normal Idling Hours'] / df_sorted_i['Total Idling Hours']) * 100

    # Create traces for each good driving behavior with different shades of green
    fig_normalidling = go.Figure()
    fig_normalidling.add_trace(go.Bar(y=df_sorted_i['Chassis ID'], x=df_sorted_i['Total Normal Idling Hours %'], name="Normal Idling", orientation='h', marker=dict(color="rgba(255, 225, 102, 0.8)") ))

    # Update layout for aesthetics
    fig_normalidling.update_layout(
        title="Normal Idling as % of Total Idling Hours per Vehicle",
        barmode='stack',
        plot_bgcolor='white',  # White background for clean look
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, showline=False),
        yaxis=dict(showgrid=False, zeroline=False),
        showlegend=False,
        margin=dict(l=100, r=50, t=50, b=50),  # Space for chassis ID labels on y-axis
    )

    # Calculate the percentage of each normal idling records relative to total idling hours for each chassis
    df_sorted_i['Total Excessive Idling Hours %'] = (df_sorted_i['Total Excessive Idling Hours'] / df_combined['Total Idling Hours']) * 100

    # Create traces for each good driving behavior with different shades of green
    fig_excessiveidling = go.Figure()
    fig_excessiveidling.add_trace(go.Bar(y=df_sorted_i['Chassis ID'], x=df_sorted_i['Total Excessive Idling Hours %'], name="Excessive Idling", orientation='h', marker=dict(color="rgba(218, 165, 32, 0.8)") ))

    # Update layout for aesthetics
    fig_excessiveidling.update_layout(
        title="Excessive Idling as % of Total Idling Hours per Vehicle",
        barmode='stack',
        plot_bgcolor='white',  # White background for clean look
        xaxis=dict(
            showgrid=False,
            showticklabels=False,
            zeroline=False,
            showline=False,
            autorange='reversed'  # Flip the direction of the bars
        ),
        yaxis=dict(showgrid=False, zeroline=False, side='right'),
        showlegend=False,
        margin=dict(l=50, r=150, t=50, b=50)  # Adjust margin for flipped layout
    )

    return [fig_total_vehicles, fig_avg_speed, fig_total_engine_hours, fig_total_distance, fig_total_fuel_consumed, fig_fuel_saving, efdonutcombined_fig, 
            efbarcombined_fig, fig_sunburst, fig_histogram, fig_good_bad, fig_good_f, fig_bad_f,
            fig_normal_excessive, fig_normalidling, fig_excessiveidling]


# OpenAI API Key setup (replace with your actual API key)
import os
openai.api_key = os.getenv("OPENAI_API_KEY")
# Function to fetch AI-generated insights for each visual type
def fetch_ai_insights(df):
    # Convert the DataFrame into a summarized string for GPT-4o-mini to understand
    data_summary = df.to_string()

    # Create a shorter prompt to generate insights based on the data and visual type
    prompt = f"""
    You are a Data Analyst at UD Trucks MEENA, analyzing truck fleet telematics data reports. There are 3 types of reports: Fleet Overview, Fuel Utilization, and Driving Behavior. Each report has been visualized to give actionable insights. For each report there are different types of visuals which are outlined below:
    Fuel Utilization Breakdown (Driving, PTO, Idling (L)) - pie chart, Fuel Utilization Breakdown by Chassis ID - stacked bar chart (ordered starting with highest fuel usage), 
    Engine Hours Breakdown (Total Driving, PTO, Idling Hours) - pie chart, Engine Hours Breakdown by Chassis ID - stacked bar chart (ordered starting with highest engine hours), 
    Good Driving Behavior Fuel Breakdown by Chassis ID (Ordered by Driving Efficiency %) - 100% stacked bar chart (Coasting, Top Gear, Sweetspot, Cruise Control (L)), 
    Good Driving Behavior Hour Breakdown by Chassis ID (Ordered by Driving Efficiency %) - 100% stacked bar chart (Total Coasting, Top Gear, Sweetspot, Cruise Control Hours)
    Fuel Efficiency (km/L vs. L/h) - 2 line graph, Fuel vs AdBlue Consumed per Chassis ID - bar (fuel consumed (L)) and line graph (Adblue Consumed (L)).
    ### Data Summary:
    {data_summary}
    
    Analyze the data, determine the type of report, and provide actionable insights to help the fleet manager optimize business operations based on the provided data.
    Please return the insights in the following labeled format:
    1. **Fuel Utilization Breakdown**: [Your insight here]
    2. **Fuel Utilization Breakdown by Chassis ID**: [Your insight here]
    3. **Engine Hours Breakdown**: [Your insight here]
    4. **Engine Hours Breakdown by Chassis ID**: [Your insight here]
    5. **Good Driving Behavior Fuel Breakdown by Chassis ID (Ordered by Driving Efficiency %)**: [Your insight here]
    6. **Good Driving Behavior Hour Breakdown by Chassis ID (Ordered by Driving Efficiency %)**: [Your insight here]
    7. **Fuel Efficiency (km/L vs. L/h)**: [Your insight here]
    8. **Fuel vs AdBlue Consumed per Chassis ID**: [Your insight here]

    Use the Chassis IDs whenever referring to the data and ensure it is accurate. Make sure to write in paragraphs (no bulletpoints or other sorts of formatting).
    """

    # Call the OpenAI API using the GPT-4o-mini model to generate insights
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini-2024-07-18",  # Specify the GPT-4o-mini model
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1000  # Limit the response to around 1000 tokens to control cost
    )
    # Extract and return the AI-generated insights
    return response['choices'][0]['message']['content']


def parse_insights(response_text):
    # Define titles to look for (strip any extra characters in titles to make matching easier)
    titles = [
        'Fuel Utilization Breakdown', 
        'Fuel Utilization Breakdown by Chassis ID', 
        'Engine Hours Breakdown', 
        'Engine Hours Breakdown by Chassis ID', 
        'Good Driving Behavior Fuel Breakdown by Chassis ID (Ordered by Driving Efficiency %)',
        'Good Driving Behavior Hour Breakdown by Chassis ID (Ordered by Driving Efficiency %)',
        'Fuel Efficiency (km/L vs. L/h)',
        'Fuel vs AdBlue Consumed per Chassis ID'
    ]
    
    # Create an empty dictionary to store insights
    insights_dict = {}

    # Loop through the titles and extract the insights following each title
    for i, title in enumerate(titles):
        # Try to find the section starting with the current title
        start_index = response_text.find(title)
        
        if start_index != -1:
            # Find the end of this section (before the next title, or the end of the text)
            if i < len(titles) - 1:
                # Find the next title and ensure to search from after the current title
                next_title = titles[i + 1]
                end_index = response_text.find(next_title, start_index + len(title))
            else:
                # For the last title, capture everything until the end of the response
                end_index = len(response_text)

            # Extract the insight text and clean it up
            insight_text = response_text[start_index + len(title):end_index].strip()

            # Clean any unwanted characters like '**:', numbers, and extra symbols
            cleaned_insight = re.sub(r'^\*\*:\s*|\d+\.\s*\*\*', '', insight_text).strip()

            # Store the cleaned insight
            insights_dict[title] = cleaned_insight if cleaned_insight else "No insight available"
        else:
            # If the title is not found, set the default message
            insights_dict[title] = "No insight available"
    
    return insights_dict

# Global variable to store processed data after file upload
stored_data_summary = ""

# Function to process and store data after the first question
def process_and_store_data(contents, filename):
    global stored_data_summary
    df = process_fuel_utilization(contents, filename)
    stored_data_summary = df.to_string()
    return df

# Function to handle user questions using GPT with conversation history and optimized data handling
def fetch_ai_answer(question, conversation_history, is_initial_question=False, df=None):
    global stored_data_summary  # Use the global variable to store the initial data summary

    # Ensure conversation_history is a list
    if isinstance(conversation_history, str):
        conversation_history = []

    # Prepare the messages to send to GPT, including conversation history
    messages = [{"role": "system", "content": "You are a helpful data analyst at UD Trucks MEENA."}]

    # Add previous conversation history (if it exists)
    if isinstance(conversation_history, list):
        for entry in conversation_history:
            if isinstance(entry, dict) and 'role' in entry and 'content' in entry:
                messages.append({"role": entry['role'], "content": entry['content']})

    # If it's the first question, include the data summary in the prompt
    if is_initial_question and df is not None:
        # Convert the DataFrame into a summarized string for GPT-4o-mini to understand
        full_dataset = prepare_full_dataset_for_gpt(df)

        prompt = f"""
        The user needs actionable insights based on the data and suggestions on how to optimize their fleet operations. Avoid providing obvious statements or general 
        calculations involved in analyzing the data for your answer. Be precise and to-the-point when answering. Make sure to write in paragraphs (no bulletpoints or other sorts of formatting). Dataset:
        {full_dataset}

        Question: "{question}"
        """
    else:
        # For subsequent questions, avoid sending the entire dataset but refer to it in context
        prompt = f"""
        The user is asking a follow-up question based on the previously provided complete dataset. Avoid providing obvious statements or general 
        calculations. Be precise and refer to the existing dataset when answering. Make sure to write in paragraphs (no bulletpoints or other sorts of formatting).

        Question: "{question}"
        """

    messages.append({"role": "user", "content": prompt})

    # Call GPT to get the answer
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini-2024-07-18",
        messages=messages,
        max_tokens=1000  # Adjust the token limit as needed
    )

    # Extract the response
    answer = response['choices'][0]['message']['content']

    # Append answer to conversation history
    conversation_history.append({"role": "assistant", "content": answer})

    return answer, conversation_history

# Layout and app
navbar = html.Div([
    # Navbar container
    html.Div([
        # Left side: Logo and Title
        html.Div([
            html.Img(
                src="https://1000logos.net/wp-content/uploads/2021/01/UD-logo-480x400.png",
                style={'height': '50px', 'padding': '5px'}
            ),
            html.H1(
                "UD Trucks",
                style={
                    'color': 'white',
                    'font-size': '24px',
                    'padding-left': '15px',
                    'padding-top': '10px',
                    'margin': '0'
                }
            )
        ], style={'display': 'flex', 'align-items': 'center'}),

        # Right side: User Manual Button
        html.Div([
            html.A(
                html.Button(
                    "Video Demo",
                    style={
                        'color': 'white',
                        'background-color': '#28a745',  # Green color for differentiation
                        'border': 'none',
                        'border-radius': '5px',
                        'padding': '10px 20px',
                        'font-size': '16px',
                        'cursor': 'pointer',
                        'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                        'margin-right': '10px'  # Add spacing between buttons
                    }
                ),
                href="./assets/UD Telematics Dashboard Demo.mp4",  # Link to your local video file
                target="_blank",  # Opens in a new tab
                style={'text-decoration': 'none'}
            ),
            html.A(
                html.Button(
                    "User Manual",
                    style={
                        'color': 'white',
                        'background-color': '#007bff',
                        'border': 'none',
                        'border-radius': '5px',
                        'padding': '10px 20px',
                        'font-size': '16px',
                        'cursor': 'pointer',
                        'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)'
                    }
                ),
                href="https://drive.google.com/file/d/1Surt21UCybDEPZBuEm0fyvYiHjSNkomE/preview",
                target="_blank",
                style={'text-decoration': 'none'}
            )
        ], style={'margin-left': 'auto', 'margin-right': '20px'})  # Adjusted alignment
    ], style={
        'display': 'flex',
        'align-items': 'center',
        'justify-content': 'space-between',
        'width': '100%',
        'padding': '0 10px',  # Padding added for better alignment
        'box-sizing': 'border-box'
    })
], style={
    'background-color': 'black',
    'height': '60px',
    'width': '100vw',
    'color': 'white',
    'position': 'fixed',
    'top': '0',
    'left': '0',
    'zIndex': '1000',
    'box-shadow': '0px 2px 5px rgba(0, 0, 0, 0.2)'
})

# Dash Layout (Add multiple file upload options and buttons)
app.layout = html.Div([
    html.Div(className="background"),
    html.Div([
        navbar,
        html.Div(style={'height': '80px'}),
        html.H1("Welcome to My UD Fleet (Telematics) Dashboard", style={'text-align': 'center', 'margin-top': '80px'}),

        # Upload for FO and FU reports
        html.Div([
            # Fleet Overview Upload Section
            dcc.Upload(
                id='upload-data-fo',
                children=html.Div([html.Div(['Attach ', html.A('FLEET OVERVIEW Report')], className='upload-button-text')]),
                style={
                    'width': '25%', 'height': '60px', 'lineHeight': '60px', 
                    'borderWidth': '2px', 'borderStyle': 'solid', 'borderRadius': '10px', 
                    'textAlign': 'center', 'margin': 'auto', 'backgroundColor': '#2c2c2c', 
                    'borderColor': 'white', 'color': '#eeeeee', 'fontSize': '16px', 
                    'fontWeight': 'bold', 'cursor': 'pointer', 'transition': 'all 0.3s ease'
                },
                multiple=False
            ),
            html.Div([
                html.Div(id='fo-upload-status', style={
                    'backgroundColor': '#f0fff0', 'color': 'green', 
                    'padding': '10px', 'fontSize': '16px', 'fontWeight': 'bold', 
                    'borderRadius': '5px', 'boxShadow': '0px 4px 8px rgba(0, 128, 0, 0.2)', 
                    'maxWidth': '80%', 'textAlign': 'left', 'display': 'inline-block'
                }),
                html.Button(
                    html.I(className="fas fa-trash-alt remove-button-icon"),  # Trash icon for Fleet Overview
                    id="remove-fo-file",
                    className="remove-button",
                    style={
                        'backgroundColor': '#b22222', 'color': 'white', 
                        'border': 'none', 'borderRadius': '5px', 'padding': '10px', 
                        'cursor': 'pointer', 'fontSize': '16px', 'width': '40px', 
                        'height': '40px', 'display': 'inline-flex', 'alignItems': 'center', 
                        'justifyContent': 'center', 'marginLeft': '5px'
                    }
                )
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '1px', 'marginTop': '10px', 'width': '100%', 'maxWidth': '600px', 'margin': 'auto'}),
            dcc.Store(id='reset-fo-upload', data=False),
        ], style={'marginBottom': '20px'}),
        
        html.Div([
            # Fuel Utilization Upload Section
            dcc.Upload(
                id='upload-data-fu',
                children=html.Div([html.Div(['Attach ', html.A('FUEL UTILIZATION Report')], className='upload-button-text')]),
                style={
                    'width': '25%', 'height': '60px', 'lineHeight': '60px', 
                    'borderWidth': '2px', 'borderStyle': 'solid', 'borderRadius': '10px', 
                    'textAlign': 'center', 'margin': 'auto', 'backgroundColor': '#2c2c2c', 
                    'borderColor': 'white', 'color': '#eeeeee', 'fontSize': '16px', 
                    'fontWeight': 'bold', 'cursor': 'pointer', 'transition': 'all 0.3s ease'
                },
                multiple=False
            ),
            html.Div([
                html.Div(id='fu-upload-status', style={
                    'width': '40%', 'height': '60px', 'lineHeight': '60px', 'borderWidth': '2px',
                    'borderStyle': 'solid', 'borderRadius': '10px', 'textAlign': 'center',
                    'margin': 'auto', 'background-color': '#2c2c2c', 'border-color': 'white',
                    'color': '#eeeeee', 'font-size': '16px', 'font-weight': 'bold',
                    'cursor': 'pointer', 'margin-top': '20px', 'margin-bottom': '20px',
                    'transition': 'all 0.3s ease'
                }),
                html.Button(
                    html.I(className="fas fa-trash-alt remove-button-icon"),  # Trash icon for Fleet Overview
                    id="remove-fu-file",
                    className="remove-button",
                    style={
                        'backgroundColor': '#b22222', 'color': 'white', 
                        'border': 'none', 'borderRadius': '5px', 'padding': '10px', 
                        'cursor': 'pointer', 'fontSize': '16px', 'width': '40px', 
                        'height': '40px', 'display': 'inline-flex', 'alignItems': 'center', 
                        'justifyContent': 'center', 'marginLeft': '5px'
                    }
                )
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '1px', 'marginTop': '10px', 'width': '100%', 'maxWidth': '600px', 'margin': 'auto'}),
            dcc.Store(id='reset-fu-upload', data=False),
        ], style={'marginBottom': '20px'}),
        # Analyze Button
        html.Button('Analyze', id='analyze-button', n_clicks=0, style={
                'display': 'block', 
                'margin': '20px auto', 
                'background-color': '#8dc63f', 
                'color': '#1c1c1c', 
                'border-radius': '10px', 
                'padding': '15px 30px', 
                'border': 'none', 
                'font-size': '18px', 
                'font-weight': 'bold',
                'box-shadow': '0px 4px 12px rgba(0, 0, 0, 0.2)', 
                'cursor': 'pointer',
                'transition': 'all 0.3s ease'
            }),
        html.Div(style={'height': '120px'}),
        html.Div(
            dcc.Loading(
                id="loading-icon",
                type="circle",
                children=[
                    # Add a clear white background div for the report
                    html.Div(
                        id="report-section",
                        children=[
                            html.Div(id='report-type-title', style={'text-align': 'center', 'font-size': '24px', 'margin-top': '20px', 'margin-bottom': '20px'}),
                            html.Div(
                                id="filter-section",
                                children=[
                                    html.Div([
                                        html.Label("Model", style={"margin-right": "10px"}),
                                        dcc.Dropdown( id="filter-model", options=[], placeholder="Select Model", style={"width": "200px"}),
                                        html.Label("Truck Type", style={"margin-right": "10px", "margin-left": "20px"}),
                                        dcc.Dropdown( id="filter-truck-type", options=[], placeholder="Select Truck Type", style={"width": "200px"}),
                                        html.Label("Axle Configuration", style={"margin-right": "10px", "margin-left": "20px"}),
                                        dcc.Dropdown( id="filter-axle-config", options=[], placeholder="Select Axle Configuration", style={"width": "200px"}),
                                    ], style={"display": "flex", "align-items": "center", "justify-content": "center", "margin-bottom": "20px", "gap": "10px"}),
                                ],
                                style={"display": "none", "margin-top": "20px"}  # Hidden by default
                            ),
                            html.Div(id='visual-content', style={'margin-top': '50px'}),
                            html.Div(id='data-table', style={'margin-top': '30px', 'width': '90%', 'margin-left': 'auto', 'margin-right': 'auto'}),

                            # Conditional display of fuel cost section and savings output
                            dcc.Loading(
                                id="loading-fuel-cost",
                                children=[
                                    html.Div([
                                        dcc.Input(
                                            id="fuel-cost-input",
                                            type="number",
                                            placeholder="Enter current fuel cost in selected currency",
                                            style={"margin-right": "10px", "width": "200px", "padding": "10px", "font-size": "16px", "border": "1px solid #ccc", "border-radius": "5px"}
                                        ),
                                        dcc.Dropdown(
                                            id="currency-dropdown",
                                            options=[
                                                {"label": "AED (د.إ)", "value": "AED"},
                                                {"label": "USD ($)", "value": "USD"},
                                                {"label": "ZAR (R)", "value": "ZAR"},
                                                {"label": "BHD (ب.د)", "value": "BHD"},
                                                {"label": "QAR (ر.ق)", "value": "QAR"},
                                                {"label": "JPY (¥)", "value": "JPY"},
                                            ],
                                            value="AED",
                                            clearable=False,  # Prevent clearing the selection
                                            searchable=False,
                                            style={"width": "150px", "padding": "10px", "font-size": "16px", "border": "1px solid #ccc", "border-radius": "5px"}
                                        ),
                                    ], style={"display": "none", "align-items": "center", "justify-content": "center", "margin-bottom": "20px"}, id="fuel-cost-section"),  # Initially hidden
                                    # Add the Calculate button
                                    html.Div(
                                        html.Button(
                                            "Calculate", 
                                            id="calculate-button", 
                                            style={"padding": "10px 20px", "font-size": "16px", "background-color": "black", "color": "white", "border": "none", "border-radius": "5px","text-align": "center"}
                                        ), style={"display": "none", "justify-content": "center", "margin-bottom": "20px"}
                                    ),
                                    html.Div(
                                        id="fuel-cost-saving",
                                        style={"font-size": "24px", "font-weight": "bold", "text-align": "center", "color": "#4CAF50", "font-family": "Arial, sans-serif", "margin-top": "20px", "display": "none"}
                                    ),
                                ]
                            ),

                            # Placeholders for the side-panel and info buttons to avoid callback errors
                            html.Div(id="side-panel", className="side-panel", style={"display": "none"}, children=[
                                html.Span("✖", id="close-panel", className="close-btn"),
                                html.H5(id="panel-title", children="Placeholder Title"),
                                html.P(id="panel-content", children="Placeholder Content")
                            ]),

                            # Info buttons placeholders for initial layout
                            html.Div([
                                html.A("ℹ️", id="info-eh_split", className="insight-button", style={"display": "none"}),
                                html.A("ℹ️", id="info-eh_bd", className="insight-button", style={"display": "none"}),
                                html.A("ℹ️", id="info-cf_split", className="insight-button", style={"display": "none"}),
                                html.A("ℹ️", id="info-cf_bd", className="insight-button", style={"display": "none"}),
                                html.A("ℹ️", id="info-gb_bg", className="insight-button", style={"display": "none"}),
                                html.A("ℹ️", id="info-ne_bg", className="insight-button", style={"display": "none"})
                            ]),

                            # Chatbot container (hidden by default until file is uploaded)
                            html.Div(id="chatbot-container", children=[
                                html.H3("Ask a Question About Your Data", style={'text-align': 'center', 'margin-top': '50px'}),
                                html.Div([
                                    dcc.Input(id="user-input", type="text", placeholder="Ask a question...", 
                                            style={'width': '80%', 'padding': '10px', 'border': '1px solid #ccc', 'border-radius': '5px'}),
                                    html.Button('Submit', id='submit-button', n_clicks=0, 
                                                style={'display': 'block', 'margin': '20px auto', 'background-color': '#007bff', 'color': 'white', 'border-radius': '5px', 'padding': '10px 20px', 'border': 'none'}),
                                ], style={'text-align': 'center'}),
                                html.Div(id='chatbot-response', style={'text-align': 'center', 'margin-top': '20px', 'font-size': '18px', 'padding': '20px', 'border': '1px solid #ddd', 'border-radius': '5px', 'background-color': '#f9f9f9'}),
                            ], style={'display': 'none'})  # Initially hidden
                        ],
                        style={
                            'background-color': 'white',  # White background for this section
                            'padding': '20px',           # Padding to prevent content from touching edges
                            'min-height': '100vh',       # Ensure the section takes at least the full viewport height
                        }
                    )
                ], fullscreen=True, style={'margin-top': '50px'}  # Add space before this section
            )
        ),
    ])
])

# Inline hover CSS in app.index_string
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Telematics Dashboard</title>
        {%favicon%}
        {%css%}
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css" rel="stylesheet">
        <style>
            /* Enhanced styling for the side-panel */
            .side-panel {
                position: fixed;
                top: 0;
                right: 0;
                width: 350px;
                height: 100%;
                background-color: #f8f9fa;
                border-left: 1px solid #e0e0e0;
                box-shadow: -4px 0 10px rgba(0, 0, 0, 0.15);
                padding: 20px;
                display: none;  /* Hidden initially */
                overflow-y: auto;
                z-index: 1100;
                transition: transform 0.3s ease-in-out;
                transform: translateX(100%);
            }
            
            /* Show class for sliding effect */
            .side-panel.show {
                display: block;
                transform: translateX(0%);
            }

            /* Styling for the insights header and content */
            .side-panel h5 {
                font-size: 20px;
                color: #333;
                margin-bottom: 15px;
            }
            
            .side-panel p {
                font-size: 16px;
                line-height: 1.6;
                color: #555;
            }

            /* Close button styling */
            .close-btn {
                cursor: pointer;
                font-size: 18px;
                color: #888;
                position: absolute;
                top: 20px;
                right: 20px;
                transition: color 0.3s;
            }

            .close-btn:hover {
                color: #333;
            }

            .insight-button {
                    cursor: pointer;
                    color: #ffffff;
                    background-color: #007bff;
                    padding: 4px 10px;
                    border-radius: 50%;
                    font-size: 16px;
                    transition: background-color 0.3s ease;
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    margin-left: 10px;
                    text-decoration: none;
                }
                .insight-button:hover {
                    background-color: #0056b3;
                }

            /* Style for responsive visuals container */
            .graph-container {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                justify-content: center;
                width: 100%;
                max-width: 100%;  /* Ensures it doesn't overflow */
            }

            /* Style for the Graph itself to be fully responsive */
            .responsive-graph {
                width: 100%;
                height: auto;
            }

            .upload-button-text:hover {
                background-color: #3c3c3c !important;  /* Lighter gray on hover */
                color: #ffffff !important;
                border-radius: 8px;
            }
            #analyze-button:hover {
                background-color: #a1d76f !important;  /* Lighter green on hover */
            }

            .remove-button {
                background-color: #8B0000; /* Darker red */
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px;
                cursor: pointer;
                font-size: 16px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 40px; /* Square button */
                height: 40px;
                transition: background-color 0.3s ease;
            }

            .remove-button:hover {
                background-color: #a80000; /* Slightly darker red on hover */
            }

            .remove-button-icon {
                font-size: 18px; /* Icon size */
                color: white;
            }

            /* Adjust the flex container for better spacing */
            #fo-upload-status,
            #fu-upload-status {
                margin: 0; /* Reset margins */
                padding: 10px;
                background-color: #f0fff0; /* Light green for success */
                border-radius: 5px;
                box-shadow: 0px 4px 8px rgba(0, 128, 0, 0.2);
                max-width: 400px; /* Constrain width */
                text-align: left;
            }

            .navbar-button:hover {
                background-color: #0056b3; /* Darker blue on hover */
            }

            /* Background container to hold the images */
            .background {
                position: fixed;
                top: 60px; /* Adjust to align below the navbar */
                left: 0;
                width: 100%;
                height: calc(100vh - 60px); /* Full screen height minus navbar */
                z-index: -1; /* Ensure it stays behind all content */
                background-size: cover;
                background-repeat: no-repeat;
                background-position: center center;
                animation: backgroundTransition 12s infinite; /* Adjust timing as needed */
                opacity: 0.4; /* Adjust transparency for better content visibility */
            }

            /* Keyframes for transitioning between images */
            @keyframes backgroundTransition {
                0% {
                    background-image: url('/assets/Quester.jpg'); /* Replace with your image paths */
                }
                33% {
                    background-image: url('/assets/Quester.jpg');
                }
                66% {
                    background-image: url('/assets/Quester2.jpg');
                }
                100% {
                    background-image: url('/assets/Quester3.jpg'); /* Loop back to the first image */
                }
            }

            /* Default white background below the Analyze button */
            .scroll-default-background {
                background-color: white;
                height: auto;
                padding-top: calc(100vh - 60px); /* Ensure white starts below the transitioning background */
            }

            /* Ensure full-screen background behavior for the initial sections */
            .background-image {
                width: 100%;
                height: 100vh; /* Adjust to always cover the full viewport height */
                background-size: cover;
                background-position: center;
                background-repeat: no-repeat;
                position: relative;
            }

            /* White background after images */
            #report-section {
                background-color: white;
            }

        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

# Define sample insights to show in the sliding panel
sample_insights = {
    "ehs": """
        <h3>Description</h3>
        <ul>
            <li>This donut chart visualizes the distribution of total fleet engine hours into various driving behaviors. The total engine hours are mainly divided into 3 main categories: Driving, Idling, and PTO.</li>
            <li>Driving hours include Good Driving behaviors (such as Top Gear, Coasting, Sweetspot, and Cruise Control), Neutral Driving, and Some of Inefficient Driving Behaviors (Engine Overrev and Overspeeding).</li>
            <li>Idling hours include Normal Idling and Excessive Idling.</li>
            <li>Each segment's percentage is displayed along with its respective color-coded legend.</li>
            <li>These segments can be hidden by clicking the legends, for better clarity.</li>
        </ul>
        
        <h3>Interpretation</h3>
        <ul>
            <li>Users can easily identify the portion of time spent on productive driving behaviors (Good Driving) versus non-productive activities like Excessive Idling and Inefficient Driving.</li>
            <li>The chart helps fleet managers focus on minimizing time spent on unproductive or Inefficient Driving behaviors to improve overall operational efficiency.</li>
        </ul>

        <h3>Note</h3>
        <ul>
            <li>Excessive Idling = Vehicle in Idling mode for more than 15minutes …. Idling ≥ 15minutes</li>
            <li>Overspeeding = Vehicle speed greater than 90 KM/H for 20 seconds or more taken as Overspped</li>
            <li>Engine Overrevving = Vehicle RPM’s greater than 2,500 RPM for over 5 seconds taken as Overrevving of Engine</li>
        </ul>
    """,
    "ehbd": """
        <h3>Description</h3>
        <ul>
            <li>This stacked bar chart breaks down total engine hours by individual vehicles (Chassis IDs) into Good Driving, Neutral Driving, Inefficient Driving behaviors, Idling, and PTO.</li>
            <li>Each color in the stack represents a specific category, and the total hours by the Chassis ID are annotated above each bar, along with the average fuel efficiency in m/L.</li>
            <li>These segments can be hidden by clicking the legends, for better clarity.</li>
        </ul>
        
        <h3>Interpretation</h3>
        <ul>
            <li>The Chassis IDs are arranged in ascending order of the highest good driving hours and the lowest Inefficient Driving hours as a percentage of the total engine hours.</li>
            <li>The visualization highlights which vehicles exhibit higher engine hours for bad behaviors, such as Excessive Idling or Engine Overrev.</li>
            <li>Fleet managers can use this information to identify vehicles needing attention or driver training to reduce wasteful engine hours.</li>
            <li>Combined with the total engine hours and fuel efficiency (km/L) noted above each bar, users can evaluate the efficiency of engine hour utilization per vehicle.</li>
        </ul>
        <h3>Note</h3>
        <ul>
            <li>Excessive Idling = Vehicle in Idling mode for more than 15minutes …. Idling ≥ 15minutes</li>
            <li>Overspeeding = Vehicle speed greater than 90 KM/H for 20 seconds or more taken as Overspped</li>
            <li>Engine Overrevving = Vehicle RPM’s greater than 2,500 RPM for over 5 seconds taken as Overrevving of Engine</li>
        </ul>
    """,
    "fcs": """
        <h3>Description</h3>
        <ul>
            <li>This donut chart shows the percentage breakdown of total fuel consumption into different driving behaviors, neutral driving, Idling and PTO.</li>
            <li>The categories for good driving include Top Gear, Cruise Control, Sweetspot and Inefficient Driving includes Excessive Idling, Engine Overrev, and Overspeed.</li>
            <li>These segments can be hidden by clicking the legends, for better clarity.</li>
        </ul>
        
        <h3>Interpretation</h3>
        <ul>
            <li>Users can easily spot which behaviors contribute to the most significant share of fuel consumption.</li>
            <li>Good Driving behaviors like Top Gear and Sweetspot should ideally represent a larger segment, while Excessive Idling and Neutral Driving should be minimized to save fuel.</li>
            <li>This visualization aids in targeting inefficiencies for improving fuel economy.</li>
        </ul>
        
        <h3>Note</h3>
        <ul>
            <li>Excessive Idling = Vehicle in Idling mode for more than 15minutes …. Idling ≥ 15minutes</li>
            <li>Overspeeding = Vehicle speed greater than 90 KM/H for 20 seconds or more taken as Overspped</li>
            <li>Engine Overrevving = Vehicle RPM’s greater than 2,500 RPM for over 5 seconds taken as Overrevving of Engine</li>
        </ul>
    """,
    "fcbd": """
        <h3>Description</h3>
        <ul>
            <li>This stacked bar chart displays fuel consumption per vehicle (Chassis IDs) categorized by Good Driving, Inefficient Driving, Neutral Driving, Idling, and PTO.</li>
            <li>Each bar segment is color-coded for specific categories, with the total fuel consumption (L) noted above each bar.</li>
            <li>These segments can be hidden by clicking the legends, for better clarity.</li>
        </ul>
        
        <h3>Interpretation</h3>
        <ul>
            <li>The chart helps identify which vehicles are consuming excessive fuel due to Inefficient Driving behaviors, such as Overspeed or Excessive Idling.</li>
            <li>Fleet managers can use this insight to target specific vehicles for performance optimization.</li>
            <li>The combination of total fuel consumption and km/L efficiency data provides a comprehensive understanding of vehicle efficiency.</li>
        </ul>

        <h3>Note</h3>
        <ul>
            <li>Excessive Idling = Vehicle in Idling mode for more than 15minutes …. Idling ≥ 15minutes</li>
            <li>Overspeeding = Vehicle speed greater than 90 KM/H for 20 seconds or more taken as Overspped</li>
            <li>Engine Overrevving = Vehicle RPM’s greater than 2,500 RPM for over 5 seconds taken as Overrevving of Engine</li>
        </ul>
    """,
    "gbbg": """
        <h3>Description</h3>
        <ul>
            <li>This horizontal bar chart summarizes the fleet’s overall driving behavior by dividing it into Good Driving, Neutral Driving, and Inefficient Driving percentages.</li>
            <li>Each category is color-coded, and the percentage values are displayed prominently on the chart.</li>
            <li>The charts below the main bar, provide details for the overall percentages by giving a breakdown per Chassis ID of the good and Inefficient Driving separately.</li>
        </ul>
        
        <h3>Interpretation</h3>
        <ul>
            <li>This chart provides a fleet-wide perspective on how driving hours are distributed.</li>
            <li>A higher percentage of Good Driving hours reflects an efficient fleet, while higher Neutral or Inefficient Driving percentages indicate areas for improvement.</li>
            <li>Users can assess the overall performance and identify trends needing correction.</li>
        </ul>

        <h3>Note</h3>
        <ul>
            <li>Excessive Idling = Vehicle in Idling mode for more than 15minutes …. Idling ≥ 15minutes</li>
            <li>Overspeeding = Vehicle speed greater than 90 KM/H for 20 seconds or more taken as Overspped</li>
            <li>Engine Overrevving = Vehicle RPM’s greater than 2,500 RPM for over 5 seconds taken as Overrevving of Engine</li>
        </ul>
    """,
    "nebg": """
        <h3>Description</h3>
        <ul>
            <li>This horizontal bar chart divides the fleet’s total idling hours into Normal Idling and Excessive Idling percentages.</li>
            <li>The chart uses contrasting colors to highlight these categories, with their percentage values clearly displayed.</li>
        </ul>
        
        <h3>Interpretation</h3>
        <ul>
            <li>This visualization helps pinpoint the proportion of idling hours that are excessive and wasteful.</li>
            <li>By focusing on reducing Excessive Idling, fleet managers can enhance fuel efficiency and lower operational costs.</li>
            <li>The chart provides a high-level view, helping users prioritize initiatives for better idling behavior.</li>
        </ul>

        <h3>Note</h3>
        <ul>
            <li>Excessive Idling = Vehicle in Idling mode for more than 15minutes …. Idling ≥ 15minutes</li>
            <li>Overspeeding = Vehicle speed greater than 90 KM/H for 20 seconds or more taken as Overspped</li>
            <li>Engine Overrevving = Vehicle RPM’s greater than 2,500 RPM for over 5 seconds taken as Overrevving of Engine</li>
        </ul>
    """,
}

# Define the insights panel with a close button
side_panel = html.Div(
    id="side-panel", className="side-panel", children=[
        html.Span("✖", id="close-panel", className="close-btn"),  # Close button
        html.H5(id="panel-title"),
        html.P(id="panel-content")
    ]
)

# Callback to handle processing and displaying the reports
@app.callback(
    [
        Output("report-type-title", "children"),
        Output("visual-content", "children"),
        Output("data-table", "children"),
        Output("filter-section", "style"),  # To show/hide filters
        Output("filter-model", "options"),  # Populate Model filter
        Output("filter-truck-type", "options"),  # Populate Truck Type filter
        Output("filter-axle-config", "options")  # Populate Axle Config filter
    ],
    [
        Input("analyze-button", "n_clicks"),
        Input("filter-model", "value"),
        Input("filter-truck-type", "value"),
        Input("filter-axle-config", "value")
    ],
    [
        State("upload-data-fo", "contents"),
        State("upload-data-fu", "contents"),
        State("upload-data-fo", "filename"),
        State("upload-data-fu", "filename")
    ]
)
def update_output(n_clicks, filter_model, filter_truck_type, filter_axle_config, fo_contents, fu_contents, fo_filename, fu_filename):
    # Check if the analyze button has been clicked
    if n_clicks is None or n_clicks == 0:
        # Return default empty values on the initial page load
        return "", "", "", {"display": "none"}, [], [], []
    
    if n_clicks > 0:
        # If only the FO report is uploaded
        if fo_contents and not fu_contents:
            # Check if the file names or contents indicate the correct report type
            report_type = detect_report_type(fo_contents, fo_filename)
            if report_type == 'Fleet Overview':
                df_fo = process_fleet_overview(fo_contents, fo_filename)

                # Apply filters
                if filter_model:
                    df_fo = df_fo[df_fo['Model'] == filter_model]
                if filter_truck_type:
                    df_fo = df_fo[df_fo['Truck Type'] == filter_truck_type]
                if filter_axle_config:
                    df_fo = df_fo[df_fo['Axle Configuration'] == filter_axle_config]

                visuals = generate_visuals(df_fo, report_type)
                title = "Fleet Overview Report" 
                
                # Populate filter options
                model_options = [{'label': model, 'value': model} for model in df_fo['Model'].unique()]
                truck_type_options = [{'label': tt, 'value': tt} for tt in df_fo['Truck Type'].unique()]
                axle_config_options = [{'label': ac, 'value': ac} for ac in df_fo['Axle Configuration'].unique()]

                visuals_div = html.Div([
                    # Small box for the vehicle count
                    html.Div([
                        html.Div([
                            dcc.Graph(figure=visuals[2], style={'height': '150px'})  # Total number of vehicles
                        ], style={'flex': '0 0 155px', 'padding': '8px', 'max-width': '200px', 'margin': '10px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),

                        html.Div([
                            dcc.Graph(figure=visuals[4], style={'height': '150px'})  # Total distance travelled
                        ], style={'flex': '0 0 155px', 'padding': '8px', 'max-width': '200px', 'margin': '10px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),

                        html.Div([
                            dcc.Graph(figure=visuals[1], style={'height': '150px'})  # Total engine hours
                        ], style={'flex': '0 0 155px', 'padding': '8px', 'max-width': '200px', 'margin': '10px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),

                        html.Div([
                            dcc.Graph(figure=visuals[0], style={'height': '150px'})  # Total fuel consumed
                        ], style={'flex': '0 0 155px', 'padding': '8px', 'max-width': '200px', 'margin': '10px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),

                        html.Div([
                            dcc.Graph(figure=visuals[3], style={'height': '150px'})  # Average speed
                        ], style={'flex': '0 0 155px', 'padding': '8px', 'max-width': '200px', 'margin': '10px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),
                        html.Div([
                            dcc.Graph(figure=visuals[12], style={'height': '150px'})  # Potential Fuel Saving
                        ], style={'flex': '0 0 155px', 'padding': '8px', 'max-width': '200px', 'margin': '10px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),
                    ], style={'display': 'flex', 'justify-content': 'center', 'flex-wrap': 'wrap', 'margin-bottom': '10px', 'margin-top': '10px'}),

                    html.Div(style={'border-bottom': '2px solid #A9A9A9', 'margin-bottom': '15px'}),
                    
                    # First row: Histogram and Fuel Efficiency vs Excessive Idling (side by side)
                    html.Div([
                        html.Div([dcc.Graph(figure=visuals[6])], style={'flex': '1', 'padding': '10px'}),  # Truck model sunburst
                        html.Div([dcc.Graph(figure=visuals[5])], style={'flex': '1', 'padding': '10px'}),  # Engine hours distribution
                    ], style={'display': 'flex', 'flex-wrap': 'nowrap', 'margin-bottom': '30px'}),  # Wide display with visuals side by side

                    html.Div(style={'border-bottom': '2px solid #A9A9A9', 'margin-bottom': '15px'}),
                    
                    # Second row: Sunburst chart and Wasted Engine Hours (side by side)
                    html.Div([
                        html.Div([dcc.Graph(figure=visuals[8])], style={'flex': '1', 'padding': '10px'}),  # Fuel wasted on Inefficient Driving Behaviors
                        html.Div([dcc.Graph(figure=visuals[9])], style={'flex': '1', 'padding': '10px', 'overflowX': 'scroll'}),  # Wasted Fuel Breakdown
                    ], style={'display': 'flex', 'flex-wrap': 'nowrap', 'margin-bottom': '30px'}),  # Side by side

                    html.Div(style={'border-bottom': '2px solid #A9A9A9', 'margin-bottom': '15px'}),
                    
                    # Third row: Fuel wasted and Bad behaviors vs efficiency (stacked)
                    html.Div([
                        html.Div([dcc.Graph(figure=visuals[7])], style={'flex': '1', 'padding': '10px'}),  # Wasted engine hours on Inefficient Driving Behaviors
                        html.Div([dcc.Graph(figure=visuals[10])], style={'flex': '1', 'padding': '10px', 'overflowX': 'scroll'}),  # Wasted Engine Hours Breakdown
                    ], style={'display': 'flex', 'flex-wrap': 'wrap'}),  # Allow to stack or spread depending on screen size

                    html.Div(style={'border-bottom': '2px solid #A9A9A9', 'margin-bottom': '15px'}),
                                        
                    html.Div([
                        html.Div([dcc.Graph(figure=visuals[11])], style={'flex': '1', 'padding': '10px', 'overflowX': 'scroll'}),  # Wasted Engine Hours Breakdown
                    ], style={'display': 'flex', 'flex-wrap': 'wrap'}),  # Allow to stack or spread depending on screen size

                ])


                    
                # Data table
                data_table = dash_table.DataTable(
                    columns=[{"name": i, "id": i} for i in df_fo.columns],
                    data=df_fo.to_dict('records'),
                    page_size=len(df_fo),
                    style_table={'height': '300px', 'overflowY': 'auto', 'margin-top': '20px'},
                    style_cell={'textAlign': 'left', 'whiteSpace': 'normal', 'height': 'auto'},
                    style_header={'backgroundColor': 'black', 'color': 'white', 'fontWeight': 'bold', 'position': 'sticky', 'top': 0, 'zIndex': 1}
                )
                return [title, visuals_div, data_table, {"display": "block"}, model_options, truck_type_options, axle_config_options]
            else:
                analyze_status = "Error: Incorrect report uploaded as Fleet Overview."
                return [analyze_status, visuals_div, data_table, {"display": "none"}, [], [], []]
        elif fu_contents and not fo_contents:
            report_type = detect_report_type(fu_contents, fu_filename)
            if report_type == 'Fuel Utilization':
                df_fu = process_fuel_utilization(fu_contents, fu_filename)

                # Apply filters
                if filter_model:
                    df_fu = df_fu[df_fu['Model'] == filter_model]
                if filter_truck_type:
                    df_fu = df_fu[df_fu['Truck Type'] == filter_truck_type]
                if filter_axle_config:
                    df_fu = df_fu[df_fu['Axle Configuration'] == filter_axle_config]

                visuals = generate_visuals(df_fu, report_type)
                # ai_response = fetch_ai_insights(df_fu)  # Get the combined response from GPT
                # insights_dict = parse_insights(ai_response)
                title = "Fuel Utilization Report"
                
                # Populate filter options
                model_options = [{'label': model, 'value': model} for model in df_fu['Model'].unique()]
                truck_type_options = [{'label': tt, 'value': tt} for tt in df_fu['Truck Type'].unique()]
                axle_config_options = [{'label': ac, 'value': ac} for ac in df_fu['Axle Configuration'].unique()]

                visuals_div = html.Div([
                    html.Div([
                        html.Div([
                            html.Div([
                                dcc.Graph(figure=visuals[5], style={'height': '150px'})  # Total number of vehicles
                            ], style={'flex': '1', 'padding': '10px', 'max-width': '200px', 'margin': '30px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),

                            html.Div([
                                dcc.Graph(figure=visuals[6], style={'height': '150px'})  # Total distance travelled
                            ], style={'flex': '1', 'padding': '10px', 'max-width': '200px', 'margin': '30px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),

                            html.Div([
                                dcc.Graph(figure=visuals[7], style={'height': '150px'})  # Total engine hours
                            ], style={'flex': '1', 'padding': '10px', 'max-width': '200px', 'margin': '30px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),

                            html.Div([
                                dcc.Graph(figure=visuals[8], style={'height': '150px'})  # Total fuel consumed
                            ], style={'flex': '1', 'padding': '10px', 'max-width': '200px', 'margin': '30px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),

                            html.Div([
                                dcc.Graph(figure=visuals[9], style={'height': '150px'})  # Average speed
                            ], style={'flex': '1', 'padding': '10px', 'max-width': '200px', 'margin': '30px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),
                        ], style={'display': 'flex', 'justify-content': 'center', 'flex-wrap': 'wrap', 'margin-bottom': '10px', 'margin-top': '10px'}),
                    ]),
                    # Vehicles Sunburst
                    html.Div([
                        dcc.Graph(figure=visuals[10]),
                    ], style={'width': '50%', 'display': 'inline-block'}),

                    # Distance Travelled per Vehicle
                    html.Div([
                        dcc.Graph(figure=visuals[11]),
                    ], style={'width': '50%', 'display': 'inline-block'}),

                    # Fuel vs Adblue Consumed over Travelled Distance
                    html.Div([
                        dcc.Graph(figure=visuals[3]),
                        # html.Div(
                        #     insights_dict.get('Fuel Efficiency Comparison (km/L vs. L/h)', 'No insight available'),
                        #     style={'padding': '10px', 'backgroundColor': '#f4f4f4', 'borderRadius': '5px','fontSize': '16px', 'lineHeight': '1.5'}
                        # )
                    ], style={'width': '100%', 'margin-top': '20px'}),

                    # Good Driving Behavior Fuel Breakdown by Chassis ID
                    html.Div([
                        dcc.Graph(figure=visuals[4]),
                        # html.Div(
                        #     insights_dict.get('Fuel vs AdBlue Consumed per Chassis ID', 'No insight available'),
                        #     style={'padding': '10px', 'backgroundColor': '#f4f4f4', 'borderRadius': '5px','fontSize': '16px', 'lineHeight': '1.5'}
                        # )
                    ], style={'width': '100%', 'margin-top': '20px'}),
                    
                    html.Div(style={'border-bottom': '2px solid #A9A9A9', 'margin-bottom': '15px'}),

                    # Fuel Utilization Breakdown
                    html.Div([
                        dcc.Graph(figure=visuals[0]),
                        # html.Div(
                        #     insights_dict.get('Fuel Utilization Breakdown', 'No insight available'),
                        #     style={'padding': '10px', 'backgroundColor': '#f4f4f4', 'borderRadius': '5px', 'fontSize': '16px', 'lineHeight': '1.5'}
                        # )
                    ], style={'width': '50%', 'display': 'inline-block'}),

                    html.Div([
                        dcc.Graph(figure=visuals[12]),
                        # html.Div(
                        #     insights_dict.get('Engine Hours Breakdown', 'No insight available'),
                        #     style={'padding': '10px', 'backgroundColor': '#f4f4f4', 'borderRadius': '5px', 'fontSize': '16px', 'lineHeight': '1.5'}
                        # )
                    ], style={'width': '50%', 'display': 'inline-block'}),
                    
                    html.Div(style={'border-bottom': '2px solid #A9A9A9', 'margin-bottom': '15px'}),

                    # Engine Hours Breakdown
                    html.Div([
                        dcc.Graph(figure=visuals[1]),
                        # html.Div(
                        #     insights_dict.get('Fuel Utilization Breakdown by Chassis ID', 'No insight available'),
                        #     style={'padding': '10px', 'backgroundColor': '#f4f4f4', 'borderRadius': '5px','fontSize': '16px', 'lineHeight': '1.5'}
                        # )
                    ], style={'width': '50%', 'display': 'inline-block'}),

                    # Engine Hours Breakdown per Chassis ID
                    html.Div([
                        dcc.Graph(figure=visuals[13]),
                        # html.Div(
                        #     insights_dict.get('Engine Hours Breakdown by Chassis ID', 'No insight available'),
                        #     style={'padding': '10px', 'backgroundColor': '#f4f4f4', 'borderRadius': '5px','fontSize': '16px', 'lineHeight': '1.5'}
                        # )
                    ], style={'width': '50%', 'display': 'inline-block'}),
                    
                    html.Div(style={'border-bottom': '2px solid #A9A9A9', 'margin-bottom': '15px'}),

                    # Good Driving Behavior Hours Breakdown by Chassis ID
                    html.Div([
                        dcc.Graph(figure=visuals[2]),
                        # html.Div(
                        #     insights_dict.get('Good Driving Behavior Hour Breakdown by Chassis ID (Ordered by Driving Efficiency %)', 'No insight available'),
                        #     style={'padding': '10px', 'backgroundColor': '#f4f4f4', 'borderRadius': '5px','fontSize': '16px', 'lineHeight': '1.5'}
                        # )
                    ], style={'width': '100%', 'margin-top': '20px'}),

                    # Fuel Efficiency: km/L vs. L/h
                    html.Div([
                        dcc.Graph(figure=visuals[14]),
                        # html.Div(
                        #     insights_dict.get('Good Driving Behavior Fuel Breakdown by Chassis ID (Ordered by Driving Efficiency %)', 'No insight available'),
                        #     style={'padding': '10px', 'backgroundColor': '#f4f4f4', 'borderRadius': '5px','fontSize': '16px', 'lineHeight': '1.5'}
                        # )
                    ], style={'width': '100%', 'margin-top': '20px'}),

                    html.Div(style={'border-bottom': '2px solid #A9A9A9', 'margin-bottom': '15px'}),
                ])
                    
                # Data table
                data_table = dash_table.DataTable(
                    columns=[{"name": i, "id": i} for i in df_fu.columns],
                    data=df_fu.to_dict('records'),
                    page_size=len(df_fu),
                    style_table={'height': '300px', 'overflowY': 'auto', 'margin-top': '20px'},
                    style_cell={'textAlign': 'left', 'whiteSpace': 'normal', 'height': 'auto'},
                    style_header={'backgroundColor': 'black', 'color': 'white', 'fontWeight': 'bold', 'position': 'sticky', 'top': 0, 'zIndex': 1}
                )

                # Make chatbot visible
                chatbot_style = {'display': 'block'}
                return [title, visuals_div, data_table, {"display": "block"}, model_options, truck_type_options, axle_config_options]
            else:
                analyze_status = "Error: Incorrect report uploaded as Fuel Utilization."
                return [analyze_status, visuals_div, data_table, {"display": "none"}, [], [], []]
        
        # If both reports are uploaded, process and merge
        elif fo_contents and fu_contents:

            # If both reports are uploaded, check if same fleet and date
            metadata_match = check_report_metadata(fo_contents, fu_contents)
            if not metadata_match:
                return "Error: The start/end times or fleet name do not match between the two reports.", "", ""
            
            report_type_fo = detect_report_type(fo_contents, fo_filename)
            report_type_fu = detect_report_type(fu_contents, fu_filename)
            
            if report_type_fo == 'Fleet Overview' and report_type_fu == 'Fuel Utilization':
                df_fo = process_fleet_overview(fo_contents, fo_filename)
                df_fu = process_fuel_utilization(fu_contents, fu_filename)
                title = "Combined Fleet Overview and Fuel Utilization Report"
                # Create the merged dataset using Chassis ID
                df_combined = process_combined_dataset(df_fo, df_fu)
                
                # Apply filters
                if filter_model:
                    df_combined = df_combined[df_combined['Model'] == filter_model]
                if filter_truck_type:
                    df_combined = df_combined[df_combined['Truck Type'] == filter_truck_type]
                if filter_axle_config:
                    df_combined = df_combined[df_combined['Axle Configuration'] == filter_axle_config]

                # Generate visuals using the combined data
                visuals_combined = generate_combined_visuals(df_combined)

                # Populate filter options
                model_options = [{'label': model, 'value': model} for model in df_combined['Model'].unique()]
                truck_type_options = [{'label': tt, 'value': tt} for tt in df_combined['Truck Type'].unique()]
                axle_config_options = [{'label': ac, 'value': ac} for ac in df_combined['Axle Configuration'].unique()]

                visuals_div = html.Div([
                    html.Div([
                        html.Div([
                            dcc.Graph(figure=visuals_combined[0], style={'height': '150px'})  # Total number of vehicles
                        ], style={'flex': '0 0 155px', 'padding': '8px', 'max-width': '200px', 'margin': '10px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),

                        html.Div([
                            dcc.Graph(figure=visuals_combined[3], style={'height': '150px'})  # Total distance travelled
                        ], style={'flex': '0 0 155px', 'padding': '8px', 'max-width': '200px', 'margin': '10px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),

                        html.Div([
                            dcc.Graph(figure=visuals_combined[2], style={'height': '150px'})  # Total engine hours
                        ], style={'flex': '0 0 155px', 'padding': '8px', 'max-width': '200px', 'margin': '10px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),

                        html.Div([
                            dcc.Graph(figure=visuals_combined[4], style={'height': '150px'})  # Total fuel consumed
                        ], style={'flex': '0 0 155px', 'padding': '8px', 'max-width': '200px', 'margin': '10px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),

                        html.Div([
                            dcc.Graph(figure=visuals_combined[1], style={'height': '150px'})  # Average speed
                        ], style={'flex': '0 0 155px', 'padding': '8px', 'max-width': '200px', 'margin': '10px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),
                        html.Div([
                            dcc.Graph(figure=visuals_combined[5], style={'height': '150px'})  # Potential Fuel Saving
                        ], style={'flex': '0 0 155px', 'padding': '8px', 'max-width': '200px', 'margin': '10px', 'border': '1px solid #ccc', 'border-radius': '10px', 'box-shadow': '2px 2px 12px rgba(0, 0, 0, 0.1)', 'background-color': 'white', 'overflow': 'hidden'}),
                    ], style={'display': 'flex', 'justify-content': 'center', 'flex-wrap': 'wrap', 'margin-bottom': '10px', 'margin-top': '10px'}),

                    # Fuel cost input section
                    # Content wrapper to center everything
                    html.Div([
                        # Title
                        html.H2("Fuel Cost Savings Calculator", style={"text-align": "center", "font-family": "Arial, sans-serif","font-weight": "bold","margin-bottom": "40px","color": "#333"}),
                        # Loading animation for fuel cost inputs and calculations
                        dcc.Loading(
                            id="loading-fuel-cost",
                            children=[
                                # Fuel cost input section
                                html.Div([
                                    dcc.Input(
                                        id="fuel-cost-input",
                                        type="number",
                                        placeholder="Enter current fuel cost in selected currency",
                                        style={"margin-right": "10px", "width": "315px", "padding": "10px", "font-size": "16px", "border": "1px solid #ccc", "border-radius": "5px"}
                                    ),
                                    dcc.Dropdown(
                                        id="currency-dropdown",
                                        options=[
                                            {"label": "AED (د.إ)", "value": "AED"},
                                            {"label": "USD ($)", "value": "USD"},
                                            {"label": "ZAR (R)", "value": "ZAR"},
                                            {"label": "BHD (ب.د)", "value": "BHD"},
                                            {"label": "QAR (ر.ق)", "value": "QAR"},
                                            {"label": "JPY (¥)", "value": "JPY"},
                                        ],
                                        value="AED",
                                        clearable=False,  # Prevent clearing the selection
                                        searchable=False,
                                        style={"width": "135px", "padding": "2px", "font-size": "16px", "border-radius": "5px", "text-align": "center", "align-items": "center", "justify-content": "center"}
                                    ),
                                ], style={"display": "flex", "align-items": "center", "justify-content": "center", "margin-bottom": "20px"}),

                                # Add the Calculate button
                                html.Div(
                                    html.Button(
                                        "Calculate", 
                                        id="calculate-button", 
                                        style={"padding": "10px 20px", "font-size": "16px", "background-color": "black", "color": "white", "border": "none", "border-radius": "5px","text-align": "center"}
                                    ), style={"display": "flex", "justify-content": "center", "margin-bottom": "20px"}
                                ),

                                # Output for fuel cost saving
                                html.Div(
                                    id="fuel-cost-saving",
                                    style={"font-size": "24px", "font-weight": "bold", "text-align": "center", "color": "#4CAF50", "font-family": "Arial, sans-serif", "margin-top": "20px", "padding": "20px"}
                                ),
                            ]
                        )
                    ], style={"display": "flex", "flex-direction": "column", "align-items": "center", "justify-content": "center", "height": "auto", "background-color": "#f7f7f7", "width": "675px", "margin": "auto", "border": "1px solid #ccc", "border-radius": "5px"}),

                    # First row
                    html.Div([
                        html.Div([dcc.Graph(figure=visuals_combined[8])], style={'flex': '1', 'padding': '10px'}),
                        html.Div([dcc.Graph(figure=visuals_combined[9])], style={'flex': '1', 'padding': '10px'}),
                    ], style={'display': 'flex', 'flex-wrap': 'nowrap', 'margin-bottom': '30px'}),

                    html.Div(style={'border-bottom': '2px solid #A9A9A9', 'margin-bottom': '15px'}),

                    side_panel,  # Add the side-panel here
                    # Pie Chart of Engine Hour Breakdown (with Show Data)
                    html.Div(className="graph-container", children=[
                        html.Div([
                            html.H4("Information ", style={"display": "inline-block", "margin-right": "5px"}),
                            html.A("ℹ️", id="info-eh_split", className="insight-button", title="Click for insights")
                        ], style={"display": "flex", "align-items": "center"}),

                        # The Graph
                        dcc.Graph(figure=visuals_combined[6], style={'width': '100%', 'height': '525px'}),  

                        # Show Data Button (Styled for better UX)
                        html.Button("📊 Show Data", id="toggle-data-eh_split", n_clicks=0, className="toggle-button",  
                            style={"background-color": "#000000",  "color": "white",  "border": "none","border-radius": "8px","padding": "10px 20px",
                                "font-size": "16px","cursor": "pointer","transition": "all 0.3s ease","box-shadow": "0px 4px 6px rgba(0, 0, 0, 0.1)",
                                "margin-top": "15px","display": "block","text-align": "center","width": "150px"
                            }
                        ),  

                        # Scrollable Data Table (Aesthetic Design)
                        html.Div(
                            dash_table.DataTable(
                                columns=[{"name": col, "id": col} for col in ["Chassis ID", "Total Driving Hours", "Total Idling Hours", "Total PTO Hours"]],
                                data=df_combined[["Chassis ID", "Total Driving Hours", "Total Idling Hours", "Total PTO Hours"]]
                                    .round(2)  # Round values to 2 decimal places
                                    .to_dict("records"),
                                style_table={'height': '300px', 'overflowY': 'auto', 'border': '1px solid #ddd', 'border-radius': '8px',
                                            'box-shadow': '0px 4px 8px rgba(0, 0, 0, 0.1)', 'backgroundColor': 'white', 'margin-top': '10px'},  
                                style_cell={'textAlign': 'left',  'padding': '10px',  'font-size': '14px',  
                                            'color': '#333','backgroundColor': '#f9f9f9','border-bottom': '1px solid #ddd'},  
                                style_header={'backgroundColor': '#000000',  'color': 'white',  'position': 'sticky', 'fontWeight': 'bold','textAlign': 'center','border-radius': '8px 8px 0 0'},fixed_rows={'headers': True}
                            ),
                            id="data-table-eh_split",
                            style={"display": "none", "width": "80%", "margin": "auto"}  # Initially hidden
                        )
                    ]),

                    # Breakdown of Engine Hours per Chassis ID
                    html.Div(className="graph-container", children=[
                        html.Div([
                            html.H4("Information ", style={"display": "inline-block", "margin-right": "5px"}),
                            html.A("ℹ️", id="info-eh_bd", className="insight-button", title="Click for insights")
                        ], style={"display": "flex", "align-items": "center"}),

                        dcc.Graph(figure=visuals_combined[7], style={'width': '100%', 'height': '550px'})  # Responsive graph
                    ]),

                    html.Div(style={'border-bottom': '2px solid #A9A9A9', 'margin-bottom': '15px'}),

                    # Good vs Inefficient Driving Bar
                    html.Div(className="graph-container", children=[
                        html.Div([
                            html.H4("Information ", style={"display": "inline-block", "margin-right": "5px"}),
                            html.A("ℹ️", id="info-gb_bg", className="insight-button", title="Click for insights")
                        ], style={"display": "flex", "align-items": "center"}),

                        dcc.Graph(figure=visuals_combined[10], style={'width': '100%', 'height': '250px'})  # Responsive graph
                    ]),

                    html.Div([
                        html.Div([dcc.Graph(figure=visuals_combined[11])], style={'flex': '1', 'padding': '10px'}),
                        html.Div([dcc.Graph(figure=visuals_combined[12])], style={'flex': '1', 'padding': '10px'}),
                    ], style={'display': 'flex', 'flex-wrap': 'nowrap', 'margin-bottom': '30px'}),

                    html.Div(style={'border-bottom': '2px solid #A9A9A9', 'margin-bottom': '15px'}),

                    # Normal vs Excessive Idling Bar
                    html.Div(className="graph-container", children=[
                        html.Div([
                            html.H4("Information ", style={"display": "inline-block", "margin-right": "5px"}),
                            html.A("ℹ️", id="info-ne_bg", className="insight-button", title="Click for insights")
                        ], style={"display": "flex", "align-items": "center"}),

                        dcc.Graph(figure=visuals_combined[13], style={'width': '100%', 'height': '250px'})  # Responsive graph
                    ]),

                    html.Div([
                        html.Div([dcc.Graph(figure=visuals_combined[14])], style={'flex': '1', 'padding': '10px'}),
                        html.Div([dcc.Graph(figure=visuals_combined[15])], style={'flex': '1', 'padding': '10px'}),
                    ], style={'display': 'flex', 'flex-wrap': 'nowrap', 'margin-bottom': '30px'}),

                    html.Div(style={'border-bottom': '2px solid #A9A9A9', 'margin-bottom': '15px'}),

                    # html.Div([dcc.Graph(figure=visuals_combined[6])], style={'flex': '1', 'padding': '10px'}),
                    # html.Div([dcc.Graph(figure=visuals_combined[7])], style={'flex': '1', 'padding': '10px'}),
                    # html.Div([dcc.Graph(figure=visuals_combined[9])], style={'flex': '1', 'padding': '10px'}),
                    # html.Div([dcc.Graph(figure=visuals_combined[10])], style={'flex': '1', 'padding': '10px'})
                ])

                # Data table
                data_table = dash_table.DataTable(
                    columns=[{"name": i, "id": i} for i in df_combined.columns],
                    data=df_combined.to_dict('records'),
                    page_size=len(df_combined),
                    style_table={'height': '300px', 'overflowY': 'auto', 'margin-top': '20px'},
                    style_cell={'textAlign': 'left', 'whiteSpace': 'normal', 'height': 'auto'},
                    style_header={'backgroundColor': 'black', 'color': 'white', 'fontWeight': 'bold', 'position': 'sticky', 'top': 0, 'zIndex': 1}
                )
                return [title, visuals_div, data_table, {"display": "block"}, model_options, truck_type_options, axle_config_options]
            else:
                analyze_status = "Error: Incorrect combination of reports uploaded."
                return [analyze_status, visuals_div, data_table, {"display": "none"}, [], [], []]
        # Return values for all 6 outputs
        return ["No files uploaded", "", "", {"display": "none"}, [], [], []]

@app.callback(
    [Output("side-panel", "className"), Output("panel-title", "children"), Output("panel-content", "children")],
    [
        Input("info-eh_split", "n_clicks"),
        Input("info-eh_bd", "n_clicks"),
        Input("info-cf_split", "n_clicks"),
        Input("info-cf_bd", "n_clicks"),
        Input("info-gb_bg", "n_clicks"),
        Input("info-ne_bg", "n_clicks"),
        Input("close-panel", "n_clicks")
    ],
    prevent_initial_call=True
)
def toggle_panel(n_clicks_eh_split, n_clicks_eh_bd, n_clicks_cf_split, n_clicks_cf_bd, n_clicks_gb_bg, n_clicks_ne_bg, n_clicks_close):
    ctx = dash.callback_context
    if not ctx.triggered:
        return "side-panel", "", ""

    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    # Check if the close button was clicked
    if button_id == "close-panel":
        return "side-panel", "", ""  # Hide panel

    # Set panel content based on which button was clicked
    if button_id == "info-eh_split":
        return "side-panel show", "Fleet Engine Hours Split - % Donut Chart", DangerouslySetInnerHTML(sample_insights["ehs"])
    elif button_id == "info-eh_bd":
        return "side-panel show", "Engine Hours Breakdown- per Chassis ID", DangerouslySetInnerHTML(sample_insights["ehbd"])
    elif button_id == "info-cf_split":
        return "side-panel show", "Fleet Consumed Fuel Split - % Donut Chart", DangerouslySetInnerHTML(sample_insights["fcs"])
    elif button_id == "info-cf_bd":
        return "side-panel show", "Fuel Consumed Breakdown- per Chassis ID", DangerouslySetInnerHTML(sample_insights["fcbd"])
    elif button_id == "info-gb_bg":
        return "side-panel show", "Good vs. Inefficient Driving as a % of Total Driving Hours", DangerouslySetInnerHTML(sample_insights["gbbg"])
    elif button_id == "info-ne_bg":
        return "side-panel show", "Normal vs. Excessive Idling as a % of Total Idling Hours", DangerouslySetInnerHTML(sample_insights["nebg"])

    return "side-panel", "", ""

# Callback to calculate and display fuel cost saving
@app.callback(
    Output("fuel-cost-saving", "children"),
    [Input("calculate-button", "n_clicks"),  # Button click as trigger
     Input("fuel-cost-input", "n_submit"),   # Enter key as trigger
     Input("currency-dropdown", "value")],   # Currency change as trigger
    [State("fuel-cost-input", "value")]
)
def update_fuel_cost_saving(n_clicks, n_submit, currency, fuel_cost):
    # Check if any trigger (button, Enter key, or currency change) and fuel cost is valid
    if (n_clicks is not None or n_submit is not None or currency) and fuel_cost is not None and fuel_cost > 0:
        global potential_fuel_saving_liters
        total_saving = potential_fuel_saving_liters * fuel_cost
        currency_symbols = {
            "USD": "$",
            "ZAR": "R",
            "BHD": "ب.د",
            "QAR": "ر.ق",
            "JPY": "¥",
            "AED": "د.إ"
        }
        return f"Potential Fuel Cost Saving: {currency_symbols[currency]} {total_saving:,.2f}"
    else:
        return "Please enter the current fuel cost to calculate savings."

# Callback for FO Report
@app.callback(
    [
        Output('upload-data-fo', 'contents'),
        Output('upload-data-fo', 'filename'),
        Output('upload-data-fo', 'last_modified'),
        Output('fo-upload-status', 'children'),
        Output('fo-upload-status', 'style'),
        Output('remove-fo-file', 'style'),
        Output('reset-fo-upload', 'data')  # Reset tracker for FO
    ],
    [
        Input('upload-data-fo', 'contents'),
        Input('remove-fo-file', 'n_clicks')
    ],
    [State('upload-data-fo', 'filename'),
     State('reset-fo-upload', 'data')]
)
def update_fo_status(fo_contents, remove_clicks, fo_filename, reset_tracker):
    if remove_clicks and not reset_tracker:
        # Clear FO file input
        return None, None, None, "❌ No file uploaded", {
            'color': 'red', 'backgroundColor': '#ffe6e6', 'textAlign': 'center',
            'padding': '10px', 'fontSize': '16px', 'fontWeight': 'bold',
            'borderRadius': '5px', 'margin': '10px auto', 'maxWidth': '400px'
        }, {'display': 'none'}, True

    if fo_contents:
        return dash.no_update, dash.no_update, dash.no_update, f"✅ {fo_filename} uploaded successfully!", {
            'color': 'green', 'backgroundColor': '#f0fff0', 'textAlign': 'center',
            'padding': '10px', 'fontSize': '16px', 'fontWeight': 'bold',
            'borderRadius': '5px', 'margin': '10px auto', 'maxWidth': '400px'
        }, {'display': 'inline-block', 'marginTop': '10px', 'backgroundColor': 'red',
            'color': 'white', 'border': 'none', 'borderRadius': '5px',
            'padding': '10px', 'cursor': 'pointer', 'fontSize': '14px'}, False

    return dash.no_update, dash.no_update, dash.no_update, "❌ No file uploaded", {
        'color': 'red', 'backgroundColor': '#ffe6e6', 'textAlign': 'center',
        'padding': '10px', 'fontSize': '16px', 'fontWeight': 'bold',
        'borderRadius': '5px', 'margin': '10px auto', 'maxWidth': '400px'
    }, {'display': 'none'}, False


# Callback for FU Report
@app.callback(
    [
        Output('upload-data-fu', 'contents'),
        Output('upload-data-fu', 'filename'),
        Output('upload-data-fu', 'last_modified'),
        Output('fu-upload-status', 'children'),
        Output('fu-upload-status', 'style'),
        Output('remove-fu-file', 'style'),
        Output('reset-fu-upload', 'data')  # Reset tracker for FU
    ],
    [
        Input('upload-data-fu', 'contents'),
        Input('remove-fu-file', 'n_clicks')
    ],
    [State('upload-data-fu', 'filename'),
     State('reset-fu-upload', 'data')]
)
def update_fu_status(fu_contents, remove_clicks, fu_filename, reset_tracker):
    if remove_clicks and not reset_tracker:
        # Clear FU file input
        return None, None, None, "❌ No file uploaded", {
            'color': 'red', 'backgroundColor': '#ffe6e6', 'textAlign': 'center',
            'padding': '10px', 'fontSize': '16px', 'fontWeight': 'bold',
            'borderRadius': '5px', 'margin': '10px auto', 'maxWidth': '400px'
        }, {'display': 'none'}, True

    if fu_contents:
        return dash.no_update, dash.no_update, dash.no_update, f"✅ {fu_filename} uploaded successfully!", {
            'color': 'green', 'backgroundColor': '#f0fff0', 'textAlign': 'center',
            'padding': '10px', 'fontSize': '16px', 'fontWeight': 'bold',
            'borderRadius': '5px', 'margin': '10px auto', 'maxWidth': '400px'
        }, {'display': 'inline-block', 'marginTop': '10px', 'backgroundColor': 'red',
            'color': 'white', 'border': 'none', 'borderRadius': '5px',
            'padding': '10px', 'cursor': 'pointer', 'fontSize': '14px'}, False

    return dash.no_update, dash.no_update, dash.no_update, "❌ No file uploaded", {
        'color': 'red', 'backgroundColor': '#ffe6e6', 'textAlign': 'center',
        'padding': '10px', 'fontSize': '16px', 'fontWeight': 'bold',
        'borderRadius': '5px', 'margin': '10px auto', 'maxWidth': '400px'
    }, {'display': 'none'}, False

@app.callback(
    Output("data-table-eh_split", "style"),
    Input("toggle-data-eh_split", "n_clicks"),
    prevent_initial_call=True
)
def toggle_data_visibility(n_clicks):
    return {"display": "block"} if n_clicks % 2 == 1 else {"display": "none"}

def prepare_full_dataset_for_gpt(df):
    """
    Converts the entire dataframe into a structured JSON format for GPT.
    Includes metadata such as column names and data types.
    """
    # Metadata
    metadata = {
        "columns": list(df.columns),
        "num_rows": len(df),
        "num_columns": len(df.columns),
        "data_types": df.dtypes.apply(str).to_dict()
    }

    # Data: Convert the entire dataframe to a list of dictionaries
    data = df.to_dict(orient='records')

    # Combine metadata and data
    structured_data = {
        "metadata": metadata,
        "data": data
    }

    # Convert to a compact JSON string without indentation to reduce token usage
    return json.dumps(structured_data)

# Callback to handle the chatbot functionality
@app.callback(
    Output('chatbot-response', 'children'),
    [Input('submit-button', 'n_clicks')],
    [State('user-input', 'value'),
     State('upload-data-fo', 'contents'),
     State('upload-data-fo', 'filename'),
     State('upload-data-fu', 'contents'),
     State('upload-data-fu', 'filename'),
     State('chatbot-response', 'children')]  # Maintain conversation history
)
def handle_chatbot(n_clicks, question, fo_contents, fo_filename, fu_contents, fu_filename, conversation_history):
    if n_clicks > 0 and question:
        if not conversation_history or isinstance(conversation_history, str):
            conversation_history = []  # Ensure conversation history is initialized as an empty list
        
        # Check if this is the first question after data upload
        is_initial_question = (len(conversation_history) == 0)
        
        df = None
        if is_initial_question:
            # Process the first available report
            if fo_contents:
                df = process_fleet_overview(fo_contents, fo_filename)
            elif fu_contents:
                df = process_fuel_utilization(fu_contents, fu_filename)
            else:
                return "No report data available. Please upload a report."

        # Fetch the AI answer while keeping the conversation history
        answer, conversation_history = fetch_ai_answer(question, conversation_history, is_initial_question, df)

        # Format the conversation history for display
        conversation_display = ""
        for entry in conversation_history:
            if entry['role'] == 'user':
                conversation_display += f"You: {entry['content']}<br>"
            else:
                conversation_display += f"Chatbot: {entry['content']}<br>"

        return conversation_display
    return ""

@app.callback(
    Output("chatbot-container", "style"),
    [Input("analyze-button", "n_clicks")],
    [
        State("upload-data-fo", "contents"),
        State("upload-data-fu", "contents")
    ]
)
def toggle_chatbot_visibility(n_clicks, fo_contents, fu_contents):
    if n_clicks and (fo_contents or fu_contents):
        # Display chatbot only when analysis is triggered with valid report data
        return {"display": "block"}
    return {"display": "none"}  # Hide chatbot by default

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))  # Render assigns a dynamic port
    app.run_server(debug=False, host='0.0.0.0', port=port)