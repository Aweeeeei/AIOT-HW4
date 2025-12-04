import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import feedparser
from newspaper import Article
from transformers import pipeline
import time

# --- 1. 頁面設定 ---
st.set_page_config(page_title="AI 新聞摘要小幫手", page_icon="📰", layout="wide")
st.title("📰 AI Google 新聞搜尋與摘要")
st.markdown("輸入關鍵字，AI 將為您搜尋前 5 篇新聞並進行重點摘要。")
st.markdown("*(注意：由於在 CPU 環境運行深度學習模型，每篇文章摘要約需 10-30 秒，請耐心等待)*")

# --- 2. 核心功能函式定義 ---

@st.cache_resource
def load_summarizer_model():
    """
    載入摘要模型。使用 cache_resource 避免每次重新載入。
    選擇 'sshleifer/distilbart-cnn-12-6' 是因為它比標準 BART 模型更輕量，適合 CPU。
    """
    with st.spinner('正在初始化 AI 摘要模型 (首次執行需下載模型，約 300MB)...'):
        # 定義摘要 pipeline
        summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6")
    return summarizer

def search_google_news_rss(keyword, limit=5):
    """
    使用 Google News RSS Feed 進行搜尋 (比直接爬 HTML 更穩定)
    """
    encoded_keyword = requests.utils.quote(keyword)
    rss_url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    feed = feedparser.parse(rss_url)
    
    news_list = []
    for entry in feed.entries[:limit]:
        # Google RSS 提供的連結是跳轉連結，需要解析出真實 URL
        real_url = get_actual_url(entry.link)
        if real_url:
            news_list.append({
                "title": entry.title,
                "link": real_url,
                "published": entry.published
            })
    return news_list

def get_actual_url(google_url):
    """
    從 Google News 的跳轉連結中獲取真實的網站連結。
    """
    try:
        # 設定 User-Agent 模擬瀏覽器行為，避免被擋
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # 發送請求並獲取最終跳轉後的 URL
        response = requests.head(google_url, allow_redirects=True, headers=headers, timeout=5)
        return response.url
    except Exception as e:
        # print(f"解析 URL 失敗: {e}")
        return None

def extract_and_summarize(url, summarizer_pipeline):
    """
    抓取新聞內文並呼叫 AI 模型進行摘要
    """
    try:
        # 1. 使用 newspaper3k 抓取文章內容
        article = Article(url)
        article.download()
        article.parse()
        
        text_content = article.text
        
        if len(text_content) < 200:
             return "文章內容太短，無法進行有效摘要。"

        # 2. 使用 Transformers 進行摘要
        # max_length: 摘要最大長度, min_length: 摘要最小長度
        # 為了速度，我們限制輸入文本的長度 (truncation=True)
        summary_result = summarizer_pipeline(text_content, max_length=130, min_length=50, do_sample=False, truncation=True)
        
        return summary_result[0]['summary_text']
        
    except Exception as e:
        return f"抓取或摘要失敗: {str(e)}"

# --- 3. 主程式邏輯 ---

# 預先載入模型
try:
    summarizer = load_summarizer_model()
    st.success("AI 模型準備就緒！")
except Exception as e:
    st.error(f"模型載入失敗，請檢查記憶體或網路狀態: {e}")
    st.stop()


# 使用者輸入介面
with st.form(key='search_form'):
    col1, col2 = st.columns([3, 1])
    with col1:
        keyword = st.text_input("請輸入新聞關鍵字", placeholder="例如：台積電、人工智慧...")
    with col2:
        submit_button = st.form_submit_button(label='🔍 開始搜尋與摘要')

if submit_button and keyword:
    st.divider()
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    results_data = []

    # 步驟 1: 搜尋新聞
    status_text.info(f"正在搜尋「{keyword}」的相關新聞...")
    news_items = search_google_news_rss(keyword)
    
    if not news_items:
        st.warning("找不到相關新聞，請嘗試其他關鍵字。")
    else:
        total_items = len(news_items)
        
        # 步驟 2 & 3: 逐一抓取內容並摘要
        for i, item in enumerate(news_items):
            status_text.info(f"正在處理第 {i+1}/{total_items} 篇新聞：{item['title']}...")
            progress_bar.progress((i) / total_items)
            
            # 執行摘要 (這一步最花時間)
            summary = extract_and_summarize(item['link'], summarizer)
            
            results_data.append({
                "新聞標題": item['title'],
                "AI 摘要": summary,
                "原始連結": item['link']
            })
        
        progress_bar.progress(100)
        status_text.success("✅ 所有新聞處理完成！")
        time.sleep(1)
        status_text.empty()
        progress_bar.empty()

        # 步驟 4: 以表格呈現結果
        st.subheader(f"📊 「{keyword}」的新聞摘要結果")
        
        # 將資料轉換為 Pandas DataFrame
        df = pd.DataFrame(results_data)
        
        # 使用 Streamlit 的 dataframe 展示，並設定連結欄位顯示為可點擊的 URL
        st.dataframe(
            df,
            column_config={
                "原始連結": st.column_config.LinkColumn("原始連結", display_text="點擊閱讀原文")
            },
            hide_index=True,
            use_container_width=True
        )