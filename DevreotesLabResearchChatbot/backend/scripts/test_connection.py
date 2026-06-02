import os
import sys
from pathlib import Path
from neo4j import GraphDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.paths import load_project_dotenv


load_project_dotenv()

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),
)

with driver.session() as session:
    result = session.run("RETURN 'Connection successful!' AS msg")
    print(result.single()["msg"])

driver.close()
