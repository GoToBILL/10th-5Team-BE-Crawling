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
#RDS_QUEUE_URL = os.environ.get('RDS_QUEUE_URL')  # RDS 처리용 SQS 큐


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
                    
                    # 주요 필드 매핑
                    if '협찬 상품' in field_name:
                        campaign_details['제공내역'] = field_value
                    elif '모집 및 선정 기간' in field_name:
                        campaign_details['신청기간'] = field_value
                    elif '리뷰 제출 마감일' in field_name:
                        campaign_details['등록기간'] = field_value
        
        # 모집 인원 정보 추출
        recruit_info = None
        
        # 방법 1: 클래스명의 일부로 검색
        for span in soup.find_all('span'):
            if span.has_attr('class') and any('text-[#949494]' in cls for cls in span['class']):
                recruit_info = span
                break
        
        # 방법 2: "신청" 텍스트가 포함된 span 찾기
        if not recruit_info:
            for span in soup.find_all('span'):
                if '신청' in span.text and '명' in span.text:
                    recruit_info = span
                    break
        
        # 모집인원 처리
        if recruit_info:
            recruit_text = recruit_info.text.strip()
            if '신청' in recruit_text and '명' in recruit_text:
                # "신청 X / Y명" 형식에서 숫자 추출
                match = re.search(r'신청\s*(\d+)\s*/\s*(\d+)명', recruit_text)
                if match:
                    campaign_details['신청인원'] = match.group(1)
                    campaign_details['모집인원'] = match.group(2)
        
        # 추가 정보 추출 (필요시)
        # 우대사항, 플랫폼 정보 등
        
    except Exception as e:
        logger.error(f"상세 정보 추출 중 오류: {e}")
    
    return campaign_details


# def send_to_rds_queue(campaign_data):
    # """RDS 처리용 SQS로 데이터 전송"""
    # if not RDS_QUEUE_URL:
    #     logger.warning("RDS_QUEUE_URL이 설정되지 않음. RDS 전송 건너뜀.")
    #     return False
        
    # try:
    #     response = sqs.send_message(
    #         QueueUrl=RDS_QUEUE_URL,
    #         MessageBody=json.dumps(campaign_data, ensure_ascii=False)
    #     )
    #     logger.info(f"RDS 큐로 전송 완료: {campaign_data.get('title', 'Unknown')}")
    #     return True
    # except Exception as e:
    #     logger.error(f"RDS 큐 전송 실패: {e}")
    #     return False


def process_campaign(driver, campaign_data):
    """단일 캠페인 세부 정보 처리"""
    try:
        title = campaign_data.get('title', 'Unknown')
        detail_url = campaign_data.get('detail_url', '')
        
        if not detail_url:
            logger.error(f"URL이 없는 캠페인: {title}")
            return False
        
        logger.info(f"🔍 포포몬 세부 크롤링 시작: {title}")
        
        # 세부 페이지 크롤링
        detail_html = get_page_content_with_selenium(driver, detail_url)
        if not detail_html:
            logger.error(f"페이지 로드 실패: {detail_url}")
            return False
        
        # 상세 정보 추출
        details = extract_campaign_details(detail_html)
        
        # 기존 데이터와 병합
        final_data = {**campaign_data, **details}
        
        # 결과 출력 (확인용)
        logger.info(f"크롤링 완료: {title}")
        logger.info(f"추출된 정보:")
        for key, value in details.items():
            logger.info(f"   - {key}: {value}")
        
        # RDS 처리용 SQS로 전송
        #send_to_rds_queue(final_data)
        
        return True
        
    except Exception as e:
        logger.error(f"캠페인 처리 중 오류: {e}")
        return False