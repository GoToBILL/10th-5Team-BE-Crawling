import time
import csv
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urljoin

def setup_driver():
    """크롬 드라이버 설정"""
    chrome_options = Options()
    # chrome_options.add_argument('--headless')  # 필요시 헤드리스 모드 활성화
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36')
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

def scroll_to_bottom(driver):
    """페이지 끝까지 스크롤"""
    print("페이지 끝까지 스크롤 중...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    while True:
        # 페이지 끝까지 스크롤
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        
        # 페이지 로딩 대기
        time.sleep(2)
        
        # 새 스크롤 높이 계산
        new_height = driver.execute_script("return document.body.scrollHeight")
        
        # 스크롤 높이가 같으면 더 이상 스크롤할 수 없음 (끝에 도달)
        if new_height == last_height:
            break
            
        last_height = new_height
    
    print("스크롤 완료")

def get_all_taste_links(url):
    """페이지에서 모든 taste 링크 수집"""
    driver = setup_driver()
    driver.get(url)
    
    # 페이지 로딩 대기
    time.sleep(2)
    
    # 페이지 끝까지 스크롤
    scroll_to_bottom(driver)
    
    # 모든 링크 추출
    taste_links = []
    base_url = "https://dinnerqueen.net"
    link_elements = driver.find_elements(By.CSS_SELECTOR, "a.qz-dq-card__link")
    
    for element in link_elements:
        href = element.get_attribute('href')
        if href and '/taste/' in href:
            # 링크 추출
            taste_links.append({
                'link': href,
                'title': element.get_attribute('title') if element.get_attribute('title') else 'No Title'
            })
    
    print(f"총 {len(taste_links)}개의 맛집 링크를 찾았습니다.")
    driver.quit()
    return taste_links

def save_links_to_csv(links, filename='taste_product_links.csv'):
    """링크 리스트를 CSV 파일로 저장"""
    # Pandas DataFrame으로 변환 후 저장
    df = pd.DataFrame(links)
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    print(f"{filename} 파일로 {len(links)}개의 링크를 저장했습니다.")

def main():
    # 전체
    #url = "https://dinnerqueen.net/taste?ct=%EC%A0%84%EC%B2%B4&lpage=4&query=&deal=&cate=&order=&area1=%EC%A0%84%EA%B5%AD&area2=%EC%A0%84%EC%B2%B4&ctype="
    
    # 제품
    url = "https://dinnerqueen.net/taste?ct=%EB%B0%B0%EC%86%A1"
    # 모든 taste 링크 수집
    taste_links = get_all_taste_links(url)
    
    # CSV 파일로 저장
    save_links_to_csv(taste_links)

if __name__ == "__main__":
    main()