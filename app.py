import streamlit as st
import mysql.connector
from mysql.connector import Error
import os
from langchain.prompts import ChatPromptTemplate
from sentence_transformers import SentenceTransformer
import re
import pandas as pd
from langchain_groq import ChatGroq
from langchain.schema import HumanMessage, AIMessage
from dotenv import load_dotenv

try:
    from langchain.vectorstores import Chroma
except ImportError as e:
    st.error(f"Error importing Chroma: {e}")
    raise

# Load environment variables from .env file
load_dotenv()

# Environment variables
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = os.getenv("MYSQL_PORT")
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DB = os.getenv("MYSQL_DB")

def build_schema_desc(cursor, table_name, prefix=""):
    desc = []
    cursor.execute(f"DESCRIBE {table_name}")
    for column in cursor.fetchall():
        d = f"{prefix}- Name: {column[0]}, Type: {column[1]}, Null: {column[2]}, Key: {column[3]}"
        desc.append(d)
    return desc

def fetch_schemas(db_connection):
    schemas = []
    simple_table_list = []
    cursor = db_connection.cursor()
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    for table in tables:
        table_name = table[0]
        simple_table_list.append(f"- {table_name}")
        schema_desc = [f"Schema for {table_name}:"]
        schema_desc += build_schema_desc(cursor, table_name)
        schema_desc.append("") # For newline
        schemas += schema_desc
    cursor.close()
    return "\n".join(simple_table_list) + "\n\n" + "\n".join(schemas)

llm_groq = ChatGroq(temperature=0.2, model_name="llama3-70b-8192")
template = """Based on the schema below, write a SQL query that answers the question.

schema: {schema}

Question: {question}

SQL Query:"""
prompt = ChatPromptTemplate.from_template(template)

message_history = []

# Initialize the SentenceTransformer model with 768-dimensional embeddings
model = SentenceTransformer('all-mpnet-base-v2')

class CustomHuggingFaceEmbeddings:
    def __init__(self, model_name):
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts):
        return self.model.encode(texts).tolist()

    def embed_query(self, text):
        return self.model.encode([text])[0].tolist()

def get_embeddings(text_list):
    embeddings = model.encode(text_list, convert_to_tensor=True)
    return embeddings

def store_schema_embeddings(db_connection):
    cursor = db_connection.cursor()
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    
    descriptions = []
    for table in tables:
        table_name = table[0]
        schema_desc = build_schema_desc(cursor, table_name)
        descriptions += schema_desc

    vectorstore = Chroma(
        collection_name="schema_descriptions", 
        embedding_function=CustomHuggingFaceEmbeddings('all-mpnet-base-v2')
    )

    embeddings = get_embeddings(descriptions)
    vectorstore.add_texts(texts=descriptions, embeddings=embeddings)
    
    cursor.close()
    return vectorstore

def find_similar_schema_description(query, vectorstore):
    query_embedding = CustomHuggingFaceEmbeddings('all-mpnet-base-v2').embed_query(query)
    results = vectorstore.similarity_search_by_vector(query_embedding, k=5)
    similar_descriptions = [result.page_content for result in results]
    return "\n".join(similar_descriptions)

def extract_sql(response):
    match = re.search(r"```(.*?)```", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    else:
        return response.strip()

def execute_query_with_retries(my_query, vectorstore, db_connection, max_attempts=5):
    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        st.write(f"Attempt {attempts} of {max_attempts}")
        
        similar_descriptions = find_similar_schema_description(my_query, vectorstore)
        schema_context = fetch_schemas(db_connection) + "\n" + similar_descriptions
        
        message_history.append(HumanMessage(content=my_query))
        
        res = llm_groq(messages=message_history + [HumanMessage(content=prompt.format(question=my_query, schema=schema_context, messages=message_history))])
        clean_sql = extract_sql(res.content)
        st.write(f"Generated SQL Query:\n{clean_sql}")
        
        message_history.append(AIMessage(content=clean_sql))
        
        try:
            st.write("Attempting to run the query and convert it to a DataFrame")
            cursor = db_connection.cursor()
            cursor.execute(clean_sql)
            result = cursor.fetchall()
            dataframe = pd.DataFrame(result, columns=[x[0] for x in cursor.description])
            st.write("Query executed successfully.")
            cursor.close()
            return dataframe
        except Exception as e:
            error_message = str(e)
            st.write("Query failed with the following error:")
            st.write(error_message)
            if attempts == max_attempts:
                st.write("Reached maximum attempt limit. Stopping retries.")
                return None

def main():
    st.title("SQL Query Generator")

    st.write("Connect to your MySQL database:")
    db_host = st.text_input("Host", MYSQL_HOST)
    db_port = st.text_input("Port", MYSQL_PORT)
    db_user = st.text_input("User", MYSQL_USER)
    db_password = st.text_input("Password", MYSQL_PASSWORD, type="password")
    db_name = st.text_input("Database", MYSQL_DB)

    if st.button("Connect"):
        try:
            db_connection = mysql.connector.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                passwd=db_password,
                database=db_name
            )
            st.write("Connected to MySQL server")
            vectorstore = store_schema_embeddings(db_connection)
            st.write("Stored schema embeddings")

            my_query = st.text_input("Enter your query:", "Get all of the order numbers for the first 3 customers.")
            if st.button("Generate and Run SQL Query"):
                df = execute_query_with_retries(my_query, vectorstore, db_connection)
                if df is not None:
                    st.write(df)
        except Error as e:
            st.write("Error while connecting to MySQL:", e)

if __name__ == "__main__":
    main()
