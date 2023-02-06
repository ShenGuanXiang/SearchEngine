# 文本索引
# es配环境：https://blog.csdn.net/shawroad88/article/details/107337086
# 模板：https://github.com/elastic/elasticsearch-py/blob/main/examples/bulk-ingest/bulk-ingest.py
import tqdm
from elasticsearch import Elasticsearch
from elasticsearch.helpers import streaming_bulk
import pandas as pd
import csv

data_path = 'data.csv'


class Indexer(object):

    def __init__(self, index_name: str):
        """Creates an index in Elasticsearch if one isn't already there."""
        self.client = Elasticsearch("http://localhost:9200", )  # Add your cluster configuration here!
        self.index_name = index_name
        if self.client.indices.exists(index=self.index_name):
            print("Deleting old index...")
            self.client.indices.delete(index=self.index_name)
        print("Creating an index...")
        self.client.options(
            ignore_status=400,  # ignore 400 caused by IndexAlreadyExistsException when creating an index
        ).indices.create(
            index=self.index_name,
            settings={
                "number_of_shards": 1,  # 不分片
                # 相似度评分标准采用BM25模型（默认也是这个）
                # https://www.elastic.co/guide/en/elasticsearch/reference/current/index-modules-similarity.html#bm25
                "similarity": {
                    "my_custom_similarity": {
                        "type": "BM25",
                        "k1": 1.2,
                        "b": 0.75,
                        "discount_overlaps": True
                    }
                }
            },
            mappings={
                "properties": {                    # search_analyzer默认和索引的分词器一致
                    "url": {"type": "keyword", },  # 不需要分词的字段设置为keyword提高性能
                    "title": {"type": "text",
                              "analyzer": "ik_max_word", },
                    "author": {"type": "text",
                               "analyzer": "ik_max_word", },
                    "date": {"type": "date",
                             "format": "date_optional_time", },  # 与strict_date_optional_time的区别是不需要严格4位、2位、2位
                    "days": {"type": "integer", },
                    "cost": {"type": "integer", },
                    "how": {"type": "text",
                            "analyzer": "ik_max_word"},
                    "anchors": {"type": "text",
                                "analyzer": "ik_max_word", },
                    "text": {"type": "text",
                             "analyzer": "ik_smart", },  # 正文的分词粒度相对粗一些
                    "pagerank": {"type": "rank_feature", },
                }
            },
        )

    def generate_actions(self) -> dict:
        """Reads the file through df and for each row
        yields a single document. This function is passed into the bulk()
        helper to create many documents in sequence.
        """
        with open(data_path, encoding='utf_8_sig', newline='') as csvfile:
            reader = csv.DictReader(csvfile)

            i = 0
            for row in reader:
                doc = {
                    'index': self.index_name,
                    '_op_type': 'create',  # 之前建完索引就不更新了
                    '_id': i,
                    '_source': {
                        "url": row['url'],
                        "title": row['title'],
                        "author": row['author'],
                        "date": row['date'],
                        "days": '200' if row['days'] == '99+' else row['days'],
                        "cost": '-1' if row['cost'] == '' else row['cost'],
                        "how": row['how'],
                        "anchors": row['anchors'].strip('[').strip(']').replace("'", ''),
                        "text": row['text'],
                        "pagerank": row['pagerank'],
                    }
                }
                # print(doc['_source'])
                i += 1
                yield doc

    def run(self):
        print("Indexing documents...")
        number_of_docs = len(pd.read_csv(data_path, usecols=['url']))
        progress = tqdm.tqdm(unit="docs", total=number_of_docs)
        successes = 0
        for ok, action in streaming_bulk(client=self.client, index=self.index_name, actions=self.generate_actions(),
                                         # raise_on_exception=False, raise_on_error=False  # 由于格式等原因无法构建索引的文档直接跳过
                                         ):
            progress.update(1)
            successes += ok
        print("Indexed %d/%d documents" % (successes, number_of_docs))


if __name__ == "__main__":
    indexer = Indexer(index_name="travel-info")
    indexer.run()

# es python API参考：
# https://www.cnblogs.com/ljhdo/p/4981928.html
# https://elasticsearch-py.readthedocs.io/en/master/api.html
