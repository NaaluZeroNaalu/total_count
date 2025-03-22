import streamlit as st
import pandas as pd
import requests
import json
import openpyxl
import time

st.title("Excel File Reader with Month and Year Filter")


WATSONX_API_URL = "https://us-south.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29"
MODEL_ID = "meta-llama/llama-3-2-90b-vision-instruct"
PROJECT_ID = "4152f31e-6a49-40aa-9b62-0ecf629aae42"
API_KEY = "KEmIMzkw273qBcek8IdF-aShRUvFwH7K4psARTqOvNjI"


if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None

if 'total_count_df' not in st.session_state:
    st.session_state.total_count_df = None

# Function to get access token
def GetAccesstoken():
    auth_url = "https://iam.cloud.ibm.com/identity/token"
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    
    data = {
        "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
        "apikey": API_KEY
    }
    response = requests.post(auth_url, headers=headers, data=data)
    
    if response.status_code != 200:
        st.write(f"Failed to get access token: {response.text}")
        return None
    else:
        token_info = response.json()
        return token_info['access_token']

# Generate prompt for Watson API
def generatePrompt(json_datas):
    body = {
        "input": f"""
        Read this JSON data: {json_datas}
        Count the occurrences of each unique 'Activity Name' for each 'Finish_Month_Name' for this months {', '.join(selected_months)}. 
        Return the result as a JSON object where each key is an 'Activity Name' and each value is a dictionary with 'Finish_Month_Name' as keys and counts as values, like this example:
        {{
            "Install Windows": {{"Mar": 2, "Apr": 1}},
            "Paint Walls": {{"Mar": 1, "Apr": 3}}
        }}
        No code, no explanation, just the JSON for python.
        """, 
        "parameters": {
            "decoding_method": "greedy",
            "max_new_tokens": 8100,
            "min_new_tokens": 0,
            "stop_sequences": [";"],
            "repetition_penalty": 1.05,
            "temperature": 0.5
        },
        "model_id": MODEL_ID,
        "project_id": PROJECT_ID
    }
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GetAccesstoken()}"
    }
    
    if not headers["Authorization"]:
        return "Error: No valid access token."
    
    response = requests.post(WATSONX_API_URL, headers=headers, json=body)
    
    if response.status_code != 200:
        st.write(f"Failed to generate prompt: {response.text}")
        return "Error generating prompt"
    
    return response.json()['results'][0]['generated_text'].strip()

# Function to create chunks and process data
def createChunk():
    chunk_size = 500
    num_rows = len(filtered_df)
    num_chunks = (num_rows + chunk_size - 1) // chunk_size  # Ceiling division to get the number of chunks
    all_chunks = {}  # Dictionary to store all the merged chunks
    temp = []
   
    st.write(f"Filtered rows in JSON format (split into {chunk_size}-row chunks):")
    
    # Iterate over each chunk
    for i in range(num_chunks):
        start_idx = i * chunk_size
        end_idx = min((i + 1) * chunk_size, num_rows)
        chunk_df = filtered_df.iloc[start_idx:end_idx]
        
        # Convert chunk to JSON format (as a dictionary)
        chunk_json = chunk_df.to_json(orient="index", date_format="iso")  # Using "index" to keep tasks as keys
        
        # Convert string JSON to a Python dictionary
        chunk_json_data = json.loads(chunk_json)
        
        # Merge the chunk data into the all_chunks dictionary
        for task, month_data in chunk_json_data.items():
            if task not in all_chunks:
                all_chunks[task] = month_data
            else:
                # Merge monthly data for tasks that appear in multiple chunks
                for month, quantity in month_data.items():
                    if month in all_chunks[task]:
                        all_chunks[task][month] += quantity  # Combine quantities (e.g., sum them)
                    else:
                        all_chunks[task][month] = quantity
        
        # Display the chunk (optional, as per your previous code)
        st.write(f"Chunk {i + 1} (Rows {start_idx + 1} to {end_idx}):")
        # st.write(generatePrompt(chunk_json))  # If you need to process each chunk with generatePrompt()
        temp.append(json.loads(generatePrompt(chunk_json)))
    table_data = []

    for data in temp:
        for name, months in data.items():
            # For each activity (name), count the occurrences of each month
            for month, count in months.items():
                table_data.append({"Name": name, "Month": month, "Count": count})

    # Convert table_data to DataFrame
    df = pd.DataFrame(table_data)

    # Pivot the data to create the month-wise table for each name
    pivot_df = df.pivot_table(index="Name", columns="Month", values="Count", aggfunc="sum", fill_value=0)

    # Add a 'Total Count' column
    pivot_df['Total Count'] = pivot_df.sum(axis=1)

    st.session_state.total_count_df = pivot_df.copy()

    # Display the pivot table with total count
    st.dataframe(pivot_df)
    # st.dataframe(st.session_state.total_count_df)

    


