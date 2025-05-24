from json import load
import psycopg2
import openai
import os
from pgvector.psycopg2 import register_vector

conn = psycopg2.connect(
    dbname="fpkg",
    user=os.environ.get("PGUSER"),
    password=os.environ.get("PGPASSWORD"),
    host="localhost",
    port="5431"
)

cursor = conn.cursor()

# Load the AGE extension (only needed once per session if not already loaded)
cursor.execute("LOAD 'age';")
# Set the search path to include AGE
cursor.execute("SET search_path = ag_catalog, \"$user\", public;")
conn.commit()

# Creating a new graph for the database, if it doesn't exist
# Check if the graph exists
cursor.execute("SELECT * FROM ag_catalog.ag_graph WHERE name = 'fcsv';")
if cursor.fetchone() is None:
    # Graph doesn't exist, so create it
    cursor.execute("SELECT * FROM ag_catalog.create_graph('fcsv');")
    conn.commit()
    print("Created new graph 'fcsv'")
else:
    # Graph exists, drop it and recreate for a clean start
    cursor.execute("SELECT * FROM ag_catalog.drop_graph('fcsv', true);") 
    cursor.execute("SELECT * FROM ag_catalog.create_graph('fcsv');")
    conn.commit()
    print("Recreated graph 'fcsv'")

# Register vertex and edge labels
def register_labels():
    # Register vertex labels
    node_types = [
        "Drug", "ActiveIngredient", "Excipient", "GenericGroup", 
        "LegalSubstanceList", "Indication", "Contraindication", "ROA"
    ]
    
    print("\nRegistering node labels...")
    for node_type in node_types:
        try:
            cursor.execute(f"SELECT create_vlabel('fcsv', '{node_type}');")
            print(f"  - Registered '{node_type}' node label")
        except Exception as e:
            if "already exists" in str(e):
                print(f"  - Label '{node_type}' already exists")
            else:
                print(f"  - Error registering '{node_type}': {str(e)}")
    
    # Register edge labels
    edge_types = [
        "IsAdministeredVia", "ContainsActiveIngredient", "ContainsExcipient",
        "IsPartOfGenericGroup", "IsReferenceDrugInGroup", "IsGenericDrugInGroup",
        "BelongsToLegalSubstanceList", "HasIndication", "HasContraindication"
    ]
    
    print("\nRegistering edge labels...")
    for edge_type in edge_types:
        try:
            cursor.execute(f"SELECT create_elabel('fcsv', '{edge_type}');")
            print(f"  - Registered '{edge_type}' edge label")
        except Exception as e:
            if "already exists" in str(e):
                print(f"  - Label '{edge_type}' already exists")
            else:
                print(f"  - Error registering '{edge_type}': {str(e)}")
    
    conn.commit()
    print("All labels registered successfully")

# Loading all nodes from the CSV files
def load_nodes_from_csv():
    csv_dir = '/tmp/csv/nodes'
    
    # Check if the csv directory exists
    if not os.path.exists(csv_dir):
        print(f"Directory '{csv_dir}' not found.")
        return
    
    # Iterate through all files in the csv directory
    for filename in os.listdir(csv_dir):
        if filename.endswith('.csv'):
            file_path = os.path.abspath(os.path.join(csv_dir, filename))
            print(f"Processing {file_path}...")
            
            # Assuming the file name without extension represents the node type
            node_type = os.path.splitext(filename)[0]
            
            # Read the CSV file and create nodes
            try:
                cursor.execute(f"""
                    SELECT * FROM ag_catalog.load_labels_from_file(
                        'fcsv', 
                        '{node_type}', 
                        '{file_path}'
                    );
                """)
                conn.commit()
                print(f"Successfully loaded nodes from {filename}")
            except Exception as e:
                conn.rollback()
                print(f"Error loading {filename}: {str(e)}")

def load_edges_from_csv():
    csv_dir = '/tmp/csv/edges'
    
    # Check if the csv directory exists
    if not os.path.exists(csv_dir):
        print(f"Directory '{csv_dir}' not found.")
        return
    
    # Iterate through all files in the csv directory
    for filename in os.listdir(csv_dir):
        if filename.endswith('.csv'):
            file_path = os.path.abspath(os.path.join(csv_dir, filename))
            print(f"Processing {file_path}...")
            
            # Assuming the file name without extension represents the edge type
            edge_type = os.path.splitext(filename)[0]
            
            # Read the CSV file and create edges
            try:
                cursor.execute(f"""
                    SELECT * FROM ag_catalog.load_edges_from_file(
                        'fcsv', 
                        '{edge_type}', 
                        '{file_path}'
                    );
                """)
                conn.commit()
                print(f"Successfully loaded edges from {filename}")
            except Exception as e:
                conn.rollback()
                print(f"Error loading {filename}: {str(e)}")

