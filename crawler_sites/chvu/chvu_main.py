from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import re
import boto3
import os
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs = boto3.client('sqs')
MAIN_TO_DETAIL_QUEUE_URL = os.environ.get('MAIN_TO_DETAIL_QUEUE_URL')
RDS_QUEUE_URL = os.environ.get('RDS_QUEUE_URL')


def scroll_to_bottom(driver):
    """페이지 끝까지 스크롤"""
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


def parse_application_info(card):
    """신청 정보 파싱: 신청 9/5, D - 9 형태에서 정보 추출"""
    application_data = {
        'applicant_count': None,
        'recruit_count': None,
        'competition_rate': None,
        'remaining_days': None
    }
    
    try:
        app_elem = card.find_element(By.CSS_SELECTOR, '[class*="Application"]')
        app_text = app_elem.text.strip()
        
        # "신청 9/5" 파싱
        app_match = re.search(r'신청\s*(\d+)/(\d+)', app_text)
        if app_match:
            applicant_count = int(app_match.group(1))
            recruit_count = int(app_match.group(2))
            
            application_data['applicant_count'] = applicant_count
            application_data['recruit_count'] = recruit_count
            
            if recruit_count > 0:
                application_data['competition_rate'] = round(applicant_count / recruit_count, 2)
        
        # "D - 9" 파싱
        d_day_match = re.search(r'D\s*-\s*(\d+)', app_text)
        if d_day_match:
            application_data['remaining_days'] = int(d_day_match.group(1))
        elif 'D-DAY' in app_text or 'D - DAY' in app_text:
            application_data['remaining_days'] = 0
            
    except NoSuchElementException:
        pass
    
    return application_data


def parse_campaign_info(card, current_category):
    """캠페인 카드에서 정보 추출"""
    data = {}
    try:
        # 기본 정보
        link = card.get_attribute("href")
        if not link:
            return None
        data['detail_url'] = link
        data['source_site'] = 'chvu'
        data['page_flag'] = 'main'

        # 제목 추출
        title_selectors = [
            '[class*="NewFlexibleCard__Title"]',
            '[class*="FlexibleCard__Title"]',
            '[class*="Title"]'
        ]
        
        for selector in title_selectors:
            try:
                title_elem = card.find_element(By.CSS_SELECTOR, selector)
                full_title = title_elem.text.strip()
                
                # 대괄호 안의 지역 정보 추출
                region_match = re.search(r'\[(.*?)\]', full_title)
                if region_match:
                    data['address'] = region_match.group(1).strip()  # [서울/양천] -> 서울/양천
                    # 제목에서 대괄호 부분 제거
                    data['title'] = re.sub(r'\[.*?\]\s*', '', full_title).strip()  # 나다피트니스
                else:
                    # 대괄호가 없으면 배송형 - 전체 텍스트를 title로
                    data['address'] = None
                    data['title'] = full_title
                break
            except NoSuchElementException:
                continue
        else:
            data['title'] = "제목 없음"

        # 현재 카테고리를 campaign_type으로 설정
        data['campaign_type'] = current_category

        # SNS 타입 추출 (컴팩트하게)
        try:
            sns_elem = card.find_element(By.CSS_SELECTOR, '[class*="ChannelType__TypeDiv"]')
            sns = sns_elem.text.strip().lower()
            if sns == 'instagram':
                sns = "insta"
            data['sns_type'] = sns
        except NoSuchElementException:
            data['sns_type'] = None

        # 신청 정보 파싱
        app_info = parse_application_info(card)
        data.update(app_info)

    except Exception as e:
        logger.error(f"캠페인 정보 파싱 중 오류: {e}")
        return None

    return data


def send_to_detail_queue(data):
    """Detail Queue로 데이터 전송"""
    try:
        response = sqs.send_message(
            QueueUrl=MAIN_TO_DETAIL_QUEUE_URL,
            MessageBody=json.dumps(data, ensure_ascii=False)
        )
        logger.info(f"Detail Queue 전송 완료: {data['title'][:50]}")
        return True
    except Exception as e:
        logger.error(f"Detail Queue 전송 실패: {e}")
        return False


def send_to_rds_queue(data):
    """RDS Queue로 데이터 전송"""
    try:
        response = sqs.send_message(
            QueueUrl=RDS_QUEUE_URL,
            MessageBody=json.dumps(data, ensure_ascii=False)
        )
        logger.info(f"RDS Queue 전송 완료: {data['title'][:50]}")
        return True
    except Exception as e:
        logger.error(f"RDS Queue 전송 실패: {e}")
        return False


