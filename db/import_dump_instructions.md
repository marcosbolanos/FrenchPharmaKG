### Importing the database from SQL dump file

Instead of manually running csv_loader.py then node_embedder.py, you can import the database from the available dump file. 

```
pg_restore -U $PGUSER -h localhost -p 5431 -d fpkg -v full_db.dump
```