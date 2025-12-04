import streamlit as st
import pandas as pd
import requests
import feedparser
from newspaper import Article, Config
import jieba
import nltk
from bs4 import BeautifulSoup
import re

# --- 1. NLTK 強制修復 ---
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
st.set_page_config(page_title="Google News 摘要 (雲端修正版)", page_icon="🛡️", layout="wide")
st.title("🛡️ Google News AI 摘要 (雲端阻擋突破版)")
st.markdown("針對 **Streamlit Cloud IP** 被 Google 識別為機器人的問題進行修復。")

# --- 3. 核心功能：強力連結解析 ---

def get_real_url(google_url):
    """
    針對 Streamlit Cloud 環境的強力解碼。
    當 requests 拿到 Google 的中轉頁面 (Consent Page) 時，
    直接用 BeautifulSoup 暴力挖出裡面的目標連結。
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://news.google.com/'
        }
        
        # 1. 發送請求
        response = requests.get(google_url, headers=headers, timeout=15)
        
        # 2. 如果網址已經跳轉出 google，直接回傳
        if 'news.google.com' not in response.url and 'google.com' not in response.url:
            return response.url

        # 3. 如果還在 Google，代表被擋住了。解析 HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Google 中轉頁通常有一個主要的連結寫著 "Opening..." 或隱藏在 JS 中
        # 方法 A: 找尋頁面中主要的 <a> 標籤 (通常是第一個非 Google 的連結)
        links = soup.find_all('a')
        for link in links:
            href = link.get('href')
            if href and href.startswith('http') and 'google.com' not in href:
                return href

        # 方法 B: 搜尋 JavaScript 中的跳轉連結
        # 類似 window.location.replace("https://...")
        match = re.search(r'window\.location\.replace\("(.*?)"\)', response.text)
        if match:
            return match.group(1)
            
        # 方法 C: 搜尋 <noscript> 區塊中的連結
        noscript = soup.find('noscript')
        if noscript:
            link = noscript.find('a')
            if link and link.get('href'):
                return link.get('href')

        # 如果都失敗，回傳原始連結 (雖然可能會摘要失敗，但沒辦法了)
        return google_url
        
    except Exception as e:
        return google_url

def sumy_summarize(text, sentence_count=3):
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
        return f"摘要運算錯誤: {e}"

def extract_and_process(google_url):
    try:
        # 步驟 1: 獲取真實網址 (關鍵步驟)
        real_url = get_real_url(google_url)
        
        # 如果解碼後還是 google 網址，顯示警告
        if "google.com" in real_url:
            return "⚠️ 無法穿透 Google 轉址頁 (IP 被阻擋)", real_url

        # 步驟 2: 爬取內容
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        config.request_timeout = 10
        
        article = Article(real_url, config=config)
        article.download()
        article.parse()
        
        # 步驟 3: 檢查長度
        if len(article.text) < 50:
             if article.meta_description and len(article.meta_description) > 10:
                 return f"📌 (來源簡介) {article.meta_description}", real_url
             return "⚠️ 網站阻擋爬蟲 (無內容)", real_url

        summary = sumy_summarize(article.text, sentence_count=3)
        return summary, real_url
        
    except Exception as e:
        return f"❌ 處理錯誤: {str(e)}", google_url

def search_google_news_rss(keyword, limit=5):
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
        keyword = st.text_input("輸入關鍵字", placeholder="例如：台積電...")
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
            progress_text.text(f"正在處理 ({i+1}/{total}): 嘗試破解轉址... {item['title'][:10]}")
            progress_bar.progress((i + 1) / total)
            
            # 呼叫處理函式
            summary, real_url = extract_and_process(item['link'])
            
            results_data.append({
                "新聞標題": item['title'],
                "AI 重點摘要": summary,
                "真實連結": real_url
            })
        
        progress_bar.empty()
        progress_text.empty()
        
        st.success("✅ 完成！如果摘要顯示 IP 阻擋，建議重新整理或稍後再試。")
        
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