# Verify the loaded data
def verify_graph():
    # Count vertices by label
    cursor.execute("""
    SELECT label_id, count(*) 
    FROM ag_catalog.ag_label 
    WHERE graph_id = (SELECT id FROM ag_catalog.ag_graph WHERE name = 'fcsv')
    GROUP BY label_id 
    ORDER BY label_id;
    """)
    vertex_counts = cursor.fetchall()
    
    # Map label_ids to label names
    cursor.execute("""
    SELECT id, name FROM ag_catalog.ag_label 
    WHERE graph_id = (SELECT id FROM ag_catalog.ag_graph WHERE name = 'fcsv')
    AND kind = 'v';
    """)
    vertex_labels = {id: name for id, name in cursor.fetchall()}
    
    # Count edges by label
    cursor.execute("""
    SELECT label_id, count(*) 
    FROM ag_catalog.ag_edge 
    WHERE graph_id = (SELECT id FROM ag_catalog.ag_graph WHERE name = 'fcsv')
    GROUP BY label_id 
    ORDER BY label_id;
    """)
    edge_counts = cursor.fetchall()
    
    # Map label_ids to label names
    cursor.execute("""
    SELECT id, name FROM ag_catalog.ag_label 
    WHERE graph_id = (SELECT id FROM ag_catalog.ag_graph WHERE name = 'fcsv')
    AND kind = 'e';
    """)
    edge_labels = {id: name for id, name in cursor.fetchall()}
    
    # Print summary
    print("\nData Verification Summary:")
    print("------------------------")
    print("Vertices:")
    for label_id, count in vertex_counts:
        label_name = vertex_labels.get(label_id, f"Unknown (ID: {label_id})")
        print(f"  - {label_name}: {count}")
    
    print("\nEdges:")
    for label_id, count in edge_counts:
        label_name = edge_labels.get(label_id, f"Unknown (ID: {label_id})")
        print(f"  - {label_name}: {count}")

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
                id UUID PRIMARY KEY,
                node_name TEXT,
                node_type TEXT,
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
    openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    # Get all nodes from the graph database
    print("Retrieving nodes from graph database...")
    try:
        # First, get all vertex label tables for the graph
        cursor.execute("""
            SELECT name, relation FROM ag_catalog.ag_label 
            WHERE graph = (SELECT id FROM ag_catalog.ag_graph WHERE name = 'fcsv')
            AND kind = 'v'
            AND name != '_ag_label_vertex'
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
                # The table_relation contains the full table path like 'fcsv."Drug"'
                cursor.execute(f"""
                    SELECT id::text as node_id, 
                           properties->>'name' as node_name,
                           '{label_name}' as node_type
                    FROM {table_relation}
                    WHERE properties->>'name' IS NOT NULL
                    AND properties->>'name' != ''
                """)
                label_nodes = cursor.fetchall()
                all_nodes.extend(label_nodes)
                print(f"  Found {len(label_nodes)} nodes in {label_name}")
                
            except Exception as label_error:
                print(f"  Error querying {label_name}: {str(label_error)}")
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
        
        for node_id, node_name, node_type in batch:
            try:
                # Skip if node_name is empty or None
                if not node_name or node_name.strip() == '':
                    continue
                
                # Create text to embed (combine name and type for better context)
                text_to_embed = f"{node_type}: {node_name}"
                
                # Generate embedding using OpenAI
                response = openai_client.embeddings.create(
                    model="text-embedding-3-small",
                    input=text_to_embed
                )
                
                embedding = response.data[0].embedding
                
                # Insert into document_vectors table
                cursor.execute("""
                    INSERT INTO document_vectors (id, node_name, node_type, embedding)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        node_name = EXCLUDED.node_name,
                        node_type = EXCLUDED.node_type,
                        embedding = EXCLUDED.embedding
                """, (node_id, node_name, node_type, embedding))
                
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
    # First register all labels
    register_labels()
    
    # Then load nodes
    print("\nLoading nodes...")
    load_nodes_from_csv()
    
    # Then load edges
    print("\nLoading edges...")
    load_edges_from_csv()
    
    # Verify the graph
    # verify_graph()

    # Add vector embeddings to nodes
    add_vector_embeddings()
    
    print("\nDatabase loading completed successfully!")

except Exception as e:
    conn.rollback()
    print(f"Error: {str(e)}")
    print("Connection was rolled back")

finally:
    # Close the connection
    cursor.close()
    conn.close()
    print("\nDatabase connection closed.")
