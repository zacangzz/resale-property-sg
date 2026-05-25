import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime

# ============================
# Title of the Dashboard
# ============================
st.title('HDB Resale Prices Dashboard')

# ============================
# Data Loading with Caching
# ============================
@st.cache_data
def load_data():
    try:
        return pd.read_feather('hdb_downloaded.feather')
    except FileNotFoundError:
        st.error("Data file 'hdb_downloaded.feather' not found.")
        return pd.DataFrame()  # Return empty DataFrame on error

data_load_state = st.text('Loading data...')
dataset = load_data()
data_load_state.text('Loading data...done!')

# Stop execution if data is not loaded
if dataset.empty:
    st.stop()

# Ensure 'date' column is datetime
if dataset['date'].dtype != 'datetime64[ns]':
    dataset['date'] = pd.to_datetime(dataset['date'])

# ============================
# Sidebar Filters with Dropdowns
# ============================
st.sidebar.header('Filter Options')

# 1. Filter by Flat Type
with st.sidebar.expander("Filter by Flat Type", expanded=True):
    flat_type_options = sorted(dataset['flat_type'].dropna().unique())
    selected_flat_type = st.multiselect(
        label='Select Flat Type',
        options=flat_type_options,
        default=[],  # No default selection
        help="Choose one or more flat types to filter the data."
    )

# 2. Filter by Town
with st.sidebar.expander("Filter by Town", expanded=True):
    town_options = sorted(dataset['town'].dropna().unique())
    selected_town = st.multiselect(
        label='Select Town',
        options=town_options,
        default=[],  # No default selection
        help="Choose one or more towns to filter the data."
    )

# 3. Filter by Street Name (Dependent on Town Selection)
with st.sidebar.expander("Filter by Street Name", expanded=True):
    if selected_town:
        street_name_options = sorted(dataset[dataset['town'].isin(selected_town)]['street_name'].dropna().unique())
    else:
        street_name_options = sorted(dataset['street_name'].dropna().unique())
    selected_street = st.multiselect(
        label='Select Street Name',
        options=street_name_options,
        default=[],  # No default selection
        help="Choose one or more street names to filter the data."
    )

# 4. Filter by Date Range
with st.sidebar.expander("Filter by Date Range", expanded=True):
    min_date = dataset['date'].min()
    max_date = dataset['date'].max()
    selected_date = st.date_input(
        label='Select Date Range',
        value=[min_date, max_date],
        min_value=min_date,
        max_value=max_date,
        help="Select the date range to filter transactions."
    )
    if isinstance(selected_date, tuple) or isinstance(selected_date, list):
        start_date, end_date = selected_date
    else:
        start_date = selected_date
        end_date = selected_date

# ============================
# Data Filtering Logic
# ============================
# Start with the full dataset
filtered_data = dataset.copy()

# Apply Flat Type filter if any selection is made
if selected_flat_type:
    filtered_data = filtered_data[filtered_data['flat_type'].isin(selected_flat_type)]

# Apply Town filter if any selection is made
if selected_town:
    filtered_data = filtered_data[filtered_data['town'].isin(selected_town)]

# Apply Street Name filter if any selection is made
if selected_street:
    filtered_data = filtered_data[filtered_data['street_name'].isin(selected_street)]

# Apply Date Range filter
filtered_data = filtered_data[
    (filtered_data['date'] >= pd.to_datetime(start_date)) &
    (filtered_data['date'] <= pd.to_datetime(end_date))
]

# Drop rows with missing values in critical columns
filtered_data = filtered_data.dropna(subset=['resale_price', 'priceper_sqft'])

# Convert 'year' to integer if not already
filtered_data['year'] = filtered_data['year'].astype(int)

# ============================
# Display Filtered Data Table
# ============================
st.subheader('Filtered Data')
st.dataframe(filtered_data[['date', 'town', 'street_name', 'flat_type', 'resale_price', 'priceper_sqft']])

