import streamlit as st
import pandas as pd
import requests
from newspaper import Article, Config
import jieba
import nltk
from datetime import datetime

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
st.set_page_config(page_title="GNews AI 新聞助手", page_icon="📡", layout="wide")
st.title("📡 GNews AI 新聞摘要助手")
st.markdown("來源：**GNews API** | 技術：**RESTful API** + **LSA 演算法**")

# --- 3. 設定 API Key ---
# 建議：實際部署時，最好將 API Key 放在 st.secrets，但作業繳交直接寫在變數也可以
GNEWS_API_KEY = "b8bba61d5cec4532cc9b3630311eed30"

# --- 4. 核心功能函式 ---

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

def extract_and_process(url):
    """
    抓取並摘要
    GNews 給的是直連網址，我們直接用 newspaper3k 抓取即可。
    """
    try:
        # 設定偽裝瀏覽器 (雖然 API 給了連結，但目標新聞網站可能還是會擋爬蟲)
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        config.request_timeout = 10
        
        article = Article(url, config=config)
        article.download()
        article.parse()
        
        # 檢查內容長度
        if len(article.text) < 50:
             return "⚠️ 網站內容過短或阻擋爬蟲 (建議點擊連結閱讀)", url

        # 執行摘要
        summary = sumy_summarize(article.text, sentence_count=3)
        return summary, url
        
    except Exception as e:
        return f"❌ 抓取錯誤: {str(e)}", url

def search_gnews(keyword, limit=5):
    """
    使用 GNews API 進行搜尋
    文件：https://gnews.io/docs/v4
    """
    try:
        url = "https://gnews.io/api/v4/search"
        params = {
            'q': keyword,
            'token': GNEWS_API_KEY,
            'lang': 'zh',       # 語言：中文
            'country': 'tw',    # 國家：台灣
            'max': limit,       # 數量限制
            'sortby': 'publishedAt' # 按時間排序
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        if response.status_code != 200:
            st.error(f"API 請求失敗: {data.get('errors', 'Unknown error')}")
            return []

        articles = data.get('articles', [])
        return articles

    except Exception as e:
        st.error(f"連線錯誤: {e}")
        return []

# --- 5. 主程式介面 ---

with st.form(key='search_form'):
    col1, col2 = st.columns([3, 1])
    with col1:
        keyword = st.text_input("輸入關鍵字", placeholder="例如：台積電、AI...")
    with col2:
        submit_button = st.form_submit_button(label='🚀 搜尋 GNews')

if submit_button and keyword:
    st.divider()
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    progress_text.text(f"🔍 正在呼叫 GNews API 搜尋「{keyword}」...")
    
    # 1. 呼叫 API
    articles = search_gnews(keyword, limit=5)
    
    if not articles:
        st.warning("找不到相關新聞，或 API 配額已用盡。")
        progress_bar.empty()
    else:
        results_data = []
        total = len(articles)
        
        for i, item in enumerate(articles):
            title = item.get('title')
            url = item.get('url')
            # GNews API 本身有提供 description，如果爬蟲失敗可以用這個當備案
            api_description = item.get('description', '')
            
            progress_text.text(f"正在處理 ({i+1}/{total}): {title[:15]}...")
            progress_bar.progress((i + 1) / total)
            
            # 2. 爬取內文並 LSA 摘要
            summary, real_url = extract_and_process(url)
            
            # 如果爬蟲失敗 (summary 開頭是 ⚠️ 或 ❌)，回退使用 API 提供的簡短描述
            if summary.startswith("⚠️") or summary.startswith("❌"):
                summary = f"📌 (API 原文摘要) {api_description}"
            
            results_data.append({
                "新聞標題": title,
                "AI 重點摘要": summary,
                "發布時間": item.get('publishedAt', '')[:10], # 只取日期
                "連結": real_url
            })
        
        progress_bar.empty()
        progress_text.empty()
        
        st.success(f"✅ 完成！共搜尋到 {total} 篇新聞。")
        
        df = pd.DataFrame(results_data)
        st.dataframe(
            df,
            column_config={
                "連結": st.column_config.LinkColumn("連結", display_text="🔗 閱讀原文"),
                "AI 重點摘要": st.column_config.TextColumn("AI 重點摘要", width="large"),
            },
            hide_index=True,
            use_container_width=True
        )