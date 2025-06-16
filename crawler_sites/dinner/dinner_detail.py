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
    """Selenium을 사용하여 JavaScript가 로드된 페이지 콘텐츠 가져오기"""
    try:
        logger.info(f"페이지 로드 중: {url}")
        driver.get(url)
        
        time.sleep(2)
        
        # 페이지가 로드될 때까지 대기
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except:
            logger.warning("페이지 로드 대기 실패. 페이지 전체 소스를 반환합니다.")
        
        html_content = driver.page_source
        return html_content
        
    except Exception as e:
        logger.error(f"페이지 가져오기 실패: {e}")
        return None


def extract_campaign_details(html_content):
    """HTML에서 캠페인 상세 정보 추출 (디너의여왕 구조)"""
    if not html_content:
        return {}
    
    soup = BeautifulSoup(html_content, 'html.parser')
    campaign_details = {}

    try:
        # 날짜 컨테이너에서 순서대로 추출
        date_elems = soup.select('p.qz-body-kr--line')
        
        if len(date_elems) >= 3:
            # 첫 번째: 신청기간 (25.06.11 – 25.06.17)
            first_text = date_elems[0].text.strip()
            if '–' in first_text:
                dates = first_text.split('–')
                if len(dates) == 2:
                    campaign_details['application_startdate'] = dates[0].strip()
                    campaign_details['application_enddate'] = dates[1].strip()
            
            # 두 번째: 발표일 (25.06.18)
            second_text = date_elems[1].text.strip()
            campaign_details['selection_date'] = second_text
            
            # 세 번째: 체험&리뷰 (25.06.19 – 25.07.03)
            third_text = date_elems[2].text.strip()
            if '–' in third_text:
                dates = third_text.split('–')
                if len(dates) == 2:
                    campaign_details['review_deadline'] = dates[1].strip()
            else:
                campaign_details['review_deadline'] = third_text
        
    except Exception as e:
        logger.error(f"상세 정보 추출 중 오류: {e}")
    
    return campaign_details


def send_to_rds_queue(campaign_data):
    """RDS 처리용 SQS로 데이터 전송"""
    if not RDS_QUEUE_URL:
        logger.warning("RDS_QUEUE_URL이 설정되지 않음. RDS 전송 건너뜀.")
        return False
        
    try:
        response = sqs.send_message(
            QueueUrl=RDS_QUEUE_URL,
            MessageBody=json.dumps(campaign_data, ensure_ascii=False)
        )
        logger.info(f"RDS 큐로 전송 완료: {campaign_data.get('title', 'Unknown')}")
        return True
    except Exception as e:
        logger.error(f"RDS 큐 전송 실패: {e}")
        return False


def run(driver, campaign_data):
    """단일 캠페인 세부 정보 처리 - 하나씩 바로 처리"""
    try:
        title = campaign_data.get('title', 'Unknown')
        detail_url = campaign_data.get('detail_url', '')
        
        if not detail_url:
            logger.error(f"URL이 없는 캠페인: {title}")
            return False
        
        logger.info(f"디너의여왕 세부 크롤링 시작: {title}")
        
        # 세부 페이지 크롤링
        detail_html = get_page_content_with_selenium(driver, detail_url)
        if not detail_html:
            logger.error(f"페이지 로드 실패: {detail_url}")
            return False
        
        # 상세 정보 추출
        details = extract_campaign_details(detail_html)
        
        # 기존 데이터와 병합
        final_data = {**campaign_data, **details}
        
        # page_flag를 detail로 변경
        final_data['page_flag'] = 'detail'

        
        # 추출된 정보 로깅
        logger.info(f"상세 정보 추출 완료: {title}")
        if details:
            for key, value in details.items():
                logger.info(f"   - {key}: {value}")
        else:
            logger.warning(f"상세 정보 추출 실패 또는 없음: {title}")
        
        # RDS 처리용 SQS로 즉시 전송
        success = send_to_rds_queue(final_data)
        
        if success:
            logger.info(f"디테일 처리 완료: {title}")
        else:
            logger.error(f"RDS Queue 전송 실패: {title}")
        
        return success
        
    except Exception as e:
        logger.error(f"캠페인 처리 중 오류: {e}")
        logger.error(f"오류 발생 캠페인: {campaign_data}")
        return False