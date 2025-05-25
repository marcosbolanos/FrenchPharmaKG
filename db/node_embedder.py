from json import load
import psycopg
from openai import OpenAI
from pgvector.psycopg import register_vector
import os
import uuid

conn = psycopg.connect(
    dbname="fpkg",
    user=os.environ.get("POSTGRES_USER"),
    password=os.environ.get("POSTGRES_PASSWORD"),
    host="localhost",
    port="5431"
)

cursor = conn.cursor()

# Load the AGE extension (only needed once per session if not already loaded)
cursor.execute("LOAD 'age';")
# Set the search path to include AGE
cursor.execute("SET search_path = ag_catalog, \"$user\", public;")
conn.commit()

def add_vector_embeddings():
    print("\nAdding vector embeddings...")
    cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Commit the transaction so the extension is available
    conn.commit()
    
    # Register vector extension
    register_vector(conn)
    
    # Create a new table for vector embeddings
    print("Creating document_vectors table...")
    try:
        query = """
            CREATE TABLE IF NOT EXISTS document_vectors (
                id TEXT PRIMARY KEY,
                node_name TEXT,
                node_label TEXT,
                embedding vector(1536)  -- OpenAI text-embedding-3-small dimensionality
            );
        """
        cursor.execute(query)
        conn.commit()
        print("Document vectors table created successfully")
    except Exception as e:
        print(f"Error creating table: {str(e)}")
        return
    
    # Set up OpenAI client
    openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))  # Changed this line
    
    # Get all nodes from the graph database
    print("Retrieving nodes from graph database...")
    try:
        # First, get all vertex label tables for the graph
        cursor.execute("""
            SELECT name, relation
            FROM ag_catalog.ag_label
            WHERE kind = 'v' AND name != '_ag_label_vertex'
            AND graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'fcsv')
        """)
        vertex_labels = cursor.fetchall()
        
        if not vertex_labels:
            print("No vertex labels found in the graph")
            return
            
        print(f"Found {len(vertex_labels)} vertex label types")
        
        all_nodes = []
        
        # Query each vertex label table
        for label_name, table_relation in vertex_labels:
            try:
                # Now that we retrieved the label names, we can embed them
                cursor.execute(f"""
                    SELECT * FROM cypher('fcsv', $$
                        MATCH (v:{label_name})
                        RETURN v.id, v.name, labels(v)
                    $$) AS (v_id agtype, v_name agtype, v_labels agtype);
                """)
                label_nodes = cursor.fetchall()
                all_nodes.extend(label_nodes)
                print(f"Found {len(label_nodes)} nodes in {label_name}")
                
            except Exception as label_error:
                print(f"Error querying {label_name}: {str(label_error)}")
                continue
        
        nodes = all_nodes
        print(f"Total found {len(nodes)} nodes to embed")
        
    except Exception as e:
        print(f"Error retrieving nodes: {str(e)}")
        return
    
    # Process nodes in batches to avoid overwhelming the API
    batch_size = 100
    embedded_count = 0
    
    for i in range(0, len(nodes), batch_size):
        batch = nodes[i:i + batch_size]
        print(f"Processing batch {i//batch_size + 1}/{(len(nodes) + batch_size - 1)//batch_size}...")
        
        for node_id, node_name, node_label in batch:
            try:
                # Skip if node_name is empty or None
                if not node_name or node_name.strip() == '':
                    continue
                
                # Create text to embed (combine name and type for better context)
                text_to_embed = f"{node_label}: {node_name}"
                
                # Generate embedding using OpenAI
                response = openai_client.embeddings.create(
                    model="text-embedding-3-small",
                    input=text_to_embed
                )
                
                embedding = response.data[0].embedding
                
                # Insert into document_vectors table
                cursor.execute("""
                    INSERT INTO document_vectors (id, node_name, node_label, embedding)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        node_name = EXCLUDED.node_name,
                        node_label = EXCLUDED.node_label,
                        embedding = EXCLUDED.embedding
                """, (node_id, node_name, node_label, embedding))
                
                embedded_count += 1
                
                if embedded_count % 50 == 0:
                    print(f"  Embedded {embedded_count}/{len(nodes)} nodes...")
                    
            except Exception as e:
                print(f"Error embedding node {node_id} ({node_name}): {str(e)}")
                continue
        
        # Commit batch
        try:
            conn.commit()
        except Exception as e:
            print(f"Error committing batch: {str(e)}")
            conn.rollback()
    
    print(f"Successfully embedded {embedded_count} nodes")
    print("Vector embeddings added successfully!")

# Main execution
try:
   add_vector_embeddings()

except Exception as e:
    conn.rollback()
    print(f"Error: {str(e)}")
    print("Connection was rolled back")

finally:
    # Close the connection
    cursor.close()
    conn.close()
    print("\nDatabase connection closed.")