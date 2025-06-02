from selenium.webdriver.common.by import By
from utils.common import normalize_platforms
import time
import boto3
import json
import os

sqs = boto3.client('sqs')
QUEUE_URL = os.environ.get('QUEUE_URL')


def scroll_to_bottom(driver, delay: float = 1.0):
    """페이지 끝까지 스크롤"""
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(delay)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def parse_card(card, campaign_type: str):
    """단일 캠페인 카드에서 필요한 정보 파싱"""
    image_url = card.find_element(By.CSS_SELECTOR, "div.main-img-div img").get_attribute("src")
    title = card.find_element(By.CSS_SELECTOR, "span.camp-name").text
    detail_url = card.get_attribute("href")
    reward = card.find_element(By.CSS_SELECTOR, "div.emphasize").text

    try:
        ads_imgs = card.find_element(By.CSS_SELECTOR, "span.label img")
        platforms_text = ads_imgs.get_attribute("src").split("/")[-1][:-4]
    except Exception:
        platforms_text = "blog"

    return {
        'title': title,
        'detail_url': detail_url,
        'benefit': reward,
        'source_site': "4blog",
        'image_url': image_url,
        'platforms': normalize_platforms(platforms_text),
        'campaign_type': campaign_type,
        'page_flag': "main"
    }


def send_to_sqs(data: dict):
    """SQS 메시지 전송"""
    response = sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(data)
    )
    return response


def crawl_target(driver, url: str, campaign_type: str):
    """단일 URL 크롤링"""
    driver.get(url)
    scroll_to_bottom(driver)
    time.sleep(1)

    campaign_cards = driver.find_elements(By.CSS_SELECTOR, "a.nounderline")
    cnt, err_cnt = 0, 0

    for idx, card in enumerate(campaign_cards, start=1):
        try:
            result = parse_card(card, campaign_type)
            send_to_sqs(result)
            cnt += 1
        except Exception as e:
            err_cnt += 1

    return cnt, err_cnt


def run(driver):
    """
    전체 타겟들 순회하며 크롤링
    NOTE: 기자단만 살려놓고 테스트 시, 빠른 테스트 가능
    TODO: 체험단 날짜 별 분기처리 추가 필요
    """
    targets = [
        {"type": "방문", "url": "https://4blog.net/list/all/local"},
        {"type": "배송", "url": "https://4blog.net/list/all/deliv"},
        {"type": "기자단", "url": "https://4blog.net/list/all/reporter"},
    ]

    total_cnt, total_err_cnt = 0, 0
    for target in targets:
        cnt, err_cnt = crawl_target(driver, target["url"], target["type"])
        total_cnt += cnt
        total_err_cnt += err_cnt

    return total_cnt, total_err_cnt