# File upload and processing
uploaded_file = st.file_uploader("Choose an Excel file", type="xlsx")

if uploaded_file is not None and st.session_state.processed_df is None:
    workbook = openpyxl.load_workbook(uploaded_file)
    sheet = workbook["TOWER 4 FINISHING."]
    
    activity_col_idx = 5  

    non_bold_rows = []
    for row_idx, row in enumerate(sheet.iter_rows(min_row=17, max_col=16), start=16):
        cell = row[activity_col_idx]  
        if cell.font and not cell.font.b:  
            non_bold_rows.append(row_idx)

    df = pd.read_excel(uploaded_file, sheet_name="TOWER 4 FINISHING.", skiprows=15)
    
    df.columns = ['Module', 'Floor', 'Flat', 'Domain', 'Activity ID', 'Activity Name', 
                  'Monthly Look Ahead', 'Baseline Duration', 'Baseline Start', 'Baseline Finish', 
                  'Actual Start', 'Actual Finish', '%Complete', 'Start', 'Finish', 'Delay Reasons']
    
    required_columns = ['Module', 'Floor', 'Flat', 'Activity ID', 'Activity Name', 'Start', 'Finish']
    df = df[required_columns]
    
    df.index = df.index + 16
    df = df.loc[df.index.isin(non_bold_rows)]

    df['Start'] = pd.to_datetime(df['Start'], errors='coerce', dayfirst=True)
    df['Finish'] = pd.to_datetime(df['Finish'], errors='coerce', dayfirst=True)

    df['Finish_Year'] = df['Finish'].dt.year
    df['Finish_Month'] = df['Finish'].dt.month
    df['Finish_Month_Name'] = df['Finish'].dt.strftime('%b')

    st.session_state.processed_df = df

# Process the filtered data
if st.session_state.processed_df is not None:
    df = st.session_state.processed_df
    available_years = sorted(df['Finish_Year'].unique())
    available_months = sorted(df['Finish_Month_Name'].unique())

    selected_year = st.sidebar.selectbox('Select Year', available_years, index=available_years.index(df['Finish_Year'].max()))
    selected_months = st.sidebar.multiselect('Select Months', available_months, default=available_months)

    filtered_df = df[(df['Finish_Year'] == selected_year) & (df['Finish_Month_Name'].isin(selected_months))]

    st.write(f"Filtered rows based on the selected months and year: {', '.join(selected_months)} {selected_year}")
    st.write(filtered_df)
    st.write(f"Number of rows: {len(filtered_df)}")

    activity_month_counts = pd.pivot_table(
        filtered_df, 
        values='Activity ID', 
        index='Activity Name', 
        columns='Finish_Month_Name', 
        aggfunc='count', 
        fill_value=0
    )

    activity_month_counts['Total Count'] = activity_month_counts.sum(axis=1)

    # st.write(f"Activity counts by month for {selected_year}:")
    # st.write(activity_month_counts)

if st.button('Count The activity'):
    createChunk()
