from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import re

def setup_driver():
    """Chrome 드라이버 설정"""
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # 브라우저 창 숨기기
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        print(f"Chrome 드라이버 설정 실패: {e}")
        return None

def scroll_to_bottom(driver, max_scrolls=3):
    """페이지 스크롤 (테스트용 제한)"""
    print("페이지 스크롤 중...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    for i in range(max_scrolls):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        new_height = driver.execute_script("return document.body.scrollHeight")
        print(f"   스크롤 {i+1}/{max_scrolls} 완료")
        
        if new_height == last_height:
            print("   페이지 끝 도달")
            break
        last_height = new_height
    
    print("스크롤 완료")

def parse_remaining_days(text):
    """남은 기간 텍스트를 파싱하여 일수 반환"""
    if not text:
        return None
    text = text.strip()
    if "오늘 마감" in text or "시간 남음" in text or "마감임박" in text:
        return 0
    match = re.search(r'(\d+)\s*일', text)
    return int(match.group(1)) if match else None

def extract_campaign_info(link, idx, campaign_type):
    """캠페인 링크에서 정보 추출"""
    href = link.get('href')
    if not href:
        return None

    full_link = f"https://xn--939au0g4vj8sq.net{href}"
    
    # 제목 추출 개선
    title = link.get_text(strip=True)
    if not title:
        title = f"캠페인_{idx}"

    campaign = {
        'title': title,
        'detail_url': full_link,
        'applicant_count': None,
        'recruit_count': None,
        'remaining_days': None,
        'source_site': 'gangnam',
        'page_flag': 'main',
        'campaign_type': campaign_type
    }

    parent = link.parent
    while parent:
        if campaign['remaining_days'] is None:
            day_tag = parent.find('em', class_='day_c')
            if day_tag:
                campaign['remaining_days'] = parse_remaining_days(day_tag.text)

        if campaign['applicant_count'] is None:
            numb_tag = parent.find('span', class_='numb')
            if numb_tag:
                numbers = re.findall(r'[\d,]+', numb_tag.text)
                if len(numbers) >= 2:
                    campaign['applicant_count'] = int(numbers[0].replace(',', ''))
                    campaign['recruit_count'] = int(numbers[1].replace(',', ''))
                    
        if campaign.get('recruit_count') is not None and campaign.get('recruit_count') != 0 and campaign.get('applicant_count') is not None:
            campaign['competition_rate'] = round(campaign.get('applicant_count') / campaign.get('recruit_count'), 2)

        if campaign['remaining_days'] is not None and campaign['applicant_count'] is not None:
            break
        parent = parent.parent

    return campaign

def extract_and_process_campaigns_test(html_content, campaign_type, max_campaigns=3):
    """HTML에서 캠페인 정보 추출 (테스트용 - 최대 3개)"""
    soup = BeautifulSoup(html_content, 'html.parser')
    # 제목이 있는 링크만 선택 (dt.tit 안의 a 태그)
    campaign_links = soup.select("dt.tit a[href*='/cp/?id=']")

    print(f"{campaign_type} 카테고리에서 {len(campaign_links)}개 링크 발견")
    
    campaigns = []
    processed_count = 0
    seen_urls = set()  # 중복 URL 체크용

    for idx, link in enumerate(campaign_links, 1):
        if processed_count >= max_campaigns:
            break
            
        try:
            campaign = extract_campaign_info(link, idx, campaign_type)
            if not campaign:
                continue

            # 중복 URL 체크
            if campaign['detail_url'] in seen_urls:
                continue
            seen_urls.add(campaign['detail_url'])

            campaigns.append(campaign)
            processed_count += 1
            
            # 결과 출력
            print(f"[{processed_count}] {campaign['title'][:50]}...")
            print(f"    URL: {campaign['detail_url']}")
            print(f"    지원자/모집: {campaign['applicant_count']}/{campaign['recruit_count']}")
            print(f"    경쟁률: {campaign['competition_rate']}")
            
            # 남은 일수 표시 개선
            remaining_days = campaign['remaining_days']
            if remaining_days is None:
                print(f"    남은 일수: 불명")
            else:
                print(f"    남은 일수: {remaining_days}일")
            
            # 처리 방식 결정
            if remaining_days is None:
                print(f"    처리 방식: Detail Queue (남은 기간 불명)")
            elif remaining_days < 6:
                print(f"    처리 방식: RDS Queue (마감 임박)")
            else:
                print(f"    처리 방식: Detail Queue (여유 있음)")
            print()

        except Exception as e:
            print(f"[{idx}] 캠페인 정보 추출 실패: {e}")

    print(f"{campaign_type} 카테고리에서 총 {len(campaigns)}개 캠페인 추출 완료")
    return campaigns

def crawl_target_test(driver, url, campaign_type):
    """단일 URL 크롤링 테스트"""
    try:
        print(f"URL 로드 중: {url}")
        driver.get(url)
        time.sleep(1)

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        scroll_to_bottom(driver, max_scrolls=3)

        time.sleep(1)
        html = driver.page_source
        
        # 캠페인 추출 (최대 3개)
        campaigns = extract_and_process_campaigns_test(html, campaign_type, max_campaigns=3)
        
        return campaigns

    except Exception as e:
        print(f"크롤링 중 오류 발생: {e}")
        return []

def run_gangnam_test():
    """강남맛집 전체 타겟들 테스트 (각 타입마다 3개씩)"""
    print("강남맛집 메인 크롤링 테스트 시작")
    print("="*80)
    
    targets = [
        {"type": "전체", "url": "https://xn--939au0g4vj8sq.net/cp/?ca=20"},
        {"type": "제품", "url": "https://xn--939au0g4vj8sq.net/cp/?ca=30"},
        {"type": "기자단", "url": "https://xn--939au0g4vj8sq.net/cp/?ca=40"}
    ]

    # 드라이버 설정
    driver = setup_driver()
    if not driver:
        print("드라이버 설정 실패")
        return
    
    print("Chrome 드라이버 설정 완료")
    
    all_campaigns = []
    
    try:
        for idx, target in enumerate(targets, 1):
            print(f"[{idx}/3] {target['type']} 캠페인 크롤링 시작")
            print("-" * 60)
            
            campaigns = crawl_target_test(driver, target['url'], target['type'])
            all_campaigns.extend(campaigns)
            
            print(f"{target['type']} 완료: {len(campaigns)}개 추출")
            
            # 다음 타겟 전 딜레이
            if idx < len(targets):
                print("2초 대기 중...")
                time.sleep(2)
        
        # 최종 결과 요약
        print("="*80)
        print("강남맛집 크롤링 테스트 완료!")
        print(f"총 추출된 캠페인: {len(all_campaigns)}개")
        
        # 타입별 통계
        type_stats = {}
        detail_queue_count = 0
        rds_queue_count = 0
        
        for campaign in all_campaigns:
            campaign_type = campaign['campaign_type']
            type_stats[campaign_type] = type_stats.get(campaign_type, 0) + 1
            
            remaining_days = campaign.get('remaining_days')
            if remaining_days is None or remaining_days >= 6:
                detail_queue_count += 1
            else:
                rds_queue_count += 1
        
        print("타입별 통계:")
        for campaign_type, count in type_stats.items():
            print(f"   - {campaign_type}: {count}개")
        
        print("처리 방식 통계:")
        print(f"   - Detail Queue: {detail_queue_count}개")
        print(f"   - RDS Queue: {rds_queue_count}개")
        print("="*80)
        
        return all_campaigns
        
    except Exception as e:
        print(f"테스트 실행 중 오류: {e}")
        return []
    finally:
        driver.quit()
        print("드라이버 종료 완료")

def test_single_category(category_type, url):
    """개별 카테고리 테스트"""
    print(f"'{category_type}' 개별 테스트 시작")
    
    driver = setup_driver()
    if not driver:
        return []
    
    try:
        campaigns = crawl_target_test(driver, url, category_type)
        return campaigns
    finally:
        driver.quit()

# 테스트 실행
if __name__ == "__main__":
    # 전체 테스트 실행 (각 타입마다 3개씩)
    all_results = run_gangnam_test()
    
    # 또는 개별 카테고리 테스트
    # result = test_single_category("전체", "https://xn--939au0g4vj8sq.net/cp/?ca=20") 