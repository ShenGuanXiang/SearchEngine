# 个性化查询

# 所有文本域
default_fields = ['url', 'title', 'author', 'how', 'anchors', 'text']

# 个性化查询项中，某些域boost调小一点
weight = {
    'url': 4,
    'title': 4,
    'author': 2,
    # 'date': 2,
    'days': 40,
    'cost': 40,
    'how': 40,
    'anchors': 2,
    'text': 1,
}


class PersonalizedQuery(object):
    """
    基于用户个人信息，在es查询中增加bool或查询项，相当于每次查询都额外加了一些查询条件
    """
    def __init__(self, user: dict):
        self.user = user

    def run(self):
        return [
            {
                'multi_match': {
                    'query': self.user['destinations'],
                    'type': 'best_fields',
                    'fields': [f'{field}^{weight[field]}' for field in default_fields],
                    'tie_breaker': 0.3,
                    'minimum_should_match': '20%',
                    'fuzziness': 'AUTO',
                    'operator': 'or',
                }
            },
            {
                'range': {
                    'cost': {
                        'gte': self.user['min_cost'],
                        'lte': self.user['max_cost'],
                        'boost': weight['cost']
                    }
                }
            },
            {
                'range': {
                    'days': {
                        'gte': self.user['min_days'],
                        'lte': self.user['max_days'],
                        'boost': weight['days']
                    }
                }
            },
            {
                'match': {
                    'how': {
                        'query': self.user['who'],
                        'boost': weight['how'],
                    }
                },
            },
            {
                'match': {
                    'how': {
                        'query': self.user['how'],
                        'boost': weight['how'],
                    }
                },
            }
        ]
