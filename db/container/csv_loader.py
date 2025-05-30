from json import load
import psycopg
import os

conn = psycopg.connect(
    dbname="fpkg",
    user=os.environ.get("POSTGRES_USER"),
    password=os.environ.get("POSTGRES_PASSWORD"),
    host="localhost",
    port="5432"
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
    csv_dir = './csv/nodes'
    
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
    csv_dir = './csv/edges'
    
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
