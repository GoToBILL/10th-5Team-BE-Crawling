from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import csv
import re

def setup_driver():
    """
    셀레니움 웹드라이버 설정
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # 헤드리스 모드 (화면 표시 없음)
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def scroll_to_end(driver, max_scrolls=100):
    """
    페이지 끝까지 스크롤
    """
    print("페이지 스크롤 시작...")
    prev_height = driver.execute_script("return document.body.scrollHeight")
    scroll_count = 0
    
    while scroll_count < max_scrolls:
        # 페이지 맨 아래로 스크롤
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        
        # 페이지 로딩 대기
        time.sleep(1)
        
        # 새 스크롤 높이 계산
        new_height = driver.execute_script("return document.body.scrollHeight")
        
        # 스크롤 진행 상황 표시
        scroll_count += 1
        print(f"스크롤 {scroll_count}/{max_scrolls} 완료")
        
        # 높이가 같으면 더 이상 스크롤할 내용이 없음
        if new_height == prev_height:
            print("페이지 끝에 도달함")
            break
            
        prev_height = new_height
    
    print("스크롤 완료")

def extract_campaign_links(html_content):
    """
    HTML 내용에서 캠페인 타이틀과 링크 추출
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    campaigns = []
    
    # 캠페인 링크를 포함하는 a 태그 찾기
    campaign_links = soup.select('a[href^="/next/campaign/"]')
    
    for link in campaign_links:
        try:
            # 링크 href 속성 가져오기
            href = link.get('href')
            
            # 절대 URL로 변환
            full_link = f"https://popomon.com{href}"
            
            # 캠페인 이름 추출
            title = None
            title_elem = link.select_one('h3')
            if title_elem:
                title = title_elem.text.strip()
            else:
                # 다른 방법으로 시도
                title_elem = link.select_one('.line-1skip, .my-2')
                if title_elem:
                    title = title_elem.text.strip()
            
            if title and href:
                campaigns.append({
                    'title': title,
                    'link': full_link
                })
            
        except Exception as e:
            print(f"링크 추출 중 오류 발생: {e}")
    
    return campaigns

def main():

    # 애는 지역
    #url = "https://popomon.com/next/campaign?searchAlign=latest&bigRecruitType=Lvisiting&recruitType=visiting&interestsFilter=ALL&cityLocation=&countyLocation=&pageNum=420"
    # 얘는 제품
    # url = "https://popomon.com/next/campaign?searchAlign=latest&bigRecruitType=Pshipping&recruitType=shipping&interestsFilter=ALL&pageNum=0"
    # 얘는 기자단
    url = "https://popomon.com/next/campaign?searchAlign=latest&bigRecruitType=Lvisiting&recruitType=reporting&interestsFilter=ALL&pageNum=0"
    
    driver = setup_driver()
    
    try:
        print(f"{url} 로드 중...")
        driver.get(url)
        
        # 페이지 완전히 로드될 때까지 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/next/campaign/']"))
        )
        
        # 페이지 끝까지 스크롤
        scroll_to_end(driver)
        
        # 현재 페이지 소스 가져오기
        page_source = driver.page_source
        
        # 캠페인 링크 추출
        campaigns = extract_campaign_links(page_source)
        
        print(f"총 {len(campaigns)}개 캠페인 링크 추출됨")
        
        # CSV 파일로 저장
        if campaigns:
            with open('popomon_campaigns_test.csv', 'w', newline='', encoding='utf-8-sig') as csvfile:
                fieldnames = ['title', 'link']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for campaign in campaigns:
                    writer.writerow(campaign)
            
            print(f"총 {len(campaigns)}개 캠페인 링크가 popomon_campaigns.csv 파일에 저장되었습니다.")
        else:
            print("추출된 캠페인이 없습니다.")
    
    except Exception as e:
        print(f"오류 발생: {e}")
    
    finally:
        driver.quit()

if __name__ == "__main__":
    main()