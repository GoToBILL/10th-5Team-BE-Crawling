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
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "campInfo")))
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
        camp_info = soup.find(id='campInfo')
        if camp_info:
            for li in camp_info.find_all('li'):
                b_tag = li.find('b')
                span_tag = li.find('span')
                if b_tag:
                    field_name = b_tag.text.strip()
                    field_value = span_tag.text.strip() if span_tag else ""

                    if '협찬 상품' in field_name:
                        campaign_details['benefit'] = field_value

                    elif '모집 및 선정 기간' in field_name:
                        period_match = re.search(r'(\d{2}\.\d{2}\.\d{2})\s*~\s*(\d{2}\.\d{2}\.\d{2})', field_value)
                        if period_match:
                            campaign_details['application_startdate'] = period_match.group(1)
                            campaign_details['application_enddate'] = period_match.group(2)

                    elif '리뷰 제출 마감일' in field_name:
                        campaign_details['review_deadline'] = field_value

                    elif '신청' in field_name and '명' in field_value:
                        nums = re.findall(r'\d+', field_value.replace(',', ''))
                        if len(nums) >= 2:
                            applicants = int(nums[0])
                            recruits = int(nums[1])
                            campaign_details['applicant_count'] = applicants
                            campaign_details['recruit_count'] = recruits

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
