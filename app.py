import streamlit as st
import pandas as pd
import requests
import feedparser
from newspaper import Article, Config
import jieba
import nltk
import time

# --- 1. NLTK 自動修復區 (解決 punkt_tab 錯誤) ---
# Streamlit Cloud 每次啟動都是全新環境，必須強制下載字典檔
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab', quiet=True)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer

# --- 2. 頁面設定 ---
st.set_page_config(page_title="Google News AI 摘要", page_icon="📰", layout="wide")
st.title("📰 Google News AI 摘要 (Thunderbit 方法修正版)")
st.markdown("來源：**Google News** | 技術：**URL 解碼** + **LSA 摘要**")

# --- 3. 核心功能函式 ---

def decode_google_news_url(source_url):
    """
    關鍵函式：解決 Google News 連結轉址問題。
    Google 的 RSS 給的是 'news.google.com/...' 的跳轉連結，
    直接爬會失敗。必須透過 requests 獲取最終的真實網址。
    """
    try:
        # 模擬真實瀏覽器的 Headers，騙過 Google 的防爬蟲機制
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Referer': 'https://news.google.com/'
        }
        
        # 發送請求，allow_redirects=True 會自動跟隨跳轉直到最後的真實網址
        response = requests.get(source_url, headers=headers, timeout=10, allow_redirects=True)
        
        # 檢查是否真的跳轉到了外部網站 (網址不包含 google.com)
        if 'google.com' not in response.url:
            return response.url
        
        # 如果還是在 google 網域，可能是被 Consent 頁面擋住了，回傳原網址試試運氣
        return source_url
    except Exception as e:
        print(f"解碼失敗: {e}")
        return source_url

def sumy_summarize(text, sentence_count=3):
    """使用 Sumy + Jieba 進行中文萃取式摘要"""
    try:
        if not text: return "無內容"
        
        # 中文斷詞
        seg_list = jieba.cut(text)
        text_segmented = " ".join(seg_list)
        
        # 初始化摘要器
        parser = PlaintextParser.from_string(text_segmented, Tokenizer("english")) 
        summarizer = LsaSummarizer() 
        summary_sentences = summarizer(parser.document, sentence_count)
        
        result = ""
        for sentence in summary_sentences:
            raw_sent = str(sentence).replace(" ", "")
            result += raw_sent + "。"
        return result
    except Exception as e:
        return f"摘要運算錯誤: {e}"

def extract_and_process(google_url):
    """
    流程：解碼 Google 連結 -> 爬取真實網頁 -> 產生摘要
    """
    try:
        # 步驟 1: 獲取真實網址 (這是之前失敗的關鍵)
        real_url = decode_google_news_url(google_url)
        
        # 步驟 2: 設定爬蟲 Config (偽裝成瀏覽器)
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        config.request_timeout = 10
        
        article = Article(real_url, config=config)
        article.download()
        article.parse()
        
        # 檢查內容長度
        if len(article.text) < 50:
             # 如果正文抓不到，嘗試抓 Meta Description 當作備案
             if article.meta_description and len(article.meta_description) > 10:
                 return f"📌 (來源簡介) {article.meta_description}", real_url
             return "⚠️ 無法抓取內容 (網站阻擋爬蟲)", real_url

        # 步驟 3: 摘要
        summary = sumy_summarize(article.text, sentence_count=3)
        return summary, real_url
        
    except Exception as e:
        return f"❌ 處理錯誤: {str(e)}", google_url

def search_google_news_rss(keyword, limit=5):
    """
    使用 Google News RSS (最接近 Thunderbit 指南的 Python 實作方式)
    """
    # 使用 params 編碼關鍵字
    encoded_keyword = requests.utils.quote(keyword)
    
    # 這是標準的 Google News RSS 格式
    rss_url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    feed = feedparser.parse(rss_url)
    
    results = []
    # 只取前 limit 筆
    for entry in feed.entries[:limit]:
        results.append({
            "title": entry.title,
            "link": entry.link, # 這裡拿到的是 Google 的轉址連結
            "published": entry.published
        })
    return results

# --- 4. 主程式介面 ---

with st.form(key='search_form'):
    col1, col2 = st.columns([3, 1])
    with col1:
        keyword = st.text_input("輸入關鍵字", placeholder="例如：台積電、OpenAI...")
    with col2:
        submit_button = st.form_submit_button(label='🚀 搜尋')

if submit_button and keyword:
    st.divider()
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    progress_text.text(f"🔍 正在 Google News 搜尋「{keyword}」...")
    
    # 1. 獲取 RSS 列表
    news_items = search_google_news_rss(keyword, limit=5)
    
    if not news_items:
        st.warning("Google News 找不到相關新聞，請嘗試其他關鍵字。")
        progress_bar.empty()
    else:
        results_data = []
        total = len(news_items)
        
        for i, item in enumerate(news_items):
            progress_text.text(f"正在處理 ({i+1}/{total}): 解碼連結並摘要中... {item['title'][:10]}...")
            progress_bar.progress((i + 1) / total)
            
            # 2. 爬取與摘要 (包含連結解碼)
            summary, real_url = extract_and_process(item['link'])
            
            results_data.append({
                "新聞標題": item['title'],
                "AI 重點摘要": summary,
                "真實連結": real_url
            })
        
        progress_bar.empty()
        progress_text.empty()
        
        st.success("✅ 完成！")
        
        df = pd.DataFrame(results_data)
        st.dataframe(
            df,
            column_config={
                "真實連結": st.column_config.LinkColumn("連結", display_text="🔗 前往閱讀"),
                "AI 重點摘要": st.column_config.TextColumn("AI 重點摘要", width="large"),
            },
            hide_index=True,
            use_container_width=True
        )