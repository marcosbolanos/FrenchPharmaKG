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

class NameWithID(TypedDict):
    name:str
    id:str

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
) -> NameWithID | None:
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
    
def get_stripped_property_lists_from_query(
    drug_id: str,
    query: str,
    props_and_paths: dict[str, list[str]],
    cursor: psycopg.Cursor,
    conn: psycopg.Connection
) -> list[dict[str, str]] | None:
    """
    This is a basic helper function to execute a query with a drug_id, then return a list of results.
    'query' must be a valid Cypher query as a string, while 'drug_id' must be an existing drug id as str

    The function will return a list of results as plain strings. 

    The props and paths parameter determines which properties of the resulting json will be displayed
    It's a dictionary mapping desired output parameters to key paths, which are themselves lists of keys

    For instance, if the result of the query is res and 'props_and_paths' = ['name':['properties', 'name'], 'id':['properties', 'id']]
    The parsed result will be { 'name' :  res['properties']['name'], 'id' : res['properties']['id']] } 
    And the output will be a list containing all parsed results
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
        output = []
        # Parse all of the cursor's results into the desired output format
        for res in results:
            # Strip the text and load as json
            res = re.sub(r'::\w+$', '', res[0])
            res = json.loads(res)
            # Initialize the parsed result as an empty dictionary
            parsed_res = {}
            # Each desired property is extracted from the result and added to the dictionary
            for prop, key_path in props_and_paths.items():
                res_property = res
                # Filter the result according to the key path of the property
                for key in key_path:
                    res_property = res_property[key]
                parsed_res[prop] = res_property
            # The dictionary is added to the list of output dictionaries
            output.append(parsed_res)
        return output

    except Exception as e:
        print(e)
        conn.rollback()
        return


def get_generics(
    drug_id: str,
    cursor: psycopg.Cursor,
    conn: psycopg.Connection
) -> list[NameWithID] | None:
    """Find generic drugs using graph search"""

    query = f"""
    SELECT * FROM cypher('fcsv', $$ 
        MATCH(x:Drug)-[r:IsPartOfGenericGroup]->(g:GenericGroup)<-[q:IsPartOfGenericGroup]-(d:Drug)
        WHERE d.id = $drug_id
        RETURN x
    $$, %(cypher_params)s) AS (x agtype);
    """

    props_and_paths = {
        "name": ["properties", "name"],
        "id": ["properties", "id"],
    }

    result = get_stripped_property_lists_from_query(
        drug_id = drug_id,
        query = query,
        props_and_paths = props_and_paths,
        cursor = cursor,
        conn = conn,
    )

    return result


type Excipient = str
def get_excipients(
    drug_id: str,
    cursor: psycopg.Cursor,
    conn: psycopg.Connection
) -> list[NameWithID]:
    """Find a drugs' ingredients using graph search"""

    query = f"""
    SELECT * FROM cypher('fcsv', $$ 
        MATCH(d:Drug)-[r:ContainsExcipient]->(e:Excipient)
        WHERE d.id = $drug_id
        RETURN e
    $$, %(cypher_params)s) AS (x agtype);
    """

    props_and_paths = {
        "name": ["properties", "name"],
        "id": ["properties", "id"],
    }

    result = get_stripped_property_lists_from_query(
        drug_id = drug_id,
        query = query,
        props_and_paths = props_and_paths,
        cursor = cursor,
        conn = conn,
    )

    return result

def get_indications(
    drug_id: str,
    cursor: psycopg.Cursor,
    conn: psycopg.Connection
) -> list[NameWithID]:
    """Find a drug's indications using graph search"""

    query = f"""
    SELECT * FROM cypher('fcsv', $$ 
        MATCH(d:Drug)-[r:HasIndication]->(i:Indication)
        WHERE d.id = $drug_id
        RETURN i
    $$, %(cypher_params)s) AS (x agtype);
    """

    props_and_paths = {
        "name": ["properties"],
        "id": ["properties"],
    }

    result = get_stripped_property_lists_from_query(
        drug_id = drug_id,
        query = query,
        props_and_paths = props_and_paths,
        cursor = cursor,
        conn = conn,
    )

    return result

def get_contraindications(
    drug_id: str,
    cursor: psycopg.Cursor,
    conn: psycopg.Connection
) -> list[NameWithID]:
    """Find a drug's contraindications using graph search"""

    query = f"""
    SELECT * FROM cypher('fcsv', $$ 
        MATCH(d:Drug)-[r:HasContraindication]->(c:Contraindication)
        WHERE d.id = $drug_id
        RETURN c
    $$, %(cypher_params)s) AS (x agtype);
    """

    props_and_paths = {
        "name": ["properties", "type"],
        "id": ["properties", "id"],
    }

    result = get_stripped_property_lists_from_query(
        drug_id = drug_id,
        query = query,
        props_and_paths = props_and_paths,
        cursor = cursor,
        conn = conn,
    )

    return result


