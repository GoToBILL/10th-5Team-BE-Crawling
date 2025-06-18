import requests
from bs4 import BeautifulSoup
import re
import time

def get_page_content(category_id, page_number):
    """지정된 카테고리와 페이지의 내용을 가져오는 함수"""
    url = f"https://www.dailyview.kr/item_list.php?category_id={category_id}&sst=&sod=&page={page_number}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        print(f"페이지 요청: 카테고리 {category_id}, 페이지 {page_number}")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"페이지 {page_number} 가져오기 실패: {e}")
        return None

def parse_campaign_info(item, current_category):
    """캠페인 아이템에서 정보 추출"""
    data = {}
    
    try:
        # 기본 정보
        data['source_site'] = 'dailyview'
        data['page_flag'] = 'main'
        data['campaign_type'] = current_category

        # 링크 추출
        link = item.get('href')
        if link:
            data['detail_url'] = f"https://www.dailyview.kr/{link}"
        else:
            data['detail_url'] = None

        name_elem = item.select_one('.it_name')
        if name_elem:
            full_title = name_elem.text.strip()
            
            # 대괄호 안의 지역 정보 추출
            region_match = re.search(r'\[(.*?)\]', full_title)
            if region_match:
                data['address'] = region_match.group(1).strip()  # [경상 김해] -> 경상 김해
                # 제목에서 대괄호 부분 제거
                data['title'] = re.sub(r'\[.*?\]\s*', '', full_title).strip()
            else:
                data['address'] = None
                data['title'] = full_title
        else:
            data['title'] = "제목 없음"
            data['address'] = None

        # SNS 타입 추출
        sns_icon = item.select_one('.option_re i.blog')
        if sns_icon:
            data['sns_type'] = 'Blog'
        else:
            data['sns_type'] = None

        # 신청/모집 정보 추출
        option_re = item.select_one('.option_re')
        if option_re:
            peo_cnt = option_re.select_one('.peo_cnt')
            if peo_cnt:
                peo_text = peo_cnt.text
                
                # 신청 인원 추출
                applicant_match = re.search(r'신청\s*(\d+)\s*명', peo_text)
                if applicant_match:
                    data['applicant_count'] = int(applicant_match.group(1))
                else:
                    data['applicant_count'] = None
                
                # 모집 인원 추출
                recruit_match = re.search(r'모집\s*(\d+)\s*명', peo_text)
                if recruit_match:
                    data['recruit_count'] = int(recruit_match.group(1))
                else:
                    data['recruit_count'] = None
                
                # 경쟁률 계산
                if data['applicant_count'] is not None and data['recruit_count'] is not None and data['recruit_count'] > 0:
                    data['competition_rate'] = round(data['applicant_count'] / data['recruit_count'], 2)
                else:
                    data['competition_rate'] = None
            
            # D-day 추출
            txt_num = option_re.select_one('.txt_num')
            if txt_num:
                remaining_text = txt_num.text.strip()
                if "D-day" in remaining_text:
                    match = re.search(r'D-day\s*(\d+)', remaining_text)
                    if match:
                        data['remaining_days'] = int(match.group(1))
                    else:
                        data['remaining_days'] = None
                elif "D-0" in remaining_text or "D-DAY" in remaining_text:
                    data['remaining_days'] = 0
                else:
                    data['remaining_days'] = None
            else:
                data['remaining_days'] = None
        else:
            data['applicant_count'] = None
            data['recruit_count'] = None
            data['competition_rate'] = None
            data['remaining_days'] = None

    except Exception as e:
        print(f"캠페인 정보 파싱 중 오류: {e}")
        return None

    return data

def test_crawl_category(category_id, category_name, max_items=10):
    """테스트용 크롤링 함수 - 지정된 개수만큼만 추출"""
    print(f"\n{'='*60}")
    print(f"테스트 시작: {category_name} (카테고리 ID: {category_id})")
    print(f"{'='*60}")
    
    # 첫 번째 페이지만 가져오기
    html_content = get_page_content(category_id, 1)
    if not html_content:
        print("❌ 페이지 로드 실패")
        return []
    
    # HTML 파싱
    soup = BeautifulSoup(html_content, 'html.parser')
    all_items = soup.select('a[href*="item.php?it_id="]')
    
    # 실제 캠페인만 필터링
    items = [item for item in all_items if item.select_one('.it_name')]
    
    print(f"✅ 전체 항목: {len(all_items)}개, 실제 캠페인: {len(items)}개")
    print(f"📋 최대 {max_items}개 추출 예정\n")
    
    results = []
    
    for idx, item in enumerate(items[:max_items]):
        try:
            campaign_info = parse_campaign_info(item, category_name)
            if campaign_info:
                results.append(campaign_info)
                
                # 결과 출력
                print(f"[{idx+1:2d}] {campaign_info['title'][:50]}")
                print(f"     📍 타입: {campaign_info['campaign_type']}, SNS: {campaign_info['sns_type']}")
                print(f"     👥 지원자: {campaign_info['applicant_count']}, 모집: {campaign_info['recruit_count']}, 경쟁률: {campaign_info['competition_rate']}")
                print(f"     ⏰ 남은 일수: {campaign_info['remaining_days']}일")
                print(f"     🔗 URL: {campaign_info['detail_url']}")
                print(f"지역 : {campaign_info['address']}")
                print()
            else:
                print(f"[{idx+1:2d}] ❌ 파싱 실패")
                
        except Exception as e:
            print(f"[{idx+1:2d}] ❌ 처리 실패: {e}")
    
    print(f"✅ 총 {len(results)}개 캠페인 추출 완료")
    return results

def run_test():
    """테스트 실행 함수"""
    categories = [
        {"id": "001", "name": "지역"},
        {"id": "002", "name": "제품"},
        {"id": "004", "name": "기자단"}
    ]
    
    all_results = []
    
    for category in categories:
        try:
            results = test_crawl_category(category["id"], category["name"], max_items=10)
            all_results.extend(results)
            
            # 카테고리 간 딜레이
            time.sleep(1)
            
        except Exception as e:
            print(f"❌ 카테고리 {category['name']} 처리 중 오류: {e}")
    
    print(f"\n{'='*60}")
    print(f"🎉 전체 테스트 완료!")
    print(f"총 {len(all_results)}개 캠페인 추출됨")
    print(f"{'='*60}")
    
    return all_results

# 테스트 실행
if __name__ == "__main__":
    test_results = run_test()
