from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import boto3
import json
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs = boto3.client('sqs')
QUEUE_URL = os.environ.get('MAIN_TO_DETAIL_QUEUE_URL')


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


def extract_campaign_links(html_content):
    """HTML 내용에서 캠페인 정보 추출"""
    soup = BeautifulSoup(html_content, 'html.parser')
    campaigns = []
    
    campaign_links = soup.select('a[href^="/next/campaign/"]')
    
    for link in campaign_links:
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
            
            if title and href:
                campaign_data = {
                    'title': title,
                    'detail_url': full_link,
                    'source_site': 'popomon',
                    'page_flag': 'main'
                }
                campaigns.append(campaign_data)
        except Exception as e:
            logger.error(f"링크 추출 중 오류 발생: {e}")
    
    return campaigns


def determine_campaign_type(url):
    """URL에서 캠페인 타입 결정"""
    if 'visiting' in url:
        return '방문'
    elif 'shipping' in url:
        return '배송'
    elif 'reporting' in url:
        return '기자단'
    else:
        return '기타'


def send_to_sqs(data):
    """SQS 메시지 전송"""
    try:
        response = sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(data, ensure_ascii=False)
        )
        logger.info(f"SQS(Main To Detail) - Message sent: {data['title'][:50]}")
        return response
    except Exception as e:
        logger.error(f"SQS 전송 실패: {e}")
        return False


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
        
        # 캠페인 링크 추출
        campaigns = extract_campaign_links(page_source)
        
        # 캠페인 타입 설정
        for campaign in campaigns:
            campaign['campaign_type'] = campaign_type
        
        logger.info(f"총 {len(campaigns)}개 캠페인 추출됨 ({campaign_type})")
        
        # SQS로 전송
        suc_cnt, err_cnt = 0, 0
        for idx,campaign in enumerate(campaigns, start=1):
            try:
                send_to_sqs(campaign)
                suc_cnt += 1
            except Exception as e:
                err_cnt += 1
                logger.error(f"[ERROR] ({campaign_type}) Card #{idx} 처리 실패: {e}")
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
        logger.info(f"▶ 크롤링 시작: {target['type']} 캠페인")
        cnt, err_cnt = crawl_target(driver, target["url"], target["type"])
        logger.info(f"  ⤷ 완료: {cnt}개 / 실ㅌ패: {err_cnt}개")
        total_cnt += cnt
        total_err_cnt += err_cnt

    
    logger.info(f"포포몬 크롤링 완료 - 총 성공: {total_cnt}개, 실패: {total_err_cnt}개")
    return total_cnt, total_err_cnt