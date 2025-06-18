import requests
from bs4 import BeautifulSoup
import re
import boto3
import os
import json
import logging
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs = boto3.client('sqs')
MAIN_TO_DETAIL_QUEUE_URL = os.environ.get('MAIN_TO_DETAIL_QUEUE_URL')
RDS_QUEUE_URL = os.environ.get('RDS_QUEUE_URL')


def get_page_content(category_id, page_number):
    """지정된 카테고리와 페이지의 내용을 가져오는 함수"""
    url = f"https://www.dailyview.kr/item_list.php?category_id={category_id}&sst=&sod=&page={page_number}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        logger.info(f"페이지 요청: 카테고리 {category_id}, 페이지 {page_number}")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error(f"페이지 {page_number} 가져오기 실패: {e}")
        return None


def parse_remaining_days(remaining_text):
    """D-day 텍스트에서 남은 일수 추출"""
    if not remaining_text:
        return None
    
    remaining_text = remaining_text.strip()
    
    # "D-day 6" 형태
    if "D-day" in remaining_text:
        match = re.search(r'D-day\s*(\d+)', remaining_text)
        if match:
            return int(match.group(1))
    
    # "D-0" 또는 "D-DAY" 형태
    if "D-0" in remaining_text or "D-DAY" in remaining_text:
        return 0
    
    logger.warning(f"남은 기간 파싱 실패: {remaining_text}")
    return None


def parse_campaign_info(item, current_category):
    """캠페인 아이템에서 정보 추출 (수정된 버전)"""
    data = {}
    
    try:
        # 기본 정보
        data['source_site'] = 'dailyview'
        data['page_flag'] = 'main'
        data['campaign_type'] = current_category

        # 링크 추출 (a 태그의 href 속성)
        link = item.get('href')
        if link:
            data['detail_url'] = f"https://www.dailyview.kr/{link}"
        else:
            data['detail_url'] = None

        # 제목 추출
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
                data['remaining_days'] = parse_remaining_days(remaining_text)
            else:
                data['remaining_days'] = None
        else:
            data['applicant_count'] = None
            data['recruit_count'] = None
            data['competition_rate'] = None
            data['remaining_days'] = None

    except Exception as e:
        logger.error(f"캠페인 정보 파싱 중 오류: {e}")
        return None

    return data


def send_to_detail_queue(data):
    """Detail Queue로 데이터 전송"""
    try:
        response = sqs.send_message(
            QueueUrl=MAIN_TO_DETAIL_QUEUE_URL,
            MessageBody=json.dumps(data, ensure_ascii=False)
        )
        logger.info(f"Detail Queue 전송 완료: {data['title'][:50]}")
        return True
    except Exception as e:
        logger.error(f"Detail Queue 전송 실패: {e}")
        return False


def send_to_rds_queue(data):
    """RDS Queue로 데이터 전송"""
    try:
        response = sqs.send_message(
            QueueUrl=RDS_QUEUE_URL,
            MessageBody=json.dumps(data, ensure_ascii=False)
        )
        logger.info(f"RDS Queue 전송 완료: {data['title'][:50]}")
        return True
    except Exception as e:
        logger.error(f"RDS Queue 전송 실패: {e}")
        return False


def process_campaign_by_remaining_days(campaign):
    """남은 일수에 따라 캠페인 처리"""
    remaining_days = campaign.get('remaining_days')
    title = campaign.get('title', 'Unknown')[:50]
    
    applicant_count = campaign.get('applicant_count', 'N/A')
    recruit_count = campaign.get('recruit_count', 'N/A')
    competition_rate = campaign.get('competition_rate', 'N/A')
    sns_type = campaign.get('sns_type', 'N/A')
    campaign_type = campaign.get('campaign_type', 'N/A')
    
    logger.info(f"{title}")
    logger.info(f"   타입: {campaign_type}, SNS: {sns_type}")
    logger.info(f"   지원자: {applicant_count}, 모집: {recruit_count}, 경쟁률: {competition_rate}")

    if remaining_days is None:
        logger.info(f"남은 기간 불명 → Detail Queue: {title}")
        return send_to_detail_queue(campaign)

    if remaining_days < 8:
        logger.info(f"마감 임박 ({remaining_days}일) → RDS Queue: {title}")
        return send_to_rds_queue(campaign)
    else:
        logger.info(f"여유 있음 ({remaining_days}일) → Detail Queue: {title}")
        return send_to_detail_queue(campaign)


