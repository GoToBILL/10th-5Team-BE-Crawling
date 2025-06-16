import boto3
import json
import os
import logging
import time
import re
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# SQS 클라이언트 (RDS 처리용)
sqs = boto3.client('sqs')
RDS_QUEUE_URL = os.environ.get('RDS_QUEUE_URL')  # RDS 처리용 SQS 큐


def get_page_content_with_requests(url):
    """requests를 사용하여 페이지 콘텐츠 가져오기"""
    try:
        logger.info(f"페이지 로드 중: {url}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        return response.text
        
    except Exception as e:
        logger.error(f"페이지 가져오기 실패: {e}")
        return None


def parse_date_range(date_text):
    """날짜 범위 텍스트를 시작일과 종료일로 분리"""
    if not date_text:
        return None, None
    
    # "06.17 ~ 06.30" 형태 파싱
    date_match = re.search(r'(\d{2}\.\d{2})\s*~\s*(\d{2}\.\d{2})', date_text)
    if date_match:
        start_date = date_match.group(1)
        end_date = date_match.group(2)
        
        # 연도 추가 (현재 연도 기준)
        current_year = "25"  # 2025년 기준
        start_date = f"{current_year}.{start_date}"
        end_date = f"{current_year}.{end_date}"
        
        return start_date, end_date
    
    return None, None


def extract_campaign_details(html_content):
    """HTML에서 캠페인 상세 정보 추출 (포포몬 스타일 변수명)"""
    if not html_content:
        return {}
    
    soup = BeautifulSoup(html_content, 'html.parser')
    campaign_details = {}

    try:
        # 아이템 정보 영역 찾기
        item_info = soup.select_one('.item_info')
        if not item_info:
            logger.warning("item_info 영역을 찾을 수 없습니다")
            return campaign_details

        # 리뷰 일정 정보 추출
        review_wrap = item_info.select_one('.review_wrap')
        if review_wrap:
            for box in review_wrap.select('.box01'):
                label_elem = box.select_one('em')
                if not label_elem:
                    continue
                
                label = label_elem.text.strip()
                value = box.get_text().replace(label, '').strip()
                
                # 리뷰어 신청 기간 -> application_startdate, application_enddate
                if '리뷰어 신청' in label:
                    start_date, end_date = parse_date_range(value)
                    if start_date and end_date:
                        campaign_details['application_startdate'] = start_date
                        campaign_details['application_enddate'] = end_date
                        logger.info(f"신청 기간: {start_date} ~ {end_date}")
                
                # 리뷰등록 기간 -> review_deadline (종료일만)
                elif '리뷰등록' in label:
                    start_date, end_date = parse_date_range(value)
                    if end_date:
                        campaign_details['review_deadline'] = end_date
                        logger.info(f"리뷰 마감일: {end_date}")
        
        # 제공 내역 추출 -> benefit
        provision_elem = item_info.select_one('.etc_list2 .etc2')
        if provision_elem:
            benefit_text = provision_elem.get_text().strip().replace('\n', ' ')
            campaign_details['benefit'] = benefit_text
            logger.info(f"혜택: {benefit_text}")
        
        # 로그 출력
        if campaign_details:
            logger.info("데일리뷰 상세 정보 추출 완료:")
            for key, value in campaign_details.items():
                logger.info(f"   - {key}: {value}")
        else:
            logger.warning("데일리뷰 상세 정보 추출 실패")
        
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


def run(campaign_data):
    """단일 캠페인 세부 정보 처리 - 하나씩 바로 처리 (requests 사용)"""
    try:
        title = campaign_data.get('title', 'Unknown')
        detail_url = campaign_data.get('detail_url', '')
        
        if not detail_url:
            logger.error(f"URL이 없는 캠페인: {title}")
            return False
        
        logger.info(f"데일리뷰 세부 크롤링 시작: {title}")
        
        # 세부 페이지 크롤링 (requests 사용)
        detail_html = get_page_content_with_requests(detail_url)
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
            logger.info(f"데일리뷰 디테일 처리 완료: {title}")
        else:
            logger.error(f"RDS Queue 전송 실패: {title}")
        
        return success
        
    except Exception as e:
        logger.error(f"캠페인 처리 중 오류: {e}")
        logger.error(f"오류 발생 캠페인: {campaign_data}")
        return False
