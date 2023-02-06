# 个性化推荐
import os.path

import pandas as pd
import numpy as np
import scipy.sparse as sparse
import implicit  # https://implicit.readthedocs.io/en/latest/
import pickle as pkl

# 1. 采用交替最小二乘法（Alternating Least Squares），本质是分解用户评分矩阵，[M*N]->[M*K]×[K*N]，K是我们抽象出的（user和item）的特征数
# 2. 将url作为推荐系统中的物品(item)
# 3. 以用户点击链接的记录作为隐式反馈，点击次数作为评分
# 4. 数据集（查询日志）是手动生成的，规模较小，而ALS也正好是处理稀疏矩阵的

log_path = 'log.csv'
model_path = 'recommender_data/model.pkl'
map_path = 'recommender_data/map.npz'
data_path = 'data.csv'


class Recommender(object):
    def __init__(self):
        self.maps = None
        self.model = None
        # 建立url->title的映射关系，方便推荐结果显示title
        self.url2title = {}
        df = pd.read_csv(data_path, usecols=['url', 'title'], dtype=str)
        for i in range(0, len(df)):
            self.url2title[df.loc[i, 'url']] = df.loc[i, 'title']
        self.load()
        # self.train()

    def train(self):
        """需要定期调用一次，更新模型"""
        print('=================训练ALS推荐模型===================')
        # 读取查询日志，删除无用信息
        df = pd.read_csv(log_path)
        df = df[df['event'] == 'CLICK'].drop(columns=['timestamp', 'event'])
        # 为 default_user 模拟访问每个url一次，这样后面构建的url索引就全了
        df = pd.concat([df, pd.DataFrame([['default', url] for url in list(pd.read_csv(data_path)['url'])],
                                         columns=['user_id', 'value'])], ignore_index=True)
        # 以用户点击链接的历史次数作为该用户对该url的评分
        df['rating'] = [1] * len(df)
        df = df.groupby(['user_id', 'value']).sum(numeric_only=True).reset_index()
        # default_user不参与训练
        for i in range(0, len(df)):
            if df.loc[i, 'user_id'] == 'default':
                df.loc[i, 'rating'] = 0
        # 构建用户ID、url的索引
        df['user_idx'], user_map = pd.factorize(df['user_id'])
        df['item_idx'], item_map = pd.factorize(df['value'])
        print('评分信息：', df)
        # 评分矩阵按行压缩存储
        sparse_user_item = sparse.csr_matrix((df['rating'].astype(float), (df['user_idx'], df['item_idx'])))
        # 调库完成ALS模型训练，特征数20
        self.model = implicit.als.AlternatingLeastSquares(factors=20, regularization=0.1,
                                                          iterations=50)
        self.model.fit(sparse_user_item)
        # 保存模型数据
        print('ALS分解得到的用户矩阵和物品矩阵的形状：', self.model.user_factors.shape, self.model.item_factors.shape)
        if not os.path.exists('recommender_data'):
            os.mkdir('recommender_data')
        with open(model_path, 'wb') as f:
            pkl.dump(self.model, f)
        self.maps = {
            'item_map': item_map,
            'user_map': user_map
        }
        np.savez(map_path, **self.maps)
        print('=================训练完成===================')

    def load(self):
        with open(model_path, 'rb') as f:
            self.model = pkl.load(f)
        self.maps = np.load(map_path, allow_pickle=True)

    def recommend(self, item_labels: list):
        """
        :param item_labels: 本页查询结果（一个个url）
        :return: 相似推荐（url+标题+得分）
        """
        self.load()
        item_map = self.maps['item_map']
        items_id = [list(item_map).index(item_label) for item_label in item_labels]
        recommendations = self.model.similar_items(items_id, N=10)
        result = []
        for items_id, scores in zip(recommendations[0], recommendations[1]):
            for item_id, score in zip(items_id, scores):
                if item_map[item_id] not in item_labels:
                    result.append(
                        {
                            'url': item_map[item_id],
                            'title': self.url2title[item_map[item_id]],
                            'score': score,
                        }
                    )
        result.sort(key=lambda x: x['score'], reverse=True)
        print('=================相关推荐===================')
        if len(result) > 5:
            result = result[:5]
        print(result)
        return result


if __name__ == '__main__':
    recommender = Recommender()
    recommender.train()
    recommender.recommend(['https://travel.qunar.com/youji/7675772', 'https://bbs.qyer.com/thread-3661010-1.html'])

# https://towardsdatascience.com/recommending-github-repositories-with-google-bigquery-and-the-implicit-library-e6cce666c77
