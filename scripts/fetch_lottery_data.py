#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取双色球(福彩)与大乐透(体彩)历史开奖数据，写入 data/ssq.json 和 data/dlt.json。

数据来源：500彩票网(500.com) 的历史开奖数据页面。

【为什么不直接用官方接口(cwl.gov.cn / sporttery.cn)？】
实测过官方接口在 GitHub Actions 上会直接返回 403 / 非200状态码 —— 这是官方接口的常规反爬策略：
海外数据中心IP(GitHub Actions 跑的机器就是)基本会被直接拦截，不管请求头写得多像浏览器都没用。
500.com 的历史数据页面被大量个人爬虫项目长期使用，对这类自动化请求宽容得多，是社区里的标准做法。

设计原则（尽力而为、优雅降级）：
  1. 每次运行都重新抓取一段历史区间，取最近 N 期整份覆盖写入 JSON；
  2. 如果本次抓取失败或抓到的数据异常少，保留上一次成功抓取的旧数据文件不被破坏，
     并以非零退出码结束，方便在 GitHub Actions 里观察到"这次没抓到"；
  3. 如果 500.com 页面结构变了导致解析失败，报错信息会给出原始响应片段方便后续调整。
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TARGET_COUNT = 1000  # 期望保留的期数量（抓到的历史区间可能更多，最后会截取最近N期）
CN_TZ = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}


def _fetch_table(url):
    """请求500.com的历史数据页面，返回 <tbody id="tdata"> 里的所有 <tr> 行(bs4 Tag列表)。"""
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding  # 页面编码有时是gb2312，自动探测更稳
    soup = BeautifulSoup(resp.text, "html.parser")
    tbody = soup.find("tbody", id="tdata")
    if tbody is None:
        raise ValueError(f"没找到 <tbody id=\"tdata\">，页面结构可能变了。原始内容片段：{resp.text[:500]}")
    rows = tbody.find_all("tr")
    if not rows:
        raise ValueError(f"表格是空的，原始内容片段：{resp.text[:500]}")
    return rows


def fetch_ssq(target_count=TARGET_COUNT):
    """抓取双色球历史数据。500.com 表格列顺序：期号,红1..红6,蓝球,...(中间是奖金统计列)...,开奖日期"""
    url = "https://datachart.500.com/ssq/history/newinc/history.php?start=16001"
    rows = _fetch_table(url)

    draws = []
    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) < 9:
            continue  # 跳过非数据行(比如注释行)
        texts = [td.get_text(strip=True) for td in tds]
        issue = texts[0]
        if not re.match(r"^\d{5,7}$", issue):
            continue
        front = sorted(int(x) for x in texts[1:7])
        back = [int(texts[7])]
        date = texts[-1]
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", date)
        draws.append({
            "issue": issue,
            "date": date_match.group(0) if date_match else date,
            "front": front,
            "back": back,
        })

    draws.sort(key=lambda d: d["issue"], reverse=True)
    return draws[:target_count]


def fetch_dlt(target_count=TARGET_COUNT):
    """抓取大乐透历史数据。500.com 表格列顺序：期号,前区1..5,后区1..2,...(中间是奖金统计列)...,开奖日期"""
    url = "https://datachart.500.com/dlt/history/newinc/history.php?start=16001"
    rows = _fetch_table(url)

    draws = []
    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) < 10:
            continue
        texts = [td.get_text(strip=True) for td in tds]
        issue = texts[0]
        if not re.match(r"^\d{5,7}$", issue):
            continue
        front = sorted(int(x) for x in texts[1:6])
        back = sorted(int(x) for x in texts[6:8])
        date = texts[-1]
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", date)
        draws.append({
            "issue": issue,
            "date": date_match.group(0) if date_match else date,
            "front": front,
            "back": back,
        })

    draws.sort(key=lambda d: d["issue"], reverse=True)
    return draws[:target_count]


def write_json(filename, draws):
    path = os.path.join(DATA_DIR, filename)
    payload = {
        "updatedAt": datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "count": len(draws),
        "draws": draws,
    }
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)  # 原子替换，避免写到一半被中断产生半截文件
    print(f"[OK] 写入 {path}（{len(draws)} 期，最新期号 {draws[0]['issue'] if draws else '无'}）")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    had_error = False

    try:
        ssq_draws = fetch_ssq()
        if len(ssq_draws) < 5:
            raise ValueError(f"双色球抓到的期数过少（{len(ssq_draws)}期），疑似页面结构异常，本次不覆盖旧文件")
        write_json("ssq.json", ssq_draws)
    except Exception as e:
        had_error = True
        print(f"[ERROR] 双色球抓取失败：{e}", file=sys.stderr)

    try:
        dlt_draws = fetch_dlt()
        if len(dlt_draws) < 5:
            raise ValueError(f"大乐透抓到的期数过少（{len(dlt_draws)}期），疑似页面结构异常，本次不覆盖旧文件")
        write_json("dlt.json", dlt_draws)
    except Exception as e:
        had_error = True
        print(f"[ERROR] 大乐透抓取失败：{e}", file=sys.stderr)

    sys.exit(1 if had_error else 0)


if __name__ == "__main__":
    main()
