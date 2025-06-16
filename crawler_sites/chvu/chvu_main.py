from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import time
import re
import boto3
import os
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs = boto3.client('sqs')
MAIN_TO_DETAIL_QUEUE_URL = os.environ.get('MAIN_TO_DETAIL_QUEUE_URL')
RDS_QUEUE_URL = os.environ.get('RDS_QUEUE_URL')


def scroll_to_bottom(driver):
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
        last_height = new_height


def parse_remaining_days(remaining_text):
    if not remaining_text:
        return None
    remaining_text = remaining_text.strip()
    if "오늘 마감" in remaining_text:
        return 0
    match = re.search(r'(\d+)일\s*남음', remaining_text)
    if match:
        return int(match.group(1))
    if "시간 남음" in remaining_text:
        return 0
    logger.warning(f"남은 기간 파싱 실패: {remaining_text}")
    return None


def parse_campaign_info(card):
    data = {}
    try:
        link = card.get_attribute("href")
        if not link:
            return None
        data['detail_url'] = link
        data['source_site'] = 'chvu'
        data['page_flag'] = 'main'

        campaign_id = re.search(r'/campaign/(\d+)', link)
        if campaign_id:
            data['id'] = campaign_id.group(1)

        try:
            title_elem = card.find_element(By.CSS_SELECTOR, '.FlexibleCard__Title-sc-1dw1ej1-6')
            data['title'] = title_elem.text.strip()
        except NoSuchElementException:
            data['title'] = "제목 없음"

        try:
            header = card.find_element(By.CSS_SELECTOR, '.FlexibleCard__ItemHeader-sc-1dw1ej1-5')
            header_text = header.text.strip()
            try:
                channel_type = card.find_element(By.CSS_SELECTOR, '.ChannelType__TypeDiv-sc-ka7sa4-0').text.strip()
                data['campaign_type'] = header_text.replace(channel_type, '').strip()
            except NoSuchElementException:
                data['campaign_type'] = header_text
        except NoSuchElementException:
            data['campaign_type'] = "알 수 없음"

        try:
            remain_elem = card.find_element(By.CSS_SELECTOR, 'span.text-purple-600.font-semibold')
            remaining_text = remain_elem.text.strip()
            data['remaining_days'] = parse_remaining_days(remaining_text)
        except NoSuchElementException:
            data['remaining_days'] = None

    except Exception as e:
        logger.error(f"캠페인 정보 파싱 중 오류: {e}")
        return None

    return data


def send_to_detail_queue(data):
    try:
        response = sqs.send_message(
            QueueUrl=MAIN_TO_DETAIL_QUEUE_URL,
            MessageBody=json.dumps(data, ensure_ascii=False)
        )
        logger.info(f"Detail Queue 전송 완료: {data['title'][:50]}")
        return True
    except Exception as e:
        logger.error(f"Detail Queue 전송 실패: {e}")
        return False


def send_to_rds_queue(data):
    try:
        response = sqs.send_message(
            QueueUrl=RDS_QUEUE_URL,
            MessageBody=json.dumps(data, ensure_ascii=False)
        )
        logger.info(f"RDS Queue 전송 완료: {data['title'][:50]}")
        return True
    except Exception as e:
        logger.error(f"RDS Queue 전송 실패: {e}")
        return False


def process_campaign_by_remaining_days(campaign):
    remaining_days = campaign.get('remaining_days')
    title = campaign.get('title', 'Unknown')[:50]

    if remaining_days is None:
        logger.info(f"남은 기간 불명 → Detail Queue: {title}")
        return send_to_detail_queue(campaign)

    if remaining_days < 7:
        logger.info(f"마감 임박 ({remaining_days}일) → RDS Queue: {title}")
        return send_to_rds_queue(campaign)
    else:
        logger.info(f"여유 있음 ({remaining_days}일) → Detail Queue: {title}")
        return send_to_detail_queue(campaign)


def crawl_target(driver):
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'a.FlexibleCard__StyledCard-sc-1dw1ej1-0'))
        )
        scroll_to_bottom(driver)
        time.sleep(1)

        cards = driver.find_elements(By.CSS_SELECTOR, 'a.FlexibleCard__StyledCard-sc-1dw1ej1-0')
        logger.info(f"총 {len(cards)}개의 캠페인 카드 발견")

        suc_cnt, err_cnt = 0, 0
        for idx, card in enumerate(cards):
            try:
                info = parse_campaign_info(card)
                if info:
                    success = process_campaign_by_remaining_days(info)
                    if success:
                        suc_cnt += 1
                    else:
                        err_cnt += 1
            except Exception as e:
                err_cnt += 1
                logger.error(f"[ERROR] 카드 #{idx} 처리 실패: {e}")

        return suc_cnt, err_cnt
    except Exception as e:
        logger.error(f"크롤링 중 오류 발생: {e}")
        return 0, 1


def run(driver):
    selectors = [
        {"label": "방문형"},
        {"label": "배송형"},
        {"label": "기자단"}
    ]

    total_suc, total_err = 0, 0
    driver.get("https://chvu.co.kr/campaign")

    for selector in selectors:
        try:
            label = selector["label"]
            logger.info(f"선택자 클릭 시도: {label}")
            buttons = driver.find_elements(By.CSS_SELECTOR, "div.CategorySelector__SelectorCategory-sc-vn201x-0")
            for btn in buttons:
                if label in btn.text:
                    btn.click()
                    time.sleep(2)
                    break

            logger.info(f"크롤링 시작: {label} 캠페인")
            cnt, err = crawl_target(driver)
            logger.info(f"  완료: {cnt}개 / 실패: {err}개")
            total_suc += cnt
            total_err += err
        except Exception as e:
            logger.error(f"선택자 클릭 실패: {label} / 오류: {e}")
            total_err += 1

    logger.info(f"CHVU 크롤링 완료 - 총 성공: {total_suc}개, 실패: {total_err}개")
    return total_suc, total_err
