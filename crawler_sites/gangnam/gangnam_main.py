from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import boto3
import json
import os
import logging
import re

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

def parse_remaining_days(text):
    if not text:
        return None
    text = text.strip()
    if "오늘 마감" in text or "시간 남음" in text or "마감임박" in text:
        return 0
    match = re.search(r'(\d+)\s*일', text)
    return int(match.group(1)) if match else None

def extract_campaign_info(link, idx, campaign_type):
    href = link.get('href')
    if not href:
        return None

    full_link = f"https://xn--939au0g4vj8sq.net{href}"
    
    # 제목 추출 개선
    title = link.get_text(strip=True)
    if not title:
        title = f"캠페인_{idx}"

    campaign = {
        'title': title,
        'detail_url': full_link,
        'applicant_count': None,
        'recruit_count': None,
        'remaining_days': None,
        'source_site': 'gangnam',
        'page_flag': 'main',
        'campaign_type': campaign_type
    }

    parent = link.parent
    while parent:
        if campaign['remaining_days'] is None:
            day_tag = parent.find('em', class_='day_c')
            if day_tag:
                campaign['remaining_days'] = parse_remaining_days(day_tag.text)

        if campaign['applicant_count'] is None:
            numb_tag = parent.find('span', class_='numb')
            if numb_tag:
                numbers = re.findall(r'[\d,]+', numb_tag.text)
                if len(numbers) >= 2:
                    campaign['applicant_count'] = int(numbers[0].replace(',', ''))
                    campaign['recruit_count'] = int(numbers[1].replace(',', ''))
                    
        if campaign.get('recruit_count') is not None and campaign.get('recruit_count') != 0 and campaign.get('applicant_count') is not None:
            campaign['competition_rate'] = round(campaign.get('applicant_count') / campaign.get('recruit_count'), 2)

        if campaign['remaining_days'] is not None and campaign['applicant_count'] is not None:
            break
        parent = parent.parent

    return campaign

def extract_and_process_campaigns(html_content, campaign_type):
    soup = BeautifulSoup(html_content, 'html.parser')
    # 제목이 있는 링크만 선택 (dt.tit 안의 a 태그)
    campaign_links = soup.select("dt.tit a[href*='/cp/?id=']")
    

    suc_cnt = err_cnt = detail_cnt = rds_cnt = 0

    for idx, link in enumerate(campaign_links, 1):
        try:
            campaign = extract_campaign_info(link, idx, campaign_type)
            if not campaign:
                continue

            success = process_campaign_by_remaining_days(campaign)
            if success:
                suc_cnt += 1
                if campaign['remaining_days'] is None or campaign['remaining_days'] >= 6:
                    detail_cnt += 1
                else:
                    rds_cnt += 1
            else:
                err_cnt += 1

        except Exception as e:
            err_cnt += 1
            logger.error(f"[ERROR] ({campaign_type}) Card #{idx} 처리 실패: {e}")

    logger.info(f"처리 완료 - Detail Queue: {detail_cnt}개, RDS Queue: {rds_cnt}개")
    return suc_cnt, err_cnt

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
    days = campaign.get('remaining_days')
    title = campaign.get('title', 'Unknown')[:50]

    if days is None:
        logger.info(f"남은 기간 불명 → Detail Queue: {title}")
        return send_to_detail_queue(campaign)
    elif days < 6:
        logger.info(f"마감 임박 ({days}일) → RDS Queue: {title}")
        return send_to_rds_queue(campaign)
    else:
        logger.info(f"여유 있음 ({days}일) → Detail Queue: {title}")
        return send_to_detail_queue(campaign)

def crawl_target(driver, url, campaign_type):
    try:
        logger.info(f"URL 로드 중: {url}")
        driver.get(url)
        time.sleep(1)

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        scroll_to_bottom(driver)

        time.sleep(1)
        html = driver.page_source
        return extract_and_process_campaigns(html, campaign_type)

    except Exception as e:
        logger.error(f"크롤링 오류: {e}")
        return 0, 1

def run(driver):
    targets = [
        {"type": "전체", "url": "https://xn--939au0g4vj8sq.net/cp/?ca=20"},
        {"type": "제품", "url": "https://xn--939au0g4vj8sq.net/cp/?ca=30"},
        {"type": "기자단", "url": "https://xn--939au0g4vj8sq.net/cp/?ca=40"}
    ]

    total_cnt = total_err_cnt = 0
    for target in targets:
        logger.info(f"크롤링 시작: {target['type']}")
        cnt, err = crawl_target(driver, target['url'], target['type'])
        logger.info(f"완료: {cnt} / 실패: {err}")
        total_cnt += cnt
        total_err_cnt += err

    logger.info(f"총 크롤링 완료 - 성공: {total_cnt}, 실패: {total_err_cnt}")
    return total_cnt, total_err_cnt
