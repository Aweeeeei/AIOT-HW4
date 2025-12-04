import streamlit as st
import pandas as pd
import requests
import feedparser
from newspaper import Article, Config
import jieba
import nltk # 引入 nltk

# --- NLTK 資料下載修正區 (解決摘要錯誤) ---
# Streamlit Cloud 預設沒有這些資料，必須在執行時下載
try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt', quiet=True)
    nltk.download('punkt_tab', quiet=True)

from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer

# --- 1. 頁面設定 ---
st.set_page_config(page_title="新聞摘要助手", page_icon="📰", layout="wide")
st.title("📰 AI 新聞搜尋與摘要 (Bing 來源穩定版)")
st.markdown("使用 **Bing News RSS** 搜尋，搭配 **LSA 演算法** 進行極速摘要。")

# --- 2. 核心功能函式 ---

def sumy_summarize(text, sentence_count=3):
    """使用 Sumy + Jieba 進行中文萃取式摘要"""
    try:
        if not text: return "無內容"
        
        # 中文斷詞處理
        seg_list = jieba.cut(text)
        text_segmented = " ".join(seg_list)
        
        # 初始化摘要器
        parser = PlaintextParser.from_string(text_segmented, Tokenizer("english")) 
        summarizer = LsaSummarizer() 
        summary_sentences = summarizer(parser.document, sentence_count)
        
        # 組合結果
        result = ""
        for sentence in summary_sentences:
            raw_sent = str(sentence).replace(" ", "")
            result += raw_sent + "。"
        return result
    except Exception as e:
        return f"摘要錯誤: {e}"

def extract_and_process(url):
    """
    抓取並摘要
    """
    try:
        # 設定偽裝瀏覽器 User-Agent
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        config.request_timeout = 10
        
        article = Article(url, config=config)
        article.download()
        article.parse()
        
        # 如果正文太短，改抓 Meta Description
        if len(article.text) < 50:
             if article.meta_description and len(article.meta_description) > 10:
                 return f"📌 (來源簡介) {article.meta_description}"
             return "⚠️ 無法抓取內容 (網站阻擋爬蟲)"

        # 執行摘要
        summary = sumy_summarize(article.text, sentence_count=3)
        return summary
        
    except Exception as e:
        return f"❌ 處理錯誤: {str(e)}"

def search_bing_rss(keyword, limit=5):
    """
    使用 Bing News RSS 進行搜尋
    """
    rss_url = f"https://www.bing.com/news/search?q={keyword}&format=rss"
    feed = feedparser.parse(rss_url)
    
    results = []
    # 這裡會回傳實際找到的數量，最多 limit 筆
    for entry in feed.entries[:limit]:
        results.append({
            "title": entry.title,
            "link": entry.link,
            "published": entry.published if 'published' in entry else "Unknown"
        })
        
    return results, len(feed.entries) # 回傳資料與總搜尋數

# --- 3. 主程式邏輯 ---

with st.form(key='search_form'):
    col1, col2 = st.columns([3, 1])
    with col1:
        keyword = st.text_input("輸入關鍵字", placeholder="例如：OpenAI, 台積電...")
    with col2:
        submit_button = st.form_submit_button(label='🚀 搜尋')

if submit_button and keyword:
    st.divider()
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    progress_text.text(f"🔍 正在透過 Bing 搜尋「{keyword}」...")
    
    # 執行搜尋
    news_items, total_found = search_bing_rss(keyword, limit=5)
    
    if not news_items:
        st.warning(f"Bing 找不到相關新聞 (搜尋回傳 0 筆)。請嘗試其他關鍵字。")
        progress_bar.empty()
    else:
        # 顯示實際找到的數量，讓你知道為什麼只有 2 筆
        st.info(f"Bing 共回傳 {total_found} 筆相關新聞，系統將處理前 {len(news_items)} 筆。")
        
        results_data = []
        process_count = len(news_items)
        
        for i, item in enumerate(news_items):
            progress_text.text(f"正在處理 ({i+1}/{process_count}): {item['title']} ...")
            progress_bar.progress((i + 1) / process_count)
            
            summary = extract_and_process(item['link'])
            
            results_data.append({
                "新聞標題": item['title'],
                "AI 重點摘要": summary,
                "連結": item['link']
            })
        
        progress_bar.empty()
        progress_text.empty()
        
        st.success("✅ 完成！")
        
        df = pd.DataFrame(results_data)
        st.dataframe(
            df,
            column_config={
                "連結": st.column_config.LinkColumn("連結", display_text="🔗 前往閱讀"),
                "AI 重點摘要": st.column_config.TextColumn("AI 重點摘要", width="large"),
            },
            hide_index=True,
            use_container_width=True
        )