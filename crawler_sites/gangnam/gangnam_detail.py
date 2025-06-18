import boto3
import json
import os
import logging
import time
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# SQS 클라이언트 (RDS 처리용)
sqs = boto3.client('sqs')
RDS_QUEUE_URL = os.environ.get('RDS_QUEUE_URL')  # RDS 처리용 SQS 큐

def get_page_content_with_selenium(driver, url):
    try:
        logger.info(f"페이지 로드 중: {url}")
        driver.get(url)
        time.sleep(1.2)
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CLASS_NAME, "cmp_info"))
        )
        return driver.page_source
    except Exception as e:
        logger.error(f"페이지 가져오기 실패: {e}")
        return None

def extract_campaign_details(html_content):
    if not html_content:
        return {}

    soup = BeautifulSoup(html_content, 'html.parser')
    campaign_details = {}

    try:
        cmp_info = soup.find('div', class_='cmp_info')
        if cmp_info:
            print("cmp_info 처리")
            for li in cmp_info.find_all('li'):
                dt_tag = li.find('dt')
                dd_tag = li.find('dd')
                if dt_tag and dd_tag:
                    field_name = dt_tag.text.strip()
                    field_value = dd_tag.text.strip()
                    
                    print(f"필드 발견: {field_name} = {field_value}")

                    if '캠페인 신청기간' in field_name:
                        # "06.18 ~ 06.24" 형식 처리
                        period_match = re.search(r'(\d{2}\.\d{2})\s*~\s*(\d{2}\.\d{2})', field_value)
                        if period_match:
                            campaign_details['apply_startdate'] = f"25.{period_match.group(1)}"
                            campaign_details['apply_enddate'] = f"25.{period_match.group(2)}"
                    elif '리뷰 등록기간' in field_name:
                        period_match = re.search(r'(\d{2}\.\d{2})\s*~\s*(\d{2}\.\d{2})', field_value)
                        if period_match:
                            campaign_details['content_submission_start'] = f"25.{period_match.group(1)}"
                            campaign_details['content_submission_end'] = f"25.{period_match.group(2)}"
                    elif '리뷰어 발표' in field_name:
                        if re.search(r'\d{2}\.\d{2}', field_value):
                            campaign_details['reviewer_announcement'] = f"25.{field_value.strip()}"
                    elif '캠페인 결과발표' in field_name:
                        if re.search(r'\d{2}\.\d{2}', field_value):
                            campaign_details['result_date'] = f"25.{field_value.strip()}"
        else:
            print("cmp_info 클래스를 찾을 수 없습니다")

        address_found = False
        # div 내부의 span 요소들을 검색
        address_regex = re.compile(r'([가-힣]+시\s*[가-힣]+(구|군)?\s*[가-힣0-9]+(동|읍|면)?\s*\d+[\-\d]*(?:\s*\d+층)?)')
        
        for tag in soup.find_all(['span', 'div', 'p', 'li']):
            text = tag.get_text(strip=True)
            if not text or len(text) < 7 or len(text) > 100:
                continue
            
            match = address_regex.search(text)
            if match:
                address = match.group(1).strip()
                campaign_details['address'] = address
                address_found = True
                print(f"주소 발견: {address}")
                break
    
        
        if not address_found:
            campaign_details['address'] = None
            print("주소 정보를 찾을 수 없습니다")

    except Exception as e:
        logger.error(f"상세 정보 추출 중 오류: {e}")

    return campaign_details

def send_to_rds_queue(campaign_data):
    if not RDS_QUEUE_URL:
        logger.warning("RDS_QUEUE_URL이 설정되지 않음. 전송 건너뜀.")
        return False
    try:
        sqs.send_message(
            QueueUrl=RDS_QUEUE_URL,
            MessageBody=json.dumps(campaign_data, ensure_ascii=False)
        )
        logger.info(f"RDS 큐 전송 완료: {campaign_data.get('title', 'Unknown')}")
        return True
    except Exception as e:
        logger.error(f"RDS 큐 전송 실패: {e}")
        return False

def run(driver, campaign_data):
    try:
        title = campaign_data.get('title', 'Unknown')
        detail_url = campaign_data.get('detail_url', '')

        if not detail_url:
            logger.error(f"URL 없음: {title}")
            return False

        logger.info(f"세부 크롤링 시작: {title}")
        detail_html = get_page_content_with_selenium(driver, detail_url)
        if not detail_html:
            logger.error(f"페이지 로드 실패: {detail_url}")
            return False

        details = extract_campaign_details(detail_html)
        final_data = {**campaign_data, **details}
        final_data['page_flag'] = 'detail'

        logger.info(f"상세 정보 추출 완료: {title}")
        for k, v in details.items():
            logger.info(f" - {k}: {v}")

        return send_to_rds_queue(final_data)

    except Exception as e:
        logger.error(f"캠페인 처리 중 오류: {e}")
        logger.error(f"오류 데이터: {campaign_data}")
        return False
