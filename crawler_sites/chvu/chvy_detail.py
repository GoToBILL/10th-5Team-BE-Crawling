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

sqs = boto3.client('sqs')
RDS_QUEUE_URL = os.environ.get('RDS_QUEUE_URL')  


def get_page_content_with_selenium(driver, url):
    """Selenium을 사용하여 JavaScript가 로드된 페이지 콘텐츠 가져오기"""
    try:
        logger.info(f"페이지 로드 중: {url}")
        driver.get(url)
        
        time.sleep(1.2)
        
        # 캠페인 정보가 로드될 때까지 대기
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[class*="CampaignMain__ImformationBlock"]'))
            )
        except:
            logger.warning("CampaignMain__ImformationBlock 요소를 찾을 수 없습니다. 페이지 전체 소스를 반환합니다.")
        
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
        # 1. 모집시작일, 모집마감일, 리뷰마감일 추출
        info_block = soup.find('div', class_=lambda x: x and 'CampaignMain__ImformationBlock' in x)
        if info_block:
            info_divs = info_block.find_all('div', class_=lambda x: x and 'CampaignMain__Imformation' in x)
            
            for div in info_divs:
                text = div.text.strip()
                
                # 모집시작일 추출
                start_match = re.search(r'모집시작일\s*(\d{2}\.\d{2}\.\d{2})', text)
                if start_match:
                    campaign_details['application_startdate'] = start_match.group(1)
                    logger.info(f"모집시작일: {start_match.group(1)}")
                
                # 모집마감일 추출
                end_match = re.search(r'모집마감일\s*(\d{2}\.\d{2}\.\d{2})', text)
                if end_match:
                    campaign_details['application_enddate'] = end_match.group(1)
                    logger.info(f"모집마감일: {end_match.group(1)}")
                
                # 리뷰마감일 추출
                review_match = re.search(r'리뷰마감일\s*(\d{2}\.\d{2}\.\d{2})', text)
                if review_match:
                    campaign_details['review_deadline'] = review_match.group(1)
                    logger.info(f"리뷰마감일: {review_match.group(1)}")
        
        # 2. 혜택(benefit) 추출
        desc_div = soup.find('div', class_=lambda x: x and 'CampaignMain__Desc' in x)
        if desc_div:
            # 제공포인트 부분 제거하고 혜택만 추출
            reward_point_div = desc_div.find('div', class_=lambda x: x and 'CampaignMain__RewardPoint' in x)
            if reward_point_div:
                reward_point_div.extract()  # 제거
            
            # 남은 텍스트가 혜택
            benefit_text = desc_div.get_text(strip=True)
            if benefit_text:
                campaign_details['benefit'] = benefit_text
                logger.info(f"혜택: {benefit_text}")
        
        # 로그 출력
        if campaign_details:
            logger.info("CHVU 상세 정보 추출 완료:")
            for key, value in campaign_details.items():
                logger.info(f"   - {key}: {value}")
        else:
            logger.warning("CHVU 상세 정보 추출 실패")
        
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
        
        logger.info(f"CHVU 세부 크롤링 시작: {title}")
        
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
            logger.info(f"CHVU 디테일 처리 완료: {title}")
        else:
            logger.error(f"RDS Queue 전송 실패: {title}")
        
        return success
        
    except Exception as e:
        logger.error(f"캠페인 처리 중 오류: {e}")
        logger.error(f"오류 발생 캠페인: {campaign_data}")
        return False
