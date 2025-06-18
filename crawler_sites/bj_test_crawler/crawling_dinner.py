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
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        print(f"❌ Chrome 드라이버 설정 실패: {e}")
        return None

def scroll_to_bottom(driver, max_scrolls=3):
    """페이지 스크롤 (테스트용 제한)"""
    print("📜 페이지 스크롤 중...")
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
    
    print("✅ 스크롤 완료")

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
    
    return None

def extract_first_campaign(html_content, campaign_type):
    """HTML에서 첫 번째 캠페인만 추출"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 첫 번째 캠페인 링크만 선택
    link = soup.select_one("a.qz-dq-card__link[href*='/taste/']")
    
    if not link:
        print(f"❌ {campaign_type} 캠페인을 찾을 수 없습니다")
        return None
    
    try:
        href = link.get('href')
        if not href:
            return None
        
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
                title = f"캠페인_1"
        
        # 대괄호 안의 지역 정보 추출 및 제목 분리
        address = None
        if title:
            region_match = re.search(r'\[(.*?)\]', title)
            if region_match:
                address = region_match.group(1).strip()
                title = re.sub(r'\[.*?\]\s*', '', title).strip()
        
        # 신청인원/모집인원 추출
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
                        print(f"⚠️ 신청/모집 인원 파싱 실패: {text}")
            if applicants and recruitments:
                break
            card_parent = card_parent.parent
        
        # 경쟁률 계산
        if applicants is not None and recruitments is not None and recruitments > 0:
            competition_rate = round(applicants / recruitments, 2)
        
        # 남은 기간 추출
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
        
        # 결과 출력
        print(f"\n📝 [{campaign_type}] 캠페인 추출 결과:")
        print(f"   제목: {title}")
        print(f"   URL: {full_link}")
        print(f"   지원자/모집: {applicants}/{recruitments}")
        print(f"   경쟁률: {competition_rate}")
        print(f"   남은 일수: {remaining_days}일")
        
        # 처리 방식 결정 (시뮬레이션)
        if remaining_days is None:
            processing_type = "Detail Queue (남은 기간 불명)"
        elif remaining_days < 7:
            processing_type = "RDS Queue (마감 임박)"
        else:
            processing_type = "Detail Queue (여유 있음)"
        
        print(f"   📋 처리 방식: {processing_type}")
        
        return {
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
        
    except Exception as e:
        print(f"❌ {campaign_type} 캠페인 정보 추출 실패: {e}")
        return None

def test_single_type(driver, target):
    """단일 타입 테스트"""
    try:
        print(f"\n{'='*60}")
        print(f"🔍 {target['type']} 캠페인 테스트 시작")
        print(f"🔗 URL: {target['url']}")
        print(f"{'='*60}")
        
        # 페이지 로드
        print("📄 페이지 로드 중...")
        driver.get(target['url'])
        time.sleep(2)
        
        # 페이지 로드 대기
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a.qz-dq-card__link"))
            )
            print("✅ 페이지 로드 완료")
        except:
            print("⚠️ 페이지 로드 실패")
            return None
        
        # 페이지 스크롤 (제한적)
        scroll_to_bottom(driver, max_scrolls=3)
        
        # 페이지 소스 가져오기
        page_source = driver.page_source
        
        # 첫 번째 캠페인만 추출
        campaign = extract_first_campaign(page_source, target['type'])
        
        if campaign:
            print(f"✅ {target['type']} 캠페인 추출 성공")
            return campaign
        else:
            print(f"❌ {target['type']} 캠페인 추출 실패")
            return None
            
    except Exception as e:
        print(f"❌ {target['type']} 처리 중 오류: {e}")
        return None

def run_dinnerqueen_test():
    """디너의여왕 테스트 실행 (각 타입별 1개씩)"""
    print("🚀 디너의여왕 메인 크롤링 테스트 시작")
    print("📋 각 타입별로 1개씩만 추출합니다")
    
    targets = [
        {
            "type": "지역",
            "url": "https://dinnerqueen.net/taste?ct=%EC%A7%80%EC%97%AD"
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
    
    # 드라이버 설정
    driver = setup_driver()
    if not driver:
        print("❌ 드라이버 설정 실패")
        return
    
    print("✅ Chrome 드라이버 설정 완료")
    
    results = []
    
    try:
        for idx, target in enumerate(targets, 1):
            print(f"\n[{idx}/3] {target['type']} 처리 중...")
            
            campaign = test_single_type(driver, target)
            if campaign:
                results.append(campaign)
            
            # 다음 타입 전 딜레이
            if idx < len(targets):
                print("⏳ 2초 대기 중...")
                time.sleep(2)
        
        # 최종 결과 요약
        print(f"\n{'='*80}")
        print(f"🎉 디너의여왕 크롤링 테스트 완료!")
        print(f"📊 총 추출된 캠페인: {len(results)}개")
        
        # 타입별 결과
        print(f"\n📈 타입별 결과:")
        for result in results:
            campaign_type = result['campaign_type']
            title = result['title'][:30] + "..." if len(result['title']) > 30 else result['title']
            address = result.get('address', 'N/A')
            print(f"   ✅ {campaign_type}: {title} ({address})")
        
        # 처리 방식 통계
        detail_count = sum(1 for r in results if r['remaining_days'] is None or r['remaining_days'] >= 7)
        rds_count = len(results) - detail_count
        
        print(f"\n📋 처리 방식 통계:")
        print(f"   - Detail Queue: {detail_count}개")
        print(f"   - RDS Queue: {rds_count}개")
        print(f"{'='*80}")
        
        return results
        
    except Exception as e:
        print(f"❌ 테스트 실행 중 오류: {e}")
        return []
    finally:
        driver.quit()
        print("🔄 드라이버 종료 완료")

def test_individual_type(type_name, url):
    """개별 타입 테스트"""
    print(f"🔍 '{type_name}' 개별 테스트 시작")
    
    driver = setup_driver()
    if not driver:
        return None
    
    try:
        target = {"type": type_name, "url": url}
        result = test_single_type(driver, target)
        return result
    finally:
        driver.quit()

# 테스트 실행
if __name__ == "__main__":
    # 전체 테스트 실행 (각 타입별 1개씩)
    all_results = run_dinnerqueen_test()
    
    # 또는 개별 타입 테스트
    # result = test_individual_type("전체", "https://dinnerqueen.net/taste?ct=%EC%A0%84%EC%B2%B4")
