from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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
        print(f"   📊 신청 정보: {app_text}")
        
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
        print("   ⚠️ 신청 정보 요소를 찾을 수 없습니다")
    
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

        # SNS 타입 추출
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
        print(f"❌ 캠페인 정보 파싱 중 오류: {e}")
        return None

    return data

def crawl_target(driver, campaign_type):
    """특정 카테고리의 캠페인들 크롤링 (테스트용 - 첫 번째만)"""
    success_count = 0
    error_count = 0
    
    try:
        print(f"🔍 {campaign_type} 캠페인 크롤링 시작...")
        
        # 캠페인 카드 찾기
        card_selectors = [
            'a.NewFlexibleCard__StyledCard-sc-1eu57ly-0',
            'a.FlexibleCard__StyledCard-sc-1dw1ej1-0',
            '[class*="StyledCard"]',
            'a[href*="/campaign/"]'
        ]
        
        cards = []
        for selector in card_selectors:
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                cards = driver.find_elements(By.CSS_SELECTOR, selector)
                if cards:
                    print(f"✅ {len(cards)}개의 캠페인 카드 발견")
                    break
            except TimeoutException:
                continue
        
        if not cards:
            print(f"❌ {campaign_type} 카테고리에서 캠페인 카드를 찾을 수 없습니다")
            return 0, 1
        
        # 테스트용으로 첫 번째 카드만 처리
        card = cards[0]
        campaign_info = parse_campaign_info(card, campaign_type)
        
        if campaign_info:
            success_count = 1
            print(f"✅ 캠페인 추출 성공:")
            print(f"   📝 제목: {campaign_info['title'][:50]}")
            print(f"지역 : {campaign_info['address']}")
            print(f"   🔗 URL: {campaign_info['detail_url']}")
            print(f"   📍 타입: {campaign_info['campaign_type']}")
            print(f"   📱 SNS: {campaign_info['sns_type']}")
            print(f"   👥 지원자/모집: {campaign_info['applicant_count']}/{campaign_info['recruit_count']}")
            print(f"   📊 경쟁률: {campaign_info['competition_rate']}")
            print(f"   ⏰ 남은 일수: {campaign_info['remaining_days']}일")
        else:
            error_count = 1
            print(f"❌ 캠페인 정보 추출 실패")
        
    except Exception as e:
        print(f"❌ {campaign_type} 크롤링 중 오류: {e}")
        error_count = 1
    
    return success_count, error_count

def run_chvu_test(driver):
    """CHVU 메인 크롤링 테스트 함수 (원본 로직과 동일)"""
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
            
            print(f"\n[{idx+1}/3] {label} 카테고리 처리 중...")
            print("-" * 60)
            
            # 리프레시 로직 (원본과 동일)
            if idx == 0:
                driver.get("https://chvu.co.kr/campaign")
                print(f"✅ 첫 페이지 로드: {label}")
            else:
                driver.refresh()
                print(f"🔄 페이지 리프레시 후 {label} 선택자 클릭 시도")
            
            time.sleep(3)
            
            # 카테고리 버튼 클릭 (원본과 동일)
            print(f"🔍 선택자 클릭 시도: {label}")
            buttons = driver.find_elements(By.CSS_SELECTOR, "div.CategorySelector__SelectorCategory-sc-vn201x-0")
            
            clicked = False
            for btn in buttons:
                if label in btn.text:
                    btn.click()
                    time.sleep(2)
                    clicked = True
                    print(f"✅ {label} 버튼 클릭 완료")
                    break
            
            if not clicked:
                print(f"⚠️ {label} 버튼을 찾을 수 없습니다")
                total_err += 1
                continue

            # 크롤링 실행 (현재 카테고리 전달)
            print(f"🚀 크롤링 시작: {label} 캠페인")
            cnt, err = crawl_target(driver, campaign_type)
            print(f"📊 완료: {cnt}개 / 실패: {err}개")
            total_suc += cnt
            total_err += err
            
        except Exception as e:
            print(f"❌ 선택자 클릭 실패: {label} / 오류: {e}")
            total_err += 1

    print(f"\n{'='*80}")
    print(f"🎉 CHVU 크롤링 완료!")
    print(f"📊 총 성공: {total_suc}개, 실패: {total_err}개")
    print(f"📈 성공률: {total_suc/(total_suc+total_err)*100:.1f}%" if (total_suc+total_err) > 0 else "성공률: 0%")
    print(f"{'='*80}")
    
    return total_suc, total_err

def test_chvu_main_crawling():
    """체험뷰 메인 크롤링 전체 테스트"""
    print("🚀 체험뷰 메인 크롤링 테스트 시작")
    print("="*80)
    
    # 드라이버 설정
    driver = setup_driver()
    if not driver:
        print("❌ 드라이버 설정 실패")
        return
    
    print("✅ Chrome 드라이버 설정 완료")
    
    try:
        # 메인 크롤링 실행
        success_count, error_count = run_chvu_test(driver)
        
        # 최종 결과
        total_attempts = success_count + error_count
        if total_attempts > 0:
            success_rate = (success_count / total_attempts) * 100
            print(f"\n🎯 최종 테스트 결과:")
            print(f"   ✅ 성공: {success_count}개")
            print(f"   ❌ 실패: {error_count}개")
            print(f"   📊 성공률: {success_rate:.1f}%")
        else:
            print("\n⚠️ 처리된 캠페인이 없습니다")
            
    except Exception as e:
        print(f"❌ 테스트 실행 중 오류: {e}")
    finally:
        driver.quit()
        print("🔄 드라이버 종료 완료")

# 개별 카테고리 테스트 함수
def test_single_category(category_label):
    """개별 카테고리만 테스트"""
    print(f"🔍 '{category_label}' 개별 테스트 시작")
    
    driver = setup_driver()
    if not driver:
        return
    
    try:
        driver.get("https://chvu.co.kr/campaign")
        time.sleep(3)
        
        # 카테고리 버튼 클릭
        buttons = driver.find_elements(By.CSS_SELECTOR, "div.CategorySelector__SelectorCategory-sc-vn201x-0")
        
        clicked = False
        for btn in buttons:
            if category_label in btn.text:
                btn.click()
                time.sleep(2)
                clicked = True
                print(f"✅ {category_label} 버튼 클릭 완료")
                break
        
        if clicked:
            success, error = crawl_target(driver, category_label)
            print(f"📊 결과: 성공 {success}개, 실패 {error}개")
        else:
            print(f"❌ {category_label} 버튼을 찾을 수 없습니다")
            
    finally:
        driver.quit()

# 테스트 실행
if __name__ == "__main__":
    # 전체 테스트 실행 (원본 로직과 동일)
    test_chvu_main_crawling()
    
    # 또는 개별 카테고리 테스트
    # test_single_category("방문형")
    # test_single_category("배송형")
    # test_single_category("기자단")
