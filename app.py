import streamlit as st
import pandas as pd
import requests
import feedparser
from newspaper import Article, Config
import time
import jieba
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer

# --- 1. 頁面設定 ---
st.set_page_config(page_title="極速新聞摘要助手", page_icon="⚡", layout="wide")
st.title("⚡ 極速版 Google 新聞摘要 (爬蟲強化版)")
st.markdown("使用 **LSA 演算法** + **偽裝瀏覽器爬蟲**，解決抓取失敗問題。")

# --- 2. 核心功能函式 ---

def get_actual_url(google_url):
    """
    嘗試解析 Google News 的跳轉連結，獲取真實網址。
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        # 使用 requests.get 而非 head，並開啟 allow_redirects
        # Google 有時會用 JS 跳轉，這裡嘗試獲取最終響應的 URL
        response = requests.get(google_url, headers=headers, timeout=10, allow_redirects=True)
        
        # 如果網址還是 google 的，代表跳轉沒成功 (可能是 JS 轉址)，這時只能回傳原網址試試運氣
        if "news.google.com" in response.url:
            return google_url
        return response.url
    except Exception as e:
        print(f"URL 解析錯誤: {e}")
        return google_url # 解析失敗就回傳原網址

def sumy_summarize(text, sentence_count=3):
    """使用 Sumy + Jieba 進行中文萃取式摘要"""
    try:
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

def extract_and_process(url):
    """
    抓取並摘要 (加入 Config 防止被擋)
    """
    try:
        # --- 關鍵修正：設定 Config 偽裝成瀏覽器 ---
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        config.request_timeout = 10  # 設定超時
        config.fetch_images = False  # 不抓圖片，加速
        
        article = Article(url, config=config)
        article.download()
        article.parse()
        
        # debug 用：如果抓不到字，顯示長度
        text_len = len(article.text)
        
        if text_len < 50:
             # 嘗試另一種容錯：如果正文抓不到，試試看抓 meta description
             if article.meta_description and len(article.meta_description) > 20:
                 return f"(使用 Meta 描述) {article.meta_description}"
             
             return f"⚠️ 無法抓取內容 (長度僅 {text_len} 字) - 可能是網站阻擋或需登入"

        # 使用 Sumy 進行摘要
        summary = sumy_summarize(article.text, sentence_count=3)
        if not summary:
            return "摘要產生失敗 (內容可能過於破碎)"
            
        return summary
        
    except Exception as e:
        return f"❌ 處理錯誤: {str(e)}"

def search_google_news_rss(keyword, limit=5):
    encoded_keyword = requests.utils.quote(keyword)
    rss_url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    feed = feedparser.parse(rss_url)
    
    news_list = []
    for entry in feed.entries[:limit]:
        # 先給 Google 連結，後續處理時再解析
        news_list.append({
            "title": entry.title,
            "link": entry.link, 
            "published": entry.published
        })
    return news_list

# --- 3. 主程式邏輯 ---

with st.form(key='search_form'):
    col1, col2 = st.columns([3, 1])
    with col1:
        keyword = st.text_input("輸入關鍵字", placeholder="例如：台積電、輝達...")
    with col2:
        submit_button = st.form_submit_button(label='🚀 搜尋並摘要')

if submit_button and keyword:
    st.divider()
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    progress_text.text("正在搜尋新聞來源...")
    news_items = search_google_news_rss(keyword)
    
    results_data = []
    total = len(news_items)
    
    for i, item in enumerate(news_items):
        progress_text.text(f"正在處理 ({i+1}/{total}): {item['title']} ...")
        progress_bar.progress((i + 1) / total)
        
        # 1. 嘗試解析真實 URL
        real_url = get_actual_url(item['link'])
        
        # 2. 抓取與摘要
        summary = extract_and_process(real_url)
        
        results_data.append({
            "新聞標題": item['title'],
            "重點摘要": summary,
            "原始連結": real_url
        })
    
    progress_bar.empty()
    progress_text.empty()
            
    if results_data:
        st.success(f"已完成！")
        df = pd.DataFrame(results_data)
        st.dataframe(
            df,
            column_config={
                "原始連結": st.column_config.LinkColumn("連結", display_text="🔗"),
                "重點摘要": st.column_config.TextColumn("重點摘要", width="large")
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.warning("找不到相關新聞。")