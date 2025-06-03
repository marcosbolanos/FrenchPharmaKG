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

class Database: 
    def __init__(
            self, 
            db_config: DBConfig
    ):
        try:
            # Connect to the Postgres database and to the OpenAI API
            self.conn = psycopg.connect(
                dbname=db_config.get("dbname", "fpkg"),
                user=db_config.get("user", os.environ.get("PGUSER")),
                password=db_config.get("password", os.environ.get("PGPASSWORD")),
                host=db_config.get("host", "localhost"),
                port=db_config.get("port", "5431")
            )

            self.cursor = self.conn.cursor()

            self.cursor.execute("LOAD 'age';")
            self.cursor.execute("SET search_path = ag_catalog, \"$user\", public;")

            self.conn.commit()

            self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
            print("Successfully initialized database and OpenAI embeddings")

        except Exception as e:
            print(e)
        
    def vsearch_drug(
        self,
        drug: str
    ) -> dict[str, str] | None:
        embedding = self.embeddings.embed_query(drug)

        embedding_string = "[" + ','.join(str(x) for x in embedding) + "]"

        # Using vector search to find nodes 
        query = f"""
            SELECT node_name, id, embedding
            FROM document_vectors
            ORDER BY embedding <-> %(vector)s
            LIMIT 5;
        """

        try:
            self.cursor.execute(query, {'vector':embedding_string})
            results = self.cursor.fetchall()
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
            self.conn.rollback()
            return

    def find_generics(
        self,
        drug_id: str
    ) -> list[str]:
        query = f"""
        SELECT * FROM cypher('fcsv', $$ 
            MATCH(x:Drug)-[r:IsPartOfGenericGroup]->(g:GenericGroup)<-[q:IsPartOfGenericGroup]-(d:Drug)
            WHERE d.id = $drug_id
            RETURN x
        $$, %(cypher_params)s) AS (x agtype);
        """

        try:
            self.cursor.execute(query,params={
                "cypher_params": json.dumps(
                    {
                        "drug_id": drug_id,
                    }
                )
            })
            results = self.cursor.fetchall()
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
            self.conn.rollback()
