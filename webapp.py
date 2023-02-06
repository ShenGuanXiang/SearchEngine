# web页面 图形化界面 flask框架
# 数据传递：后端->前端：render_template; 前端->后端：request.values.get
import copy

import pandas as pd
from flask import Flask, render_template, request
from searcher import Querier, Searcher, default_user, default_fields
from recommender import Recommender
import os
import requests
import json
import codecs
import csv
from datetime import datetime
import time
import psutil

app = Flask(__name__,
            static_folder='./static',
            template_folder='./templates')

users_path = 'users.csv'  # 用户信息
log_path = 'log.csv'  # 所有用户的查询日志，包括查询和点击历史
snapshot_path = './snapshot'

users = {}

recommender = Recommender()

# 缓存以下几个全局变量，传给前端完成html渲染
user = copy.deepcopy(default_user)  # 当前用户
links = []  # 当前页面查询结果
query_string = ''
page_no = 1  # 当前结果页面的页号
advanced = {
    'site_url': '',
    'fields': default_fields,
    'query_type': 'default'
}
query_history = []  # 所有用户的查询历史
recommendations = []


def main():
    global users, query_history
    if not os.path.exists(users_path) or os.path.getsize(users_path) == 0:  # 初始化时写入csv第一行
        with open(users_path, 'wb') as f:  # 不存在则创建
            f.write(codecs.BOM_UTF8)  # 解决中文乱码问题
        with open(users_path, mode='a', encoding='utf_8_sig', newline='') as f:  # 追加写
            csv.writer(f).writerow(['id', 'destinations', 'min_cost', 'max_cost', 'min_days', 'max_days', 'who', 'how'])
    with open(users_path, mode='r', encoding='utf_8_sig', newline='') as f:
        csv_reader = csv.DictReader(f)
        for item in csv_reader:
            users[item['id']] = item
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:  # 初始化时写入csv第一行
        with open(log_path, 'wb') as f:  # 不存在则创建
            f.write(codecs.BOM_UTF8)  # 解决中文乱码问题
        with open(log_path, mode='a', encoding='utf_8_sig', newline='') as f:  # 追加写
            csv.writer(f).writerow(['timestamp', 'user_id', 'event', 'value'])
    with open(log_path, mode='r', encoding='utf_8_sig', newline='') as f:
        csv_reader = csv.DictReader(f)
        for item in csv_reader:
            if item['event'] == 'QUERY':
                query_history.append(item['value'])
    if len(query_history) > 10:
        query_history = query_history[-10:]
    # # 打开es
    # es_started = False
    # pl = psutil.pids()
    # for pid in pl:
    #     # print(psutil.Process(pid).name())
    #     if psutil.Process(pid).name() == 'java.exe':
    #         es_started = True
    # if not es_started:
    #     print('=================启动elasticsearch...===================')
    #     os.system('start %s' % (os.path.realpath('./elasticsearch-8.6.1//bin//elasticsearch.bat')))
    #     time.sleep(15)
    app.run()
    # os.system('taskkill /f /t /im  %s' % (os.path.realpath('./elasticsearch-8.6.1//bin//elasticsearch.bat')))


@app.route('/')
def index() -> str:
    return render_template('start.html', user=user, query_history=query_history)


