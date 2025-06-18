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

def get_page_content_with_selenium(driver, url):
    """Selenium을 사용하여 JavaScript가 로드된 페이지 콘텐츠 가져오기"""
    try:
        print(f"📄 페이지 로드 중: {url}")
        driver.get(url)
        
        time.sleep(1.2)
        
        # 캠페인 정보가 로드될 때까지 대기
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[class*="CampaignMain__ImformationBlock"]'))
            )
            print("✅ CampaignMain__ImformationBlock 요소 발견")
        except:
            print("⚠️ CampaignMain__ImformationBlock 요소를 찾을 수 없습니다. 페이지 전체 소스를 반환합니다.")
        
        html_content = driver.page_source
        print("✅ 페이지 소스 추출 완료")
        return html_content
        
    except Exception as e:
        print(f"❌ 페이지 가져오기 실패: {e}")
        return None

def extract_campaign_details(html_content):
    """HTML에서 캠페인 상세 정보 추출"""
    if not html_content:
        return {}
    
    soup = BeautifulSoup(html_content, 'html.parser')
    campaign_details = {}

    try:
        print("🔍 캠페인 상세 정보 추출 시작...")
        
        # 1. 모집시작일, 모집마감일, 리뷰마감일 추출
        info_block = soup.find('div', class_=lambda x: x and 'CampaignMain__ImformationBlock' in x)
        if info_block:
            print("📅 정보 블록 발견 - 날짜 정보 추출 중...")
            info_divs = info_block.find_all('div', class_=lambda x: x and 'CampaignMain__Imformation' in x)
            
            for idx, div in enumerate(info_divs):
                text = div.text.strip()
                print(f"   [{idx+1}] 정보 div 텍스트: {text}")
                
                # 모집시작일 추출
                start_match = re.search(r'모집시작일\s*(\d{2}\.\d{2}\.\d{2})', text)
                if start_match:
                    campaign_details['apply_startdate'] = start_match.group(1)
                    print(f"   ✅ 모집시작일: {start_match.group(1)}")
                
                # 모집마감일 추출
                end_match = re.search(r'모집마감일\s*(\d{2}\.\d{2}\.\d{2})', text)
                if end_match:
                    campaign_details['apply_enddate'] = end_match.group(1)
                    print(f"   ✅ 모집마감일: {end_match.group(1)}")
                
                # 리뷰마감일 추출
                review_match = re.search(r'리뷰마감일\s*(\d{2}\.\d{2}\.\d{2})', text)
                if review_match:
                    campaign_details['content_submission_end'] = review_match.group(1)
                    print(f"   ✅ 리뷰마감일: {review_match.group(1)}")
        else:
            print("⚠️ CampaignMain__ImformationBlock을 찾을 수 없습니다")
        
        # 2. 혜택(benefit) 추출
        desc_div = soup.find('div', class_=lambda x: x and 'CampaignMain__Desc' in x)
        if desc_div:
            print("🎁 혜택 정보 추출 중...")
            # 제공포인트 부분 제거하고 혜택만 추출
            reward_point_div = desc_div.find('div', class_=lambda x: x and 'CampaignMain__RewardPoint' in x)
            if reward_point_div:
                reward_point_div.extract()  # 제거
                print("   - 제공포인트 부분 제거됨")
            
            # 남은 텍스트가 혜택
            benefit_text = desc_div.get_text(strip=True)
            if benefit_text:
                campaign_details['benefit'] = benefit_text
                print(f"   ✅ 혜택: {benefit_text[:100]}...")
        else:
            print("⚠️ CampaignMain__Desc를 찾을 수 없습니다")
        
        # 추출 결과 요약
        if campaign_details:
            print("✅ CHVU 상세 정보 추출 완료:")
            for key, value in campaign_details.items():
                print(f"   - {key}: {value}")
        else:
            print("⚠️ CHVU 상세 정보 추출 실패")
        
    except Exception as e:
        print(f"❌ 상세 정보 추출 중 오류: {e}")
    
    return campaign_details