# ============================
# Visualization 1: Resale Price Distribution by Town (Box Plot)
# ============================
st.subheader('Resale Price Distribution by Town')

if not filtered_data.empty and 'resale_price' in filtered_data.columns:
    # Create box plot for resale_price by town
    box_plot = alt.Chart(filtered_data).mark_boxplot(extent='min-max').encode(
        x=alt.X('town:N', title='Town'),
        y=alt.Y(
            'resale_price:Q',
            title='Resale Price (SGD)',
            axis=alt.Axis(format="$,.0f")  # Updated format
        ),
        color=alt.Color('town:N', legend=None),
        tooltip=[
            alt.Tooltip('town:N', title='Town'),
            alt.Tooltip('resale_price:Q', title='Resale Price (SGD)', format="$,.2f")
        ]
    ).properties(
        width='container',
        height=400,
        title='Resale Price Distribution by Town'
    )

    # Calculate mean resale price per town
    mean_prices = filtered_data.groupby('town')['resale_price'].mean().reset_index()

    # Create mean points
    mean_points = alt.Chart(mean_prices).mark_point(shape='circle', size=100, color='black').encode(
        x='town:N',
        y=alt.Y('resale_price:Q', axis=alt.Axis(format="$,.0f")),  # Updated format
        tooltip=[
            alt.Tooltip('town:N', title='Town'),
            alt.Tooltip('resale_price:Q', title='Mean Resale Price (SGD)', format="$,.2f")
        ]
    )

    # Overlay box plot with mean points
    box_plot_with_mean = box_plot + mean_points

    st.altair_chart(box_plot_with_mean, use_container_width=True)
else:
    st.warning("No data available to display the Resale Price Distribution by Town box plot.")

# ============================
# Visualization 2: Average Resale Price by Town (Bar Chart)
# ============================
st.subheader('Average Resale Price by Town')

if not filtered_data.empty and 'resale_price' in filtered_data.columns:
    avg_price_town = filtered_data.groupby('town')['resale_price'].mean().reset_index()

    bar_chart_town = alt.Chart(avg_price_town).mark_bar().encode(
        x=alt.X('town:N', title='Town'),
        y=alt.Y(
            'resale_price:Q',
            title='Average Resale Price (SGD)',
            axis=alt.Axis(format="$,.0f")  # Updated format
        ),
        tooltip=[
            alt.Tooltip('town:N', title='Town'),
            alt.Tooltip('resale_price:Q', title='Average Resale Price (SGD)', format="$,.2f")
        ]
    ).properties(
        width='container',
        height=400,
        title='Average Resale Price by Town'
    ).configure_title(
        fontSize=16,
        anchor='start'
    )

    st.altair_chart(bar_chart_town, use_container_width=True)
else:
    st.warning("No data available to display the Average Resale Price by Town chart.")

# ============================
# Visualization 3: Year-on-Year Monthly Trends
# ============================
st.subheader('Year-on-Year Monthly Trends')

