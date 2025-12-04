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
st.set_page_config(page_title="GNews AI 新聞助手", page_icon="📡", layout="wide")
st.title("📡 GNews AI 新聞摘要助手 (免費版優化)")
st.markdown("來源：**GNews API** | 優化：**自動鎖定最近 30 天新聞**")

# --- 3. API Key ---
GNEWS_API_KEY = "b8bba61d5cec4532cc9b3630311eed30"

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

def search_gnews(keyword, limit=5):
    """
    使用 GNews API 進行搜尋 (針對免費版限制進行優化)
    """
    try:
        url = "https://gnews.io/api/v4/search"
        
        # --- 關鍵修正：計算 28 天前的時間字串 ---
        # 免費版只能看過去 30 天，我們設 28 天比較保險
        past_date = datetime.utcnow() - timedelta(days=28)
        from_date_str = past_date.strftime('%Y-%m-%dT%H:%M:%SZ')
        # -------------------------------------

        params = {
            'q': keyword,
            'token': GNEWS_API_KEY,
            'lang': 'zh',
            'country': 'tw',
            'max': limit,
            'sortby': 'publishedAt',
            'from': from_date_str # 強制只找這段時間內的新聞
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        # 除錯資訊：如果還是空的，可以在這裡看到原因
        if 'articles' not in data or len(data['articles']) == 0:
            # 如果還是空的，嘗試放寬條件 (移除 country 限制) 再搜一次
            if 'country' in params:
                del params['country']
                response = requests.get(url, params=params)
                data = response.json()

        if response.status_code != 200:
            st.error(f"API 狀態碼錯誤: {response.status_code}")
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
        keyword = st.text_input("輸入關鍵字", placeholder="例如：台積電...")
    with col2:
        submit_button = st.form_submit_button(label='🚀 搜尋')

if submit_button and keyword:
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    progress_text.text(f"🔍 正在搜尋最近一個月的 GNews...")
    
    # 1. 呼叫 API
    articles = search_gnews(keyword, limit=5)
    
    if not articles:
        st.warning("⚠️ 搜尋結果為空。可能是該關鍵字在過去 30 天內無新聞，或剛好被 API 限制過濾。")
        progress_bar.empty()
    else:
        results_data = []
        total = len(articles)
        
        for i, item in enumerate(articles):
            title = item.get('title')
            url = item.get('url')
            api_desc = item.get('description', '')
            
            progress_text.text(f"正在處理 ({i+1}/{total}): {title[:15]}...")
            progress_bar.progress((i + 1) / total)
            
            # 2. 爬取與摘要
            summary, real_url = extract_and_process(url)
            
            # 如果爬蟲失敗，使用 API 自帶的描述
            if summary.startswith("⚠️") or summary.startswith("❌"):
                summary = f"📌 (API 摘要) {api_desc}"
            
            results_data.append({
                "標題": title,
                "AI 摘要": summary,
                "時間": item.get('publishedAt', '')[:10],
                "連結": real_url
            })
        
        progress_bar.empty()
        progress_text.empty()
        
        st.success(f"✅ 完成！共搜尋到 {total} 篇新聞。")
        df = pd.DataFrame(results_data)
        st.dataframe(
            df, 
            column_config={"連結": st.column_config.LinkColumn("連結", display_text="🔗 閱讀")},
            hide_index=True,
            use_container_width=True
        )