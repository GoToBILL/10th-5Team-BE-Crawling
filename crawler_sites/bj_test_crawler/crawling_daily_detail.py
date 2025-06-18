import requests
from bs4 import BeautifulSoup
import re
import time

def get_page_content_with_requests(url):
    """requests를 사용하여 페이지 콘텐츠 가져오기"""
    try:
        print(f"페이지 로드 중: {url}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        return response.text
        
    except Exception as e:
        print(f"페이지 가져오기 실패: {e}")
        return None

def parse_date_range(date_text):
    """날짜 범위 텍스트를 시작일과 종료일로 분리"""
    if not date_text:
        return None, None
    
    # "06.17 ~ 06.30" 형태 파싱
    date_match = re.search(r'(\d{2}\.\d{2})\s*~\s*(\d{2}\.\d{2})', date_text)
    if date_match:
        start_date = date_match.group(1)
        end_date = date_match.group(2)
        
        # 연도 추가 (현재 연도 기준)
        current_year = "25"  # 2025년 기준
        start_date = f"{current_year}.{start_date}"
        end_date = f"{current_year}.{end_date}"
        
        return start_date, end_date
    
    return None, None

def extract_campaign_details(html_content):
    """HTML에서 캠페인 상세 정보 추출 (포포몬 스타일 변수명)"""
    if not html_content:
        return {}
    
    soup = BeautifulSoup(html_content, 'html.parser')
    campaign_details = {}

    try:
        # 아이템 정보 영역 찾기
        item_info = soup.select_one('.item_info')
        if not item_info:
            print("⚠️ item_info 영역을 찾을 수 없습니다")
            return campaign_details

        # 리뷰 일정 정보 추출
        review_wrap = item_info.select_one('.review_wrap')
        if review_wrap:
            print("📅 리뷰 일정 정보 추출 중...")
            for box in review_wrap.select('.box01'):
                label_elem = box.select_one('em')
                if not label_elem:
                    continue
                
                label = label_elem.text.strip()
                value = box.get_text().replace(label, '').strip()
                
                print(f"   - 라벨: {label}, 값: {value}")
                
                # 리뷰어 신청 기간 -> apply_startdate, apply_enddate
                if '리뷰어 신청' in label:
                    start_date, end_date = parse_date_range(value)
                    if start_date and end_date:
                        campaign_details['apply_startdate'] = start_date
                        campaign_details['apply_enddate'] = end_date
                        print(f"   ✅ 신청 기간: {start_date} ~ {end_date}")
                
                # 리뷰등록 기간 -> review_deadline (종료일만)
                elif '리뷰등록' in label:
                    start_date, end_date = parse_date_range(value)
                    if end_date:
                        campaign_details['review_deadline'] = end_date
                        print(f"   ✅ 리뷰 마감일: {end_date}")
        
        # 제공 내역 추출 -> benefit
        provision_elem = item_info.select_one('.etc_list2 .etc2')
        if provision_elem:
            benefit_text = provision_elem.get_text().strip().replace('\n', ' ')
            campaign_details['benefit'] = benefit_text
            print(f"🎁 혜택: {benefit_text}")
        
        # 추출 결과 요약
        if campaign_details:
            print("✅ 데일리뷰 상세 정보 추출 완료:")
            for key, value in campaign_details.items():
                print(f"   - {key}: {value}")
        else:
            print("⚠️ 데일리뷰 상세 정보 추출 실패")
        
    except Exception as e:
        print(f"❌ 상세 정보 추출 중 오류: {e}")
    
    return campaign_details

def test_detail_crawling(campaign_data):
    """단일 캠페인 세부 정보 처리 테스트"""
    try:
        title = campaign_data.get('title', 'Unknown')
        detail_url = campaign_data.get('detail_url', '')
        
        print(f"\n{'='*80}")
        print(f"🔍 데일리뷰 상세 크롤링 테스트: {title}")
        print(f"🔗 URL: {detail_url}")
        print(f"{'='*80}")
        
        if not detail_url:
            print("❌ URL이 없는 캠페인입니다")
            return None
        
        # 세부 페이지 크롤링
        detail_html = get_page_content_with_requests(detail_url)
        if not detail_html:
            print("❌ 페이지 로드 실패")
            return None
        
        print("✅ 페이지 로드 성공")
        
        # 상세 정보 추출
        details = extract_campaign_details(detail_html)
        
        # 기존 데이터와 병합
        final_data = {**campaign_data, **details}
        final_data['page_flag'] = 'detail'
        
        print(f"\n📋 최종 데이터:")
        print(f"   - 제목: {final_data.get('title', 'N/A')}")
        print(f"   - 신청 시작일: {final_data.get('apply_startdate', 'N/A')}")
        print(f"   - 신청 종료일: {final_data.get('apply_enddate', 'N/A')}")
        print(f"   - 리뷰 마감일: {final_data.get('review_deadline', 'N/A')}")
        print(f"   - 혜택: {final_data.get('benefit', 'N/A')[:100]}...")
        print(f"   - 페이지 플래그: {final_data.get('page_flag', 'N/A')}")
        
        return final_data
        
    except Exception as e:
        print(f"❌ 캠페인 처리 중 오류: {e}")
        return None

def get_sample_campaigns():
    """테스트용 샘플 캠페인 데이터 생성"""
    # 실제 데일리뷰 URL들 (테스트용)
    sample_campaigns = [
        {
            'title': '[서울 강남] 테스트 캠페인 1',
            'detail_url': 'https://www.dailyview.kr/item.php?it_id=1750227002&category_id=001',
            'source_site': 'dailyview',
            'page_flag': 'main',
            'campaign_type': '지역'
        }
    ]
    return sample_campaigns

def run_detail_test():
    """상세 크롤링 테스트 실행"""
    print("🚀 데일리뷰 상세 크롤링 테스트 시작")
    print("="*80)
    
    # 샘플 캠페인 데이터 가져오기
    sample_campaigns = get_sample_campaigns()
    
    successful_tests = 0
    total_tests = len(sample_campaigns)
    
    for idx, campaign in enumerate(sample_campaigns, 1):
        print(f"\n[{idx}/{total_tests}] 테스트 진행 중...")
        
        result = test_detail_crawling(campaign)
        
        if result:
            successful_tests += 1
            print("✅ 테스트 성공")
        else:
            print("❌ 테스트 실패")
        
        # 다음 테스트 전 딜레이
        if idx < total_tests:
            print("⏳ 2초 대기 중...")
            time.sleep(2)
    
    print(f"\n{'='*80}")
    print(f"🎉 테스트 완료!")
    print(f"📊 성공률: {successful_tests}/{total_tests} ({successful_tests/total_tests*100:.1f}%)")
    print(f"{'='*80}")

# 개별 테스트 함수
def test_single_campaign(title, url):
    """단일 캠페인 테스트"""
    campaign_data = {
        'title': title,
        'detail_url': url,
        'source_site': 'dailyview',
        'page_flag': 'main',
        'campaign_type': '테스트'
    }
    
    return test_detail_crawling(campaign_data)

# 테스트 실행
if __name__ == "__main__":
    # 전체 테스트 실행ㄴ
    run_detail_test()
    
    # 또는 개별 테스트
    # test_single_campaign("테스트 캠페인", "https://www.dailyview.kr/item.php?it_id=실제ID")
