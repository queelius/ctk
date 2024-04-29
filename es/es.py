import json
from elasticsearch.helpers import bulk
from elasticsearch import Elasticsearch

# Create a connection to Elasticsearch
es = Elasticsearch(
    "http://localhost:9200",
    basic_auth=("elastic", "pGKutlxXcPckjYBbMLmt")
)

# Create index
es.indices.create(index="conversations4") #, body=mapping)
contents = open("./data.json").read()
data = json.loads(contents)

# Assuming your JSON data is loaded into a variable `data`
def generate_data_for_es(data):
    for record in data:
        yield {
            "_index": "conversations",
            "_id": record["id"],
            "_source": record
        }

# Execute bulk insertion and capture errors
success, failed = bulk(es, generate_data_for_es(data), stats_only=False, raise_on_error=False)
#print(f"Successful documents: {success}")
#print("Failed documents:")
#for failure in failed:
#    print(failure)

print("Num of docs in index:", es.count(index="conversations")["count"])
print("Failed docs:", len(failed))
print("Successful docs:", success)

print("Details of first failed doc:", failed[0])