if not filtered_data.empty:
    # Extract year and month from the date
    filtered_data['year'] = filtered_data['date'].dt.year
    filtered_data['month'] = filtered_data['date'].dt.month

    # Create a 'month_name' column for better readability
    filtered_data['month_name'] = filtered_data['date'].dt.strftime('%b')

    # Define the order of months
    month_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    # ============================
    # a. Number of Transactions per Month per Year
    # ============================
    st.markdown("### Number of Transactions")

    transactions_yoy = filtered_data.groupby(['year', 'month_name']).size().reset_index(name='transactions')

    # Ensure months are ordered correctly
    transactions_yoy['month_name'] = pd.Categorical(transactions_yoy['month_name'], categories=month_order, ordered=True)
    transactions_yoy = transactions_yoy.sort_values(['year', 'month_name'])

    line_chart_transactions_yoy = alt.Chart(transactions_yoy).mark_line().encode(
        x=alt.X('month_name:N', title='Month'),
        y=alt.Y(
            'transactions:Q',
            title='Number of Transactions',
            axis=alt.Axis(format=",.0f")  # Updated format
        ),
        color=alt.Color('year:O', title='Year'),
        tooltip=[
            alt.Tooltip('year:O', title='Year'),
            alt.Tooltip('month_name:N', title='Month'),
            alt.Tooltip('transactions:Q', title='Number of Transactions', format=",d")  # Updated format
        ]
    ).properties(
        width='container',
        height=400,
        title='Monthly Number of Transactions Year-on-Year'
    ).configure_title(
        fontSize=16,
        anchor='start'
    ).interactive()

    st.altair_chart(line_chart_transactions_yoy, use_container_width=True)

    # ============================
    # b. Average Resale Price per Month per Year
    # ============================
    st.markdown("### Average Resale Price")

    avg_price_yoy = filtered_data.groupby(['year', 'month_name'])['resale_price'].mean().reset_index()

    # Ensure months are ordered correctly
    avg_price_yoy['month_name'] = pd.Categorical(avg_price_yoy['month_name'], categories=month_order, ordered=True)
    avg_price_yoy = avg_price_yoy.sort_values(['year', 'month_name'])

    line_chart_avg_price_yoy = alt.Chart(avg_price_yoy).mark_line().encode(
        x=alt.X('month_name:N', title='Month'),
        y=alt.Y(
            'resale_price:Q',
            title='Average Resale Price (SGD)',
            axis=alt.Axis(format="$,.0f")  # Updated format
        ),
        color=alt.Color('year:O', title='Year'),
        tooltip=[
            alt.Tooltip('year:O', title='Year'),
            alt.Tooltip('month_name:N', title='Month'),
            alt.Tooltip('resale_price:Q', title='Average Resale Price (SGD)', format="$,.2f")
        ]
    ).properties(
        width='container',
        height=400,
        title='Monthly Average Resale Price Year-on-Year'
    ).configure_title(
        fontSize=16,
        anchor='start'
    ).interactive()

    st.altair_chart(line_chart_avg_price_yoy, use_container_width=True)

    # ============================
    # c. Average Price per Sqft per Month per Year
    # ============================
    st.markdown("### Average Price per Sqft")

    avg_price_sqft_yoy = filtered_data.groupby(['year', 'month_name'])['priceper_sqft'].mean().reset_index()

    # Ensure months are ordered correctly
    avg_price_sqft_yoy['month_name'] = pd.Categorical(avg_price_sqft_yoy['month_name'], categories=month_order, ordered=True)
    avg_price_sqft_yoy = avg_price_sqft_yoy.sort_values(['year', 'month_name'])

    line_chart_avg_price_sqft_yoy = alt.Chart(avg_price_sqft_yoy).mark_line().encode(
        x=alt.X('month_name:N', title='Month'),
        y=alt.Y(
            'priceper_sqft:Q',
            title='Average Price per Sqft (SGD)',
            axis=alt.Axis(format="$,.0f")  # Updated format
        ),
        color=alt.Color('year:O', title='Year'),
        tooltip=[
            alt.Tooltip('year:O', title='Year'),
            alt.Tooltip('month_name:N', title='Month'),
            alt.Tooltip('priceper_sqft:Q', title='Average Price per Sqft (SGD)', format="$,.2f")
        ]
    ).properties(
        width='container',
        height=400,
        title='Monthly Average Price per Sqft Year-on-Year'
    ).configure_title(
        fontSize=16,
        anchor='start'
    ).interactive()

    st.altair_chart(line_chart_avg_price_sqft_yoy, use_container_width=True)
else:
    st.warning("No data available to display the Year-on-Year Monthly Trends.")

# ============================
# Optional: Download Filtered Data
# ============================
st.download_button(
    label="Download Filtered Data as CSV",
    data=filtered_data.to_csv(index=False).encode('utf-8'),
    file_name='filtered_hdb_data.csv',
    mime='text/csv',
    help="Click to download the currently filtered data as a CSV file."
)
