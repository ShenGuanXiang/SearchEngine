# 实现基础搜索和高级搜索方法
import os.path

from elasticsearch import Elasticsearch
from personalizedquery import PersonalizedQuery

# 所有文本域
default_fields = ['url', 'title', 'author', 'how', 'anchors', 'text']

default_user = {
    'id': 'default',
    'destinations': '',
    'min_cost': 0,
    'max_cost': 0,
    'min_days': 0,
    'max_days': 0,
    'who': '',
    'how': ''
}

# 查询期间增加boosting，相比索引构建时就增加boosting会更为灵活
weight = {
    'url': 40,
    'title': 40,
    'author': 20,
    # 'date': 20,
    'days': 20,
    'cost': 20,
    'how': 20,
    'anchors': 20,
    'text': 10,
}

snapshot_path = './snapshot'


# https://www.knowledgedict.com/tutorial/elasticsearch-query.html
class Querier(object):
    """
    这个类负责解析传给es的query，完成和前端的对接
    """

    def __init__(self, query_string: str, site_url='', query_type='default', user=None, fields=None):
        if user is None:
            user = default_user
        if fields is None:
            fields = default_fields
        self.query_string = query_string
        self.prefix_url = site_url
        self.query_type = query_type
        self.fields = fields
        self.user = user

    def query(self) -> dict:
        query = {  # 查询的分词器默认和构建索引时各个域上的分词器对应
            'bool': {
                'must':
                    [
                        {
                            'multi_match': {  # 默认的按域查询： 在多个域上反复执行相同查询
                                'query': self.query_string,
                                'type': 'best_fields',
                                'fields': [f'{field}^{weight[field]}' for field in self.fields],  # 在查询字段后使用 ^boost
                                'tie_breaker': 0.3,  # 除best_fields外的字段评分的权重
                                'minimum_should_match': '20%',  # 最少匹配的个数为query子句个数的百分比向下取整。
                                'fuzziness': 'AUTO',  # 允许一个自适应的编辑距离，实现拼写校正
                                'operator': 'or',  # 只要一个词匹配就行
                            }
                        }
                    ] if self.query_type == 'default' else
                    [
                        {
                            'multi_match': {  # 短语查询：1、分词后所有词项都要出现。2、词项顺序要一致(slop=0)。
                                'query': self.query_string,
                                'type': 'phrase',  # 使用匹配最好的域的score
                                'fields': [f'{field}^{weight[field]}' for field in self.fields],  # 在查询字段后使用 ^boost
                                'operator': 'and',  # 每个词都要匹配
                                'slop': 0,  # slop参数告诉match_phrase查询词条能够相隔多远时仍然将文档视为匹配。
                            }
                        }
                    ] if self.query_type == 'match_phrase' else
                    [
                        {
                            'bool': {
                                "should": [  # 逻辑或，一个域上满足即可
                                    {
                                        'wildcard': {  # 通配查询，需要扫描倒排索引中的词列表才能找到所有匹配的词，然后依次获取每个词相关的文档 ID
                                            field: {
                                                'value': self.query_string,  # 支持 ? 和 *，左通配会导致查询速度比较慢
                                                'boost': weight[field],
                                                'rewrite': 'constant_score',
                                                # 匹配的词项数较少时为每一个匹配的词项增加一个should子句，匹配的词项较多时，利用bitset计算？
                                                # https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-multi-term-rewrite.html
                                            }
                                        }
                                    } for field in self.fields
                                ]
                            }
                        }
                    ] if self.query_type == 'wildcard' else [],
                'should':
                    [
                        {
                            'rank_feature': {
                                # https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-rank-feature-query.html
                                'field': 'pagerank',
                                'boost': 10,
                                "saturation": {
                                    "pivot": 0.0001  # ≈web图中孤立节点的pagerank，score=pr/pr+pivot
                                }
                            }
                        },
                    ],
                'filter':
                    [
                        {
                            'prefix': {  # 过滤url前缀，实现站内搜索，默认为空字符串
                                'url':
                                    {
                                        'value': self.prefix_url,
                                        'rewrite': 'constant_score',
                                    }
                            }
                        }
                    ],
            }
        }
        query['bool']['should'] += PersonalizedQuery(user=self.user).run()  # 个性化查询通过额外加分实现
        return query


class Searcher(object):
    def __init__(self, index_name: str, query: dict, from_=0, size=10):
        self.client = Elasticsearch("http://localhost:9200", )
        self.index_name = index_name
        self.query = query
        self.from_ = from_
        self.size = size

    def run(self) -> dict:
        print('==================本次es查询请求===================')
        print(self.query)
        response = self.client.search(index=self.index_name,
                                      query=self.query,
                                      highlight={  # 预览-高亮 https://blog.csdn.net/qq330983778/article/details/103690377
                                          "boundary_scanner_locale": "zh_CN",
                                          "pre_tags": ["<em>"],
                                          "post_tags": ["</em>"],
                                          "fields": {
                                              "title": {
                                                  "fragment_size": 20,
                                                  "no_match_size": 20,
                                              },
                                              "text": {
                                                  "fragment_size": 40,
                                                  "no_match_size": 40,
                                              },
                                          },
                                      },
                                      # 分页：https://zhuanlan.zhihu.com/p/347173510，比较朴素，每次都要重新查询并从top0开始返回
                                      from_=self.from_,  # 从“第几条”开始查询
                                      size=self.size,  # 查询多少条
                                      )

        result = {
            'links': [
                {
                    'url': link['_source']['url'],
                    'title': link['highlight']['title'] if 'title' in link['highlight'] else '',
                    'author': link['_source']['author'],
                    'date': link['_source']['date'],
                    'days': link['_source']['days'] if link['_source']['days'] != '200' else '99+',
                    'cost': link['_source']['cost'] if link['_source']['cost'] != '-1' else '',
                    'how': link['_source']['how'],
                    # 'anchors': link['_source']['anchors'],
                    'text': link['highlight']['text'] if 'text' in link['highlight'] else '',
                    'snapshot': os.path.exists(snapshot_path + '\\' +
                                               link['_source']['url'][link['_source']['url'].rindex('/') + 1:] + '.html')
                } for link in response['hits']['hits']
            ]
        }

        print("==================本次es查询结果===================")
        print(result)

        return result


if __name__ == "__main__":
    # querier = Querier("天津五大道")
    querier = Querier("天津", site_url='https://travel.qunar.com/youji')
    # querier = Querier("天津*", query_type='wildcard', fields=['title', 'text'])
    # querier = Querier("在五大道中驻足遥想津城", query_type='match_phrase')
    searcher = Searcher(index_name='travel-info', query=querier.query())
    searcher.run()