def crawl_category(category_id, category_name, max_pages=25):
    """특정 카테고리의 모든 페이지 크롤링 (빈 페이지 감지 포함)"""
    total_suc, total_err = 0, 0
    empty_page_count = 0
    max_empty_pages = 2  # 연속 2페이지 비어있으면 종료
    
    logger.info(f"카테고리 크롤링 시작: {category_name} (ID: {category_id})")
    
    for page in range(1, max_pages + 1):
        try:
            logger.info(f"페이지 {page}/{max_pages} 처리 중...")
            
            # 페이지 내용 가져오기
            html_content = get_page_content(category_id, page)
            if not html_content:
                logger.error(f"페이지 {page} 로드 실패")
                empty_page_count += 1
                total_err += 1
                
                # 연속 빈 페이지 체크
                if empty_page_count >= max_empty_pages:
                    logger.info(f"연속 {max_empty_pages}페이지 로드 실패. 크롤링 종료.")
                    break
                continue
            
            # HTML 파싱 (수정된 부분)
            soup = BeautifulSoup(html_content, 'html.parser')
            all_items = soup.select('a[href*="item.php?it_id="]')
            
            # 필터: .it_name이 있는 실제 캠페인만
            items = [item for item in all_items if item.select_one('.it_name')]
            
            logger.info(f"전체 항목: {len(all_items)}개, 실제 캠페인: {len(items)}개")
            
            if not items:
                empty_page_count += 1
                logger.warning(f"페이지 {page}에서 실제 캠페인을 찾을 수 없습니다. (빈 페이지 {empty_page_count}/{max_empty_pages})")
                
                # 연속 빈 페이지 체크
                if empty_page_count >= max_empty_pages:
                    logger.info(f"연속 {max_empty_pages}페이지가 비어있어 크롤링 종료.")
                    break
                
                continue
            
            # 항목이 있으면 빈 페이지 카운터 리셋
            empty_page_count = 0
            logger.info(f"페이지 {page}에서 {len(items)}개 실제 캠페인 발견")
            
            # 각 항목 처리
            for idx, item in enumerate(items):
                try:
                    campaign_info = parse_campaign_info(item, category_name)
                    if campaign_info:
                        success = process_campaign_by_remaining_days(campaign_info)
                        if success:
                            total_suc += 1
                        else:
                            total_err += 1
                    else:
                        total_err += 1
                        logger.warning(f"페이지 {page}, 항목 #{idx}: 정보 파싱 실패")
                        
                except Exception as e:
                    total_err += 1
                    logger.error(f"페이지 {page}, 항목 #{idx} 처리 실패: {e}")
            
            # 페이지 간 딜레이
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"페이지 {page} 처리 중 오류: {e}")
            empty_page_count += 1
            total_err += 1
            
            # 연속 오류 페이지 체크
            if empty_page_count >= max_empty_pages:
                logger.info(f"연속 {max_empty_pages}페이지에서 오류 발생. 크롤링 종료.")
                break
    
    logger.info(f"{category_name} 크롤링 완료 - 성공: {total_suc}개, 실패: {total_err}개")
    return total_suc, total_err



def run():
    """데일리뷰 메인 크롤링 함수"""
    categories = [
        {"id": "001", "name": "지역"},
        {"id": "002", "name": "제품"},
        {"id": "004", "name": "기자단"}
    ]
    
    total_success, total_error = 0, 0
    
    for category in categories:
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"카테고리 시작: {category['name']}")
            logger.info(f"{'='*60}")
            
            suc, err = crawl_category(category["id"], category["name"])
            total_success += suc
            total_error += err
            
        except Exception as e:
            logger.error(f"카테고리 {category['name']} 처리 중 오류: {e}")
            total_error += 1
    
    logger.info(f"데일리뷰 크롤링 완료 - 총 성공: {total_success}개, 실패: {total_error}개")
    return total_success, total_error