def process_campaign_by_remaining_days(campaign):
    """남은 일수에 따라 캠페인 처리"""
    remaining_days = campaign.get('remaining_days')
    title = campaign.get('title', 'Unknown')[:50]
    
    applicant_count = campaign.get('applicant_count', 'N/A')
    recruit_count = campaign.get('recruit_count', 'N/A')
    competition_rate = campaign.get('competition_rate', 'N/A')
    sns_type = campaign.get('sns_type', 'N/A')
    campaign_type = campaign.get('campaign_type', 'N/A')
    
    logger.info(f"{title}")
    logger.info(f"   타입: {campaign_type}, SNS: {sns_type}")
    logger.info(f"   지원자: {applicant_count}, 모집: {recruit_count}, 경쟁률: {competition_rate}")

    if remaining_days is None:
        logger.info(f"남은 기간 불명 → Detail Queue: {title}")
        return send_to_detail_queue(campaign)

    if remaining_days < 20:
        logger.info(f"마감 임박 ({remaining_days}일) → RDS Queue: {title}")
        return send_to_rds_queue(campaign)
    else:
        logger.info(f"여유 있음 ({remaining_days}일) → Detail Queue: {title}")
        return send_to_detail_queue(campaign)


def crawl_target(driver, current_category):
    """캠페인 카드들을 크롤링"""
    try:
        # 카드 선택자
        card_selectors = [
            'a.NewFlexibleCard__StyledCard-sc-1eu57ly-0',
            'a.FlexibleCard__StyledCard-sc-1dw1ej1-0',
            '[class*="StyledCard"]',
            'a[href*="/campaign/"]'
        ]
        
        cards = []
        for selector in card_selectors:
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                cards = driver.find_elements(By.CSS_SELECTOR, selector)
                if cards:
                    logger.info(f"선택자 '{selector}'로 {len(cards)}개 카드 발견")
                    break
            except TimeoutException:
                continue
        
        if not cards:
            logger.error("캠페인 카드를 찾을 수 없습니다")
            return 0, 1
            
        scroll_to_bottom(driver)
        time.sleep(1)

        # 스크롤 후 다시 카드 찾기
        cards = driver.find_elements(By.CSS_SELECTOR, card_selectors[0])
        logger.info(f"총 {len(cards)}개의 캠페인 카드 발견")

        suc_cnt, err_cnt = 0, 0
        for idx, card in enumerate(cards):
            try:
                info = parse_campaign_info(card, current_category)
                if info:
                    success = process_campaign_by_remaining_days(info)
                    if success:
                        suc_cnt += 1
                    else:
                        err_cnt += 1
                else:
                    err_cnt += 1
                    logger.warning(f"카드 #{idx}: 정보 파싱 실패")
            except Exception as e:
                err_cnt += 1
                logger.error(f"[ERROR] 카드 #{idx} 처리 실패: {e}")

        return suc_cnt, err_cnt
    except Exception as e:
        logger.error(f"크롤링 중 오류 발생: {e}")
        return 0, 1


def run(driver):
    """CHVU 메인 크롤링 함수"""
    categories = [
        {"label": "방문형", "type": "방문형"},
        {"label": "배송형", "type": "배송형"},
        {"label": "기자단", "type": "기자단"}
    ]

    total_suc, total_err = 0, 0
    
    for idx, category in enumerate(categories):
        try:
            label = category["label"]
            campaign_type = category["type"]
            
            # 리프레시 로직
            if idx == 0:
                driver.get("https://chvu.co.kr/campaign")
                logger.info(f"첫 페이지 로드: {label}")
            else:
                driver.refresh()
                logger.info(f"페이지 리프레시 후 {label} 선택자 클릭 시도")
            
            time.sleep(2)
            
            # 카테고리 버튼 클릭
            logger.info(f"선택자 클릭 시도: {label}")
            buttons = driver.find_elements(By.CSS_SELECTOR, "div.CategorySelector__SelectorCategory-sc-vn201x-0")
            
            clicked = False
            for btn in buttons:
                if label in btn.text:
                    btn.click()
                    time.sleep(1)
                    clicked = True
                    logger.info(f"{label} 버튼 클릭 완료")
                    break
            
            if not clicked:
                logger.warning(f"{label} 버튼을 찾을 수 없습니다")
                continue

            # 크롤링 실행 (현재 카테고리 전달)
            logger.info(f"크롤링 시작: {label} 캠페인")
            cnt, err = crawl_target(driver, campaign_type)
            logger.info(f"  완료: {cnt}개 / 실패: {err}개")
            total_suc += cnt
            total_err += err
            
        except Exception as e:
            logger.error(f"선택자 클릭 실패: {label} / 오류: {e}")
            total_err += 1

    logger.info(f"CHVU 크롤링 완료 - 총 성공: {total_suc}개, 실패: {total_err}개")
    return total_suc, total_err
