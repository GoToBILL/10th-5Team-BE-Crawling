from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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
        print(f"❌ Chrome 드라이버 설정 실패: {e}")
        return None

def scroll_to_bottom(driver):
    """페이지 끝까지 스크롤 (테스트용 - 제한적)"""
    print("📜 페이지 스크롤 시작...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_count = 0
    max_scrolls = 5  # 테스트용으로 스크롤 횟수 제한
    
    while scroll_count < max_scrolls:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        new_height = driver.execute_script("return document.body.scrollHeight")
        scroll_count += 1
        print(f"   📍 스크롤 {scroll_count}/{max_scrolls} 완료")
        
        if new_height == last_height:
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                print("✅ 페이지 끝에 도달함")
                break
        last_height = new_height
    
    print("✅ 스크롤 완료")

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
    print(f"⚠️ 남은 기간 파싱 실패: {remaining_text}")
    return None

def extract_campaign_info(link, campaign_type):
    """단일 캠페인 링크에서 정보 추출"""
    try:
        href = link.get('href')
        if not href:
            return None
            
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
        competition_rate = None
        
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
                        
                        if recruitments > 0:
                            competition_rate = round(applicants / recruitments, 2)
                except (ValueError, IndexError) as e:
                    print(f"⚠️ 신청인원/모집인원 파싱 실패: {recruitment_text}, 오류: {e}")
        
        # 남은 기간 추출
        remaining_days = None
        remaining_elem = link.select_one('span.text-purple-600.font-semibold')
        if remaining_elem:
            remaining_text = remaining_elem.text.strip()
            remaining_days = parse_remaining_days(remaining_text)
        
        if title and href:
            return {
                'title': title,
                'detail_url': full_link,
                'applicant_count': applicants,
                'recruit_count': recruitments,
                'remaining_days': remaining_days,
                'source_site': 'popomon',
                'page_flag': 'main',
                'campaign_type': campaign_type,
                'competition_rate': competition_rate
            }
        
        return None
        
    except Exception as e:
        print(f"❌ 캠페인 정보 추출 중 오류: {e}")
        return None

def extract_and_process_campaigns_test(html_content, campaign_type, max_campaigns=3):
    """HTML 내용에서 캠페인 정보 추출 (테스트용 - 최대 3개)"""
    soup = BeautifulSoup(html_content, 'html.parser')
    campaign_links = soup.select('a[href^="/next/campaign/"]')
    
    print(f"🔍 {campaign_type} 카테고리에서 {len(campaign_links)}개 링크 발견")
    
    campaigns = []
    processed_count = 0
    
    for idx, link in enumerate(campaign_links, start=1):
        if processed_count >= max_campaigns:
            break
            
        campaign_data = extract_campaign_info(link, campaign_type)
        
        if campaign_data:
            campaigns.append(campaign_data)
            processed_count += 1
            
            # 결과 출력
            print(f"[{processed_count}] 📝 {campaign_data['title'][:50]}...")
            print(f"    🔗 URL: {campaign_data['detail_url']}")
            print(f"    👥 지원자/모집: {campaign_data['applicant_count']}/{campaign_data['recruit_count']}")
            print(f"    📊 경쟁률: {campaign_data['competition_rate']}")
            print(f"    ⏰ 남은 일수: {campaign_data['remaining_days']}일")
            
            # 처리 방식 결정
            remaining_days = campaign_data.get('remaining_days')
            if remaining_days is None:
                print(f"    📋 처리 방식: Detail Queue (남은 기간 불명)")
            elif remaining_days < 7:
                print(f"    📋 처리 방식: RDS Queue (마감 임박)")
            else:
                print(f"    📋 처리 방식: Detail Queue (여유 있음)")
            print()
        else:
            print(f"[{idx}] ❌ 캠페인 정보 추출 실패")
    
    print(f"✅ {campaign_type} 카테고리에서 총 {len(campaigns)}개 캠페인 추출 완료")
    return campaigns

def crawl_target_test(driver, url, campaign_type):
    """단일 URL 크롤링 테스트"""
    try:
        print(f"\n📄 URL 로드 중: {url}")
        driver.get(url)
        
        # 페이지 로드 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/next/campaign/']"))
        )
        print("✅ 페이지 로드 완료")
        
        # 페이지 끝까지 스크롤 (제한적)
        scroll_to_bottom(driver)
        
        time.sleep(1)
        
        # 현재 페이지 소스 가져오기
        page_source = driver.page_source
        
        # 캠페인 추출 (최대 3개)
        campaigns = extract_and_process_campaigns_test(page_source, campaign_type, max_campaigns=3)
        
        return campaigns
        
    except Exception as e:
        print(f"❌ 크롤링 중 오류 발생: {e}")
        return []

def run_popomon_test():
    """포포몬 전체 타겟들 테스트 (각 타입마다 3개씩)"""
    print("🚀 포포몬 메인 크롤링 테스트 시작")
    print("="*80)
    
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
    
    # 드라이버 설정
    driver = setup_driver()
    if not driver:
        print("❌ 드라이버 설정 실패")
        return
    
    print("✅ Chrome 드라이버 설정 완료")
    
    all_campaigns = []
    
    try:
        for idx, target in enumerate(targets, 1):
            print(f"\n[{idx}/3] {target['type']} 캠페인 크롤링 시작")
            print("-" * 60)
            
            campaigns = crawl_target_test(driver, target["url"], target["type"])
            all_campaigns.extend(campaigns)
            
            print(f"📊 {target['type']} 완료: {len(campaigns)}개 추출")
            
            # 다음 타겟 전 딜레이
            if idx < len(targets):
                print("⏳ 3초 대기 중...")
                time.sleep(3)
        
        # 최종 결과 요약
        print(f"\n{'='*80}")
        print(f"🎉 포포몬 크롤링 테스트 완료!")
        print(f"📊 총 추출된 캠페인: {len(all_campaigns)}개")
        
        # 타입별 통계
        type_stats = {}
        detail_queue_count = 0
        rds_queue_count = 0
        
        for campaign in all_campaigns:
            campaign_type = campaign['campaign_type']
            type_stats[campaign_type] = type_stats.get(campaign_type, 0) + 1
            
            remaining_days = campaign.get('remaining_days')
            if remaining_days is None or remaining_days >= 7:
                detail_queue_count += 1
            else:
                rds_queue_count += 1
        
        print(f"📈 타입별 통계:")
        for campaign_type, count in type_stats.items():
            print(f"   - {campaign_type}: {count}개")
        
        print(f"📋 처리 방식 통계:")
        print(f"   - Detail Queue: {detail_queue_count}개")
        print(f"   - RDS Queue: {rds_queue_count}개")
        print(f"{'='*80}")
        
        return all_campaigns
        
    except Exception as e:
        print(f"❌ 테스트 실행 중 오류: {e}")
        return []
    finally:
        driver.quit()
        print("🔄 드라이버 종료 완료")

def test_single_category(category_type, url):
    """개별 카테고리 테스트"""
    print(f"🔍 '{category_type}' 개별 테스트 시작")
    
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
    all_results = run_popomon_test()
    
    # 또는 개별 카테고리 테스트
    # result = test_single_category("방문", "https://popomon.com/next/campaign?searchAlign=latest&bigRecruitType=Lvisiting&recruitType=visiting&interestsFilter=ALL&pageNum=0")
