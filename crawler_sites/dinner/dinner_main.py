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
    """페이지 끝까지 스크롤"""
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
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
    
    # "오늘 마감", "시간 남음" 케이스
    if "오늘 마감" in remaining_text or "시간 남음" in remaining_text:
        return 0
    
    # "D-7" 패턴 (디너의여왕)
    d_match = re.search(r'D-(\d+)', remaining_text)
    if d_match:
        return int(d_match.group(1))
    
    # "X일 남음" 패턴
    match = re.search(r'(\d+)일.*남음', remaining_text)
    if match:
        return int(match.group(1))
    
    # 파싱 실패 시 None 반환
    logger.warning(f"남은 기간 파싱 실패: {remaining_text}")
    return None


def extract_and_process_campaigns(html_content, campaign_type):
    """HTML 내용에서 캠페인 정보 추출하고 바로 처리"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 디너의여왕 캠페인 링크 찾기
    campaign_links = soup.select("a.qz-dq-card__link[href*='/taste/']")
    
    suc_cnt, err_cnt = 0, 0
    detail_cnt, rds_cnt = 0, 0
    
    for idx, link in enumerate(campaign_links, start=1):
        try:
            href = link.get('href')
            if not href:
                continue
            
            # 절대 URL로 변환
            full_link = f"https://dinnerqueen.net{href}" if href.startswith('/') else href
            
            # 캠페인 제목 추출
            title = None
            title_attr = link.get('title')
            if title_attr and title_attr != 'No Title':
                title = title_attr.strip()
            else:
                # 다른 방법으로 제목 찾기 시도
                title_elem = link.select_one('.qz-dq-card__title, h3, .title')
                if title_elem:
                    title = title_elem.text.strip()
                else:
                    title = f"캠페인_{idx}"
            
            # 신청인원/모집인원 추출 (디너의여왕 구조)
            applicants = None
            recruitments = None
            competition_rate = None
            
            # 부모 요소에서 신청/모집 정보 찾기
            card_parent = link.parent
            while card_parent and card_parent.name != 'body':
                for elem in card_parent.select('span, p, strong'):
                    text = elem.text.strip()
                    if '신청' in text and ('모집' in text or '/' in text):
                        try:
                            # 숫자만 추출
                            nums = re.findall(r'\d+', text)
                            if len(nums) >= 2:
                                applicants = int(nums[0])
                                recruitments = int(nums[1])
                                break
                        except (ValueError, IndexError):
                            logger.warning(f"신청/모집 인원 파싱 실패: {text}")
                if applicants and recruitments:
                    break
                card_parent = card_parent.parent
            
            # 경쟁률 계산
            if applicants is not None and recruitments is not None and recruitments > 0:
                competition_rate = round(applicants / recruitments, 2)
            
            # 남은 기간 추출 (디너의여왕 구조)
            remaining_days = None
            card_parent = link.parent
            while card_parent and card_parent.name != 'body':
                for elem in card_parent.select('span, p, strong'):
                    text = elem.text.strip()
                    if 'D-' in text or ('일' in text and '남' in text):
                        remaining_days = parse_remaining_days(text)
                        if remaining_days is not None:
                            break
                if remaining_days is not None:
                    break
                card_parent = card_parent.parent
            
            if title and href:
                campaign_data = {
                    'title': title,
                    'detail_url': full_link,
                    'applicant_count': applicants,
                    'recruit_count': recruitments,
                    'remaining_days': remaining_days,
                    'source_site': 'dinnerqueen',
                    'page_flag': 'main',
                    'campaign_type': campaign_type,
                    'competition_rate': competition_rate
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
        time.sleep(2)
        
        # 페이지 로드 대기
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a.qz-dq-card__link"))
            )
        except:
            logger.warning("페이지 로드 실패")
            return 0, 1
        
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
    디너의여왕 전체 타겟들 순회하며 크롤링
    """
    targets = [
        {
            "type": "전체",
            "url": "https://dinnerqueen.net/taste?ct=%EC%A0%84%EC%B2%B4"
        },
        {
            "type": "배송", 
            "url": "https://dinnerqueen.net/taste?ct=%EB%B0%B0%EC%86%A1"
        },
        {
            "type": "방문",
            "url": "https://dinnerqueen.net/taste?ct=%EB%B0%A9%EB%AC%B8"
        }
    ]
    
    total_cnt, total_err_cnt = 0, 0
    
    for target in targets:
        logger.info(f"크롤링 시작: {target['type']} 캠페인")
        cnt, err_cnt = crawl_target(driver, target["url"], target["type"])
        logger.info(f"  완료: {cnt}개 / 실패: {err_cnt}개")
        total_cnt += cnt
        total_err_cnt += err_cnt
    
    logger.info(f"디너의여왕 크롤링 완료 - 총 성공: {total_cnt}개, 실패: {total_err_cnt}개")
    return total_cnt, total_err_cnt