@app.route('/search', methods=['GET'])
def search() -> str:
    global query_string, page_no, links, advanced, recommendations
    edit_advanced_options = request.values.get('edit_advanced_options', default='0', type=str)
    query_string = request.values.get('query', default='', type=str)
    if edit_advanced_options == '1':
        advanced['fields'] = request.values.getlist('fields', type=str)
        if len(advanced['fields']) == 0:
            advanced['fields'] = default_fields
        advanced['site_url'] = request.values.get('site_url', default='', type=str)
        advanced['query_type'] = request.values.get('method', default='default', type=str)
    querier = Querier(query_string=query_string,
                      fields=advanced['fields'],
                      site_url=advanced['site_url'],
                      query_type=advanced['query_type'],
                      user=user,
                      )

    query_history.append(query_string)
    if len(query_history) > 10:
        query_history.pop(0)
    with open(log_path, mode='a', encoding='utf_8_sig', newline='') as f:
        csv.writer(f).writerow([datetime.now().timestamp(), user['id'], 'QUERY', query_string])

    page_no = max(int(request.values.get('page_no', default='1', type=str)), 1)
    searcher = Searcher(index_name='travel-info', query=querier.query(),
                        from_=(page_no - 1) * 10,
                        size=10, )

    response = searcher.run()
    links = response['links']

    recommendations = recommender.recommend(item_labels=[link['url'] for link in links])
    return render_template('main.html', links=links, query_string=query_string, page_no=page_no, users=users,
                           user=user, query_history=query_history, advanced=advanced, recommendations=recommendations, )


@app.route('/snapshot', methods=['GET'])
def snapshot() -> str:
    url = request.values.get('url')
    path = os.path.join(snapshot_path, url[url.rindex('/') + 1:] + '.html')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            html = f.read()
            # 对快照手动高亮，其中借助IK分词器对查询进行分词
            url = 'http://localhost:9200/_analyze'
            data = {
                "analyzer": "ik_smart",
                "text": request.values.get('query', default='', type=str)
            }
            response_json = json.loads(requests.post(url, json=data).text)
            for token in response_json["tokens"]:
                html = html.replace(token['token'], '<font style="background: orange">' + token['token'] + '</font>')
        return html
    return ''


@app.route('/link_clicked', methods=['GET'])
def link_clicked() -> str:
    url = request.values.get('url')
    user_id = request.values.get('user_id')
    print(user_id + '点击链接' + url)
    with open(log_path, mode='a', encoding='utf_8_sig', newline='') as f:
        csv.writer(f).writerow([datetime.now().timestamp(), user['id'], 'CLICK', url])
    if len(pd.read_csv(log_path)) % 100 == 0:
        recommender.train()  # 如果能异步更好
    return ''


@app.route('/login', methods=['GET'])
def login() -> str:
    global user, users
    user_id = request.values.get('user_id')
    if user_id in users:
        user = users[user_id]
    else:
        user = copy.deepcopy(default_user)
        user['id'] = user_id
        users[user_id] = user
        with open(users_path, mode='a', encoding='utf_8_sig', newline='') as file:
            csv.writer(file).writerow(user.values())
    return render_template('main.html', links=links, query_string=query_string, page_no=page_no, users=users,
                           user=user, query_history=query_history, advanced=advanced, recommendations=recommendations, )


@app.route('/change_info', methods=['GET'])
def change_info() -> str:
    global user, users
    user['destinations'] = request.values.get('destinations', type=str)
    user['min_cost'] = max(int(request.values.get('min_cost', type=str)), 0)
    user['max_cost'] = max(int(request.values.get('max_cost', type=str)), 0)
    user['min_days'] = max(int(request.values.get('min_days', type=str)), 0)
    user['max_days'] = max(int(request.values.get('max_days', type=str)), 0)
    user['who'] = request.values.get('who', type=str)
    user['how'] = request.values.get('how', type=str)
    users[user['id']] = user
    with open(users_path, mode='w', encoding='utf_8_sig', newline='') as file:
        csv_writer = csv.writer(file)
        csv_writer.writerow(['id', 'destinations', 'min_cost', 'max_cost', 'min_days', 'max_days', 'who', 'how'])
        for user_id in users:
            csv_writer.writerow(users[user_id].values())
    return render_template('main.html', links=links, query_string=query_string, page_no=page_no, users=users,
                           user=user, query_history=query_history, advanced=advanced, recommendations=recommendations, )


@app.route('/logout', methods=['GET'])
def logout() -> str:
    global user
    user = copy.deepcopy(default_user)
    return render_template('main.html', links=links, query_string=query_string, page_no=page_no, users=users,
                           user=user, query_history=query_history, advanced=advanced, recommendations=recommendations, )


if __name__ == '__main__':
    main()
