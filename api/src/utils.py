import psycopg
import os
import json
import textwrap
import re

from langchain_openai import OpenAIEmbeddings
from typing import TypedDict


class DBConfig(TypedDict):
    dbname:str
    user:str
    password:str
    host:str
    port:str


def init_database(
    db_config: DBConfig = None,
    dbname: str = "fpkg",
    user: str = None,
    password: str = None,
    host: str = "localhost",
    port: str = "5431"
) -> tuple[psycopg.Connection, psycopg.Cursor, OpenAIEmbeddings]:
    """Initialize database connection and OpenAI embeddings"""
    try:
        # Use db_config if provided, otherwise use individual parameters
        if db_config:
            dbname = db_config.get("dbname", dbname)
            user = db_config.get("user", user or os.environ.get("PGUSER"))
            password = db_config.get("password", password or os.environ.get("PGPASSWORD"))
            host = db_config.get("host", host)
            port = db_config.get("port", port)
        else:
            user = user or os.environ.get("PGUSER")
            password = password or os.environ.get("PGPASSWORD")
        
        # Connect to the Postgres database and to the OpenAI API
        conn = psycopg.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )

        cursor = conn.cursor()

        cursor.execute("LOAD 'age';")
        cursor.execute("SET search_path = ag_catalog, \"$user\", public;")

        conn.commit()

        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        print("Successfully initialized database and OpenAI embeddings")
        
        return conn, cursor, embeddings

    except Exception as e:
        print(e)
        raise

def vsearch_drug(
    drug: str,
    cursor: psycopg.Cursor,
    conn: psycopg.Connection,
    embeddings: OpenAIEmbeddings
) -> dict[str, str] | None:
    """Search for the exact name and ID of a drug in the database"""
    embedding = embeddings.embed_query(drug)

    embedding_string = "[" + ','.join(str(x) for x in embedding) + "]"

    # Using vector search to find nodes 
    query = f"""
        SELECT node_name, id, embedding
        FROM document_vectors
        ORDER BY embedding <-> %(vector)s
        LIMIT 5;
    """

    try:
        cursor.execute(query, {'vector':embedding_string})
        results = cursor.fetchall()
        print(f"found {len(results)} results")
        drug_of_interest = {}
        drug_of_interest["name"] = results[0][0].strip('"')
        drug_of_interest["id"] = results[0][1].strip('"')
        print(textwrap.dedent(f"""
        Top result:
            Name: {drug_of_interest['name']}
            ID: {drug_of_interest['id']}
        """))
        return drug_of_interest

    except Exception as e:
        print(e)
        conn.rollback()
        return

def get_generics(
    drug_id: str,
    cursor: psycopg.Cursor,
    conn: psycopg.Connection
) -> list[dict[str, str]]:
    """Find generic drugs using graph search"""

    query = f"""
    SELECT * FROM cypher('fcsv', $$ 
        MATCH(x:Drug)-[r:IsPartOfGenericGroup]->(g:GenericGroup)<-[q:IsPartOfGenericGroup]-(d:Drug)
        WHERE d.id = $drug_id
        RETURN x
    $$, %(cypher_params)s) AS (x agtype);
    """

    try:
        cursor.execute(query,params={
            "cypher_params": json.dumps(
                {
                    "drug_id": drug_id,
                }
            )
        })
        results = cursor.fetchall()
        print(f"Found {len(results)} results:")
        output = []
        for res in results:
            res = re.sub(r'::\w+$', '', res[0])
            res = json.loads(res)
            drug_info = {}
            drug_info["name"] = res["properties"]["name"]
            drug_info["id"] = res["properties"]["id"]
            output.append(drug_info)
            print('name: ', drug_info["name"])
            print('id: ', drug_info["id"])
        return output

    except Exception as e:
        print(e)
        conn.rollback()

def get_excipients(
    drug_id: str,
    cursor: psycopg.Cursor,
    conn: psycopg.Connection
):
    """Find a drugs' ingredients using graph search"""

    query = f"""
    SELECT * FROM cypher('fcsv', $$ 
        MATCH(d:Drug)-[r:ContainsExcipient]->(e:Excipient)
        WHERE d.id = $drug_id
        RETURN e
    $$, %(cypher_params)s) AS (x agtype);
    """

    try:
        cursor.execute(query,params={
            "cypher_params": json.dumps(
                {
                    "drug_id": drug_id,
                }
            )
        })
        results = cursor.fetchall()
        print(f"Found {len(results)} results:")
        output = []
        for res in results:
            res = re.sub(r'::\w+$', '', res[0])
            res = json.loads(res)
            drugname = res["properties"]["name"]
            output.append(drugname)
            print(drugname)
        return output

    except Exception as e:
        print(e)
        conn.rollback()
    return
