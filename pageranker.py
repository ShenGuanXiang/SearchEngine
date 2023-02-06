# 链接分析 使用networkX计算节点的pagerank
# https://blog.csdn.net/weixin_43378396/article/details/90322422 pagerank总结
# https://blog.csdn.net/a_31415926/article/details/40510175 networkx原理
import networkx as nx
import matplotlib.pyplot as plt
import pandas as pd

data_path = 'data.csv'


class Pageranker(object):
    def __init__(self):
        """
        读取csv，创建web图
        """
        # 建立title->url的映射关系，从而方便地找到anchor对应的link_url
        title2url = {}
        df = pd.read_csv(data_path, usecols=['url', 'title', 'anchors'], dtype=str)
        for i in range(0, len(df)):
            title2url[df.loc[i, 'title']] = df.loc[i, 'url']
        # 将所有抓取的url节点和指向内部网页的链接边加入web图中
        self.G = nx.DiGraph()  # 创建有向图
        for i in range(0, len(df)):
            self.G.add_node(df.loc[i, 'url'])
            if type(df.loc[i, 'anchors']) == str and df.loc[i, 'anchors'] != '':
                for anchor in df.loc[i, 'anchors'].strip('[').strip(']').replace("'", '').split(","):  # str->list
                    if anchor in title2url:
                        self.G.add_edge(df.loc[i, 'url'], title2url[anchor])

    def run(self, visualize=False):
        """
        计算pagerank，存入csv
        """
        pr = nx.pagerank(self.G, alpha=0.85)  # alpha 是随机跳转的概率， 1-alpha 是随机游走的概率（满足均匀分布）
        # print(pr)

        # 有向图可视化
        if visualize:
            # layout = nx.spring_layout(self.G) # 中心放射状
            # layout = nx.circular_layout(self.G) # 在一个圆环上均匀分布节点
            # layout = nx.random_layout(self.G) # 在一个圆环上均匀分布节点
            layout = nx.shell_layout(self.G)  # 节点都在同心圆上
            # nx.draw(self.G, pos=layout, with_labels=True, hold=False)
            nx.draw(self.G, pos=layout, with_labels=True)
            plt.show()

        # 结果单独一列保存在csv
        pr_list = []
        df = pd.read_csv(data_path)
        for i in range(0, len(df)):
            pr_list.append(pr[df.loc[i, 'url']] if df.loc[i, 'url'] in pr else 0)
        df['pagerank'] = pr_list
        df.to_csv(data_path, index=False, encoding="utf_8_sig")


if __name__ == '__main__':
    Pageranker().run(visualize=True)
