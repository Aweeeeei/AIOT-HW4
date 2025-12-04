import streamlit as st
import pandas as pd
import requests
from newspaper import Article, Config
import jieba
import nltk
from datetime import datetime, timedelta

# --- 1. NLTK 自動修復 ---
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
st.set_page_config(page_title="Massive 金融新聞摘要", page_icon="🏦", layout="wide")
st.title("🏦 Massive (Polygon) 金融新聞摘要")
st.markdown("來源：**Massive (Polygon.io)** | 核心：**美股代號 (Ticker) 搜尋**")
st.info("💡 提示：Massive 是美股資料源，請輸入 **美股代號** (例如：**TSM**, **NVDA**, **AAPL**, **AMD**)")

# --- 3. API Key ---
# Massive (Polygon) API Key
MASSIVE_API_KEY = "vMnBeXpL5XKK4G1nuf2jmXR9B2wXuC15"

# --- 4. 核心功能函式 ---

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
        return f"摘要錯誤: {e}"

def extract_and_process(url):
    try:
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        config.request_timeout = 10
        article = Article(url, config=config)
        article.download()
        article.parse()
        if len(article.text) < 50:
             return "⚠️ 網站內容過短 (建議點擊連結閱讀)", url
        summary = sumy_summarize(article.text, sentence_count=3)
        return summary, url
    except Exception as e:
        return f"❌ 抓取錯誤: {str(e)}", url

def search_massive_news(ticker, limit=5):
    """
    使用 Massive (Polygon.io) REST API 搜尋新聞
    Docs: https://massive.com/docs/rest/stocks/news
    """
    try:
        # Massive 雖然改名，但 API 網域目前仍沿用 Polygon.io
        url = "https://api.polygon.io/v2/reference/news"
        
        params = {
            'ticker': ticker.upper(), # 強制轉大寫 (例如 tsm -> TSM)
            'limit': limit,
            'apiKey': MASSIVE_API_KEY,
            'sort': 'published_utc',  # 按時間排序
            'order': 'desc'           # 最新的在前面
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        # --- DEBUG 區塊 ---
        with st.expander("🔍 查看 Massive API 原始回傳", expanded=False):
            st.json(data)
        # -----------------

        if response.status_code != 200:
            st.error(f"API 請求失敗: {data.get('error', 'Unknown Error')}")
            return []

        # Polygon/Massive 的結果在 'results' 欄位中
        return data.get('results', [])

    except Exception as e:
        st.error(f"連線錯誤: {e}")
        return []

# --- 5. 主程式介面 ---

with st.form(key='search_form'):
    col1, col2 = st.columns([3, 1])
    with col1:
        # 預設值改為 TSM (台積電 ADR)
        keyword = st.text_input("輸入美股代號 (Ticker)", value="TSM", placeholder="例如：TSM, NVDA, GOOGL")
    with col2:
        submit_button = st.form_submit_button(label='🚀 搜尋 Massive')

if submit_button and keyword:
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    progress_text.text(f"🔍 正在搜尋 Massive (Polygon) 資料庫: {keyword.upper()}...")
    
    # 1. 呼叫 API
    articles = search_massive_news(keyword, limit=5)
    
    if not articles:
        st.warning(f"找不到關於 {keyword.upper()} 的新聞。請確認代號是否正確 (例如台積電請用 TSM)。")
        progress_bar.empty()
    else:
        results_data = []
        total = len(articles)
        
        for i, item in enumerate(articles):
            title = item.get('title')
            # Massive 的新聞連結欄位通常是 'article_url'
            url = item.get('article_url')
            # Massive 本身有提供 description，可用作備用摘要
            api_desc = item.get('description', '')
            publisher = item.get('publisher', {}).get('name', 'Unknown')
            
            progress_text.text(f"正在處理 ({i+1}/{total}): {title[:15]}...")
            progress_bar.progress((i + 1) / total)
            
            # 2. 爬取與摘要
            summary, real_url = extract_and_process(url)
            
            # 如果爬蟲失敗，使用 API 自帶的描述
            if summary.startswith("⚠️") or summary.startswith("❌"):
                summary = f"📌 (官方摘要) {api_desc}"
            
            results_data.append({
                "新聞標題": title,
                "媒體來源": publisher,
                "AI 重點摘要": summary,
                "發布時間 (UTC)": item.get('published_utc', '')[:10],
                "連結": real_url
            })
        
        progress_bar.empty()
        progress_text.empty()
        
        st.success(f"✅ 完成！找到 {total} 篇關於 {keyword.upper()} 的報導。")
        df = pd.DataFrame(results_data)
        st.dataframe(
            df, 
            column_config={
                "連結": st.column_config.LinkColumn("連結", display_text="🔗 閱讀"),
                "AI 重點摘要": st.column_config.TextColumn("AI 重點摘要", width="large")
            },
            hide_index=True,
            use_container_width=True
        )