def test_chvu_detail_crawling(campaign_data):
    """체험뷰 캠페인 세부 정보 처리 테스트"""
    driver = None
    try:
        title = campaign_data.get('title', 'Unknown')
        detail_url = campaign_data.get('detail_url', '')
        
        print(f"\n{'='*80}")
        print(f"🔍 체험뷰(CHVU) 상세 크롤링 테스트")
        print(f"📝 제목: {title}")
        print(f"🔗 URL: {detail_url}")
        print(f"{'='*80}")
        
        if not detail_url:
            print("❌ URL이 없는 캠페인입니다")
            return None
        
        # 드라이버 설정
        driver = setup_driver()
        if not driver:
            print("❌ 드라이버 설정 실패")
            return None
        
        print("✅ Chrome 드라이버 설정 완료")
        
        # 세부 페이지 크롤링
        detail_html = get_page_content_with_selenium(driver, detail_url)
        if not detail_html:
            print("❌ 페이지 로드 실패")
            return None
        
        # 상세 정보 추출
        details = extract_campaign_details(detail_html)
        
        # 기존 데이터와 병합
        final_data = {**campaign_data, **details}
        final_data['page_flag'] = 'detail'
        
        print(f"\n📋 최종 추출 데이터:")
        print(f"   - 제목: {final_data.get('title', 'N/A')}")
        print(f"   - 모집시작일: {final_data.get('apply_startdate', 'N/A')}")
        print(f"   - 모집마감일: {final_data.get('apply_enddate', 'N/A')}")
        print(f"   - 리뷰마감일: {final_data.get('content_submission_end', 'N/A')}")
        print(f"   - 혜택: {final_data.get('benefit', 'N/A')[:100]}...")
        print(f"   - 페이지 플래그: {final_data.get('page_flag', 'N/A')}")
        
        return final_data
        
    except Exception as e:
        print(f"❌ 캠페인 처리 중 오류: {e}")
        return None
    finally:
        if driver:
            driver.quit()
            print("🔄 드라이버 종료 완료")

def get_sample_chvu_campaigns():
    """테스트용 샘플 체험뷰 캠페인 데이터"""
    sample_campaigns = [
        {
            'title': '체험뷰 테스트 캠페인 1',
            'detail_url': 'https://chvu.co.kr/campaign/134487',
            'source_site': 'chvu',
            'page_flag': 'main',
            'campaign_type': '체험'
        }
    ]
    
    return sample_campaigns

def run_chvu_test():
    """체험뷰 상세 크롤링 테스트 실행"""
    print("🚀 체험뷰(CHVU) 상세 크롤링 테스트 시작")
    print("="*80)
    
    # 샘플 캠페인 데이터 가져오기
    sample_campaigns = get_sample_chvu_campaigns()
    
    successful_tests = 0
    total_tests = len(sample_campaigns)
    
    for idx, campaign in enumerate(sample_campaigns, 1):
        print(f"\n[{idx}/{total_tests}] 테스트 진행 중...")
        
        result = test_chvu_detail_crawling(campaign)
        
        if result and result.get('apply_startdate'):  # 최소한 하나의 날짜 정보가 있으면 성공
            successful_tests += 1
            print("✅ 테스트 성공")
        else:
            print("❌ 테스트 실패")
        
        # 다음 테스트 전 딜레이
        if idx < total_tests:
            print("⏳ 3초 대기 중...")
            time.sleep(3)
    
    print(f"\n{'='*80}")
    print(f"🎉 테스트 완료!")
    print(f"📊 성공률: {successful_tests}/{total_tests} ({successful_tests/total_tests*100:.1f}%)")
    print(f"{'='*80}")

def test_single_chvu_campaign(title, url):
    """단일 체험뷰 캠페인 테스트"""
    campaign_data = {
        'title': title,
        'detail_url': url,
        'source_site': 'chvu',
        'page_flag': 'main',
        'campaign_type': '체험'
    }
    
    return test_chvu_detail_crawling(campaign_data)

# 테스트 실행
if __name__ == "__main__":
    # 전체 테스트 실행
    run_chvu_test()
    
    # 또는 개별 테스트 (제공해주신 URL로)
    # test_single_chvu_campaign("체험뷰 테스트", "https://chvu.co.kr/campaign/134487")
