from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import re
import json

def get_page_content_with_selenium(driver, url):
    """페이지 로드"""
    try:
        print(f"📄 페이지 로드 중: {url}")
        driver.get(url)
        time.sleep(2)
        
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[class*="CampaignMain"]'))
            )
            print("✅ 페이지 로드 완료")
        except:
            print("⚠️ CampaignMain 요소 대기 실패, 전체 소스 사용")
        
        return driver.page_source
        
    except Exception as e:
        print(f"❌ 페이지 로드 실패: {e}")
        return None

def extract_campaign_details(html_content):
    """캠페인 상세 정보 추출 테스트"""
    if not html_content:
        return {}
    
    soup = BeautifulSoup(html_content, 'html.parser')
    campaign_details = {}
    
    print("\n🔍 상세 정보 추출 시작...")

    try:
        # 1. 날짜 정보 추출
        info_block = soup.find('div', class_=lambda x: x and 'CampaignMain__ImformationBlock' in x)
        if info_block:
            print("✅ ImformationBlock 발견")
            info_divs = info_block.find_all('div', class_=lambda x: x and 'CampaignMain__Imformation' in x)
            print(f"📋 정보 div 개수: {len(info_divs)}")
            
            for i, div in enumerate(info_divs):
                text = div.text.strip()
                print(f"   정보 #{i+1}: {text}")
                
                # 모집시작일
                start_match = re.search(r'모집시작일\s*(\d{2}\.\d{2}\.\d{2})', text)
                if start_match:
                    campaign_details['application_startdate'] = start_match.group(1)
                    print(f"   ✅ 모집시작일: {start_match.group(1)}")
                
                # 모집마감일
                end_match = re.search(r'모집마감일\s*(\d{2}\.\d{2}\.\d{2})', text)
                if end_match:
                    campaign_details['application_enddate'] = end_match.group(1)
                    print(f"   ✅ 모집마감일: {end_match.group(1)}")
                
                # 리뷰마감일
                review_match = re.search(r'리뷰마감일\s*(\d{2}\.\d{2}\.\d{2})', text)
                if review_match:
                    campaign_details['review_deadline'] = review_match.group(1)
                    print(f"   ✅ 리뷰마감일: {review_match.group(1)}")
        else:
            print("❌ ImformationBlock 찾을 수 없음")
        
        # 2. 혜택 정보 추출
        desc_div = soup.find('div', class_=lambda x: x and 'CampaignMain__Desc' in x)
        if desc_div:
            print("✅ Desc 블록 발견")
            
            # 제공포인트 부분 제거
            reward_point_div = desc_div.find('div', class_=lambda x: x and 'CampaignMain__RewardPoint' in x)
            if reward_point_div:
                print("   📍 RewardPoint 부분 제거")
                reward_point_div.extract()
            
            benefit_text = desc_div.get_text(strip=True)
            if benefit_text:
                campaign_details['benefit'] = benefit_text
                print(f"   ✅ 혜택: {benefit_text}")
        else:
            print("❌ Desc 블록 찾을 수 없음")
        
    except Exception as e:
        print(f"❌ 추출 중 오류: {e}")
    
    return campaign_details

def test_chvu_detail():
    """CHVU 디테일 추출 테스트"""
    service = Service(ChromeDriverManager().install())
    chrome_options = Options()
    chrome_options.add_argument('--window-size=1920,1080')
    
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        # 테스트할 URL (실제 CHVU 캠페인 URL 입력)
        test_urls = [
            "https://chvu.co.kr/campaign/135584",  # 예시 URL
            # 다른 테스트 URL들 추가 가능
        ]
        
        for i, url in enumerate(test_urls):
            print(f"\n{'='*60}")
            print(f"🧪 테스트 #{i+1}: {url}")
            print(f"{'='*60}")
            
            # 페이지 로드
            html_content = get_page_content_with_selenium(driver, url)
            
            if html_content:
                # 상세 정보 추출
                details = extract_campaign_details(html_content)
                
                # 결과 출력
                print(f"\n📊 추출 결과:")
                if details:
                    print("✅ 추출 성공!")
                    print(json.dumps(details, ensure_ascii=False, indent=2))
                    
                    # 필수 필드 체크
                    required_fields = ['application_startdate', 'application_enddate', 'review_deadline', 'benefit']
                    missing_fields = [field for field in required_fields if field not in details or not details[field]]
                    
                    if missing_fields:
                        print(f"⚠️ 누락된 필드: {missing_fields}")
                    else:
                        print("🎉 모든 필드 추출 완료!")
                else:
                    print("❌ 추출 실패 - 데이터 없음")
            else:
                print("❌ 페이지 로드 실패")
    
    finally:
        input("\n⏸️ 엔터를 누르면 종료...")
        driver.quit()

if __name__ == "__main__":
    test_chvu_detail()
