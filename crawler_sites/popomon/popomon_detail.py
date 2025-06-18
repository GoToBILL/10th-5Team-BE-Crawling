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
        
        time.sleep(1.2)
        
        # 캠페인 정보가 로드될 때까지 대기
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "campInfo"))
            )
        except:
            logger.warning("campInfo 요소를 찾을 수 없습니다. 페이지 전체 소스를 반환합니다.")
        
        html_content = driver.page_source
        return html_content
        
    except Exception as e:
        logger.error(f"페이지 가져오기 실패: {e}")
        return None


def extract_campaign_details(html_content):
    """HTML에서 캠페인 상세 정보 추출"""
    if not html_content:
        return {}
    
    soup = BeautifulSoup(html_content, 'html.parser')
    campaign_details = {}

    try:
        # 캠페인 정보 섹션
        camp_info = soup.find(id='campInfo')
        if camp_info:
            # 모든 li 요소 확인
            for li in camp_info.find_all('li'):
                b_tag = li.find('b')
                span_tag = li.find('span')
                
                if b_tag:
                    field_name = b_tag.text.strip()
                    field_value = span_tag.text.strip() if span_tag else ""
                    
                    # 주요 필드 매핑 (영문 키로 통일)
                    if '협찬 상품' in field_name:
                        campaign_details['benefit'] = field_value
                    elif '모집 및 선정 기간' in field_name:
                        # 예: "25.05.29 ~ 25.06.28 (상시 선정)"
                        period_match = re.search(r'(\d{2}\.\d{2}\.\d{2})\s*~\s*(\d{2}\.\d{2}\.\d{2})', field_value)
                        if period_match:
                            campaign_details['apply_startdate'] = period_match.group(1)
                            campaign_details['apply_enddate'] = period_match.group(2)
                    elif '리뷰 제출 마감일' in field_name:
                        campaign_details['content_submission_end'] = field_value
        # 주소 정보 추출 - 두 번째 요소 선택
        address_spans = soup.find_all('span', class_='w-[calc(100%_-_20px)] flex flex-wrap')
        if len(address_spans) >= 2 and address_spans[1].text.strip():
            campaign_details['address'] = address_spans[1].text.strip()
        elif len(address_spans) >= 1 and address_spans[0].text.strip():
            # 두 번째가 없으면 첫 번째라도
            campaign_details['address'] = address_spans[0].text.strip()
        else:
            campaign_details['address'] = None  
        # 플랫폼 정보 & 지역 정보 추출 (일단 플로우 확인 후에 나중에 추가)

        
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
        
        logger.info(f"포포몬 세부 크롤링 시작: {title}")
        
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