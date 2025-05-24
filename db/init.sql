-- Create the target database
CREATE DATABASE fpkg;

-- Connect to that database and set up extensions
\connect fpkg;

CREATE EXTENSION IF NOT EXISTS age;
CREATE EXTENSION IF NOT EXISTS vector;

SET search_path = ag_catalog, pg_catalog;