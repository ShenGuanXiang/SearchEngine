# 网页抓取
# 信息的时效性上，保证相对稳定即可
import requests
from bs4 import BeautifulSoup
import re
from queue import Queue
import time
import random
import csv
import os
import codecs
import pandas as pd
from requests.adapters import HTTPAdapter

# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.expected_conditions import visibility_of_element_located
# from selenium.webdriver.support.ui import WebDriverWait
# import win32api
# import win32con
# import win32clipboard

data_path = 'data.csv'
snapshot_path = './snapshot'

# 以下是伪装的请求头，打开Chrome开发者工具后刷新网页即可查看
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/109.0.0.0 Safari/537.36',  # 浏览器身份标识
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,'
              'application/signed-exchange;v=b3;q=0.9 ',  # 接受的数据格式
    'Connection': 'close',  # requests 默认是keep-alive的，可能没有释放
    'Upgrade-Insecure-Requests': '1',  # http可以转为https
}


# 为了节省硬盘空间，废弃mhtml格式的快照，改为直接爬取html，这个方法不再使用
# def save_snapshot(url: str):
#     """
#     模拟人的操作，保存网页快照（mhtml格式）
#     """
#     print('==============保存{}网页快照...================='.format(url))
#     options = webdriver.ChromeOptions()
#     # options.add_argument('--headless')
#     # options.add_argument('--save-page-as-mhtml')  # 打开另存为mhtml功能
#     # 设置chromedriver，并打开webdriver
#     driver = webdriver.Chrome(chrome_options=options)
#     driver.get(url)
#     time.sleep(1)
#     # 滚轮到网页最底部，将网页内容都加载出来
#     for i in range(0, 300):
#         win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, -100)
#         time.sleep(0.2)
#     # 将路径复制到剪切板
#     path = (os.path.dirname(os.path.realpath(snapshot_path)) + "\\" + snapshot_path + "\\" +
#                             url[url.rindex('/')+1:] + ".mhtml")
#     win32clipboard.OpenClipboard()
#     win32clipboard.EmptyClipboard()
#     win32clipboard.SetClipboardText(path)
#     win32clipboard.CloseClipboard()
#     # ctrl s
#     win32api.keybd_event(17, 0, 0, 0)  # 按下ctrl
#     win32api.keybd_event(83, 0, 0, 0)  # 按下s
#     win32api.keybd_event(83, 0, win32con.KEYEVENTF_KEYUP, 0)  # 释放s
#     win32api.keybd_event(17, 0, win32con.KEYEVENTF_KEYUP, 0)  # 释放ctrl
#     time.sleep(1)
#     # ctrl v
#     win32api.keybd_event(17, 0, 0, 0)  # 按下ctrl
#     win32api.keybd_event(86, 0, 0, 0)  # 按下v
#     win32api.keybd_event(86, 0, win32con.KEYEVENTF_KEYUP, 0)  # 释放v
#     win32api.keybd_event(17, 0, win32con.KEYEVENTF_KEYUP, 0)  # 释放ctrl
#     time.sleep(1)
#     # enter
#     win32api.keybd_event(13, 0, 0, 0)  # 按下enter
#     win32api.keybd_event(13, 0, win32con.KEYEVENTF_KEYUP, 0)  # 释放enter
#     # 预估下载时间，后期根据实际网速调整
#     time.sleep(15)
#     # 关闭webdriver
#     driver.close()


