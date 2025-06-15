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
MAIN_TO_DETAIL_QUEUE_URL = os.environ.get('MAIN_TO_DETAIL_QUEUE_URL')  # 디테일 크롤링용
RDS_QUEUE_URL = os.environ.get('RDS_QUEUE_URL')  # RDS 직접 처리용


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
    """남은 기간 텍스트를 파싱하여 일수 반환"""
    if not remaining_text:
        return None
    
    remaining_text = remaining_text.strip()
    
    # "오늘 마감" 케이스
    if "오늘 마감" in remaining_text:
        return 0
    
    # "X일 남음" 패턴
    match = re.search(r'(\d+)일\s*남음', remaining_text)
    if match:
        return int(match.group(1))
    
    # "X시간 남음" 패턴 (1일 미만으로 처리)
    if "시간 남음" in remaining_text:
        return 0
    
    # 파싱 실패 시 None 반환
    logger.warning(f"남은 기간 파싱 실패: {remaining_text}")
    return None


def extract_and_process_campaigns(html_content, campaign_type):
    """HTML 내용에서 캠페인 정보 추출하고 바로 처리"""
    soup = BeautifulSoup(html_content, 'html.parser')
    campaign_links = soup.select('a[href^="/next/campaign/"]')
    
    suc_cnt, err_cnt = 0, 0
    detail_cnt, rds_cnt = 0, 0
    
    for idx, link in enumerate(campaign_links, start=1):
        try:
            href = link.get('href')
            if not href:
                continue
                
            full_link = f"https://popomon.com{href}"
            
            # 캠페인 제목 추출
            title = None
            title_elem = link.select_one('h3')
            if title_elem:
                title = title_elem.text.strip()
            else:
                title_elem = link.select_one('.line-1skip, .my-2')
                if title_elem:
                    title = title_elem.text.strip()
            
            # 신청인원/모집인원 추출
            applicants = None
            recruitments = None
            
            # "신청 0/10" 형태의 텍스트를 찾기
            recruitment_elem = link.select_one('span.text-c-2.text-gray-450')
            if recruitment_elem:
                recruitment_text = recruitment_elem.text.strip()
                # "신청 0/10" 형태에서 숫자 추출
                if '신청' in recruitment_text and '/' in recruitment_text:
                    try:
                        # "신청 " 제거하고 "0/10" 부분만 추출
                        numbers_part = recruitment_text.replace('신청', '').strip()
                        if '/' in numbers_part:
                            parts = numbers_part.split('/')
                            applicants = int(parts[0].strip())
                            recruitments = int(parts[1].strip())
                    except (ValueError, IndexError) as e:
                        logger.warning(f"신청인원/모집인원 파싱 실패: {recruitment_text}, 오류: {e}")
            
            # 남은 기간 추출
            remaining_days = None
            remaining_elem = link.select_one('span.text-purple-600.font-semibold')
            if remaining_elem:
                remaining_text = remaining_elem.text.strip()
                remaining_days = parse_remaining_days(remaining_text)
            
            if title and href:
                campaign_data = {
                    'title': title,
                    'detail_url': full_link,
                    'applicant_count': applicants,
                    'recruit_count': recruitments,
                    'remaining_days': remaining_days,
                    'source_site': 'popomon',
                    'page_flag': 'main',
                    'campaign_type': campaign_type
                }
                
                # 바로 처리
                success = process_campaign_by_remaining_days(campaign_data)
                
                if success:
                    suc_cnt += 1
                    # 통계 집계
                    if remaining_days is None or remaining_days >= 7:
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
    """디테일 크롤링용 SQS 메시지 전송"""
    try:
        response = sqs.send_message(
            QueueUrl=MAIN_TO_DETAIL_QUEUE_URL,
            MessageBody=json.dumps(data, ensure_ascii=False)
        )
        logger.info("send to detail sqs, reponse : {}",response)
        logger.info(f"Detail Queue로 전송 완료: {data['title'][:50]}")
        return True
    except Exception as e:
        logger.error(f"Detail Queue 전송 실패: {e}")
        return False


def send_to_rds_queue(data):
    """RDS 직접 처리용 SQS 메시지 전송"""
    try:
        response = sqs.send_message(
            QueueUrl=RDS_QUEUE_URL,
            MessageBody=json.dumps(data, ensure_ascii=False)
        )
        logger.info("send to rds sqs, reponse : {}",response)
        logger.info(f"RDS Queue로 전송 완료: {data['title'][:50]}")
        return True
    except Exception as e:
        logger.error(f"RDS Queue 전송 실패: {e}")
        return False


def process_campaign_by_remaining_days(campaign):
    """남은 기간에 따라 캠페인 처리 방식 결정"""
    remaining_days = campaign.get('remaining_days')
    campaign_type = campaign.get('campaign_type')
    title = campaign.get('title', 'Unknown')[:50]
    
    # 남은 기간을 파싱할 수 없는 경우 디테일로 전송 (안전하게)
    if remaining_days is None:
        logger.info(f"남은 기간 불명 → Detail Queue: {title}")
        return send_to_detail_queue(campaign)
    
    # 7일 미만 (마감 임박) → RDS 직접 전송
    if remaining_days < 7:
        logger.info(f"마감 임박 ({remaining_days}일) → RDS Queue: {title}")
        return send_to_rds_queue(campaign)
    
    # 7일 이상 → 디테일 크롤링 후 처리
    else:
        logger.info(f"여유 있음 ({remaining_days}일) → Detail Queue: {title}")
        return send_to_detail_queue(campaign)


def crawl_target(driver, url, campaign_type):
    """단일 URL 크롤링"""
    try:
        logger.info(f"URL 로드 중: {url}")
        driver.get(url)
        
        # 페이지 로드 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/next/campaign/']"))
        )
        
        # 페이지 끝까지 스크롤
        scroll_to_bottom(driver)
        
        time.sleep(1)
        
        # 현재 페이지 소스 가져오기
        page_source = driver.page_source
        
        # 캠페인 추출하고 바로 처리
        suc_cnt, err_cnt = extract_and_process_campaigns(page_source, campaign_type)
        
        return suc_cnt, err_cnt
        
    except Exception as e:
        logger.error(f"크롤링 중 오류 발생: {e}")
        return 0, 1


def run(driver):
    """
    포포몬 전체 타겟들 순회하며 크롤링
    """
    targets = [
        {
            "type": "방문",
            "url": "https://popomon.com/next/campaign?searchAlign=latest&bigRecruitType=Lvisiting&recruitType=visiting&interestsFilter=ALL&pageNum=0"
        },
        {
            "type": "배송", 
            "url": "https://popomon.com/next/campaign?searchAlign=latest&bigRecruitType=Pshipping&recruitType=shipping&interestsFilter=ALL&pageNum=0"
        },
        {
            "type": "기자단",
            "url": "https://popomon.com/next/campaign?searchAlign=latest&bigRecruitType=Lvisiting&recruitType=reporting&interestsFilter=ALL&pageNum=0"
        }
    ]
    
    total_cnt, total_err_cnt = 0, 0
    
    for target in targets:
        logger.info(f"크롤링 시작: {target['type']} 캠페인")
        cnt, err_cnt = crawl_target(driver, target["url"], target["type"])
        logger.info(f"  완료: {cnt}개 / 실패: {err_cnt}개")
        total_cnt += cnt
        total_err_cnt += err_cnt

    
    logger.info(f"포포몬 크롤링 완료 - 총 성공: {total_cnt}개, 실패: {total_err_cnt}개")
    return total_cnt, total_err_cnt