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
        
        # 페이지가 로드될 때까지 대기
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            print("페이지 로딩 완료")
        except:
            print("페이지 로딩 대기 실패, 계속 진행")
        
        html_content = driver.page_source
        return html_content
    except Exception as e:
        print(f"페이지 가져오기 실패: {e}")
        return None
    finally:
        driver.quit()

def extract_campaign_details(html_content):
    """디너의여왕 사이트에 맞춘 캠페인 상세 정보 추출"""
    if not html_content:
        return {}
    
    soup = BeautifulSoup(html_content, 'html.parser')
    campaign_details = {}

    try:
        # 날짜 컨테이너에서 순서대로 추출
        date_elems = soup.select('p.qz-body-kr--line')
        
        if len(date_elems) >= 3:
            print(f"날짜 요소 {len(date_elems)}개 발견")
            
            # 첫 번째: 신청기간 (25.06.11 – 25.06.17)
            first_text = date_elems[0].text.strip()
            print(f"첫 번째 날짜: {first_text}")
            if '–' in first_text:
                dates = first_text.split('–')
                if len(dates) == 2:
                    campaign_details['application_startdate'] = dates[0].strip()
                    campaign_details['application_enddate'] = dates[1].strip()
            
            # 두 번째: 발표일 (25.06.18)
            second_text = date_elems[1].text.strip()
            print(f"두 번째 날짜: {second_text}")
            campaign_details['reviewer_announcement'] = second_text
            
            # 세 번째: 체험&리뷰 (25.06.19 – 25.07.03)
            third_text = date_elems[2].text.strip()
            print(f"세 번째 날짜: {third_text}")
            if '–' in third_text:
                dates = third_text.split('–')
                if len(dates) == 2:
                    campaign_details['content_submission_start'] = dates[0].strip()
                    campaign_details['content_submission_end'] = dates[1].strip()
            else:
                campaign_details['content_submission_end'] = third_text

        # 주소 정보 추출 - "방문 위치"가 있는 경우에만 추출 (방문형)
        print("캠페인 유형 확인 중...")
        address_found = False
        
        # "방문 위치" 텍스트가 포함된 p 태그 찾기
        visit_location_found = False
        for p_tag in soup.find_all('p'):
            if '방문 위치' in p_tag.text:
                visit_location_found = True
                print("방문형 캠페인 감지 - 주소 추출 시작")
                
                # 주소 추출
                address_text = p_tag.get_text()
                if ':' in address_text:
                    address = address_text.split(':', 1)[1].strip()
                    if address:  # 빈 문자열이 아닌 경우에만
                        campaign_details['address'] = address
                        address_found = True
                        print(f"방문 위치 발견: {address}")
                break
        
        if not visit_location_found:
            print("배송형 캠페인 감지 - 주소 추출 생략")
            campaign_details['address'] = None
        elif visit_location_found and not address_found:
            print("방문형이지만 주소 추출 실패")
            campaign_details['address'] = None

    except Exception as e:
        print(f"상세 정보 추출 중 오류: {e}")
    
    return campaign_details


def test_dinnerqueen_crawling():
    """디너의여왕 단일 URL 크롤링 테스트"""
    test_url = "https://dinnerqueen.net/taste/868145"
    
    print("=== 디너의여왕 크롤링 테스트 시작 ===")
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
    test_dinnerqueen_crawling()