class Crawler(object):
    """爬取'https://travel.qunar.com/travelbook/list.htm'(去哪)"""

    def __init__(self, max_depth=2, max_iterations=100, min_page_no=1, max_page_no=200):
        self.max_depth = max_depth  # 爬虫bfs的最大深度
        self.max_iterations = max_iterations  # 本次新爬取的游记数量上限
        self.min_page_no = min_page_no  # 该网站每页有若干个游记的链接
        self.max_page_no = max_page_no
        if not os.path.exists(data_path) or os.path.getsize(data_path) == 0:  # 初始化时写入csv第一行，标明提取的各个属性
            with open(data_path, 'wb') as f:  # 不存在则创建
                f.write(codecs.BOM_UTF8)  # 解决中文乱码问题
            with open(data_path, mode='a', encoding='utf_8_sig', newline='') as f:  # 追加写
                csv.writer(f).writerow(['url', 'title', 'author', 'date', 'days',
                                        'cost', 'how', 'anchors', 'text'])  # date是出发日期，text指正文中的文本
        if not os.path.exists(snapshot_path):
            os.makedirs(snapshot_path)

    def run(self):
        """ bfs 爬取网页，保存到csv
        这里的实现是兼容累积式抓取和增量式抓取的，因为最新的游记都被放在了前几页，所以通过修改页号范围就可以在两种抓取方式间转换
        """
        df = pd.read_csv(data_path, usecols=['url'])
        visited_urls = set(df['url'])

        # 队列初始化，前若干页包含的游记的url（种子集合）
        url_queue = Queue()  # 每个元素都形如(url, depth)
        for page_no in range(self.min_page_no, self.max_page_no):
            print('=================即将解析第{}页=================='.format(page_no))
            # 发送http get请求
            response = requests.get(
                url='https://travel.qunar.com/travelbook/list.htm?page=%d&order=elite_ctime' % page_no
                , headers=headers, timeout=(10, 10))

            # 解析html，找到该页下所有游记的url，填入队列
            bs = BeautifulSoup(response.text, 'html.parser')
            response.close()
            travels = bs.find('ul', attrs={'class': 'b_strategy_list'})
            for travel in travels:
                link_url = 'https://travel.qunar.com' + travel.h2.a['href']
                url_queue.put((link_url, 0))

            print('=================第{}页解析完成=================='.format(page_no))
            time.sleep(random.uniform(1, 2))  # 礼貌地爬取

        # bfs爬取网页并保存到csv
        with open(data_path, mode='a', encoding='utf_8_sig', newline='') as f:  # 追加写
            cur_iter = 0
            while not url_queue.empty() and cur_iter < self.max_iterations:
                url, depth = url_queue.get()
                print('==================即将解析{}==================='.format(url))

                # 发送http get请求，三次重试机会(重试的机制其实 requests 已经帮我们封装好了)
                sess = requests.Session()
                sess.mount('https://', HTTPAdapter(max_retries=3))
                sess.keep_alive = False  # 关闭多余连接
                response = requests.get(url=url, headers=headers, timeout=(10, 10))
                response.encoding = 'utf-8'
                html = response.text
                response.close()
                # 解析html，提取各个属性
                bs = BeautifulSoup(html, 'lxml')
                if '非常抱歉，您访问的页面不存在' in bs.head.title.text:
                    continue
                title = bs.find('div', class_='e_title clrfix').h1.span.text
                author = bs.find('li', class_='head').a.text
                date_li = bs.find('li', class_='f_item when')
                date = date_li.p.find('span', class_='data').text.replace('/', '-')
                days_li = bs.find('li', class_='f_item howlong')
                days = days_li.p.find('span', class_='data').text
                cost_li = bs.find('li', class_='f_item howmuch')
                cost = '' if cost_li is None else cost_li.p.find('span', class_='data').text
                who_li = bs.find('li', class_='f_item who')
                who = '' if who_li is None else who_li.p.find('span', class_='data').text
                how_li = bs.find('li', class_='f_item how')
                how = who + ('' if how_li is None else (' ' + how_li.p.find('span', class_='data').get_text()))
                anchors = []
                link_urls = []
                # 网页下方的猜你喜欢有指向其它不同的游记的链接，链接的游记标题作为锚文本并且bfs迭代下去。网页中其它的链接（大部分是广告链接）被过滤。
                for link in bs.find_all('a', href=re.compile(r'^/youji/')):
                    anchors.append(link.get('title'))
                    link_urls.append('https://travel.qunar.com' + link.get('href'))
                text = ''
                # 观察网页结构发现正文文本均位于<div, class='text js_memo_node'>标签下（但也有例外，某些游记的正文没爬到）
                for item in bs.find_all('div', class_='text js_memo_node'):
                    text += item.get_text(' ', strip=True).replace('\r', ' ').replace('\n', ' ')
                    # .replace(u'\xa0', '')
                # print(title, author, date, days, cost, who, how, anchors, link_urls)

                if url not in visited_urls:  # 保证csv里没有重复的url
                    visited_urls.add(url)
                    # 存到csv
                    csv_writer = csv.writer(f, dialect='excel')
                    csv_writer.writerow((url, title, author, date, days, cost, how, anchors, text))
                    # 收集快照
                    path = (snapshot_path + "\\" + url[url.rindex('/') + 1:] + ".html")
                    with open(path, 'w', encoding="utf-8") as snapshot:
                        snapshot.write(html)
                    cur_iter += 1
                    print('=================={}爬取完成==================='.format(url))

                # bfs出边延伸
                if depth != self.max_depth:
                    for link_url in link_urls:
                        url_queue.put((link_url, depth + 1))

                time.sleep(random.uniform(2, 6))  # 礼貌地爬取


