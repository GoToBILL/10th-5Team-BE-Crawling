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
        
        time.sleep(1.2)
        
        # 특정 요소(캠페인 정보)가 로드될 때까지 명시적으로 기다림
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "campInfo"))
            )
            print("campInfo 요소 로드 완료")
        except:
            print("campInfo 요소를 찾을 수 없습니다. 페이지 전체 소스를 반환합니다.")
        
        html_content = driver.page_source
        return html_content
    except Exception as e:
        print(f"페이지 가져오기 실패: {e}")
        return None
    finally:
        driver.quit()

def extract_campaign_details(html_content):
    """HTML에서 캠페인 상세 정보 추출"""
    if not html_content:
        return {}
    
    soup = BeautifulSoup(html_content, 'html.parser')
    campaign_details = {}

    try:
        # 캠페인 정보 섹션
        camp_info = soup.find(id='campInfo')
        if camp_info:
            # 모든 li 요소 확인
            for li in camp_info.find_all('li'):
                b_tag = li.find('b')
                span_tag = li.find('span')
                
                if b_tag:
                    field_name = b_tag.text.strip()
                    field_value = span_tag.text.strip() if span_tag else ""
                    
                    # 주요 필드 매핑 (영문 키로 통일)
                    if '협찬 상품' in field_name:
                        campaign_details['benefit'] = field_value
                    elif '모집 및 선정 기간' in field_name:
                        # 예: "25.05.29 ~ 25.06.28 (상시 선정)"
                        period_match = re.search(r'(\d{2}\.\d{2}\.\d{2})\s*~\s*(\d{2}\.\d{2}\.\d{2})', field_value)
                        if period_match:
                            campaign_details['apply_startdate'] = period_match.group(1)
                            campaign_details['apply_enddate'] = period_match.group(2)
                    elif '리뷰 제출 마감일' in field_name:
                        campaign_details['content_submission_end'] = field_value
        
        # 주소 정보 추출 - 두 번째 요소 선택
        address_spans = soup.find_all('span', class_='w-[calc(100%_-_20px)] flex flex-wrap')
        if len(address_spans) >= 2 and address_spans[1].text.strip():
            campaign_details['address'] = address_spans[1].text.strip()
        elif len(address_spans) >= 1 and address_spans[0].text.strip():
            # 두 번째가 없으면 첫 번째라도
            campaign_details['address'] = address_spans[0].text.strip()
        else:
            campaign_details['address'] = None

        
    except Exception as e:
        print(f"상세 정보 추출 중 오류: {e}")
    
    return campaign_details



def test_popomon_crawling():
    """포포몬 단일 URL 크롤링 테스트"""
    test_url = "https://popomon.com/next/campaign/103368"
    
    print("=== 포포몬 크롤링 테스트 시작 ===")
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
    

    print("=== 테스트 완료 ===")

if __name__ == "__main__":
    test_popomon_crawling()
