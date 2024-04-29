import json
from elasticsearch.helpers import bulk
from elasticsearch import Elasticsearch

# Create a connection to Elasticsearch
es = Elasticsearch(
    "http://localhost:9200",
    basic_auth=("elastic", "pGKutlxXcPckjYBbMLmt")
)



# Verify data import
res = es.search(index="conversations", query={"match_all": {}})
print(json.dumps(res['hits'], indent=2))
#print("Got %d Hits:" % res['hits']['total']['value'])
#for hit in res['hits']['hits']:
#    print(json.dumps(hit["_source"]))

# Example query to find a specific conversation by title
#res = es.search(index="conversations", query={"match": {"title": "Polynomial Differential Equation Solution"}})
#print("Query results:")
#for hit in res['hits']['hits']:
#    print(hit["_source"])