class AnotherCrawler(object):
    """
    发现只爬取一个网站不方便展示站内搜索功能，所以再爬一个：
    https://bbs.qyer.com/forum-51-1-1.html（穷游网）
    """

    def __init__(self, min_page_no=1, max_page_no=20):
        self.min_page_no = min_page_no  # 该网站每页有若干个游记的链接
        self.max_page_no = max_page_no

    def run(self):
        """这次只爬取每页可见的游记，不再沿游记中的链接继续爬取"""
        df = pd.read_csv(data_path, usecols=['url'])
        visited_urls = set(df['url'])
        with open(data_path, mode='a', encoding='utf_8_sig', newline='') as f:  # 追加写
            csv_writer = csv.writer(f)
            for page_no in range(self.min_page_no, self.max_page_no):
                print('=================即将解析第{}页=================='.format(page_no))
                response = requests.get(
                    url='https://bbs.qyer.com/forum-51-1-%d.html' % page_no,
                    headers=headers, timeout=(10, 10))
                response.encoding = 'utf-8'
                page_html = response.text
                # 解析html，找到该页下所有游记进行解析
                page_bs = BeautifulSoup(page_html, 'html.parser')
                response.close()
                i = 0
                for link in page_bs.find_all('a'):
                    url = link.get('href')
                    if '/bbs.qyer.com/thread-' not in url or url in visited_urls:
                        continue
                    print('==================即将解析{}==================='.format(url))
                    visited_urls.add(url)
                    # sess = requests.Session()
                    # sess.mount('https://', HTTPAdapter(max_retries=3))
                    # sess.keep_alive = False  # 关闭多余连接
                    response = requests.get(url=url, headers=headers, timeout=(10, 10))
                    response.encoding = 'utf-8'
                    html = response.text
                    response.close()
                    bs = BeautifulSoup(html, 'lxml')
                    title = bs.find('h1', class_='subject_con').get_text().replace('\r', '').replace('\n', '')
                    author = bs.find('a', class_='user_name').text if bs.find('a', class_='user_name') else ''
                    date = bs.find('span', class_='only_flex').text if bs.find('span', class_='only_flex') else ''
                    days = ''
                    cost = ''
                    how = ''
                    for how_a in bs.find_all('a', class_='tag_item'):
                        how += how_a.text.replace('\r', '').replace('\n', '').replace(' ', '') + ' '
                    # anchors = []
                    # for anchor_link in bs.find_all('a'):
                    #     if anchor_link.get('href') and '/bbs.qyer.com/thread-' in anchor_link.get('href') and \
                    #             '-1' in anchor_link.get('href'):
                    #         anchors.append(anchor_link.get_text())
                    anchors = ''
                    text = page_bs.find_all('dd', class_='text')[i].text.replace('\r', ' ').replace('\n', ' ') if \
                        len(page_bs.find_all('dd', class_='text')) > i else ''
                    i += 1
                    # print(title, author, date, days, cost, who, how, anchors, text)
                    csv_writer.writerow((url, title, author, date, days, cost, how, anchors, text))
                    # path = (snapshot_path + "\\" + url[url.rindex('/') + 1:] + ".html")
                    # if not os.path.exists(path):
                    #     with open(path, 'w', encoding="utf-8") as snapshot:
                    #         snapshot.write(html)
                    print('=================={}爬取完成==================='.format(url))
                    time.sleep(random.uniform(2, 5))  # 礼貌地爬取
                time.sleep(random.uniform(1, 3))  # 礼貌地爬取
                print('=================第{}页解析完成=================='.format(page_no))


if __name__ == '__main__':
    # 中间可能超时断掉，需要多爬几次
    Crawler(max_depth=2, max_iterations=5000, min_page_no=1, max_page_no=200).run()
    AnotherCrawler(min_page_no=1, max_page_no=200).run()
