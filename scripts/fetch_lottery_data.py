#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取双色球(福彩)与大乐透(体彩)历史开奖数据，写入 data/ssq.json 和 data/dlt.json。

数据来源：
- 双色球：中国福利彩票官网 findDrawNotice 接口 (cwl.gov.cn)
- 大乐透：中国体育彩票官网 webapi 接口 (sporttery.cn)

注意：
这两个接口都不是"公开文档化"的正式开放API，而是官网页面本身在用的内部接口。
官方随时可能调整参数、返回结构，甚至加上更严格的反爬校验（比如双色球官网历史上出现过的
"瑞数"加密校验）。所以这个脚本按"尽力而为、优雅降级"设计：
  1. 每次运行都尝试重新抓取最近 N 期，整份覆盖写入 JSON（不做增量更新，逻辑最简单也最不容易出错）；
  2. 如果本次抓取失败或抓到的数据异常少，脚本会保留上一次成功抓取的旧数据文件不被破坏，
     并以非零退出码结束，方便在 GitHub Actions 里观察到"这次没抓到"，而不会把网页数据清空；
  3. 如果官方接口结构变了导致解析失败，报错信息会尽量给出原始响应片段，方便你/我后续调整解析逻辑。
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TARGET_COUNT = 300  # 期望抓取的期数量（抓不满也没关系，取实际能拿到的）
CN_TZ = timezone(timedelta(hours=8))

HEADERS_SSQ = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.cwl.gov.cn/ygkj/wqkjgg/ssq/",
}
HEADERS_DLT = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.sporttery.cn/",
}


def fetch_ssq(target_count=TARGET_COUNT):
    """抓取双色球历史数据，返回统一格式的 list[dict]。"""
    url = "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
    params = {
        "name": "ssq",
        "issueCount": str(target_count),
        "pageNo": 1,
        "pageSize": target_count,
        "systemType": "PC",
    }
    resp = requests.get(url, params=params, headers=HEADERS_SSQ, timeout=15)
    resp.raise_for_status()
    payload = resp.json()

    if "result" not in payload:
        raise ValueError(f"双色球接口返回结构异常，原始内容片段：{str(payload)[:500]}")

    draws = []
    for item in payload["result"]:
        # red 形如 "01,05,12,20,28,33"；blue 形如 "07"
        front = [int(x) for x in item["red"].split(",")]
        back = [int(item["blue"])]
        draws.append({
            "issue": str(item["code"]),
            "date": item["date"][:10],
            "front": sorted(front),
            "back": back,
        })
    # 官方通常已按期号倒序返回，这里保险起见再手动排一次序
    draws.sort(key=lambda d: d["issue"], reverse=True)
    return draws


def fetch_dlt(target_count=TARGET_COUNT):
    """抓取大乐透历史数据，返回统一格式的 list[dict]。"""
    url = "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
    page_size = 30
    draws = []
    page_no = 1
    max_pages = 20  # 安全上限，避免接口分页字段异常时死循环

    while len(draws) < target_count and page_no <= max_pages:
        params = {
            "gameNo": 85,
            "provinceId": 0,
            "pageSize": page_size,
            "isVerify": 1,
            "pageNo": page_no,
        }
        resp = requests.get(url, params=params, headers=HEADERS_DLT, timeout=15)
        resp.raise_for_status()
        payload = resp.json()

        # 该接口的字段名在不同版本下出现过 value/data 等不同包裹方式，这里做兼容尝试
        container = payload.get("value") or payload.get("data") or payload
        page_list = container.get("list") if isinstance(container, dict) else None

        if not page_list:
            if page_no == 1:
                raise ValueError(f"大乐透接口返回结构异常，原始内容片段：{str(payload)[:500]}")
            break  # 后续页没有数据了，正常结束翻页

        for item in page_list:
            # 常见字段名：lotteryDrawNum（期号）/ lotteryDrawResult（"01 02 03 04 05 06 07"）
            # / lotteryDrawTime（开奖日期）。不同接口版本字段名可能略有差异，
            # 如果这里取不到值，请打印 item 看看实际字段名再调整。
            issue = str(item.get("lotteryDrawNum") or item.get("issue") or item.get("code"))
            date = str(item.get("lotteryDrawTime") or item.get("date") or "")[:10]
            result_str = item.get("lotteryDrawResult") or item.get("result") or ""
            nums = [int(x) for x in result_str.split()]
            if len(nums) < 7:
                # 有些接口把结果字段拆成两个: 前区+后区分开给
                front_str = item.get("frontWinningNum") or ""
                back_str = item.get("backWinningNum") or ""
                nums = [int(x) for x in (front_str + " " + back_str).split()]
            front, back = nums[:5], nums[5:7]
            draws.append({"issue": issue, "date": date, "front": sorted(front), "back": sorted(back)})

        page_no += 1
        time.sleep(0.3)  # 温和一点，别把官方接口打太快

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
            raise ValueError(f"双色球抓到的期数过少（{len(ssq_draws)}期），疑似接口异常，本次不覆盖旧文件")
        write_json("ssq.json", ssq_draws)
    except Exception as e:
        had_error = True
        print(f"[ERROR] 双色球抓取失败：{e}", file=sys.stderr)

    try:
        dlt_draws = fetch_dlt()
        if len(dlt_draws) < 5:
            raise ValueError(f"大乐透抓到的期数过少（{len(dlt_draws)}期），疑似接口异常，本次不覆盖旧文件")
        write_json("dlt.json", dlt_draws)
    except Exception as e:
        had_error = True
        print(f"[ERROR] 大乐透抓取失败：{e}", file=sys.stderr)

    sys.exit(1 if had_error else 0)


if __name__ == "__main__":
    main()
