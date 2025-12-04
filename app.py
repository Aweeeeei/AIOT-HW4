import streamlit as st
import pandas as pd
import requests
import feedparser
from newspaper import Article, Config
import jieba
import nltk
from bs4 import BeautifulSoup # 需用到 BS4 來解析轉址頁
import re

# --- 1. NLTK 自動修復 (Streamlit Cloud 專用) ---
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
st.title("📰 Google News AI 摘要 (轉址修復版)")
st.markdown("來源：**Google News** | 技術：**LSA 摘要** + **強力連結解碼**")

# --- 3. 核心功能函式 ---

def decode_google_news_url(source_url):
    """
    強力解碼函式：解決 Google News RSS 的轉址問題。
    如果 requests 拿到的是 Google 的轉址頁面，此函式會嘗試從 HTML 中挖出真實連結。
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        
        # 1. 發送請求，允許自動跳轉
        response = requests.get(source_url, headers=headers, timeout=10, allow_redirects=True)
        
        # 2. 檢查最終網址是否已經離開 Google
        if 'news.google.com' not in response.url and 'google.com' not in response.url:
            return response.url

        # 3. 如果還在 Google 頁面 (代表被擋在 Consent 頁或 JS 跳轉頁)，嘗試解析 HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Google 的跳轉頁通常會有一個主要的 <a href="..."> 連結
        # 或是透過 JS window.location 轉址
        
        # 嘗試找尋頁面中主要的轉外連結
        # 這是一個常見的 Google 轉址頁面特徵
        links = soup.find_all('a')
        for link in links:
            href = link.get('href')
            if href and href.startswith('http') and 'google.com' not in href:
                return href
                
        # 如果找不到，嘗試用 Regex 搜尋 JS 中的 URL
        match = re.search(r'window\.location\.replace\("(.*?)"\)', response.text)
        if match:
            return match.group(1)

        # 如果真的都失敗，回傳原始跳轉後的 URL (雖然可能還是 Google 的)
        return response.url
        
    except Exception as e:
        # print(f"解碼失敗: {e}")
        return source_url

def sumy_summarize(text, sentence_count=3):
    """使用 Sumy + Jieba 進行中文萃取式摘要"""
    try:
        if not text: return "無內容"
        seg_list = jieba.cut(text)
        text_segmented = " ".join(seg_list)
        parser = PlaintextParser.from_string(text_segmented, Tokenizer("english")) 
        summarizer = LsaSummarizer() 
        summary_sentences = summarizer(parser.document, sentence_count)
        
        result = ""
        for sentence in summary_sentences:
            raw_sent = str(sentence).replace(" ", "")
            result += raw_sent + "。"
        return result
    except Exception as e:
        return f"摘要錯誤: {e}"

def extract_and_process(google_url):
    """抓取並摘要"""
    try:
        # 步驟 1: 強力解碼 (解決 "Comprehensive..." 問題的關鍵)
        real_url = decode_google_news_url(google_url)
        
        # 如果解碼後還是 google 網址，直接跳過，因為爬不到內容
        if "google.com" in real_url:
            return "⚠️ 無法解析真實連結 (Google 加密轉址)", real_url

        # 步驟 2: 爬取
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        config.request_timeout = 10
        
        article = Article(real_url, config=config)
        article.download()
        article.parse()
        
        # 步驟 3: 檢查並摘要
        if len(article.text) < 50:
             if article.meta_description and len(article.meta_description) > 10:
                 return f"📌 (來源簡介) {article.meta_description}", real_url
             return "⚠️ 網站阻擋爬蟲 (無內容)", real_url

        summary = sumy_summarize(article.text, sentence_count=3)
        return summary, real_url
        
    except Exception as e:
        return f"❌ 錯誤: {str(e)}", google_url

def search_google_news_rss(keyword, limit=5):
    """Google News RSS"""
    encoded_keyword = requests.utils.quote(keyword)
    rss_url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    feed = feedparser.parse(rss_url)
    
    results = []
    for entry in feed.entries[:limit]:
        results.append({
            "title": entry.title,
            "link": entry.link,
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
    news_items = search_google_news_rss(keyword, limit=5)
    
    if not news_items:
        st.warning("找不到相關新聞。")
        progress_bar.empty()
    else:
        results_data = []
        total = len(news_items)
        
        for i, item in enumerate(news_items):
            progress_text.text(f"正在處理 ({i+1}/{total}): 解碼連結並摘要... {item['title'][:10]}")
            progress_bar.progress((i + 1) / total)
            
            # 呼叫 extract_and_process
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