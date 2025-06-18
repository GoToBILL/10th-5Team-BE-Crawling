from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import re

def get_page_content_with_selenium(url):
    """
    Selenium을 사용하여 JavaScript가 로드된 페이지 콘텐츠를 가져오는 함수
    """
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    # 사용자 에이전트 설정
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36')
    
    driver = webdriver.Chrome(options=options)
    
    try:
        print(f"페이지 로드 중: {url}")
        driver.get(url)
        
        time.sleep(2.0)
        
        # cmp_info 클래스만 대기
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CLASS_NAME, "cmp_info"))
        )
        print("cmp_info 요소 로드 완료")
        
        html_content = driver.page_source
        return html_content
    except Exception as e:
        print(f"페이지 가져오기 실패: {e}")
        return None
    finally:
        driver.quit()

def extract_campaign_details(html_content):
    """강남맛집 사이트에 맞춘 캠페인 상세 정보 추출"""
    if not html_content:
        return {}
    
    soup = BeautifulSoup(html_content, 'html.parser')
    campaign_details = {}

    try:
        # 강남맛집 사이트 구조 처리 (cmp_info 클래스)
        cmp_info = soup.find('div', class_='cmp_info')
        if cmp_info:
            print("cmp_info 처리")
            for li in cmp_info.find_all('li'):
                dt_tag = li.find('dt')
                dd_tag = li.find('dd')
                if dt_tag and dd_tag:
                    field_name = dt_tag.text.strip()
                    field_value = dd_tag.text.strip()
                    
                    print(f"필드 발견: {field_name} = {field_value}")

                    if '캠페인 신청기간' in field_name:
                        # "06.18 ~ 06.24" 형식 처리
                        period_match = re.search(r'(\d{2}\.\d{2})\s*~\s*(\d{2}\.\d{2})', field_value)
                        if period_match:
                            campaign_details['application_startdate'] = f"25.{period_match.group(1)}"
                            campaign_details['application_enddate'] = f"25.{period_match.group(2)}"
                    elif '리뷰 등록기간' in field_name:
                        period_match = re.search(r'(\d{2}\.\d{2})\s*~\s*(\d{2}\.\d{2})', field_value)
                        if period_match:
                            campaign_details['review_startdate'] = f"25.{period_match.group(1)}"
                            campaign_details['review_enddate'] = f"25.{period_match.group(2)}"
                    elif '리뷰어 발표' in field_name:
                        if re.search(r'\d{2}\.\d{2}', field_value):
                            campaign_details['announcement_date'] = f"25.{field_value.strip()}"
                    elif '캠페인 결과발표' in field_name:
                        if re.search(r'\d{2}\.\d{2}', field_value):
                            campaign_details['result_date'] = f"25.{field_value.strip()}"
        else:
            print("cmp_info 클래스를 찾을 수 없습니다")

        # 주소 정보 추출 - 개선된 패턴 매칭
        print("주소 정보 검색 중...")
        address_found = False
        
        # 한국 주소 패턴 정규식 (더 정확한 패턴)
        address_regex = re.compile(r'([가-힣]+시\s*[가-힣]+(구|군)?\s*[가-힣0-9]+(동|읍|면)?\s*\d+[\-\d]*(?:\s*\d+층)?)')
        
        for tag in soup.find_all(['span', 'div', 'p', 'li']):
            text = tag.get_text(strip=True)
            if not text or len(text) < 7 or len(text) > 100:
                continue
            
            match = address_regex.search(text)
            if match:
                address = match.group(1).strip()
                campaign_details['address'] = address
                address_found = True
                print(f"주소 발견: {address}")
                break
    
        
        if not address_found:
            campaign_details['address'] = None
            print("주소 정보를 찾을 수 없습니다")

    except Exception as e:
        print(f"상세 정보 추출 중 오류: {e}")
    
    return campaign_details

def test_gangnam_restaurant_crawling():
    """강남맛집 단일 URL 크롤링 테스트"""
    test_url = "https://xn--939au0g4vj8sq.net/cp/?id=1803954"
    
    print("=== 강남맛집 크롤링 테스트 시작 ===")
    print(f"테스트 URL: {test_url}")
    print()
    
    start_time = time.time()
    
    # 페이지 로드
    html_content = get_page_content_with_selenium(test_url)
    
    if html_content:
        print("페이지 로드 성공!")
        print()
        
        # 상세 정보 추출
        details = extract_campaign_details(html_content)
        
        print()
        print("=== 추출된 정보 ===")
        if details:
            for key, value in details.items():
                print(f"{key}: {value}")
        else:
            print("추출된 정보가 없습니다.")
            
    else:
        print("페이지 로드 실패!")
    
    total_time = time.time() - start_time
    print(f"\n총 소요 시간: {total_time:.2f}초")
    print("=== 테스트 완료 ===")

if __name__ == "__main__":
    test_gangnam_restaurant_crawling()
