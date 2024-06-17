import streamlit as st
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Environment variables
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = os.getenv("MYSQL_PORT")
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DB = os.getenv("MYSQL_DB")

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
        except Error as e:
            st.write("Error while connecting to MySQL:", e)

if __name__ == "__main__":
    main()
